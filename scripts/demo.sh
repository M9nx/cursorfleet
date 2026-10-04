#!/usr/bin/env bash
# Reproducible SYNTHETIC demo (no live Cursor). Thin wrapper around scripts/demo.py so the
# same script also runs on Windows (`py scripts/demo.py`). Extra arguments are passed on:
#   scripts/demo.sh --venv /path/to/venv --keep
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if command -v uv >/dev/null 2>&1; then
  exec uv run --quiet --project "$here/.." python "$here/demo.py" "$@"
fi
exec "${PYTHON:-python3}" "$here/demo.py" "$@"
