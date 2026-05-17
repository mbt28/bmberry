#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -x ".venv/bin/pygubu-designer" ]]; then
  echo "pygubu-designer is not installed in .venv. Run:"
  echo "  python3 -m venv .venv"
  echo "  .venv/bin/python -m pip install -r requirements.txt"
  exit 1
fi

ui_file="${1:-ui/cockpit.ui}"
exec .venv/bin/pygubu-designer "$ui_file"
