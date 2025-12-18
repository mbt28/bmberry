# I-Bus bridge: Linux + Pico 2 (shared decoder)

This repo contains a shared BMW I-Bus decoder (`ibus_protocol.c/.h`) with two front-ends:

- **Linux**: reads from UART, sends key events via **uinput** (`main_linux.c`)
- **Raspberry Pi Pico 2**: reads I-Bus from **UART (9600 8E1)** and exposes a **USB HID keyboard** + **USB CDC serial** for logs (`pico/main_pico.c`)

## Linux build

```bash
make -f Makefile.linux
sudo ./ibus_linux -d /dev/ttyUSB0 -h AUX -v CTS -t 15
```

> Note: `/dev/uinput` must be accessible (usually requires root, or udev permissions).

## Pico 2 build (Pico SDK)

Prereqs:
- Pico SDK installed, `PICO_SDK_PATH` set
- `tinyusb` submodule initialized inside Pico SDK (`git submodule update --init`)

Build:
```bash
mkdir build-pico
cd build-pico
cmake .. -DPICO_BOARD=pico2
cmake --build . -j
```

Flash `ibus_pico_bridge.uf2` to the Pico 2.

### Pico UART wiring (defaults)

In `pico/main_pico.c` defaults are:

- `UART0 RX` = **GP1**
- `UART0 TX` = **GP0** (not used for receive-only)
- baud/format: **9600 8E1**

You normally connect I-Bus via a proper transceiver/interface (open-collector to UART-level).
The Pico code assumes it receives UART-level data.

### Optional video/hijack GPIO

If you want a simple GPIO that indicates “hijack state active” (e.g., to drive a transistor),
set at compile time:

- `IBUS_PICO_VIDEO_GPIO` (default: `-1` = disabled)

Example:
```bash
cmake .. -DPICO_BOARD=pico2 -DCMAKE_C_FLAGS=\"-DIBUS_PICO_VIDEO_GPIO=2\"
```

### Notes

- Pico ignores RTS/CTS flow control by design.
