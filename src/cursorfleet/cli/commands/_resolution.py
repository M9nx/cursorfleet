"""Shared doctor/validate repository-resolution renderers (ADR 0009 task 15).

The facts come from ``inspect_repository`` (the Task 16 file-walk). This module
does not walk, does not write, and keeps JSON and plain text on the same mapping.
"""

from __future__ import annotations

from pathlib import Path

from cursorfleet.adapters.cursor.fsutil import safe_text
from cursorfleet.state.runtime import Resolution, inspect_repository

RESOLUTION_KEYS = (
    "input_path",
    "resolved_path",
    "repository_root",
    "common_dir",
    "marker_path",
    "marker_present",
    "marker_valid",
    "boundary",
    "status",
    "reason",
)


def build_resolution(path: Path, workspace_roots: object = None) -> Resolution:
    """Read-only classification of ``path``. Never creates files or directories."""
    try:
        start = str(path.expanduser())
    except OSError:
        start = str(path)
    return inspect_repository(start, workspace_roots)


def resolution_as_dict(resolution: Resolution) -> dict[str, object]:
    """Stable JSON object. ``render_resolution_text`` prints these same values."""
    return resolution.as_dict()


def _shown(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return safe_text(str(value))


def render_resolution_text(resolution: Resolution) -> str:
    """Plain-text block with the same facts as :func:`resolution_as_dict`."""
    data = resolution.as_dict()
    lines = ["Repository resolution:"]
    for key in RESOLUTION_KEYS:
        lines.append(f"  {key}: {_shown(data[key])}")
    return "\n".join(lines)
