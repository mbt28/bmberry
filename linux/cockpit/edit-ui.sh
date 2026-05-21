#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

ui_file="${1:-ui/cockpit.ui}"
exec pygubu-designer "$ui_file"
