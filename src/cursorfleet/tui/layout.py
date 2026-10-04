"""Responsive layout rules (docs/tui.md).

- below 100 columns: ONE pane (the list, or the detail after Enter);
- 100-159 columns: list + detail side by side;
- 160+ columns: list + detail, or an optional 2x2 tile grid (``t``).

Four panes are never placed side by side: tiles form a 2x2 grid, so each pane keeps at
least ~80 columns.
"""

from __future__ import annotations

SINGLE_BELOW = 100
TILE_FROM = 160

SINGLE = "single"
SPLIT = "split"
TILED = "tiled"


def layout_for(width: int, tile_enabled: bool) -> str:
    if width < SINGLE_BELOW:
        return SINGLE
    if width >= TILE_FROM and tile_enabled:
        return TILED
    return SPLIT
