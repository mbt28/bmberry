#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python_bin="${PYTHON:-python3}"
if [[ -x ".venv/bin/python" ]]; then
  python_bin=".venv/bin/python"
fi
exec "$python_bin" app.py
