"""The indexer also stores sanitized events as queryable rows (timeline read side)."""

from __future__ import annotations

import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from cursorfleet.events.ids import fs_name_for
from cursorfleet.state.event_store import EventFilter, query_events
from cursorfleet.state.indexer import Indexer
from cursorfleet.state.runtime import RuntimePaths
from cursorfleet.state.spool import append_event
from m2_helpers import dump, make_event


def write(rt: RuntimePaths, session: str, n: int, **extra: object) -> None:
    event = make_event(session, n, **extra)
    assert append_event(rt, session, "w1", dump(event), now_ms=1_790_000_000_000 + n)


def test_events_are_indexed_and_filterable(tmp_path: Path) -> None:
    paths = RuntimePaths(str(tmp_path / "rt"))
    write(paths, "s1", 1, kind="tool.started", tool_name="Shell", risk="high")
    write(paths, "s1", 2, kind="file.changed", paths=[{"path": "src/a_b.py", "op": "modified"}])
    write(paths, "s2", 3, kind="session.started", agent_role="reviewer", attribution="exact")
    Indexer(paths).sync()
    page = query_events(paths.db)
    assert page.total == 3 and [e.session_id for e in page.events] == ["s2", "s1", "s1"]
    assert query_events(paths.db, EventFilter(kind="tool")).total == 1
    assert query_events(paths.db, EventFilter(kind="tool.started")).total == 1
    assert query_events(paths.db, EventFilter(risk="high")).events[0].tool_name == "Shell"
    assert query_events(paths.db, EventFilter(file="a_b")).total == 1
    assert query_events(paths.db, EventFilter(file="a%b")).total == 0  # LIKE wildcards escaped
    assert query_events(paths.db, EventFilter(agent="REVIEWER")).total == 1
    assert query_events(paths.db, EventFilter(session="s1")).total == 2
    assert query_events(paths.db, EventFilter(text="shell")).total == 1
    since = datetime(2026, 10, 4, 0, 0, 2, tzinfo=UTC)
    assert query_events(paths.db, EventFilter(since=since)).total == 2
    assert query_events(paths.db, EventFilter(until=since)).total == 2
    assert len(query_events(paths.db, limit=1).events) == 1


def test_incremental_and_rebuild_agree(tmp_path: Path) -> None:
    paths = RuntimePaths(str(tmp_path / "rt"))
    write(paths, "s1", 5)
    indexer = Indexer(paths)
    indexer.sync()
    write(paths, "s1", 2)  # sorts before the watermark: forces a session rebuild
    write(paths, "s1", 9)
    indexer.sync()
    incremental = [e.event_id for e in query_events(paths.db).events]
    indexer.sync(rebuild=True)
    assert [e.event_id for e in query_events(paths.db).events] == incremental
    assert len(incremental) == 3


def test_old_projection_without_event_store_is_reindexed(tmp_path: Path) -> None:
    paths = RuntimePaths(str(tmp_path / "rt"))
    write(paths, "s1", 1)
    indexer = Indexer(paths)
    indexer.sync()
    conn = sqlite3.connect(paths.db)
    conn.execute("DELETE FROM meta WHERE key='event_store'")
    conn.execute("DELETE FROM events")
    conn.commit()
    conn.close()
    indexer.sync()
    assert query_events(paths.db).total == 1


def test_missing_or_damaged_database_yields_an_error_page(tmp_path: Path) -> None:
    missing = query_events(str(tmp_path / "nope.sqlite"))
    assert missing.events == [] and missing.error is not None
    damaged = tmp_path / "bad.sqlite"
    damaged.write_bytes(b"this is not sqlite" * 50)
    page = query_events(str(damaged))
    assert page.events == [] and page.error is not None


def test_retention_prune_removes_events(tmp_path: Path) -> None:
    paths = RuntimePaths(str(tmp_path / "rt"))
    write(paths, "s1", 1)
    write(paths, "s2", 2)
    indexer = Indexer(paths)
    indexer.sync()
    shutil.rmtree(Path(paths.spool) / fs_name_for("s1"))
    indexer.sync()
    assert [e.session_id for e in query_events(paths.db).events] == ["s2"]
