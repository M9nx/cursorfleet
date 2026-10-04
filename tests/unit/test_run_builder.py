from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cursorfleet.events.models import Event
from cursorfleet.state.artifact_scan import ArtifactRecord
from cursorfleet.state.reducer import reduce_events, snapshot
from cursorfleet.state.run_builder import build_active_run, pick_primary_task
from m2_helpers import make_event

T0 = datetime(2026, 10, 4, 12, 0, 0, tzinfo=UTC)


def _ev(n: int, **extra: object) -> Event:
    return Event.model_validate(make_event("s1", n, ts=f"2026-10-04T12:{n:02d}:00.000Z", **extra))


def test_pick_primary_task_from_newest_record() -> None:
    records = [
        ArtifactRecord(
            path="t1/a.md",
            task="t1",
            kind="plan.created",
            author_role="architect",
            created=T0,
        ),
        ArtifactRecord(
            path="t2/b.md",
            task="t2",
            kind="handoff.created",
            author_role="implementer",
            created=T0 + timedelta(days=1),
        ),
    ]
    assert pick_primary_task(records, now=T0) == "t2"


def test_build_active_run_two_reviewer_instances() -> None:
    events = [
        Event.model_validate(
            make_event(
                "s1",
                1,
                kind="subagent.started",
                agent_role="reviewer",
                attribution="exact",
                ts="2026-10-04T12:01:00.000Z",
            )
        ),
        Event.model_validate(
            make_event(
                "s2",
                2,
                kind="subagent.started",
                agent_role="reviewer",
                attribution="exact",
                ts="2026-10-04T12:02:00.000Z",
            )
        ),
    ]
    sessions = reduce_events(events)
    fleet = snapshot(sessions, now=T0 + timedelta(minutes=5))
    session_views = {s.session_id: s for s in fleet.sessions}
    records = [
        ArtifactRecord(
            path="cf/x.md",
            task="cf-smoke",
            kind="handoff.created",
            author_role="reviewer",
            created=T0,
        )
    ]
    run = build_active_run(
        task_slug="cf-smoke",
        run_id="run-test",
        sessions=sessions,
        session_views=session_views,
        records=records,
        linked_session_ids=frozenset({"s1", "s2"}),
        now=T0 + timedelta(minutes=5),
    )
    reviewer = next(g for g in run.groups if g.role == "reviewer")
    assert len(reviewer.instances) == 2
