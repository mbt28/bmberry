cmake_minimum_required(VERSION 3.13)
include(${PICO_SDK_PATH}/external/pico_sdk_import.cmake)
if(NOT DEFINED PICO_PLATFORM)
  set(PICO_PLATFORM rp2350-arm-s)
endif()
set(PICO_TINYUSB_CONFIG_PATH ${CMAKE_CURRENT_LIST_DIR})
set(PICO_TINYUSB_CONFIG_NAME "tusb_config.h")
project(pico2ibus C CXX ASM)
pico_sdk_init()

add_executable(ibus_pico_bridge
    pico/main_pico.c
    pico/usb_descriptors.c
    pico/csync.c
    ibus_protocol.c
)

target_include_directories(ibus_pico_bridge PRIVATE
    ${CMAKE_CURRENT_LIST_DIR}
    ${CMAKE_CURRENT_LIST_DIR}/pico
)

target_link_libraries(ibus_pico_bridge
    pico_stdlib
    hardware_gpio
    hardware_uart
    hardware_i2c
    hardware_irq
    hardware_timer
    hardware_pio
    hardware_clocks
    hardware_flash
    pico_multicore
    tinyusb_device
    tinyusb_board
)

# We use TinyUSB directly (CDC + HID), so we don't link pico_stdio_usb.
# If you want UART stdio for debugging, enable it in your project and avoid UART0 if it is used for I-Bus.
pico_add_extra_outputs(ibus_pico_bridge)
