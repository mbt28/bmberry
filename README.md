# I/K-Bus bridge: Linux + RPI Pico 2 (shared decoder)

This repo contains a shared BMW I-Bus decoder (`ibus_protocol.c/.h`) with two front-ends:

- **Linux**: reads from UART, sends key events via **uinput** (`main_linux.c`)
- **Raspberry Pi Pico 2**: reads I-Bus from **UART (9600 8E1)** and exposes a **USB HID keyboard** + **USB CDC serial** for logs (`pico/main_pico.c`). It can also interract with Video Module over I2C to enable RGB input. Another PIO program runs on Core1 which converts VGA Horizontal/Vertical Syncs to Composite Sync. 

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

- `UART0 RX` = **GP16**
- `UART0 TX` = **GP17** (not used for receive-only)
- baud/format: **9600 8E1**

- `I2C1 SDA` = **GP18**
- `I2C1 SCL` = **GP19**
- baud: **100khz**

- `Hsync in` = **GP2**
- `Vsync in` = **GP3**
- `Csync Out` = **GP4**
- format: **NTSC 400x240 progressive**
- 
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

- More feautures will come. Software is on very early stage but works for testing. Currently it doesnt emulate cd changer but can switch to RGB input when CDC is selected. CDC emulation will come soon. Reverse engineering of IBUS Video Modules: https://github.com/mbt28/IBUS-TV-Modules-RGB-Input
