from __future__ import annotations

import os
import sqlite3
import stat
import subprocess
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from cursorfleet.events.models import Event
from cursorfleet.state.indexer import DB_SCHEMA_VERSION, Indexer, replay_session_state
from cursorfleet.state.lock import IndexerBusy, IndexerLock
from cursorfleet.state.reducer import canonical_json, reduce_events, snapshot
from cursorfleet.state.runtime import RuntimePaths, runtime_paths
from cursorfleet.state.spool import append_event, encode_line, writer_file
from m2_helpers import dump, make_event
from m2_strategies import PROFILE, T0, event_lists

NOW_MS = 1_790_000_000_000


@pytest.fixture
def paths(tmp_path: Path) -> RuntimePaths:
    return runtime_paths(tmp_path / "common" / "cursorfleet")


def put(paths: RuntimePaths, event: Event | dict[str, object], writer: str = "main") -> None:
    data = event.model_dump(mode="json", exclude_none=True) if isinstance(event, Event) else event
    session = str(data["session_id"])
    assert append_event(paths, session, writer, dump(data), now_ms=NOW_MS)  # type: ignore[arg-type]


def ev(n: int, sec: int, kind: str = "tool.started", session: str = "s1", **extra: object) -> dict:
    ts = (T0 + timedelta(seconds=sec)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return make_event(session, n, kind=kind, ts=ts, **extra)


def canon(paths: RuntimePaths) -> str:
    return canonical_json(Indexer(paths).load_sessions())


def test_sync_indexes_and_is_incremental(paths: RuntimePaths) -> None:
    put(paths, ev(1, 1, "session.started"))
    put(paths, ev(2, 2, tool_name="Write"))
    indexer = Indexer(paths)
    first = indexer.sync()
    assert (first.events_new, first.sessions_updated) == (2, 1)
    assert indexer.sync().events_new == 0  # nothing new
    put(paths, ev(3, 3, tool_name="Read"))
    second = indexer.sync()
    assert (second.events_read, second.events_new, second.sessions_rebuilt) == (1, 1, 0)
    assert indexer.load_sessions()["s1"].events == 3


def test_duplicate_event_ids_are_ignored_across_files_and_runs(paths: RuntimePaths) -> None:
    event = ev(1, 1, tool_name="Write")
    put(paths, event, writer="a")
    put(paths, event, writer="b")  # same event written by two writers
    indexer = Indexer(paths)
    assert indexer.sync().events_new == 1
    put(paths, event, writer="c")
    assert indexer.sync().events_new == 0
    assert indexer.load_sessions()["s1"].events == 1


def test_late_event_triggers_rebuild_and_matches_replay(paths: RuntimePaths) -> None:
    put(paths, ev(1, 10, tool_name="Write"))
    indexer = Indexer(paths)
    indexer.sync()
    put(paths, ev(2, 1, "session.started"), writer="sub")  # older timestamp arrives later
    stats = indexer.sync()
    assert stats.sessions_rebuilt == 1
    replayed, _c, _f = replay_session_state(paths)
    assert canonical_json(indexer.load_sessions()) == canonical_json(replayed)


def test_torn_tail_is_picked_up_after_completion(paths: RuntimePaths) -> None:
    put(paths, ev(1, 1, "session.started"))
    file = writer_file(paths, "s1", "main")
    line = encode_line(dump(ev(2, 2, tool_name="Write")))
    with open(file, "ab") as handle:
        handle.write(line[:25])
    indexer = Indexer(paths)
    assert indexer.sync().events_new == 1
    with open(file, "ab") as handle:
        handle.write(line[25:])
    assert indexer.sync().events_new == 1
    assert indexer.corruption().total == 0


def test_corrupt_lines_are_counted_and_do_not_stop_indexing(paths: RuntimePaths) -> None:
    put(paths, ev(1, 1, "session.started"))
    file = writer_file(paths, "s1", "main")
    with open(file, "ab") as handle:
        handle.write(b"garbage line\n")
    put(paths, ev(2, 2, tool_name="Write"))
    indexer = Indexer(paths)
    stats = indexer.sync()
    assert stats.events_new == 2 and stats.corruption.bad_format == 1
    assert indexer.corruption().bad_format == 1
    indexer.sync()
    assert indexer.corruption().bad_format == 1  # not double counted on re-scan


def test_rotation_is_handled_without_rereading(paths: RuntimePaths) -> None:
    indexer = Indexer(paths)
    for n in range(5):
        append_event(paths, "s1", "main", dump(ev(n, n)), now_ms=NOW_MS + n, rotate_bytes=10**9)
    indexer.sync()
    for n in range(5, 10):  # rotate on every append from here on
        append_event(paths, "s1", "main", dump(ev(n, n)), now_ms=NOW_MS + n, rotate_bytes=200)
    stats = indexer.sync()
    assert stats.events_new == 5
    assert indexer.load_sessions()["s1"].events == 10
    replayed, _c, _f = replay_session_state(paths)
    assert canonical_json(indexer.load_sessions()) == canonical_json(replayed)


def test_misplaced_events_are_rejected_and_counted(paths: RuntimePaths) -> None:
    put(paths, ev(1, 1, session="attacker"))
    # Forge: copy the attacker's file contents under a victim's session claim.
    forged = encode_line(dump(ev(2, 2, session="victim")))
    file = writer_file(paths, "attacker", "other")
    with open(file, "wb") as handle:
        handle.write(forged)
    indexer = Indexer(paths)
    stats = indexer.sync()
    assert "victim" not in indexer.load_sessions()
    assert stats.corruption.misplaced == 1


def test_rebuild_recreates_identical_state(paths: RuntimePaths) -> None:
    for n in range(6):
        put(paths, ev(n, n, tool_name="Write", session=f"s{n % 2}"))
    indexer = Indexer(paths)
    indexer.sync()
    before = canonical_json(indexer.load_sessions())
    indexer.sync(rebuild=True)
    assert canonical_json(indexer.load_sessions()) == before


def test_corrupt_database_is_quarantined_and_rebuilt(paths: RuntimePaths) -> None:
    put(paths, ev(1, 1, "session.started"))
    indexer = Indexer(paths)
    indexer.sync()
    expected = canonical_json(indexer.load_sessions())
    Path(paths.db).write_bytes(b"this is not a sqlite database" * 100)
    Path(paths.db + "-wal").unlink(missing_ok=True)
    stats = Indexer(paths).sync()
    assert stats.db_recovered
    assert canon(paths) == expected
    assert len(os.listdir(paths.quarantine)) >= 1


def test_wrong_schema_version_is_quarantined(paths: RuntimePaths) -> None:
    put(paths, ev(1, 1, "session.started"))
    Indexer(paths).sync()
    conn = sqlite3.connect(paths.db)
    conn.execute("PRAGMA user_version=99")
    conn.close()
    stats = Indexer(paths).sync()
    assert stats.db_recovered and stats.events_new == 1


def test_schema_version_is_stamped_and_wal_enabled(paths: RuntimePaths) -> None:
    put(paths, ev(1, 1, "session.started"))
    Indexer(paths).sync()
    conn = sqlite3.connect(paths.db)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == DB_SCHEMA_VERSION
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        conn.close()


def test_database_file_is_private(paths: RuntimePaths) -> None:
    if os.name != "posix":
        pytest.skip("POSIX permission bits")
    put(paths, ev(1, 1, "session.started"))
    Indexer(paths).sync()
    assert stat.S_IMODE(os.stat(paths.db).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(paths.index_dir).st_mode) == 0o700


def test_second_indexer_is_refused_while_one_runs(paths: RuntimePaths) -> None:
    put(paths, ev(1, 1, "session.started"))
    os.makedirs(os.path.dirname(paths.indexer_lock), exist_ok=True)
    with IndexerLock(paths.indexer_lock):
        with pytest.raises(IndexerBusy):
            Indexer(paths).sync()
        assert Indexer(paths).try_sync() is None
    assert Indexer(paths).try_sync() is not None


def test_pruned_spool_removes_the_projection_rows(paths: RuntimePaths) -> None:
    put(paths, ev(1, 1, "session.started"))
    put(paths, ev(2, 1, "session.started", session="s2"))
    indexer = Indexer(paths)
    indexer.sync()
    for name in os.listdir(os.path.join(paths.spool, "s2")):
        os.remove(os.path.join(paths.spool, "s2", name))
    os.rmdir(os.path.join(paths.spool, "s2"))
    stats = indexer.sync()
    assert stats.sessions_pruned == 1 and set(indexer.load_sessions()) == {"s1"}


def test_load_without_a_database_is_empty(paths: RuntimePaths) -> None:
    assert Indexer(paths).load_sessions() == {}
    assert Indexer(paths).corruption().total == 0


def test_hooks_do_not_import_sqlite() -> None:
    code = (
        "import sys; import cursorfleet.adapters.cursor.hook_main; print('sqlite3' in sys.modules)"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60, check=True
    )
    assert out.stdout.strip() == "False"


# ------------------------------------------------------------ Hypothesis: incremental == replay


@settings(PROFILE, max_examples=30)
@given(events=event_lists, cuts=st.lists(st.integers(0, 40), max_size=4), data=st.data())
def test_incremental_indexing_equals_full_replay(
    events: list[Event], cuts: list[int], data: st.DataObject
) -> None:
    order = data.draw(st.permutations(events))  # arrival order is arbitrary
    bounds = sorted({min(c, len(order)) for c in cuts} | {len(order)})
    with tempfile.TemporaryDirectory() as tmp:
        paths = runtime_paths(Path(tmp) / "cursorfleet")
        indexer = Indexer(paths)
        start = 0
        for index, end in enumerate(bounds):
            for event in order[start:end]:
                put(paths, event, writer=f"w{index % 2}")
            start = end
            indexer.sync()
        incremental = canonical_json(indexer.load_sessions())
        expected = canonical_json(reduce_events(events))
        assert incremental == expected
        indexer.sync()  # idempotent
        assert canonical_json(indexer.load_sessions()) == expected
        indexer.sync(rebuild=True)
        assert canonical_json(indexer.load_sessions()) == expected
        fleet_a = snapshot(indexer.load_sessions(), now=T0 + timedelta(hours=1))
        fleet_b = snapshot(reduce_events(events), now=T0 + timedelta(hours=1))
        assert canonical_json(fleet_a) == canonical_json(fleet_b)
