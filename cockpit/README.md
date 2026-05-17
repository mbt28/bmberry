# Cockpit

`Cockpit` is a Linux desktop GUI for the BMW I-Bus bridge code in the parent folder.

It does not modify the parent project. It only:

- launches the bridge with a GUI for device and mode selection
- sends custom I-Bus frames from the GUI
- stores its own config in this project folder and writes the default debug log under `$HOME/.config/cockpit/`

## Features

- Linux-native GUI using Python `tkinter`
- Pygubu-editable layout in `ui/cockpit.ui`
- Pygubu-editable radio title popup fields in `ui/radio.ui`
- Auto-detect common serial devices
- Start/stop the bridge process
- Live console output
- Raw I-Bus frame sender under the console
- Structured I-Bus frame builder with automatic length/checksum preview
- Local config persistence in `config.json`
- Default log file in `$HOME/.config/cockpit/ibus.log`

## Run

Install GUI-designer dependencies once if the local `.venv` is missing packages:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

If you use the bundled virtual environment:

```bash
./run.sh
```

Without the virtual environment:

```bash
python3 app.py
```

The app falls back to its built-in Tk layout if `pygubu` is not installed.

## Edit the UI

Open the editable layout with:

```bash
./edit-ui.sh
```

Save changes back to `ui/cockpit.ui`, then restart `./run.sh`.

Open the radio popup layout with:

```bash
./edit-ui.sh ui/radio.ui
```

`radio.py` updates the title/legacy RADIO screen through named widgets in `ui/radio.ui`. The canvas is still used for the procedural select, tone, station-list, background, and fallback views. Keep the overall screen at 400x234 unless the drawing constants in `emulators/radio.py` are changed too.

Keep these widget IDs intact because `app.py` binds backend logic to them:

```text
main_frame
bridge_button radio_button clear_console_button
settings_button about_button copy_message_button
send_raw_button preset_settings_button
build_into_raw_button send_built_button
tx_raw_entry tx_sender_entry tx_receiver_entry tx_message_entry tx_data_entry tx_frame_entry
preset_button_1 preset_button_2 preset_button_3 preset_button_4 preset_button_5
console_table_frame
```

For `ui/radio.ui`, keep these widget IDs intact:

```text
radio_frame
radio_canvas
radio_title_view radio_title_header
radio_source_box_1 radio_source_box_2 radio_source_box_3
radio_title_text_label radio_tp_station_label
radio_right_box_1 radio_right_box_2
radio_body_subtitle_label radio_body_text_label
radio_footer_bar radio_date_label radio_time_label
```

## Notes

- The backend still needs access to `/dev/uinput` and the selected serial device.
- Build the parent backend separately before using the GUI:

```bash
cd ..
make -f Makefile.linux
```

- With the permissions described in `README-permissions.md`, `Cockpit` can run the backend as a normal user.
- `Cockpit` itself stays in the current folder and treats the parent folder as an external source/backend.
- Bridge settings, including the backend path, serial device, hijack/video mode, trace level, and log output path, are configured from the Settings button.
