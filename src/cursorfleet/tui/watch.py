"""Optional ``watchfiles`` integration: refresh promptly when the spool changes.

Polling is always on (the default 2 s interval); watching only makes the UI react sooner and
is skipped when ``watchfiles`` is not installed (``pip install cursorfleet[watch]``).
"""

from __future__ import annotations

import importlib
import importlib.util
from collections.abc import AsyncIterator, Callable
from typing import Any, cast

WatchFactory = Callable[[str], AsyncIterator[object]]


def watchfiles_available() -> bool:
    return importlib.util.find_spec("watchfiles") is not None


def default_watch_factory() -> WatchFactory | None:
    """A factory yielding one item per batch of changes under a directory, or ``None``."""
    if not watchfiles_available():
        return None
    awatch: Any = importlib.import_module("watchfiles").awatch

    def factory(path: str) -> AsyncIterator[object]:
        return cast(
            AsyncIterator[object],
            awatch(path, debounce=300, step=100, yield_on_timeout=False, raise_interrupt=False),
        )

    return factory
