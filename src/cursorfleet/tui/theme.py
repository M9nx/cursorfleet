"""Text helpers and styling for the TUI.

Rules enforced here for every screen:

- Untrusted strings (roles, branches, paths, refs) go through :func:`safe` and are placed in
  ``rich.text.Text`` objects, never in markup strings, so ``[bold]``-style content from a
  forged artifact cannot restyle or hide the UI.
- Status is never conveyed by colour alone: every state has a text label and an ASCII
  marker (:data:`LANE_TAG`, :data:`LANE_MARK`). Colour is only an enhancement and is
  replaced by bold/dim/reverse when ``NO_COLOR`` is set (:class:`Theme`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from cursorfleet.state.models import Lane, utc

LANE_ORDER: tuple[str, ...] = (
    Lane.QUEUED.value,
    Lane.LOADING_CONTEXT.value,
    Lane.PLANNING.value,
    Lane.WORKING.value,
    Lane.VERIFYING.value,
    Lane.AWAITING_REVIEW.value,
    Lane.PATCHING.value,
    Lane.BLOCKED.value,
    Lane.DONE.value,
    Lane.STALE_OFFLINE.value,
    Lane.UNKNOWN.value,
)

LANE_TAG: dict[str, str] = {
    "queued": "QUEUED",
    "loading_context": "LOADING CONTEXT",
    "planning": "PLANNING",
    "working": "WORKING",
    "verifying": "VERIFYING",
    "awaiting_review": "AWAITING REVIEW",
    "patching": "PATCHING",
    "blocked": "BLOCKED",
    "done": "DONE",
    "stale_offline": "STALE / OFFLINE",
    "unknown": "UNKNOWN / NO TELEMETRY",
}

LANE_MARK: dict[str, str] = {
    "queued": "[Q]",
    "loading_context": "[C]",
    "planning": "[P]",
    "working": "[W]",
    "verifying": "[V]",
    "awaiting_review": "[R]",
    "patching": "[X]",
    "blocked": "[!]",
    "done": "[D]",
    "stale_offline": "[~]",
    "unknown": "[?]",
}

BASIS_TAG: dict[str, str] = {
    "observed_activity": "observed",
    "lifecycle_only": "lifecycle-only",
    "self_reported": "SELF-REPORTED",
    "derived": "derived",
    "none": "no telemetry",
}

_COLOR: dict[str, str] = {
    "blocked": "bold red",
    "working": "cyan",
    "verifying": "magenta",
    "awaiting_review": "yellow",
    "patching": "blue",
    "done": "green",
    "stale_offline": "dim yellow",
    "unknown": "dim",
}
_MONO: dict[str, str] = {
    "blocked": "bold reverse",
    "working": "bold",
    "verifying": "bold",
    "awaiting_review": "underline",
    "patching": "underline",
    "done": "dim",
    "stale_offline": "dim italic",
    "unknown": "dim",
}

GATE_COLOR = {
    "pass": "green",
    "fail": "bold red",
    "stale": "yellow",
    "unknown": "dim",
    "not_evaluated": "dim",
    "observed": "cyan",
}
GATE_MONO = {
    "pass": "bold",
    "fail": "bold reverse",
    "stale": "underline",
    "unknown": "dim",
    "not_evaluated": "dim",
    "observed": "bold",
}

UNKNOWN_BUDGET = "unknown (not exposed by Cursor hooks)"
SELF_REPORTED_NOTE = "SELF-REPORTED (an agent's claim, not evidence)"


@dataclass(frozen=True)
class Theme:
    """Style lookup; ``mono`` drops every colour (``NO_COLOR`` or ``--no-color``)."""

    mono: bool = False

    def lane(self, lane: str) -> str:
        table = _MONO if self.mono else _COLOR
        return table.get(lane, "")

    def gate(self, state: str) -> str:
        return (GATE_MONO if self.mono else GATE_COLOR).get(state, "")

    @property
    def accent(self) -> str:
        return "bold" if self.mono else "bold cyan"

    @property
    def dim(self) -> str:
        return "dim"


def safe(value: object, limit: int = 160) -> str:
    """Printable, single-line, bounded text for untrusted values."""
    text = "".join(ch if ch.isprintable() else "?" for ch in str(value))
    return text if len(text) <= limit else text[: max(limit - 3, 0)] + "..."


def short_sha(value: str | None, width: int = 8) -> str:
    return value[:width] if value else "-"


def fmt_ts(value: datetime | None) -> str:
    """Compact absolute UTC time; the UI states that all times are UTC."""
    return "-" if value is None else utc(value).strftime("%m-%d %H:%M:%S")


def fmt_age(now: datetime, then: datetime | None) -> str:
    if then is None:
        return "never"
    seconds = int((utc(now) - utc(then)).total_seconds())
    if seconds < 0:
        return "in the future"
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def fmt_duration(seconds: float) -> str:
    total = int(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{secs:02d}s"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def plural(count: int, noun: str) -> str:
    return f"{count} {noun}" + ("" if count == 1 else "s")
