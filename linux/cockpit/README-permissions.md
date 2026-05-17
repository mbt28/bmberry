# Cockpit Linux Permissions

This project needs two kinds of access on Linux:

- serial device access for `/dev/ttyUSB*` or `/dev/ttyACM*`
- virtual input access for `/dev/uinput`

## Typical group setup

Most Linux systems work with:

- `dialout` for USB serial devices like `/dev/ttyUSB0`
- `input` for `/dev/uinput` when the node is created with that group

`tty` is usually not required for normal USB serial access.

## Why sudo is often needed at first

The usual reasons are:

- `/dev/uinput` does not exist because the `uinput` kernel module is not loaded
- `/dev/uinput` exists but is owned by `root:root` with mode `600`
- the current user is not in `dialout` and `input`

## One-time setup

Load `uinput` now:

```bash
sudo modprobe uinput
```

Make it load on boot:

```bash
echo uinput | sudo tee /etc/modules-load.d/uinput.conf
```

## Verify device ownership

Check the serial device and uinput node:

```bash
ls -l /dev/ttyUSB0 /dev/uinput
```

Typical good results are something like:

- `/dev/ttyUSB0` owned by group `dialout`
- `/dev/uinput` owned by group `input`

## If your user is missing required groups

Add the current user to `dialout` and `input`:

```bash
sudo usermod -aG dialout,input $USER
```

Then log out and log back in, or reboot.

Verify:

```bash
id
```

## If `/dev/uinput` has the wrong group or mode

Create a udev rule:

```bash
sudo tee /etc/udev/rules.d/99-cockpit-uinput.rules >/dev/null <<'EOF'
SUBSYSTEM=="misc", KERNEL=="uinput", MODE="0660", GROUP="input"
EOF
```

Reload rules and trigger:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Then reload the module:

```bash
sudo modprobe -r uinput
sudo modprobe uinput
```

## Serial device note

If `/dev/ttyUSB0` is not owned by `dialout`, inspect it:

```bash
udevadm info -a -n /dev/ttyUSB0
```

On most Debian/Raspberry Pi OS systems, USB serial adapters already use `dialout`.

## Expected no-sudo path

After the setup is correct:

1. `id` should show `dialout` and `input`
2. `/dev/uinput` should exist
3. `/dev/uinput` should typically look like `crw-rw---- root input`
4. `/dev/ttyUSB0` should be group-accessible, usually via `dialout`
5. `Cockpit` can run the backend without `sudo`
