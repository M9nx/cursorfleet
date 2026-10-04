"""Regenerate (or --check) schemas/*.json from the Pydantic models."""

from __future__ import annotations

import sys
from pathlib import Path

from cursorfleet.schema_gen import main

if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    sys.exit(main(root / "schemas", check="--check" in sys.argv[1:]))
