from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cursorfleet.state.indexer import Indexer
from cursorfleet.state.retention import apply_plan, parse_duration, plan_purge
from cursorfleet.state.runtime import RuntimePaths, runtime_paths
from cursorfleet.state.spool import CAPPED_MARKER, append_event, session_dir, writer_file
from m2_helpers import dump, make_event

NOW = datetime(2026, 10, 4, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def paths(tmp_path: Path) -> RuntimePaths:
    return runtime_paths(tmp_path / "common" / "cursorfleet")


def put(paths: RuntimePaths, session: str, n: int, *, age_days: float, writer: str = "main") -> str:
    assert append_event(
        paths, session, writer, dump(make_event(session, n)), now_ms=1_790_000_000_000 + n
    )
    file = writer_file(paths, session, writer)
    stamp = (NOW - timedelta(days=age_days)).timestamp()
    os.utime(file, (stamp, stamp))
    return file


@pytest.mark.parametrize(
    ("text", "seconds"),
    [("90s", 90), ("30m", 1800), ("12h", 43200), ("7d", 604800), ("2w", 1209600), (" 7D ", 604800)],
)
def test_parse_duration(text: str, seconds: int) -> None:
    assert parse_duration(text) == timedelta(seconds=seconds)


@pytest.mark.parametrize("bad", ["", "7", "d", "-1d", "1.5d", "7days", "1y", "999999999d"])
def test_parse_duration_rejects(bad: str) -> None:
    with pytest.raises(ValueError, match="invalid duration"):
        parse_duration(bad)


def test_default_retention_removes_only_sessions_older_than_14_days(paths: RuntimePaths) -> None:
    old = put(paths, "old", 1, age_days=15)
    recent = put(paths, "recent", 2, age_days=13)
    plan = plan_purge(paths, now=NOW)
    assert plan.sessions == 1 and plan.files == [old]
    report = apply_plan(paths, plan)
    assert report.files == 1 and report.errors == [] and report.needs_reindex
    assert not os.path.exists(old) and os.path.exists(recent)
    assert not os.path.isdir(session_dir(paths, "old"))


def test_older_than_overrides_the_age_and_ignores_the_size_cap(paths: RuntimePaths) -> None:
    put(paths, "a", 1, age_days=2)
    put(paths, "b", 2, age_days=0.1)
    plan = plan_purge(paths, now=NOW, older_than=timedelta(days=1))
    assert [os.path.basename(os.path.dirname(f)) for f in plan.files] == ["a"]


def test_size_cap_drops_oldest_segments_first(paths: RuntimePaths) -> None:
    sdir = session_dir(paths, "big")
    for n in range(6):
        append_event(
            paths,
            "big",
            "main",
            dump(make_event("big", n)),
            now_ms=1_790_000_000_000 + n,
            rotate_bytes=10,
        )
    files = sorted(os.listdir(sdir))
    assert len(files) > 3
    for index, name in enumerate(files):
        stamp = (NOW - timedelta(hours=10 - index)).timestamp()
        os.utime(os.path.join(sdir, name), (stamp, stamp))
    total = sum(os.path.getsize(os.path.join(sdir, f)) for f in files)
    # cap = 1 MB is not reachable here, so emulate a tiny cap through the planner's units
    plan = plan_purge(paths, now=NOW, max_session_mb=0)
    assert plan.partial_sessions == 1 and plan.file_bytes <= total
    oldest_first = [
        os.path.join(sdir, f)
        for f in sorted(files, key=lambda f: os.path.getmtime(os.path.join(sdir, f)))
    ]
    assert plan.files == oldest_first[: len(plan.files)]


def test_capped_marker_is_cleared_when_space_returns(paths: RuntimePaths) -> None:
    put(paths, "s1", 1, age_days=1)
    marker = os.path.join(session_dir(paths, "s1"), CAPPED_MARKER)
    Path(marker).write_text("", encoding="utf-8")
    plan = plan_purge(paths, now=NOW)
    assert plan.clear_markers == [marker]
    apply_plan(paths, plan)
    assert not os.path.exists(marker)


def test_session_selector(paths: RuntimePaths) -> None:
    put(paths, "keep", 1, age_days=0)
    put(paths, "drop", 2, age_days=0)
    report = apply_plan(paths, plan_purge(paths, now=NOW, session="drop"))
    assert report.sessions == 1
    assert os.path.isdir(session_dir(paths, "keep")) and not os.path.isdir(
        session_dir(paths, "drop")
    )


def test_everything_removes_spool_projection_quarantine_and_rotates_the_key(
    paths: RuntimePaths,
) -> None:
    put(paths, "s1", 1, age_days=0)
    Indexer(paths).sync()
    Path(paths.hmac_key).write_bytes(b"k" * 32)
    os.makedirs(paths.quarantine, exist_ok=True)
    plan = plan_purge(paths, now=NOW, everything=True)
    assert plan.remove_projection and plan.rotate_key and plan.remove_quarantine
    report = apply_plan(paths, plan)
    assert report.projection_removed and report.key_rotated
    assert not os.path.exists(paths.hmac_key) and not os.path.exists(paths.index_dir)
    assert not os.path.exists(paths.quarantine)
    assert os.listdir(paths.spool) == []
    assert os.path.exists(paths.layout)  # the root itself stays


def test_dry_plan_changes_nothing(paths: RuntimePaths) -> None:
    file = put(paths, "old", 1, age_days=30)
    plan_purge(paths, now=NOW)
    assert os.path.exists(file)


def test_nothing_to_do_gives_an_empty_plan(paths: RuntimePaths) -> None:
    assert plan_purge(paths, now=NOW).empty
    put(paths, "fresh", 1, age_days=0)
    assert plan_purge(paths, now=NOW).empty


def test_apply_refuses_paths_outside_the_runtime_dir(paths: RuntimePaths, tmp_path: Path) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_text("precious", encoding="utf-8")
    plan = plan_purge(paths, now=NOW)
    plan.files.append(str(victim))
    report = apply_plan(paths, plan)
    assert victim.read_text(encoding="utf-8") == "precious"
    assert report.errors


def test_purged_sessions_disappear_from_the_projection(paths: RuntimePaths) -> None:
    put(paths, "old", 1, age_days=30)
    put(paths, "new", 2, age_days=0)
    indexer = Indexer(paths)
    indexer.sync()
    apply_plan(paths, plan_purge(paths, now=NOW))
    indexer.sync()
    assert set(indexer.load_sessions()) == {"new"}
