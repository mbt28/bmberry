// main_pico.c
// Raspberry Pi Pico 2 (RP2350) firmware: read BMW I-Bus on UART (9600 8E1)
// and expose decoded events over USB CDC (serial) for bring-up/debug.
//
// Protocol decoding is shared with Linux via ibus_protocol.c/ibus_protocol.h.

#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
#include <stdarg.h>

#include "pico/stdlib.h"
#include "pico/multicore.h"
#include "hardware/i2c.h"
#include "hardware/uart.h"
#include "hardware/gpio.h"

#include "bsp/board.h"
#include "tusb.h"

#include "ibus_protocol.h"

// External CSYNC core entry points
void csync_init(void);
void csync_run(void);

// =========================
// Compile-time configuration
// =========================

// I-Bus UART config (9600 baud, 8E1).
#ifndef IBUS_PICO_UART_ID
#define IBUS_PICO_UART_ID        uart0
#endif
#ifndef IBUS_PICO_UART_BAUD
#define IBUS_PICO_UART_BAUD      9600u
#endif
#ifndef IBUS_PICO_UART_TX_PIN
#define IBUS_PICO_UART_TX_PIN    16u
#endif
#ifndef IBUS_PICO_UART_RX_PIN
#define IBUS_PICO_UART_RX_PIN    17u
#endif

// I2C (mode switch helper)
#ifndef IBUS_PICO_I2C_PORT
#define IBUS_PICO_I2C_PORT       i2c1
#endif
#ifndef IBUS_PICO_I2C_SDA_PIN
#define IBUS_PICO_I2C_SDA_PIN    18u
#endif
#ifndef IBUS_PICO_I2C_SCL_PIN
#define IBUS_PICO_I2C_SCL_PIN    19u
#endif
#ifndef IBUS_PICO_I2C_BAUDRATE
#define IBUS_PICO_I2C_BAUDRATE   100000u
#endif

// Inter-byte timeout that indicates "end of current I-Bus message burst".
#ifndef IBUS_PICO_CHAR_TIMEOUT_US
#define IBUS_PICO_CHAR_TIMEOUT_US 3000
#endif

// Default hijack state for the decoder (matches Linux -h option concept).
#ifndef IBUS_PICO_HIJACK_STATE
#define IBUS_PICO_HIJACK_STATE    IBUS_STATE_AUX
#endif

// Optional GPIO to indicate when we are in hijack state.
// -1 disables.
#ifndef IBUS_PICO_VIDEO_GPIO
#define IBUS_PICO_VIDEO_GPIO      (15)
#endif
#ifndef IBUS_PICO_VIDEO_GPIO_ACTIVE_LEVEL
#define IBUS_PICO_VIDEO_GPIO_ACTIVE_LEVEL 1
#endif

// Enable/disable verbose logging over USB CDC.
#ifndef IBUS_PICO_TRACE
#define IBUS_PICO_TRACE           1
#endif

// =========================
// USB CDC logging helper
// =========================

static void cdc_log_vprintf(const char *fmt, va_list ap)
{
#if IBUS_PICO_TRACE
    if (!tud_cdc_connected()) return;

    char buf[256];
    int n = vsnprintf(buf, sizeof(buf), fmt, ap);
    if (n <= 0) return;
    if (n > (int)sizeof(buf)) n = (int)sizeof(buf);

    tud_cdc_write(buf, (uint32_t)n);
    tud_cdc_write_flush();
#else
    (void)fmt; (void)ap;
#endif
}

static void cdc_log_printf(const char *fmt, ...)
{
#if IBUS_PICO_TRACE
    va_list ap;
    va_start(ap, fmt);
    cdc_log_vprintf(fmt, ap);
    va_end(ap);
#else
    (void)fmt;
#endif
}

// Timestamp for logs (ms since boot, from TinyUSB board helper).
static uint32_t now_ms(void)
{
    return board_millis();
}

static void log_prefix(void)
{
#if IBUS_PICO_TRACE
    cdc_log_printf("%lu.%03lu: ",
                   (unsigned long)(now_ms() / 1000u),
                   (unsigned long)(now_ms() % 1000u));
#endif
}

// =========================
// Platform hook implementations (required by ibus_protocol.c)
// =========================

static void ibus_i2c_mode_bmw(void);
static void ibus_i2c_mode_tv(void);

// Drive the optional video GPIO according to requested on/off state.
static void ibus_video_gpio_set(bool on)
{
#if (IBUS_PICO_VIDEO_GPIO >= 0)
    const bool level = on ? IBUS_PICO_VIDEO_GPIO_ACTIVE_LEVEL
                          : !IBUS_PICO_VIDEO_GPIO_ACTIVE_LEVEL;
    gpio_put((uint)IBUS_PICO_VIDEO_GPIO, level);
#else
    (void)on;
#endif
}

void ibus_platform_state_changed(ibus_state_t new_state, ibus_state_t hijack_state)
{
#if IBUS_PICO_TRACE
    log_prefix();
    cdc_log_printf("State changed: %d (hijack=%d)\n", (int)new_state, (int)hijack_state);
#else
    (void)new_state; (void)hijack_state;
#endif

    if (new_state == IBUS_STATE_CD_CHANGER) {
        ibus_i2c_mode_tv();
    } else {
        ibus_i2c_mode_bmw();
    }
}

void ibus_platform_button_event(uint8_t button_code, uint8_t released, uint8_t long_press)
{
#if IBUS_PICO_TRACE
    log_prefix();
    cdc_log_printf("Button code=%u %s %s\n",
                   (unsigned)button_code,
                   released ? "RELEASE" : "PRESS",
                   long_press ? "LONG" : "SHORT");
#else
    (void)button_code; (void)released; (void)long_press;
#endif
}

