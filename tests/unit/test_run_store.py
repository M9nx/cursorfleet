from __future__ import annotations

from cursorfleet.state.run_store import RunRecord, attach_session, list_runs, load_run, save_run


def test_run_round_trip(tmp_path) -> None:
    root = str(tmp_path)
    record = RunRecord(run_id="run-abc", task_slug="my-task", created_at="2026-10-05T00:00:00Z")
    save_run(root, record)
    loaded = load_run(root, "run-abc")
    assert loaded is not None and loaded.task_slug == "my-task"
    assert len(list_runs(root)) == 1
    assert attach_session(root, "run-abc", "session-1")
    assert "session-1" in load_run(root, "run-abc").session_ids  # type: ignore[union-attr]
