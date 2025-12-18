#ifndef IBUS_PROTOCOL_H
#define IBUS_PROTOCOL_H

#include <stdint.h>

/*
 * IBUS message layout
 *
 *  Byte 0 : Sender
 *  Byte 1 : Length of remaining bytes (receiver..checksum)
 *  Byte 2 : Receiver
 *  Byte 3 : Message ID
 *  Byte 4+: Data bytes (0..252 bytes)
 *  Last   : Checksum (XOR of all previous bytes)
 */

enum {
    IBUS_POS_SENDER     = 0,
    IBUS_POS_LENGTH     = 1,
    IBUS_POS_RECEIVER   = 2,
    IBUS_POS_MESSAGE    = 3,
    IBUS_POS_DATA_START = 4
};

#define IBUS_SENDER_AND_LENGTH_LEN  2u
#define IBUS_MIN_MESSAGE_LEN        5u      /* sender,len,receiver,message,checksum */
#define IBUS_MAX_MESSAGE_LEN        257u    /* 0xFF + 2 */

/* === Device addresses (only the ones we actually use) === */
#define IBUS_DEV_GM     0x00  /* Body module */
#define IBUS_DEV_GT     0x3B  /* Graphics driver (nav) */
#define IBUS_DEV_RAD    0x68  /* Radio */
#define IBUS_DEV_MFL    0x50  /* Multi-function steering wheel */
#define IBUS_DEV_BMBT   0xF0  /* Board monitor buttons */

/* === Message IDs we use === */
#define IBUS_MSG_DSREQ   0x01  /* Device status request */
#define IBUS_MSG_DSRED   0x02  /* Device status ready */
#define IBUS_MSG_BSREQ   0x03  /* Bus status request */
#define IBUS_MSG_BS      0x04  /* Bus status */
#define IBUS_MSG_UMID    0x23  /* Display Text */
#define IBUS_MSG_UANZV   0x24  /* Update ANZV */
#define IBUS_MSG_MFLB    0x32  /* MFL buttons */
#define IBUS_MSG_DSPEB   0x34  /* DSP Equalizer Button */
#define IBUS_MSG_CDSREQ  0x38  /* CD status request */
#define IBUS_MSG_CDS     0x39  /* CD status */
#define IBUS_MSG_MFLB2   0x3B  /* MFL buttons 2 */
#define IBUS_MSG_SOBCD   0x40  /* Set On-Board Computer Data */
#define IBUS_MSG_OBCDR   0x41  /* On-Board Computer Data Request */
#define IBUS_MSG_LCDC    0x46  /* LCD Clear */
#define IBUS_MSG_BMBTB0  0x47  /* BMBT buttons (local) */
#define IBUS_MSG_BMBTB1  0x48  /* BMBT buttons (RAD) */
#define IBUS_MSG_KNOB    0x49  /* KNOB button */
#define IBUS_MSG_CC      0x4A  /* Cassette control */
#define IBUS_MSG_CS      0x4B  /* Cassette Status */
#define IBUS_MSG_RGBC    0x4F  /* RGB Control */
#define IBUS_MSG_ST      0xA5  /* Screen text */

/* === Button flags (from BMBT) === */
#define IBUS_BTN_FLAG_PRESS       0x00
#define IBUS_BTN_FLAG_LONG_PRESS  0x40
#define IBUS_BTN_FLAG_RELEASE     0x80

/* === BMBT button codes (from BMBTB1 data) === */
#define IBUS_BTN_ARROW_RIGHT      0x00
#define IBUS_BTN_2                0x01
#define IBUS_BTN_4                0x02
#define IBUS_BTN_6                0x03
#define IBUS_BTN_TONE             0x04
#define IBUS_BTN_MENU_KNOB        0x05
#define IBUS_BTN_RADIO_POWER      0x06
#define IBUS_BTN_CLOCK            0x07
#define IBUS_BTN_TELEPHONE        0x08
#define IBUS_BTN_ARROW_LEFT       0x10
#define IBUS_BTN_1                0x11
#define IBUS_BTN_3                0x12
#define IBUS_BTN_5                0x13
#define IBUS_BTN_REVERSE_PLAY     0x14
#define IBUS_BTN_AM               0x21
#define IBUS_BTN_RDS              0x22
#define IBUS_BTN_MODE             0x23
#define IBUS_BTN_EJECT            0x24
#define IBUS_BTN_SWITCH           0x30
#define IBUS_BTN_FM               0x31
#define IBUS_BTN_TP               0x32
#define IBUS_BTN_DOLBY            0x33
#define IBUS_BTN_MENU             0x34

