"""Queryable event rows inside the SQLite projection (read side for the timeline).

The reducer folds events into per-session accumulators and throws the events away; the
timeline needs the events themselves. The indexer therefore also stores each accepted
(already sanitized) event as one row, keyed ``(session_id, event_id)``. Rows are derived
data: they are rebuilt with the rest of the projection and pruned with their session.

Only fields of the closed :class:`~cursorfleet.events.models.Event` model are stored (the
JSON body is ``Event.model_dump_json()``), so nothing here can hold a prompt, a file's
contents or command output. Reads open the database read-only and never raise: a missing
or damaged table yields an empty page with ``error`` set.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from cursorfleet.events.models import Event
from cursorfleet.state.models import utc

EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS events (
    session_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,
    source TEXT NOT NULL,
    attribution TEXT NOT NULL,
    risk TEXT NOT NULL,
    agent TEXT NOT NULL,
    paths TEXT NOT NULL,
    search TEXT NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY (session_id, event_id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS events_by_ts ON events(ts DESC, event_id DESC);
"""

DEFAULT_PAGE = 200
MAX_PAGE = 5000


def ts_key(value: datetime) -> str:
    """Fixed-width UTC text so string order equals time order."""
    return utc(value).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _search_text(event: Event) -> str:
    parts: list[str] = [event.kind.value, event.agent_id or "", event.tool_name or ""]
    if event.command is not None:
        command = event.command
        parts.extend([command.argv0, command.subcommand or "", command.display or ""])
    parts.extend([event.issue_ref or "", event.branch or "", event.session_id])
    return "\n".join(parts).lower()


def insert_events(conn: sqlite3.Connection, events: Iterable[Event]) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO events(session_id, event_id, ts, kind, source, attribution,"
        " risk, agent, paths, search, body) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                e.session_id,
                e.event_id,
                ts_key(e.ts),
                e.kind.value,
                e.source.value,
                e.attribution.value,
                e.risk.value,
                (e.agent_id or "").lower(),
                "\n".join(p.path for p in e.paths).lower(),
                _search_text(e),
                e.model_dump_json(),
            )
            for e in events
        ],
    )


def delete_session_events(conn: sqlite3.Connection, session_id: str) -> None:
    conn.execute("DELETE FROM events WHERE session_id=?", (session_id,))


@dataclass(frozen=True)
class EventFilter:
    """All fields optional; every given field must match (AND)."""

    agent: str | None = None  # substring of the agent id (role#instance)
    session: str | None = None  # substring of the session id
    kind: str | None = None  # exact kind, or a prefix such as ``tool``
    risk: str | None = None
    source: str | None = None
    attribution: str | None = None
    file: str | None = None  # substring of a stored (workspace-relative) path
    text: str | None = None  # substring over kind, agent, tool, command display, refs
    since: datetime | None = None
    until: datetime | None = None

    @property
    def active(self) -> bool:
        return any(v is not None for v in self.__dict__.values())


def _like(value: str) -> str:
    escaped = value.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _where(flt: EventFilter) -> tuple[str, list[str]]:
    clauses: list[str] = []
    args: list[str] = []
    if flt.agent:
        clauses.append("agent LIKE ? ESCAPE '\\'")
        args.append(_like(flt.agent))
    if flt.session:
        clauses.append("session_id LIKE ? ESCAPE '\\'")
        args.append(_like(flt.session))
    if flt.kind:
        clauses.append("(kind = ? OR kind LIKE ? ESCAPE '\\')")
        args.extend([flt.kind.lower(), _like(flt.kind.lower() + ".")[1:]])
    exact = (("risk", flt.risk), ("source", flt.source), ("attribution", flt.attribution))
    for column, value in exact:
        if value:
            clauses.append(f"{column} = ?")
            args.append(value.lower())
    if flt.file:
        clauses.append("paths LIKE ? ESCAPE '\\'")
        args.append(_like(flt.file))
    for word in (flt.text or "").split():
        clauses.append("search LIKE ? ESCAPE '\\'")
        args.append(_like(word))
    if flt.since is not None:
        clauses.append("ts >= ?")
        args.append(ts_key(flt.since))
    if flt.until is not None:
        clauses.append("ts <= ?")
        args.append(ts_key(flt.until))
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", args


def matches_filter(event: Event, flt: EventFilter) -> bool:
    """In-memory twin of the SQL filter (for events that are not in the database)."""
    agent = (event.agent_id or "").lower()
    paths = "\n".join(p.path for p in event.paths).lower()
    kind = event.kind.value
    checks = (
        not flt.agent or flt.agent.lower() in agent,
        not flt.session or flt.session.lower() in event.session_id.lower(),
        not flt.kind or kind == flt.kind.lower() or kind.startswith(flt.kind.lower() + "."),
        not flt.risk or event.risk.value == flt.risk.lower(),
        not flt.source or event.source.value == flt.source.lower(),
        not flt.attribution or event.attribution.value == flt.attribution.lower(),
        not flt.file or flt.file.lower() in paths,
        flt.since is None or ts_key(event.ts) >= ts_key(flt.since),
        flt.until is None or ts_key(event.ts) <= ts_key(flt.until),
    )
    if not all(checks):
        return False
    haystack = _search_text(event)
    return all(word.lower() in haystack for word in (flt.text or "").split())


@dataclass
class EventPage:
    events: list[Event] = field(default_factory=list)
    total: int = 0  # rows matching the filter (not just this page)
    skipped: int = 0  # rows whose body no longer validates
    error: str | None = None


def _open_readonly(db_path: str) -> sqlite3.Connection:
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=5.0)


def query_events(
    db_path: str, flt: EventFilter | None = None, *, limit: int = DEFAULT_PAGE
) -> EventPage:
    """Newest-first page of events matching ``flt``. Never raises."""
    flt = flt or EventFilter()
    limit = max(1, min(limit, MAX_PAGE))
    where, args = _where(flt)
    page = EventPage()
    try:
        conn = _open_readonly(db_path)
    except (sqlite3.Error, OSError, ValueError) as exc:
        page.error = f"events unavailable: {type(exc).__name__}"
        return page
    try:
        page.total = int(
            conn.execute(f"SELECT COUNT(*) FROM events{where}", args).fetchone()[0]  # noqa: S608
        )
        rows = conn.execute(
            f"SELECT body FROM events{where} ORDER BY ts DESC, event_id DESC LIMIT ?",  # noqa: S608
            [*args, limit],
        ).fetchall()
    except sqlite3.Error as exc:
        page.error = f"events unavailable: {type(exc).__name__}"
        return page
    finally:
        conn.close()
    for (body,) in rows:
        try:
            page.events.append(Event.model_validate_json(body))
        except (ValidationError, ValueError):
            page.skipped += 1
    return page


__all__ = [
    "DEFAULT_PAGE",
    "EVENTS_DDL",
    "MAX_PAGE",
    "EventFilter",
    "EventPage",
    "delete_session_events",
    "insert_events",
    "matches_filter",
    "query_events",
    "ts_key",
]
