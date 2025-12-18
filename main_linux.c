#include <sys/select.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <netinet/ip.h>
#include <arpa/inet.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <unistd.h>
#include <errno.h>
#include <termios.h>
#include <sys/ioctl.h>
#include <linux/input.h>
#include <linux/uinput.h>
#include <time.h>

#include "ibus_protocol.h"

/* ===== Tracing ===== */

static unsigned int trace_level = 0;
static FILE *stdout_fp = NULL;

#define TRACE_FUNCTION  (1U<<0)
#define TRACE_IBUS      (1U<<1)
#define TRACE_INPUT     (1U<<2)
#define TRACE_STATE     (1U<<3)
#define TRACE_ALL       (TRACE_FUNCTION|TRACE_IBUS|TRACE_INPUT|TRACE_STATE)

#define CHECK_TRACELEVEL(level)  ((level) & trace_level)

static void trace_timestamp_prefix(void)
{
    struct timeval now;
    gettimeofday(&now, NULL);
    fprintf(stdout_fp ? stdout_fp : stdout,
            "%ld.%06ld: ",
            (long)now.tv_sec, (long)now.tv_usec);
}

#define TRACE_WARGS(level, fmt, ...) \
    do { \
        if (CHECK_TRACELEVEL(level)) { \
            trace_timestamp_prefix(); \
            fprintf(stdout_fp ? stdout_fp : stdout, fmt, __VA_ARGS__); \
        } \
    } while (0)

#define TRACE(level, fmt) \
    do { \
        if (CHECK_TRACELEVEL(level)) { \
            trace_timestamp_prefix(); \
            fprintf(stdout_fp ? stdout_fp : stdout, "%s", fmt); \
        } \
    } while (0)

