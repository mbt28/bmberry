#!/usr/bin/env bash
set -euo pipefail

FILE="${LIVI_STATUS_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/LIVI/statusData.json}"
GPIOCHIP="${GPIOCHIP:-gpiochip0}"
MUTE_PIN="${MUTE_PIN:-6}"
TEL_ON_PIN="${TEL_ON_PIN:-13}"
gpio_pid=""

release_gpio() {
    if [ -n "$gpio_pid" ]; then
        kill "$gpio_pid" 2>/dev/null || true
        wait "$gpio_pid" 2>/dev/null || true
        gpio_pid=""
    fi
}

hold_gpio() {
    release_gpio
    gpioset -c "$GPIOCHIP" "$@" &
    gpio_pid="$!"
}

set_phone_gpio() {
    local active

    if [ ! -r "$FILE" ]; then
        return
    fi

    active="$(jq -r '.payload.phone.active // false' "$FILE" 2>/dev/null)" || return

    if [ "$active" = "true" ]; then
        hold_gpio "$MUTE_PIN=0" "$TEL_ON_PIN=1"
    else
        hold_gpio "$MUTE_PIN=1" "$TEL_ON_PIN=0"
    fi
}

trap release_gpio EXIT INT TERM

command -v jq >/dev/null || {
    echo "jq is required" >&2
    exit 1
}

command -v inotifywait >/dev/null || {
    echo "inotifywait is required" >&2
    exit 1
}

command -v gpioset >/dev/null || {
    echo "gpioset is required" >&2
    exit 1
}

mkdir -p "$(dirname "$FILE")"
set_phone_gpio

inotifywait -m -e moved_to,close_write,create,modify --format "%f" "$(dirname "$FILE")" |
    while read -r changed_file; do
        if [ "$changed_file" != "$(basename "$FILE")" ]; then
            continue
        fi

        sleep 0.05
        set_phone_gpio
    done
