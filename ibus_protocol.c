#include "ibus_protocol.h"
#include <string.h>

/* Internal RX buffer: room for several max-sized messages */
static uint8_t  ibus_data[IBUS_MAX_MESSAGE_LEN * 8];
static uint32_t ibus_data_index = 0;

/* Current headunit state and hijack mode */
static ibus_state_t ibus_state        = IBUS_STATE_UNKNOWN;
static ibus_state_t ibus_hijack_state = IBUS_STATE_UNKNOWN;

static uint8_t ibus_get_message_length(void)
{
    return (uint8_t)(ibus_data[IBUS_POS_LENGTH] + IBUS_SENDER_AND_LENGTH_LEN);
}

static uint8_t ibus_get_data_length(void)
{
    uint8_t len = ibus_get_message_length();
    if (len <= IBUS_MIN_MESSAGE_LEN) {
        return 0;
    }
    return (uint8_t)(len - IBUS_MIN_MESSAGE_LEN);
}

static uint8_t ibus_get_sender(void)
{
    return ibus_data[IBUS_POS_SENDER];
}

static uint8_t ibus_get_receiver(void)
{
    return ibus_data[IBUS_POS_RECEIVER];
}

static uint8_t ibus_get_message(void)
{
    return ibus_data[IBUS_POS_MESSAGE];
}

static uint8_t ibus_get_data_byte(uint32_t idx)
{
    return ibus_data[IBUS_POS_DATA_START + idx];
}

/* Very simple substring search over the data region.
 * NOTE: Just like the original code, this relies on the buffer having zeros
 * after the valid bytes (we always clear unused bytes when resetting/moving). */
static int ibus_data_contains(const char *tag)
{
    const char *data = (const char *)&ibus_data[IBUS_POS_DATA_START];
    return strstr(data, tag) != NULL;
}

static uint8_t ibus_calc_checksum(uint32_t checksum_index)
{
    uint8_t checksum = 0;
    for (uint32_t i = 0; i < checksum_index; ++i) {
        checksum ^= ibus_data[i];
    }
    return checksum;
}

static void ibus_change_state(ibus_state_t new_state)
{
    if (ibus_state == new_state)
        return;

    ibus_state = new_state;
    ibus_platform_state_changed(ibus_state, ibus_hijack_state);
}

ibus_state_t ibus_get_state(void)
{
    return ibus_state;
}

void ibus_reset_buffer(void)
{
    memset(ibus_data, 0, sizeof(ibus_data));
    ibus_data_index = 0;
}

void ibus_append_byte(uint8_t byte)
{
    if (ibus_data_index >= (uint32_t)sizeof(ibus_data)) {
        /* Overflow: just reset the buffer */
        ibus_reset_buffer();
        return;
    }
    ibus_data[ibus_data_index++] = byte;
}

int ibus_has_pending_data(void)
{
    return ibus_data_index > 0;
}

void ibus_init(ibus_state_t hijack_state)
{
    ibus_reset_buffer();
    ibus_state        = IBUS_STATE_UNKNOWN;
    ibus_hijack_state = hijack_state;
}

/* Headunit state changes based on UMID/ST/LCDC content */
static void ibus_handle_headunit_state(void)
{
    if (ibus_get_sender() == IBUS_DEV_RAD &&
        ibus_get_receiver() == IBUS_DEV_GT) {

        uint8_t msg = ibus_get_message();

        if (msg == IBUS_MSG_UMID) {
            if (ibus_get_data_length() > 0 && ibus_get_data_byte(0) == 0x62) { /* RadioDisplay layout */
                if (ibus_data_contains("AUX")) {
                    ibus_change_state(IBUS_STATE_AUX);
                } else if (ibus_data_contains("CDC")) {
                    ibus_change_state(IBUS_STATE_CD_CHANGER);
                } else if (ibus_data_contains("TAPE")) {
                    ibus_change_state(IBUS_STATE_TAPE);
                }
            }
        } else if (msg == IBUS_MSG_ST) {
            if (ibus_get_data_length() > 0 && ibus_get_data_byte(0) == 0x62) {
                if (ibus_data_contains("RDS") ||
                    ibus_data_contains("FM")  ||
                    ibus_data_contains("REG") ||
                    ibus_data_contains("MWA")) {
                    ibus_change_state(IBUS_STATE_FM);
                }
            }
        } else if (msg == IBUS_MSG_LCDC) {
            if (ibus_get_data_length() == 1) {
                uint8_t d0 = ibus_get_data_byte(0);
                switch (d0) {
                case 0x01: /* No Display Required */
                case 0x02: /* Radio Display Off   */
                    ibus_change_state(IBUS_STATE_MENU);
                    break;
                default:
                    break;
                }
            }
        }
    }
}

/* Process all complete messages currently in the RX buffer.
 * Any invalid message causes the buffer to be reset. */
