#ifndef _TUSB_CONFIG_H_
#define _TUSB_CONFIG_H_

// TinyUSB configuration for Pico (device mode, CDC + HID keyboard).
// Keep this header self-contained; it is included while TinyUSB is still setting
// up its own types, so avoid pulling other TinyUSB headers here.

// TinyUSB + Pico SDK will provide CFG_TUSB_MCU/OS on the compile line; keep
// defaults here for standalone builds without redefining them.
#ifndef CFG_TUSB_MCU
#define CFG_TUSB_MCU              OPT_MCU_RP2350
#endif

#ifndef CFG_TUSB_OS
#define CFG_TUSB_OS               OPT_OS_PICO
#endif

// Device mode on root hub port 0 (FS).
#ifndef CFG_TUSB_RHPORT0_MODE
#define CFG_TUSB_RHPORT0_MODE     (OPT_MODE_DEVICE | OPT_MODE_FULL_SPEED)
#endif

// Memory placement/alignment (Pico SDK style).
#ifndef CFG_TUSB_MEM_SECTION
#define CFG_TUSB_MEM_SECTION
#endif

#ifndef CFG_TUSB_MEM_ALIGN
#define CFG_TUSB_MEM_ALIGN        __attribute__ ((aligned(4)))
#endif

// Set debug level (increase for verbose TinyUSB logging).
#ifndef CFG_TUSB_DEBUG
#define CFG_TUSB_DEBUG            1
#endif

// ===== Device stack configuration =====
#ifndef CFG_TUD_ENDPOINT0_SIZE
#define CFG_TUD_ENDPOINT0_SIZE    64
#endif

// CDC (USB Serial)
#ifndef CFG_TUD_CDC
#define CFG_TUD_CDC               1
#endif

#ifndef CFG_TUD_CDC_RX_BUFSIZE
#define CFG_TUD_CDC_RX_BUFSIZE    256
#endif

#ifndef CFG_TUD_CDC_TX_BUFSIZE
#define CFG_TUD_CDC_TX_BUFSIZE    256
#endif

// HID (Keyboard)
#ifndef CFG_TUD_HID
#define CFG_TUD_HID               0
#endif

#ifndef CFG_TUD_HID_EP_BUFSIZE
#define CFG_TUD_HID_EP_BUFSIZE    16
#endif

// Disable other classes
#ifndef CFG_TUD_MSC
#define CFG_TUD_MSC               0
#endif

#ifndef CFG_TUD_MIDI
#define CFG_TUD_MIDI              0
#endif

#ifndef CFG_TUD_VENDOR
#define CFG_TUD_VENDOR            0
#endif

#endif // _TUSB_CONFIG_H_