void ibus_platform_knob_event(int clockwise, uint8_t steps)
{
#if IBUS_PICO_TRACE
    log_prefix();
    cdc_log_printf("Knob %s steps=%u\n",
                   clockwise ? "CW" : "CCW",
                   (unsigned)steps);
#else
    (void)clockwise; (void)steps;
#endif
}

void ibus_platform_log_message(const uint8_t *msg, uint8_t len)
{
#if IBUS_PICO_TRACE
    // Light-weight hex dump to CDC (can be verbose).
    log_prefix();
    cdc_log_printf("IBUS len=%u: ", (unsigned)len);
    for (uint8_t i = 0; i < len; i++) {
        cdc_log_printf("%02X ", msg[i]);
    }
    cdc_log_printf("\n");
#else
    (void)msg; (void)len;
#endif
}

// =========================
// Main
// =========================

static void ibus_uart_init(void)
{
    uart_init(IBUS_PICO_UART_ID, IBUS_PICO_UART_BAUD);

    gpio_set_function(IBUS_PICO_UART_TX_PIN, GPIO_FUNC_UART);
    gpio_set_function(IBUS_PICO_UART_RX_PIN, GPIO_FUNC_UART);

    uart_set_format(IBUS_PICO_UART_ID, 8, 1, UART_PARITY_EVEN);
    uart_set_hw_flow(IBUS_PICO_UART_ID, false, false); // ignore RTS/CTS on Pico
    uart_set_fifo_enabled(IBUS_PICO_UART_ID, true);
}

static void optional_video_gpio_init(void)
{
#if (IBUS_PICO_VIDEO_GPIO >= 0)
    gpio_init((uint)IBUS_PICO_VIDEO_GPIO);
    gpio_set_dir((uint)IBUS_PICO_VIDEO_GPIO, GPIO_OUT);
    ibus_video_gpio_set(false);
#endif
}

// Simple I2C helper to set an external device into BMW mode.
static void ibus_i2c_init(void)
{
    i2c_init(IBUS_PICO_I2C_PORT, IBUS_PICO_I2C_BAUDRATE);

    gpio_set_function(IBUS_PICO_I2C_SDA_PIN, GPIO_FUNC_I2C);
    gpio_set_function(IBUS_PICO_I2C_SCL_PIN, GPIO_FUNC_I2C);

    gpio_pull_up(IBUS_PICO_I2C_SDA_PIN);
    gpio_pull_up(IBUS_PICO_I2C_SCL_PIN);
}

static int ibus_i2c_write_bytes(uint8_t addr, const uint8_t *data, size_t len)
{
    if (!data || len == 0) return -1;

    int written = i2c_write_blocking(
        IBUS_PICO_I2C_PORT,
        addr,
        data,
        len,
        false // send STOP condition
    );

    return (written == (int)len) ? 0 : -2;
}

static void ibus_i2c_mode_bmw(void)
{
    const uint8_t val = 0x0F;
    (void)ibus_i2c_write_bytes(0x39, &val, 1);

    ibus_video_gpio_set(false);
}

static void ibus_i2c_mode_tv(void)
{
    const uint8_t val = 0x17;
    (void)ibus_i2c_write_bytes(0x39, &val, 1);

    const uint8_t cmd1[] = { 0x00, 0x07 };
    (void)ibus_i2c_write_bytes(0x45, cmd1, sizeof(cmd1));

    const uint8_t cmd2[] = { 0x11, 0x73 };
    (void)ibus_i2c_write_bytes(0x45, cmd2, sizeof(cmd2));

	// Shift image to rightest horizontal position.
    const uint8_t cmd3[] = { 0x03, 0x3F };
    (void)ibus_i2c_write_bytes(0x45, cmd3, sizeof(cmd3));
    
    ibus_video_gpio_set(true);
}

// Core1 entry point: run CSYNC generator
static void core1_main(void)
{
    csync_init();
    csync_run();
}

int main(void)
{
    // TinyUSB board init + stack init.
    board_init();
    tusb_init();

    ibus_uart_init();
    optional_video_gpio_init();
    multicore_launch_core1(core1_main);
    ibus_i2c_init();
    ibus_i2c_mode_bmw();

    ibus_init(IBUS_PICO_HIJACK_STATE);

#if IBUS_PICO_TRACE
    // Give host a moment to enumerate CDC before we start logging.
    sleep_ms(1200);
    log_prefix();
    cdc_log_printf("I-Bus CDC bridge started (UART RX pin=%u baud=%u hijack=%d)\n",
                   (unsigned)IBUS_PICO_UART_RX_PIN,
                   (unsigned)IBUS_PICO_UART_BAUD,
                   (int)IBUS_PICO_HIJACK_STATE);
#endif

    absolute_time_t last_rx_time = get_absolute_time();

    while (true) {
        // USB device task (CDC)
        tud_task();

        // Read any pending UART bytes
        while (uart_is_readable(IBUS_PICO_UART_ID)) {
            uint8_t b = uart_getc(IBUS_PICO_UART_ID);
            ibus_append_byte(b);
            last_rx_time = get_absolute_time();
        }

        // If we have buffered data and no new byte has arrived for a bit,
        // parse buffered messages.
        if (ibus_has_pending_data()) {
            int64_t idle_us = absolute_time_diff_us(last_rx_time, get_absolute_time());
            if (idle_us > (int64_t)IBUS_PICO_CHAR_TIMEOUT_US) {
                ibus_process_messages();
            }
        }

        tight_loop_contents();
    }
}
