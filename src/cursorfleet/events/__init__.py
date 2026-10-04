"""Normalized event model for CursorFleet.

Importing this package is cheap and stdlib-only. Pydantic models live in
``cursorfleet.events.models`` and are re-exported lazily (PEP 562) so the hook
hot path can import ``cursorfleet.events.kinds``/``ids``/``forbidden`` without
pulling in pydantic.
"""

from __future__ import annotations

from importlib import import_module

TYPE_CHECKING = False  # not ``typing.TYPE_CHECKING``: importing typing costs ~2 ms per hook
if TYPE_CHECKING:
    from cursorfleet.events.models import (
        Event,
        GateRef,
        Metrics,
        SanitizedCommand,
        SanitizedPath,
    )

_LAZY = {
    "Event": "cursorfleet.events.models",
    "GateRef": "cursorfleet.events.models",
    "Metrics": "cursorfleet.events.models",
    "SanitizedCommand": "cursorfleet.events.models",
    "SanitizedPath": "cursorfleet.events.models",
}

__all__ = ["Event", "GateRef", "Metrics", "SanitizedCommand", "SanitizedPath"]


def __getattr__(name: str) -> object:
    module = _LAZY.get(name)
    if module is None:
        msg = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(msg)
    return getattr(import_module(module), name)
