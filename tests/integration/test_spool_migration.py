"""A3: legacy spool lines remain readable; verification kinds converge in projection."""

from __future__ import annotations

import json
from pathlib import Path

from cursorfleet.events.models import Event
from cursorfleet.state.indexer import Indexer, replay_session_state
from cursorfleet.state.reducer import canonical_json, reduce_events
from cursorfleet.state.spool import append_event
from m2_helpers import dump, init_repo, make_event, paths_of

NOW_MS = 1_790_000_000_000

FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "cursor" / "legacy_test_completed.jsonl"
)


def test_legacy_test_completed_replays_and_matches_verification_observed(
    tmp_path: Path,
) -> None:
    repo = init_repo(tmp_path / "repo")
    paths = paths_of(repo)
    legacy = json.loads(FIXTURE.read_text(encoding="utf-8").strip())
    append_event(paths, str(legacy["session_id"]), "main", dump(legacy), now_ms=NOW_MS)
    indexer = Indexer(paths)
    assert indexer.sync().events_new == 1

    modern = Event.model_validate(
        make_event(
            "sanitized-session",
            2,
            kind="verification.observed",
            outcome="ok",
            ts="2026-10-04T12:00:00.000Z",
            source="derived",
        )
    ).model_dump(mode="json", exclude_none=True)
    append_event(paths, str(modern["session_id"]), "modern", dump(modern), now_ms=NOW_MS + 1)
    indexer.sync()
    mixed = indexer.load_sessions()

    replayed, _corruption, _files = replay_session_state(paths)
    assert canonical_json(replayed) == canonical_json(mixed)

    legacy_only = reduce_events([Event.model_validate(legacy)])
    modern_only = reduce_events([Event.model_validate(modern)])
    assert legacy_only["sanitized-session"].agents["main"].last_test is not None
    assert modern_only["sanitized-session"].agents["main"].last_test is not None


def test_fixture_is_sanitized_no_paths_outside_workspace() -> None:
    line = FIXTURE.read_text(encoding="utf-8").strip()
    data = json.loads(line)
    blob = json.dumps(data)
    assert "@" not in blob
    assert "/home/" not in blob
    assert "prompt" not in blob.lower()