#define TRACE_ERROR(fmt, ...) \
    do { \
        trace_timestamp_prefix(); \
        fprintf(stdout_fp ? stdout_fp : stdout, \
                "%s:%d ERROR=%d (%s): " fmt "\n", \
                __FILE__, __LINE__, -errno, strerror(errno), ##__VA_ARGS__); \
        if (stdout_fp) fflush(stdout_fp); \
    } while (0)

/* ===== Button mapping & device/message name tables ===== */

struct ibus_buttons {
    const char   *name;
    uint16_t      key_code;
};

/* used for the buttons that change the BM state (no uinput event) */
#define RESERVED_BUTTON 0xFFFF

/* IBUS device and message name tables (copied from original code) */
static const char *IBUSDevices[256] = {
/* 0x00 - 0x0F */
    "Body module", "0x01", "0x02", "0x03", "0x04", "0x05", "0x06", "0x07",
    "Sunroof Control", "0x09", "0x0A", "0x0B", "0x0C", "0x0D", "0x0E", "0x0F",
/* 0x10 - 0x1F */
    "0x10", "0x11", "0x12", "0x13", "0x14", "0x15", "0x16", "0x17",
    "CD Changer", "0x19", "0x1A", "0x1B", "0x1C", "0x1D", "0x1E", "0x1F",
/* 0x20 - 0x2F */
    "0x20", "0x21", "0x22", "0x23", "0x24", "0x25", "0x26", "0x27",
    "Radio controlled clock", "0x29", "0x2A", "0x2B", "0x2C", "0x2D", "0x2E", "0x2F",
/* 0x30 - 0x3F */
    "Check control module", "0x31", "0x32", "0x33", "0x34", "0x35", "0x36", "0x37",
    "0x38", "0x39", "0x3A", "Graphics driver", "0x3C", "0x3D", "0x3E", "Diagnostic",
/* 0x40 - 0x4F */
    "Remote control central locking", "0x41", "0x42", "0x43", "Immobiliser", "0x45", "Central information display", "0x47",
    "0x48", "0x49", "0x4A", "0x4B", "0x4C", "0x4D", "0x4E", "0x4F",
/* 0x50 - 0x5F */
    "Multi function steering wheel", "Mirror memory", "0x52", "0x53", "0x54", "0x55", "0x56", "0x57",
    "0x58", "0x59", "0x5A", "Integrated heating and air conditioning", "0x5C", "0x5D", "0x5E", "0x5F",
/* 0x60 - 0x6F */
    "Park distance control", "0x61", "0x62", "0x63", "0x64", "0x65", "0x66", "0x67",
    "Radio", "0x69", "Digital signal processing audio amplifier", "0x6B", "0x6C", "0x6D", "0x6E", "0x6F",
/* 0x70 - 0x7F */
    "0x70", "0x71", "Seat memory", "Sirius Radio", "0x74", "0x75", "CD changer, DIN size", "0x77",
    "0x78", "0x79", "0x7A", "0x7B", "0x7C", "0x7D", "0x7E", "Navigation",
/* 0x80 - 0x8F */
    "Instrument cluster electronics", "0x81", "0x82", "0x83", "0x84", "0x85", "0x86", "0x87",
    "0x88", "0x89", "0x8A", "0x8B", "0x8C", "0x8D", "0x8E", "0x8F",
/* 0x90 - 0x9F */
    "0x90", "0x91", "0x92", "0x93", "0x94", "0x95", "0x96", "0x97",
    "0x98", "0x99", "0x9A", "Mirror memory", "Mirror memory", "0x9D", "0x9E", "0x9F",
/* 0xA0 - 0xAF */
    "Rear multi-info-display", "0xA1", "0xA2", "0xA3", "Air bag module", "0xA5", "0xA6", "0xA7",
    "0xA8", "0xA9", "0xAA", "0xAB", "0xAC", "0xAD", "0xAE", "0xAF",
/* 0xB0 - 0xBF */
    "Speed recognition system", "0xB1", "0xB2", "0xB3", "0xB4", "0xB5", "0xB6", "0xB7",
    "0xB8", "0xB9", "0xBA", "Navigation", "0xBC", "0xBD", "0xBE", "Global, broadcast address",
/* 0xC0 - 0xCF */
    "Multi-info display", "0xC1", "0xC2", "0xC3", "0xC4", "0xC5", "0xC6", "0xC7",
    "Telephone", "0xC9", "0xCA", "0xCB", "0xCC", "0xCD", "0xCE", "0xCF",
/* 0xD0 - 0xDF */
    "Light control module", "0xD1", "0xD2", "0xD3", "RDS channel list", "0xD5", "0xD6", "0xD7",
    "0xD8", "0xD9", "0xDA", "0xDB", "0xDC", "0xDD", "0xDE", "0xDF",
/* 0xE0 - 0xEF */
    "Integrated radio information system", "0xE1", "0xE2", "0xE3", "0xE4", "0xE5", "0xE6", "Front display",
    "Rain/Light Sensor", "0xE9", "0xEA", "0xEB", "0xEC", "Television", "0xEE", "0xEF",
/* 0xF0 - 0xFF */
    "On-board monitor operating part", "0xF1", "0xF2", "0xF3", "0xF4", "0xF5", "0xF6", "0xF7",
    "0xF8", "0xF9", "0xFA", "0xFB", "0xFC", "0xFD", "0xFE", "Local"
};

static const char *IBUSMessages[256] = {
/* 0x00 - 0x0F */
    "0x00", "Device status request", "Device status ready", "Bus status request",
    "Bus status", "0x05", "DIAG read memory", "DIAG write memory",
    "DIAG read coding data", "DIAG write coding data", "0x0A", "0x0B",
    "Vehicle control", "0x0D", "0x0E", "0x0F",
/* 0x10 - 0x1F */
    "Ignition status request", "Ignition status", "IKE sensor status request",
    "IKE sensor status", "Country coding status request", "Country coding status",
    "Odometer request", "Odometer", "Speed/RPM", "Temperature",
    "IKE text display/Gong", "IKE text status", "Gong", "Temperature request",
    "0x1E", "UTC time and date",
/* 0x20 - 0x2F */
    "0x20", "Radio Short cuts", "Text display confirmation", "Display Text",
    "Update ANZV", "0x25", "0x26", "0x27", "0x28", "0x29",
    "On-Board Computer State Update", "Telephone indicators", "0x2C", "0x2D",
    "0x2E", "0x2F",
/* 0x30 - 0x3F */
    "0x30", "0x31", "MFL buttons", "0x33", "DSP Equalizer Button", "0x35", "0x36",
    "0x37", "CD status request", "CD status", "0x3A", "MFL buttons 2", "0x3C",
    "SDRS status request", "SDRS status", "0x3F",
/* 0x40 - 0x4F */
    "Set On-Board Computer Data", "On-Board Computer Data Request", "0x42", "0x43",
    "0x44", "0x45", "LCD Clear", "BMBT buttons (local)", "BMBT buttons (RAD)",
    "KNOB button", "Cassette control", "Cassette status", "0x4C", "0x4D", "0x4E",
    "RGB Control",
/* 0x50 - 0x5F */
    "0x50", "0x51", "0x52", "Vehicle data request", "Vehicle data status", "0x55",
    "0x56", "0x57", "0x58", "0x59", "Lamp status request", "Lamp status",
    "Instrument cluster lighting status", "0x5D", "0x5E", "0x5F",
/* 0x60 - 0x6F */
    "0x60", "0x61", "0x62", "0x63", "0x64", "0x65", "0x66", "0x67",
    "0x68", "0x69", "0x6A", "0x6B", "0x6C", "0x6D", "0x6E", "0x6F",
/* 0x70 - 0x7F */
    "0x70", "Rain sensor status request", "Remote Key buttons", "0x73",
    "EWS key status", "0x75", "0x76", "0x77", "Doors/windows status request",
    "Doors/windows status", "0x7B", "SHD status", "0x7D", "0x7E", "0x7F", "0x80",
/* 0x80 - 0x8F */
    "0x81", "0x82", "0x83", "0x84", "0x85", "0x86", "0x87", "0x88",
    "0x89", "0x8A", "0x8B", "0x8C", "0x8D", "0x8E", "0x8F", "0x90",
/* 0x90 - 0x9F */
    "0x91", "0x92", "0x93", "0x94", "0x95", "0x96", "0x97", "0x98",
    "0x99", "0x9A", "0x9B", "0x9C", "0x9D", "0x9E", "0x9F", "DIAG data",
/* 0xA0 - 0xAF */
    "0xA1", "Current position and time", "0xA3", "Current location", "Screen text",
    "0xA6", "TMC status request", "0xA8", "0xA9", "Navigation Control", "0xAB",
    "0xAC", "0xAD", "0xAE", "0xAF", "0xB0",
/* 0xB0 - 0xBF */
    "0xB1", "0xB2", "0xB3", "0xB4", "0xB5", "0xB6", "0xB7", "0xB8",
    "0xB9", "0xBA", "0xBB", "0xBC", "0xBD", "0xBE", "0xBF", "0xC0",
/* 0xC0 - 0xCF */
    "0xC1", "0xC2", "0xC3", "0xC4", "0xC5", "0xC6", "0xC7", "0xC8",
    "0xC9", "0xCA", "0xCB", "0xCC", "0xCD", "0xCE", "0xCF", "0xD0",
/* 0xD0 - 0xDF */
    "0xD1", "0xD2", "0xD3", "RDS channel list", "0xD5", "0xD6", "0xD7",
    "0xD8", "0xD9", "0xDA", "0xDB", "0xDC", "0xDD", "0xDE", "0xDF",
/* 0xE0 - 0xEF */
    "0xE0", "0xE1", "0xE2", "0xE3", "0xE4", "0xE5", "0xE6", "0xE7",
    "0xE8", "0xE9", "0xEA", "0xEB", "0xEC", "0xED", "0xEE", "0xEF",
/* 0xF0 - 0xFF */
    "0xF0", "0xF1", "0xF2", "0xF3", "0xF4", "0xF5", "0xF6", "0xF7",
    "0xF8", "0xF9", "0xFA", "0xFB", "0xFC", "0xFD", "0xFE", "0xFF"
};

/*
 * This is the key mapping from BMW IBUS to Linux key codes.
 * Do not map buttons that change the state like power, fm, mode etc.
 */
static const struct ibus_buttons headunit_buttons[] = {
    { "ButtonArrowRight",  KEY_UP         },   /*0x00*/
    { "Button2",           KEY_BACKSPACE  },   /*0x01*/
    { "Button4",           KEY_4          },   /*0x02*/
    { "Button6",           KEY_6          },   /*0x03*/
    { "ButtonTone",        RESERVED_BUTTON},   /*0x04*/
    { "ButtonMenuKnob",    KEY_ENTER      },   /*0x05*/
    { "ButtonRadioPower",  RESERVED_BUTTON},   /*0x06*/
    { "ButtonClock",       KEY_SETUP      },   /*0x07*/
    { "ButtonTelephone",   KEY_SETUP      },   /*0x08*/
    { "0x09",              KEY_UNKNOWN    },   /*0x09*/
    { "0x0A",              KEY_UNKNOWN    },   /*0x0A*/
    { "0x0B",              KEY_UNKNOWN    },   /*0x0B*/
    { "0x0C",              KEY_UNKNOWN    },   /*0x0C*/
    { "0x0D",              KEY_UNKNOWN    },   /*0x0D*/
    { "0x0E",              KEY_UNKNOWN    },   /*0x0E*/
    { "0x0F",              KEY_UNKNOWN    },   /*0x0F*/
    { "ButtonArrowLeft",   KEY_DOWN       },   /*0x10*/
    { "Button1",           KEY_MENU       },   /*0x11*/
    { "Button3",           KEY_SPACE      },   /*0x12*/
    { "Button5",           KEY_5          },   /*0x13*/
    { "ButtonReversePlay", KEY_SETUP      },   /*0x14*/
    { "0x15",              KEY_UNKNOWN    },   /*0x15*/
    { "0x16",              KEY_UNKNOWN    },   /*0x16*/
    { "0x17",              KEY_UNKNOWN    },   /*0x17*/
    { "0x18",              KEY_UNKNOWN    },   /*0x18*/
    { "0x19",              KEY_UNKNOWN    },   /*0x19*/
    { "0x1A",              KEY_UNKNOWN    },   /*0x1A*/
    { "0x1B",              KEY_UNKNOWN    },   /*0x1B*/
    { "0x1C",              KEY_UNKNOWN    },   /*0x1C*/
    { "0x1D",              KEY_UNKNOWN    },   /*0x1D*/
    { "0x1E",              KEY_UNKNOWN    },   /*0x1E*/
    { "0x1F",              KEY_UNKNOWN    },   /*0x1F*/
    { "0x20",              KEY_UNKNOWN    },   /*0x20*/
    { "ButtonAM",          RESERVED_BUTTON},   /*0x21*/
    { "ButtonRDS",         RESERVED_BUTTON},   /*0x22*/
    { "ButtonMode",        RESERVED_BUTTON},   /*0x23*/
    { "ButtonEject",       RESERVED_BUTTON},   /*0x24*/
    { "0x25",              KEY_UNKNOWN    },   /*0x25*/
    { "0x26",              KEY_UNKNOWN    },   /*0x26*/
    { "0x27",              KEY_UNKNOWN    },   /*0x27*/
    { "0x28",              KEY_UNKNOWN    },   /*0x28*/
    { "0x29",              KEY_UNKNOWN    },   /*0x29*/
    { "0x2A",              KEY_UNKNOWN    },   /*0x2A*/
    { "0x2B",              KEY_UNKNOWN    },   /*0x2B*/
    { "0x2C",              KEY_UNKNOWN    },   /*0x2C*/
    { "0x2D",              KEY_UNKNOWN    },   /*0x2D*/
    { "0x2E",              KEY_UNKNOWN    },   /*0x2E*/
    { "0x2F",              KEY_UNKNOWN    },   /*0x2F*/
    { "ButtonSwitch",      RESERVED_BUTTON},   /*0x30*/
    { "ButtonFM",          RESERVED_BUTTON},   /*0x31*/
    { "ButtonTP",          RESERVED_BUTTON},   /*0x32*/
    { "ButtonDolby",       KEY_UNKNOWN    },   /*0x33*/
    { "ButtonMenu",        RESERVED_BUTTON},   /*0x34*/
    { "MenuKnobClockwise", KEY_RIGHT      },   /*0x35*/
    { "MenuKnobCounterClockwise", KEY_LEFT},   /*0x36*/
    { "SelectInTapeMode",  KEY_ESC        },   /*0x37*/
    { "MFL2ButtonChannelUp", KEY_UP       },   /*0x38*/
    { "MFL2ButtonChannelDown", KEY_DOWN   }    /*0x39*/
};

/* ===== Global state for Linux platform ===== */

static volatile sig_atomic_t exit_request = 0;

static int uinput_device_fd = -1;
static int ibus_device_fd   = -1;

static unsigned char send_key_events = 0;
static ibus_video_switch_t VideoInputSwitch = IBUS_VID_SWITCH_UNKNOWN;
static ibus_state_t g_hijack_state = IBUS_STATE_UNKNOWN;

/* ===== Signal handling ===== */

static void signal_handler(int sig)
{
    (void)sig;
    exit_request = 1;
}

/* ===== uinput helpers ===== */

static int uinput_create(void)
{
    struct uinput_user_dev dev;
    int fd;
    unsigned int i;

    TRACE(TRACE_INPUT | TRACE_FUNCTION, "Creating uinput device\n");

    fd = open("/dev/uinput", O_WRONLY | O_NONBLOCK);
    if (fd < 0) {
        fd = open("/dev/input/uinput", O_WRONLY | O_NONBLOCK);
        if (fd < 0) {
            fd = open("/dev/misc/uinput", O_WRONLY | O_NONBLOCK);
            if (fd < 0) {
                TRACE_ERROR("Can't open input device");
                return -errno;
            }
        }
    }

    memset(&dev, 0, sizeof(dev));
    snprintf(dev.name, UINPUT_MAX_NAME_SIZE, "BMW IBUS");
    dev.id.bustype = BUS_RS232;
    dev.id.vendor  = 0x0000;
    dev.id.product = 0x0000;
    dev.id.version = 0x0100;

    if (write(fd, &dev, sizeof(dev)) < 0) {
        TRACE_ERROR("Can't write device information");
        close(fd);
        return -errno;
    }

    if (ioctl(fd, UI_SET_EVBIT, EV_KEY) < 0) {
        TRACE_ERROR("Can't set event bit");
        close(fd);
        return -errno;
    }

    for (i = 0; i < sizeof(headunit_buttons) / sizeof(headunit_buttons[0]); ++i) {
        if (headunit_buttons[i].key_code != KEY_UNKNOWN) {
            if (ioctl(fd, UI_SET_KEYBIT, headunit_buttons[i].key_code) < 0) {
                TRACE_ERROR("Can't set key bit");
                close(fd);
                return -errno;
            }
        }
    }

    if (ioctl(fd, UI_DEV_CREATE, NULL) < 0) {
        TRACE_ERROR("Can't create uinput device");
        close(fd);
        return -errno;
    }

    return fd;
}

static void uinput_close(void)
{
    if (uinput_device_fd >= 0) {
        ioctl(uinput_device_fd, UI_DEV_DESTROY);
        close(uinput_device_fd);
        uinput_device_fd = -1;
    }
}

static int send_key_event(uint16_t key, uint16_t value)
{
    struct input_event ev;

    if (uinput_device_fd < 0)
        return -ENODEV;

    /* key event */
    memset(&ev, 0, sizeof(ev));
    ev.type  = EV_KEY;
    ev.code  = key;
    ev.value = value;
    if (write(uinput_device_fd, &ev, sizeof(ev)) < 0) {
        TRACE_ERROR("Can't write key event");
        return -errno;
    }

    /* sync event */
    memset(&ev, 0, sizeof(ev));
    ev.type  = EV_SYN;
    ev.code  = SYN_REPORT;
    ev.value = 0;
    if (write(uinput_device_fd, &ev, sizeof(ev)) < 0) {
        TRACE_ERROR("Can't write syn event");
        return -errno;
    }

    return 0;
}

/* ===== Serial line / video switch helpers ===== */

static int set_line(int line, int enable)
{
    int status;

    if (ibus_device_fd < 0)
        return -ENODEV;

    if (ioctl(ibus_device_fd, TIOCMGET, &status) < 0) {
        TRACE_ERROR("Can't get TIOCM");
        return -errno;
    }

    int old_status = status;

    if (enable) {
        status |= line;
    } else {
        status &= ~line;
    }

    if (status != old_status) {
        if (ioctl(ibus_device_fd, TIOCMSET, &status) < 0) {
            TRACE_ERROR("Can't set TIOCM");
            return -errno;
        }
    }

    TRACE_WARGS(TRACE_STATE, "Set line 0x%x => %s, new state 0x%x\n",
                line, enable ? "on" : "off", status);
    return 0;
}

static void enable_video_input(int enable)
{
    TRACE_WARGS(TRACE_STATE, "enable_video_input(%d)\n", enable);

    switch (VideoInputSwitch) {
    case IBUS_VID_SWITCH_CTS:
        set_line(TIOCM_CTS, enable);
        break;
    case IBUS_VID_SWITCH_RTS:
        set_line(TIOCM_RTS, enable);
        break;
    case IBUS_VID_SWITCH_GPIO:
        /* TODO: GPIO-based switching if desired */
        break;
    case IBUS_VID_SWITCH_UNKNOWN:
    default:
        break;
    }
}

/* ===== Pretty-print IBUS messages (for logging) ===== */

static void print_ibus_message(const uint8_t *msg, uint8_t len)
{
    if (len < IBUS_MIN_MESSAGE_LEN)
        return;

    uint8_t sender   = msg[IBUS_POS_SENDER];
    uint8_t length   = msg[IBUS_POS_LENGTH];
    uint8_t receiver = msg[IBUS_POS_RECEIVER];
    uint8_t message  = msg[IBUS_POS_MESSAGE];
    uint8_t data_len = (len > IBUS_MIN_MESSAGE_LEN) ? (len - IBUS_MIN_MESSAGE_LEN) : 0;

    /* 1. Hex dump */
    trace_timestamp_prefix();
    for (uint8_t i = 0; i < len; ++i) {
        if (i < 4 || i == len - 1)
            fprintf(stdout_fp ? stdout_fp : stdout, " %02x", msg[i]);
        else
            fprintf(stdout_fp ? stdout_fp : stdout, "%02x", msg[i]);
    }

    /* 2. Device / message decoding */
    fprintf(stdout_fp ? stdout_fp : stdout, " = %s SENT %s TO %s",
            IBUSDevices[sender], IBUSMessages[message], IBUSDevices[receiver]);

    /* 3. Optional data printout */
    if (data_len > 0) {
        fprintf(stdout_fp ? stdout_fp : stdout, " DATA:");
        for (uint8_t i = 0; i < data_len; ++i) {
            uint8_t b = msg[IBUS_POS_DATA_START + i];
            if (b < 0x20 || b > 0x7F)
                fprintf(stdout_fp ? stdout_fp : stdout, "0x%02x ", b);
            else
                fputc(b, stdout_fp ? stdout_fp : stdout);
        }
    }

    fputc('\n', stdout_fp ? stdout_fp : stdout);
    if (stdout_fp) fflush(stdout_fp);
}

/* ===== Platform hook implementations ===== */

void ibus_platform_state_changed(ibus_state_t new_state,
                                 ibus_state_t hijack_state)
{
    TRACE_WARGS(TRACE_STATE, "IBUS state changed to %d (hijack=%d)\n",
                new_state, hijack_state);

    /* Enable key events & video only when we are in the hijack state */
    if (new_state == hijack_state && hijack_state != IBUS_STATE_UNKNOWN) {
        send_key_events = 1;
        enable_video_input(1);
    } else {
        send_key_events = 0;
        enable_video_input(0);
    }
}

void ibus_platform_button_event(uint8_t button_code,
                                uint8_t released,
                                uint8_t long_press)
{
    (void)long_press; /* currently not used for anything special */

    TRACE_WARGS(TRACE_INPUT, "Button event code=%u released=%u long=%u\n",
                button_code, released, long_press);

    if (!send_key_events)
        return;

    size_t count = sizeof(headunit_buttons) / sizeof(headunit_buttons[0]);
    if (button_code >= count) {
        TRACE_WARGS(TRACE_INPUT, "Invalid button index %u\n", button_code);
        return;
    }

    uint16_t key = headunit_buttons[button_code].key_code;

    if (key != KEY_UNKNOWN && key != RESERVED_BUTTON) {
        if (send_key_event(key, released ? 0 : 1) < 0) {
            TRACE_ERROR("Can't send key event");
        }
    }
}

void ibus_platform_knob_event(int clockwise, uint8_t steps)
{
    TRACE_WARGS(TRACE_INPUT, "Knob event clockwise=%d steps=%u\n",
                clockwise, steps);

    uint8_t idx = clockwise ? IBUS_BTN_IDX_MENUKNOB_CW
                            : IBUS_BTN_IDX_MENUKNOB_CCW;

    size_t count = sizeof(headunit_buttons) / sizeof(headunit_buttons[0]);
    if (idx >= count)
        return;

    uint16_t key = headunit_buttons[idx].key_code;
    if (key == KEY_UNKNOWN || key == RESERVED_BUTTON)
        return;

    while (steps-- > 0) {
        if (send_key_event(key, 1) < 0) break;
        if (send_key_event(key, 0) < 0) break;
    }
}

void ibus_platform_log_message(const uint8_t *msg, uint8_t len)
{
    if (!CHECK_TRACELEVEL(TRACE_IBUS))
        return;

    print_ibus_message(msg, len);
}

/* ===== CLI helper ===== */

static void print_help(const char *name)
{
    fprintf(stderr, "Usage: %s <options>\n", name);
    fprintf(stderr, "  -d <device>   Serial device (mandatory)\n");
    fprintf(stderr, "  -h <state>    Hijack state: FM/TAPE/AUX\n");
    fprintf(stderr, "  -v <switch>   Video input switch: CTS/RTS/GPIO\n");
    fprintf(stderr, "  -t <mask>     Trace level mask (1=function,2=ibus,4=input,8=state)\n");
    fprintf(stderr, "  -f <file>     Trace output file\n");
    fprintf(stderr, "\n");
    fprintf(stderr, "Example:\n");
    fprintf(stderr, "  %s -d /dev/ttyUSB0 -h AUX -v CTS -t 15 -f /tmp/ibus.log\n", name);
}

/* ===== main() ===== */

int main(int argc, char *argv[])
{
    int opt;
    char device_name[128]      = {0};
    char hijack_state_str[16]  = {0};
    char video_switch_str[16]  = {0};

    struct termios newtio, oldtio;
    sigset_t mask, orig_mask;
    struct sigaction act;

    struct timespec char_timeout;
    struct timespec shutdown_timeout;

    /* Parse CLI options */
    while ((opt = getopt(argc, argv, "d:h:v:t:f:")) != -1) {
        switch (opt) {
        case 'd':
            strncpy(device_name, optarg, sizeof(device_name) - 1);
            break;
        case 'h':
            strncpy(hijack_state_str, optarg, sizeof(hijack_state_str) - 1);
            if (strcmp(hijack_state_str, "TAPE") == 0)
                g_hijack_state = IBUS_STATE_TAPE;
            else if (strcmp(hijack_state_str, "AUX") == 0)
                g_hijack_state = IBUS_STATE_AUX;
            else if (strcmp(hijack_state_str, "FM") == 0)
                g_hijack_state = IBUS_STATE_FM;
            else
                g_hijack_state = IBUS_STATE_UNKNOWN;
            break;
        case 'v':
            strncpy(video_switch_str, optarg, sizeof(video_switch_str) - 1);
            if (strcmp(video_switch_str, "CTS") == 0)
                VideoInputSwitch = IBUS_VID_SWITCH_CTS;
            else if (strcmp(video_switch_str, "RTS") == 0)
                VideoInputSwitch = IBUS_VID_SWITCH_RTS;
            else if (strcmp(video_switch_str, "GPIO") == 0)
                VideoInputSwitch = IBUS_VID_SWITCH_GPIO;
            else
                VideoInputSwitch = IBUS_VID_SWITCH_UNKNOWN;
            break;
        case 't':
            trace_level = (unsigned int)atoi(optarg);
            break;
        case 'f':
            stdout_fp = fopen(optarg, "a+");
            if (!stdout_fp) {
                perror("fopen trace file");
            }
            break;
        default:
            print_help(argv[0]);
            return EXIT_FAILURE;
        }
    }

    if (device_name[0] == '\0') {
        print_help(argv[0]);
        return EXIT_FAILURE;
    }

    /* Initialise IBUS core */
    ibus_init(g_hijack_state);

    /* Create uinput device */
    uinput_device_fd = uinput_create();
    if (uinput_device_fd < 0) {
        fprintf(stderr, "Failed to create uinput device (%d)\n", uinput_device_fd);
        return EXIT_FAILURE;
    }

    /* Setup signal handling */
    sigemptyset(&mask);

    memset(&act, 0, sizeof(act));
    act.sa_handler = signal_handler;
    sigaction(SIGTERM, &act, NULL);
    sigaddset(&mask, SIGTERM);

    memset(&act, 0, sizeof(act));
    act.sa_handler = signal_handler;
    sigaction(SIGINT, &act, NULL);
    sigaddset(&mask, SIGINT);

    if (sigprocmask(SIG_BLOCK, &mask, &orig_mask) < 0) {
        TRACE_ERROR("sigprocmask");
        uinput_close();
        return EXIT_FAILURE;
    }

    /* Open serial port */
    ibus_device_fd = open(device_name,
                          O_RDONLY | O_NOCTTY | O_NONBLOCK);
    if (ibus_device_fd < 0) {
        TRACE_ERROR("Can't open IBUS serial device");
        uinput_close();
        return EXIT_FAILURE;
    }

    /* Save current settings and configure 9600 8E1 */
    if (tcgetattr(ibus_device_fd, &oldtio) < 0) {
        TRACE_ERROR("tcgetattr");
        close(ibus_device_fd);
        uinput_close();
        return EXIT_FAILURE;
    }

    memset(&newtio, 0, sizeof(newtio));
    newtio.c_cflag = B9600 | CS8 | PARENB | CLOCAL | CREAD;
    newtio.c_iflag = IGNPAR | IGNBRK;
    newtio.c_oflag = 0;
    newtio.c_lflag = 0;
    newtio.c_cc[VMIN]  = 1;
    newtio.c_cc[VTIME] = 0;

    if (tcflush(ibus_device_fd, TCIFLUSH) < 0) {
        TRACE_ERROR("tcflush");
    }
    if (tcsetattr(ibus_device_fd, TCSANOW, &newtio) < 0) {
        TRACE_ERROR("tcsetattr");
        close(ibus_device_fd);
        uinput_close();
        return EXIT_FAILURE;
    }

    /* Timeouts: character timeout and idle shutdown timeout */
    /* 9600 baud 8E1 => ~1.15ms/char; we use ~2.3ms char timeout */
    char_timeout.tv_sec  = 0;
    char_timeout.tv_nsec = 2300000L;

    shutdown_timeout.tv_sec  = 60 * 10;  /* 10 minutes */
    shutdown_timeout.tv_nsec = 0;

    /* Main loop */
    while (!exit_request) {
        fd_set fds;
        int res;

        FD_ZERO(&fds);
        FD_SET(ibus_device_fd, &fds);

        if (ibus_has_pending_data())
            res = pselect(ibus_device_fd + 1, &fds, NULL, NULL,
                          &char_timeout, &orig_mask);
        else
            res = pselect(ibus_device_fd + 1, &fds, NULL, NULL,
                          &shutdown_timeout, &orig_mask);

        if (res < 0 && errno != EINTR) {
            TRACE_ERROR("pselect");
            break;
        } else if (exit_request) {
            TRACE(TRACE_ALL, "Exit requested\n");
            break;
        } else if (res == 0) {
            if (ibus_has_pending_data()) {
                /* Timeout => we assume current IBUS frame is complete */
                ibus_process_messages();
                continue;
            } else {
                TRACE(TRACE_ALL,
                      "10 minutes without messages on the bus => exiting\n");
                break;
            }
        }

        if (FD_ISSET(ibus_device_fd, &fds)) {
            unsigned char byte;
            res = (int)read(ibus_device_fd, &byte, 1);
            if (res == 1) {
                ibus_append_byte(byte);
            } else if (res < 0 && errno != EAGAIN) {
                TRACE_ERROR("read");
            }
        }
    }

    /* Restore serial settings */
    tcsetattr(ibus_device_fd, TCSANOW, &oldtio);
    close(ibus_device_fd);
    uinput_close();

    if (stdout_fp) {
        fflush(stdout_fp);
        fclose(stdout_fp);
    }

    return EXIT_SUCCESS;
}
