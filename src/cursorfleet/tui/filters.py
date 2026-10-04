"""Parsing of the ``/`` filter box.

Timeline syntax: whitespace-separated ``key:value`` terms plus free words, for example
``agent:reviewer kind:tool risk:high file:src/api since:15m shell``. Keys: ``agent``,
``session``, ``kind``, ``risk``, ``source`` (``observed``/``self_reported``/``derived``),
``attribution``, ``file``, ``since``, ``until`` (relative ``90s``/``15m``/``2h``/``1d`` or an
ISO 8601 time; naive times are UTC). Free words must all match. Other views treat the whole
text as a case-insensitive substring filter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from cursorfleet.state.event_store import EventFilter

_RELATIVE = re.compile(r"^(\d{1,6})([smhd])$")
_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
_KEYS = frozenset(
    {"agent", "session", "kind", "risk", "source", "attribution", "file", "since", "until"}
)


@dataclass(frozen=True)
class ParsedFilter:
    event: EventFilter = field(default_factory=EventFilter)
    errors: tuple[str, ...] = ()


def parse_time(text: str, now: datetime) -> datetime | None:
    match = _RELATIVE.match(text.strip().lower())
    if match:
        return now - timedelta(seconds=int(match.group(1)) * _UNITS[match.group(2)])
    try:
        parsed = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def parse_timeline_filter(text: str, now: datetime) -> ParsedFilter:
    values: dict[str, str] = {}
    words: list[str] = []
    errors: list[str] = []
    for token in text.split():
        key, sep, value = token.partition(":")
        if sep and key.lower() in _KEYS and value:
            values[key.lower()] = value
        else:
            words.append(token)
    since = until = None
    if "since" in values:
        since = parse_time(values.pop("since"), now)
        if since is None:
            errors.append("since: expects 15m, 2h, 1d or an ISO time")
    if "until" in values:
        until = parse_time(values.pop("until"), now)
        if until is None:
            errors.append("until: expects 15m, 2h, 1d or an ISO time")
    return ParsedFilter(
        EventFilter(
            agent=values.get("agent"),
            session=values.get("session"),
            kind=values.get("kind"),
            risk=values.get("risk"),
            source=values.get("source"),
            attribution=values.get("attribution"),
            file=values.get("file"),
            text=" ".join(words) or None,
            since=since,
            until=until,
        ),
        tuple(errors),
    )


def matches_text(haystack: str, text: str) -> bool:
    """Case-insensitive: every whitespace-separated word of ``text`` occurs in ``haystack``."""
    lowered = haystack.lower()
    return all(word in lowered for word in text.lower().split())
