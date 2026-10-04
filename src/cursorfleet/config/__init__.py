"""Configuration and roster models.

Importing this package is cheap; models (Pydantic) are re-exported lazily
(PEP 562). Import from ``cursorfleet.config.models`` / ``.roster`` / ``.io``
for explicit, eager access.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cursorfleet.config.io import loads_config, loads_roster
    from cursorfleet.config.models import FleetConfig
    from cursorfleet.config.roster import AgentSpec, CoordinatorSpec, Roster, default_roster

_LAZY = {
    "FleetConfig": "cursorfleet.config.models",
    "AgentSpec": "cursorfleet.config.roster",
    "CoordinatorSpec": "cursorfleet.config.roster",
    "Roster": "cursorfleet.config.roster",
    "default_roster": "cursorfleet.config.roster",
    "loads_config": "cursorfleet.config.io",
    "loads_roster": "cursorfleet.config.io",
}

__all__ = [
    "AgentSpec",
    "CoordinatorSpec",
    "FleetConfig",
    "Roster",
    "default_roster",
    "loads_config",
    "loads_roster",
]


def __getattr__(name: str) -> Any:
    module = _LAZY.get(name)
    if module is None:
        msg = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(msg)
    return getattr(import_module(module), name)