/* === BMBT KNOB data bits === */
#define IBUS_BTN_MENU_KNOB_CW_MASK   0x80  /* 0x81 once, 0x82 twice... */
#define IBUS_BTN_MENU_KNOB_CCW_MASK  0x00

/* === BMBTB0 button codes === */
#define IBUS_BTN_SELECT_TAPE_MODE    0x0F  /* 2nd byte of data */

/* === MFL volume buttons (MFLB) === */
#define IBUS_MFL_BTN_VOL_UP          0x01
#define IBUS_MFL_BTN_VOL_DOWN        0x00

/* === MFLB2 meta/flags === */
#define IBUS_MFL2_BTN_PRESS          0x00
#define IBUS_MFL2_BTN_RELEASE        0x20

#define IBUS_MFL2_BTN_CH_UP          0x01
#define IBUS_MFL2_BTN_CH_DOWN        0x08
#define IBUS_MFL2_BTN_ANSWER         0x80

/*
 * Synthetic button codes (indexes into the platform's button table)
 * These are not real IBUS data codes, but convenient aliases.
 */
#define IBUS_BTN_IDX_MENUKNOB_CW     0x35
#define IBUS_BTN_IDX_MENUKNOB_CCW    0x36
#define IBUS_BTN_IDX_SELECT_TAPE     0x37
#define IBUS_BTN_IDX_MFL2_CH_UP      0x38
#define IBUS_BTN_IDX_MFL2_CH_DOWN    0x39

/* Headunit state */
typedef enum {
    IBUS_STATE_UNKNOWN = 0,
    IBUS_STATE_POWER_OFF,
    IBUS_STATE_MENU,
    IBUS_STATE_FM,
    IBUS_STATE_TAPE,
    IBUS_STATE_AUX,
    IBUS_STATE_CD_CHANGER
} ibus_state_t;

/* How we switch video input (platform-specific meaning) */
typedef enum {
    IBUS_VID_SWITCH_CTS = 0,
    IBUS_VID_SWITCH_RTS,
    IBUS_VID_SWITCH_GPIO,
    IBUS_VID_SWITCH_UNKNOWN
} ibus_video_switch_t;

/* ===== Core API (platform-independent) ===== */

/* Initialise the core with a desired hijack state (e.g. AUX, TAPE). */
void ibus_init(ibus_state_t hijack_state);

/* Reset the internal RX buffer. */
void ibus_reset_buffer(void);

/* Append a single byte received from the IBUS. */
void ibus_append_byte(uint8_t byte);

/* Non-zero if there is any data in the buffer. */
int ibus_has_pending_data(void);

/* Process all complete messages currently in the buffer. */
void ibus_process_messages(void);

/* Get current headunit state. */
ibus_state_t ibus_get_state(void);


/* ===== Platform hooks (must be implemented on Linux / RP2350 etc.) ===== */

/* Called whenever the decoded headunit state changes. */
void ibus_platform_state_changed(ibus_state_t new_state,
                                 ibus_state_t hijack_state);

/* Called when a logical button is decoded. */
void ibus_platform_button_event(uint8_t button_code,
                                uint8_t released,
                                uint8_t long_press);

/* Called when the menu knob is rotated. */
void ibus_platform_knob_event(int clockwise, uint8_t steps);

/* Called for every valid IBUS message (for logging / debugging). */
void ibus_platform_log_message(const uint8_t *msg, uint8_t len);

#endif /* IBUS_PROTOCOL_H */
