// usb_descriptors.c
// USB descriptors for a CDC-only device (USB serial).
//
// This intentionally removes HID to simplify bring-up and avoid TinyUSB HID
// configuration/link issues while validating UART + protocol decoding.

#include <stdint.h>
#include <string.h>
#include <stdbool.h>

#include "pico/unique_id.h"
#include "tusb.h"
#include "usb_descriptors.h"

//------------- Device Descriptor -------------//
tusb_desc_device_t const desc_device =
{
    .bLength            = sizeof(tusb_desc_device_t),
    .bDescriptorType    = TUSB_DESC_DEVICE,
    .bcdUSB             = 0x0200,

    // Use IAD (Interface Association Descriptor) for CDC
    .bDeviceClass       = TUSB_CLASS_MISC,
    .bDeviceSubClass    = MISC_SUBCLASS_COMMON,
    .bDeviceProtocol    = MISC_PROTOCOL_IAD,

    .bMaxPacketSize0    = CFG_TUD_ENDPOINT0_SIZE,

    // VID/PID: for hobby use; change if you have your own VID/PID
    .idVendor           = 0xCafe,
    .idProduct          = 0x4011,
    .bcdDevice          = 0x0100,

    .iManufacturer      = 0x01,
    .iProduct           = 0x02,
    .iSerialNumber      = 0x03,

    .bNumConfigurations = 0x01
};

uint8_t const *tud_descriptor_device_cb(void)
{
    return (uint8_t const *) &desc_device;
}

//------------- Configuration Descriptor -------------//
static uint8_t const desc_configuration[] =
{
    // Config number, interface count, string index, total length, attribute, power (mA)
    TUD_CONFIG_DESCRIPTOR(1, ITF_NUM_TOTAL, 0, CONFIG_TOTAL_LEN, 0x00, 100),

    // CDC: ITF_NUM_CDC, string index 4, EP notif, notif size, EP OUT, EP IN, buffer size
    TUD_CDC_DESCRIPTOR(ITF_NUM_CDC, 4, EPNUM_CDC_NOTIF, 8, EPNUM_CDC_OUT, EPNUM_CDC_IN, 64),
};

uint8_t const *tud_descriptor_configuration_cb(uint8_t index)
{
    (void) index;
    return desc_configuration;
}

//------------- String Descriptors -------------//
static char serial_str[2 * PICO_UNIQUE_BOARD_ID_SIZE_BYTES + 1];

static char const *string_desc_arr[] =
{
    (const char[]) { 0x09, 0x04 }, // 0: English (0x0409)
    "IBUS Bridge",                 // 1: Manufacturer
    "IBUS CDC",                    // 2: Product
    serial_str,                    // 3: Serial
    "IBUS CDC",                    // 4: CDC interface
};

static uint16_t _desc_str[32];

uint16_t const *tud_descriptor_string_cb(uint8_t index, uint16_t langid)
{
    (void) langid;

    // Prepare serial string once
    static bool serial_ready = false;
    if (!serial_ready) {
        pico_get_unique_board_id_string(serial_str, sizeof(serial_str));
        serial_ready = true;
    }

    uint8_t chr_count;

    if (index == 0) {
        // Language ID string
        _desc_str[1] = 0x0409;
        chr_count = 1;
    } else {
        if (index >= (sizeof(string_desc_arr) / sizeof(string_desc_arr[0]))) {
            return NULL;
        }

        const char *str = string_desc_arr[index];
        chr_count = (uint8_t) strlen(str);
        if (chr_count > 31) chr_count = 31;

        for (uint8_t i = 0; i < chr_count; i++) {
            _desc_str[1 + i] = (uint16_t) str[i];
        }
    }

    // first byte is length (including header), second byte is descriptor type
    _desc_str[0] = (uint16_t) ((TUSB_DESC_STRING << 8) | (2 * chr_count + 2));
    return _desc_str;
}