void ibus_process_messages(void)
{
    while (ibus_data_index > 0) {
        if (ibus_data_index < IBUS_MIN_MESSAGE_LEN) {
            /* Not enough data for even the shortest message. */
            break;
        }

        uint8_t cur_len = ibus_get_message_length();
        if (ibus_data_index < cur_len) {
            /* Wait for more data */
            break;
        }

        /* Validate checksum */
        uint8_t checksum_index = (uint8_t)(cur_len - 1);
        if (ibus_calc_checksum(checksum_index) != ibus_data[checksum_index]) {
            /* Invalid checksum: drop everything */
            ibus_reset_buffer();
            return;
        }

        /* We have a complete valid message */
        ibus_platform_log_message(ibus_data, cur_len);

        uint8_t sender   = ibus_get_sender();
        uint8_t receiver = ibus_get_receiver();
        uint8_t msg      = ibus_get_message();
        uint8_t data_len = ibus_get_data_length();

        /* 1) Handle button-related messages */
        if (sender == IBUS_DEV_BMBT) {
            if (msg == IBUS_MSG_BMBTB1 && data_len >= 1) {
                uint8_t databyte = ibus_get_data_byte(0);
                uint8_t longPress = 0;
                uint8_t released  = 0;

                if (databyte & IBUS_BTN_FLAG_LONG_PRESS) {
                    databyte &= ~IBUS_BTN_FLAG_LONG_PRESS;
                    longPress = 1;
                } else if (databyte & IBUS_BTN_FLAG_RELEASE) {
                    databyte &= ~IBUS_BTN_FLAG_RELEASE;
                    released = 1;
                }

                if (databyte == IBUS_BTN_RADIO_POWER) {
                    ibus_change_state(IBUS_STATE_POWER_OFF);
                }

                /* Pass raw button code to platform (mapping done there) */
                ibus_platform_button_event(databyte, released, longPress);
            } else if (msg == IBUS_MSG_BMBTB0 && data_len >= 2) {
                /* button command for select is in second byte of data */
                uint8_t databyte = ibus_get_data_byte(1);
                uint8_t longPress = 0;
                uint8_t released  = 0;

                if (databyte & IBUS_BTN_FLAG_LONG_PRESS) {
                    databyte &= ~IBUS_BTN_FLAG_LONG_PRESS;
                    longPress = 1;
                } else if (databyte & IBUS_BTN_FLAG_RELEASE) {
                    databyte &= ~IBUS_BTN_FLAG_RELEASE;
                    released = 1;
                }

                if (databyte == IBUS_BTN_SELECT_TAPE_MODE) {
                    ibus_platform_button_event(IBUS_BTN_IDX_SELECT_TAPE,
                                               released, longPress);
                } else {
                    /* Unknown BMBTB0 button: ignore or log at platform if desired */
                }
            } else if (msg == IBUS_MSG_KNOB && data_len >= 1) {
                uint8_t databyte = ibus_get_data_byte(0);
                int clockwise = 0;

                if (databyte & IBUS_BTN_MENU_KNOB_CW_MASK) {
                    databyte &= ~IBUS_BTN_MENU_KNOB_CW_MASK;
                    clockwise = 1;
                }

                /* databyte now tells how many steps */
                if (databyte > 0) {
                    ibus_platform_knob_event(clockwise, databyte);
                }
            } else if (msg == IBUS_MSG_MFLB && data_len >= 1) {
                uint8_t databyte = ibus_get_data_byte(0);
                (void)databyte;
                /* Currently just informational (volume up/down); no key mapping here. */
            }
        } else if (sender == IBUS_DEV_MFL && receiver == IBUS_DEV_RAD) {
            if (msg == IBUS_MSG_MFLB && data_len >= 1) {
                uint8_t databyte = ibus_get_data_byte(0);
                (void)databyte;
                /* If desired, volume up/down handling could be added here. */
            } else if (msg == IBUS_MSG_MFLB2 && data_len >= 1) {
                uint8_t databyte = ibus_get_data_byte(0);
                uint8_t released = 0;

                if (databyte & IBUS_MFL2_BTN_RELEASE) {
                    databyte &= ~IBUS_MFL2_BTN_RELEASE;
                    released = 1;
                }

                if (databyte & IBUS_MFL2_BTN_CH_UP) {
                    ibus_platform_button_event(IBUS_BTN_IDX_MFL2_CH_UP,
                                               released, 0);
                } else if (databyte & IBUS_MFL2_BTN_CH_DOWN) {
                    ibus_platform_button_event(IBUS_BTN_IDX_MFL2_CH_DOWN,
                                               released, 0);
                }

                /* TODO: handle answer buttons and other MFL buttons if needed */
            }
        }

        /* 2) Handle headunit state messages (only if hijack mode is set) */
        if (ibus_hijack_state != IBUS_STATE_UNKNOWN) {
            ibus_handle_headunit_state();
        }

        /* 3) Remove this message from the buffer and continue with next one */
        if (ibus_data_index >= cur_len) {
            memmove(&ibus_data[0],
                    &ibus_data[cur_len],
                    ibus_data_index - cur_len);
            ibus_data_index -= cur_len;
            memset(&ibus_data[ibus_data_index], 0, cur_len);
        } else {
            /* Should not happen but if it does, reset. */
            ibus_reset_buffer();
            return;
        }
    }

    /* Done */
}
