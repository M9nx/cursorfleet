"""Parse ``config.toml`` / ``roster.toml`` text into models. Size-capped, stdlib TOML."""

from __future__ import annotations

import tomllib

from cursorfleet.config.models import FleetConfig
from cursorfleet.config.roster import Roster

MAX_TOML_BYTES = 256 * 1024


def _parse(text: str) -> dict[str, object]:
    if len(text.encode("utf-8")) > MAX_TOML_BYTES:
        msg = f"TOML input exceeds {MAX_TOML_BYTES} bytes"
        raise ValueError(msg)
    return tomllib.loads(text)


def loads_config(text: str) -> FleetConfig:
    """Parse and validate ``config.toml`` text. Raises ValueError subclasses on any problem."""
    return FleetConfig.model_validate(_parse(text))


def loads_roster(text: str) -> Roster:
    """Parse and validate ``roster.toml`` text. Raises ValueError subclasses on any problem."""
    return Roster.model_validate(_parse(text))
