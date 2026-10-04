from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cursorfleet.events.models import Event
from cursorfleet.state.models import BUDGET_UNKNOWN, Lane
from cursorfleet.state.reducer import (
    DEFAULT_STALE_AFTER_S,
    apply_event,
    canonical_json,
    dedupe_and_sort,
    digest,
    reduce_events,
    snapshot,
    sort_key,
)
from m2_strategies import PROFILE, T0, ev, event_lists


def shell(command: str, argv0: str, sub: str | None = None) -> dict[str, Any]:
    cmd: dict[str, Any] = {"argv0": argv0, "display": command}
    if sub:
        cmd["subcommand"] = sub
    return {"tool_name": "Shell", "command": cmd}


def main_lane(events: list[Event], now_s: int = 10, session: str = "s1") -> str:
    fleet = snapshot(reduce_events(events), now=T0 + timedelta(seconds=now_s))
    view = next(s for s in fleet.sessions if s.session_id == session)
    return next(a.lane for a in view.agents if a.key == "main")


# ------------------------------------------------------------------ lanes


def test_lane_progression() -> None:
    steps: list[tuple[Event, str]] = [
        (ev(1, 1, "session.started"), "queued"),
        (ev(2, 2, "tool.started", tool_name="Read"), "loading_context"),
        (ev(3, 3, "tool.started", tool_name="TodoWrite"), "planning"),
        (ev(4, 4, "tool.started", tool_name="Write"), "working"),
        (ev(5, 5, "tool.started", **shell("pytest -q", "pytest")), "verifying"),
        (ev(6, 6, "status.changed", status="waiting"), "awaiting_review"),
        (ev(7, 7, "file.changed", paths=[{"path": "a.py", "op": "modified"}]), "patching"),
        (ev(8, 8, "status.changed", status="blocked", source="self_reported"), "blocked"),
        (ev(9, 9, "tool.started", tool_name="Write"), "patching"),
        (ev(10, 10, "session.stopped"), "done"),
    ]
    seen: list[Event] = []
    for event, expected in steps:
        seen.append(event)
        assert main_lane(seen, now_s=event.ts.second) == expected, event.kind


def test_all_documented_lanes_are_reachable_and_named() -> None:
    names = {lane.value for lane in Lane}
    assert names == {
        "queued",
        "loading_context",
        "planning",
        "working",
        "verifying",
        "awaiting_review",
        "patching",
        "blocked",
        "done",
        "stale_offline",
        "unknown",
    }


def test_failed_tool_counts_but_does_not_block() -> None:
    events = [
        ev(1, 1, "tool.started", tool_name="Write"),
        ev(2, 2, "tool.failed", tool_name="Write", outcome="failed"),
    ]
    fleet = snapshot(reduce_events(events), now=T0 + timedelta(seconds=3))
    agent = fleet.sessions[0].agents[0]
    assert agent.tool_failures == 1 and agent.lane == "working"


def test_test_completed_sets_last_test() -> None:
    events = [ev(1, 1, "test.completed", outcome="failed", source="derived")]
    agent = snapshot(reduce_events(events), now=T0 + timedelta(seconds=2)).sessions[0].agents[0]
    assert agent.lane == "verifying" and agent.last_test is not None
    assert agent.last_test.outcome == "failed" and agent.lane_basis == "derived"


# ------------------------------------------------------------------ staleness


def test_stale_is_computed_from_injected_clock_and_keeps_last_lane() -> None:
    events = [ev(1, 0, "tool.started", tool_name="Write")]
    state = reduce_events(events)
    fresh = snapshot(state, now=T0 + timedelta(seconds=DEFAULT_STALE_AFTER_S))
    stale = snapshot(state, now=T0 + timedelta(seconds=DEFAULT_STALE_AFTER_S + 1))
    assert fresh.sessions[0].agents[0].lane == "working"
    agent = stale.sessions[0].agents[0]
    assert (agent.lane, agent.stale, agent.last_lane) == ("stale_offline", True, "working")


def test_stale_threshold_is_configurable() -> None:
    state = reduce_events([ev(1, 0, "tool.started", tool_name="Write")])
    quick = snapshot(state, now=T0 + timedelta(seconds=61), stale_after_s=60)
    assert quick.sessions[0].agents[0].lane == "stale_offline"


def test_silence_is_never_idle() -> None:
    state = reduce_events([ev(1, 0, "session.started")])
    for later in (5, 10_000, 10**7):
        lane = snapshot(state, now=T0 + timedelta(seconds=later)).sessions[0].agents[0].lane
        assert lane in {"queued", "stale_offline"}
        assert lane != "idle"


def test_done_is_not_stale() -> None:
    state = reduce_events([ev(1, 0, "session.started"), ev(2, 1, "session.stopped")])
    view = snapshot(state, now=T0 + timedelta(days=30)).sessions[0]
    assert view.lane == "done" and not view.agents[0].stale


def test_self_reported_status_does_not_keep_an_agent_alive() -> None:
    events = [
        ev(1, 0, "tool.started", tool_name="Write"),
        ev(2, 2000, "status.changed", status="working", source="self_reported"),
    ]
    agent = snapshot(reduce_events(events), now=T0 + timedelta(seconds=2001)).sessions[0].agents[0]
    assert agent.lane == "stale_offline"  # only observed telemetry proves liveness


def test_no_telemetry_means_no_sessions_not_idle() -> None:
    fleet = snapshot({}, now=T0)
    assert fleet.sessions == [] and fleet.tasks == []


# ------------------------------------------------------------------ subagents


def sub_start(n: int, sec: int, role: str, inst: str) -> Event:
    return ev(
        n,
        sec,
        "subagent.started",
        agent_role=role,
        agent_instance_id=inst,
        attribution="exact",
        tool_use_id=f"tc{n}",
    )


def sub_stop(n: int, sec: int, role: str, duration_ms: int | None = None) -> Event:
    extra: dict[str, Any] = {"metrics": {"duration_ms": duration_ms}} if duration_ms else {}
    return ev(
        n, sec, "subagent.stopped", agent_role=role, attribution="inferred", outcome="ok", **extra
    )


def test_running_subagent_is_lifecycle_only_and_borrows_session_liveness() -> None:
    events = [
        ev(1, 0, "session.started"),
        sub_start(2, 1, "reviewer", "a1"),
        ev(3, 500, "tool.started", tool_name="Read"),
    ]
    state = reduce_events(events)
    view = snapshot(state, now=T0 + timedelta(seconds=600)).sessions[0]
    sub = next(a for a in view.agents if a.role == "reviewer")
    assert sub.lifecycle == "running" and sub.lifecycle_only
    assert sub.lane_basis == "lifecycle_only" and sub.attribution == "exact"
    assert sub.lane == "working" and not sub.stale  # session was active 100 s ago
    later = snapshot(state, now=T0 + timedelta(seconds=5000)).sessions[0]
    assert next(a for a in later.agents if a.role == "reviewer").lane == "stale_offline"


def test_stop_pairs_by_role_and_duration() -> None:
    events = [
        sub_start(1, 0, "reviewer", "early"),
        sub_start(2, 100, "reviewer", "late"),
        sub_start(3, 50, "tester", "other"),
        sub_stop(4, 160, "reviewer", duration_ms=55_000),  # started ~105 s => "late"
    ]
    session = reduce_events(events)["s1"]
    assert session.agents["reviewer#late"].lifecycle == "stopped"
    assert session.agents["reviewer#early"].lifecycle == "running"
    assert session.agents["tester#other"].lifecycle == "running"
    assert session.unpaired_stops == 0
    stopped = session.agents["reviewer#late"]
    assert stopped.stop_report is not None and stopped.stop_report.duration_ms == 55_000


def test_stop_without_duration_pairs_with_earliest_open_start() -> None:
    events = [
        sub_start(1, 0, "reviewer", "a"),
        sub_start(2, 5, "reviewer", "b"),
        sub_stop(3, 9, "reviewer"),
    ]
    session = reduce_events(events)["s1"]
    assert session.agents["reviewer#a"].lifecycle == "stopped"
    assert session.agents["reviewer#b"].lifecycle == "running"


def test_unpaired_stop_is_counted_not_dropped() -> None:
    session = reduce_events([sub_stop(1, 3, "ghost")])["s1"]
    assert session.unpaired_stops == 1 and "ghost" in session.agents


def test_failed_subagent_is_blocked() -> None:
    events = [
        sub_start(1, 0, "reviewer", "a"),
        ev(
            2,
            4,
            "subagent.stopped",
            agent_role="reviewer",
            attribution="inferred",
            outcome="failed",
        ),
    ]
    agent = next(
        a for a in snapshot(reduce_events(events), now=T0 + timedelta(seconds=5)).sessions[0].agents
    )
    assert agent.lane == "blocked"


def test_unattributed_events_stay_on_main_even_with_a_running_subagent() -> None:
    events = [sub_start(1, 0, "reviewer", "a"), ev(2, 1, "tool.started", tool_name="Write")]
    session = reduce_events(events)["s1"]
    assert session.agents["main"].pre_calls == 1
    assert session.agents["reviewer#a"].pre_calls == 0


# ------------------------------------------------------------------ counters


def test_shell_hooks_are_not_double_counted() -> None:
    both = [
        ev(1, 1, "tool.started", hook="preToolUse", **shell("ls", "ls")),
        ev(2, 1, "tool.started", hook="beforeShellExecution", **shell("ls", "ls")),
    ]
    only_shell_hook = [ev(3, 2, "tool.started", hook="beforeShellExecution", **shell("ls", "ls"))]
    pre_only = [ev(4, 3, "tool.started", hook="preToolUse", tool_name="Read")]

    def count(events: list[Event]) -> int:
        fleet = snapshot(reduce_events(events), now=T0 + timedelta(seconds=9))
        return fleet.sessions[0].tool_call_count

    assert count(both) == 1
    assert count(only_shell_hook) == 1
    assert count(pre_only) == 1
    # once any preToolUse Shell call exists, beforeShellExecution events are ignored
    assert count(both + only_shell_hook + pre_only) == 2


def test_compactions_and_files_are_tracked() -> None:
    events = [
        ev(1, 1, "context.compacted", metrics={"context_usage_percent": 85.0}),
        ev(2, 2, "file.changed", paths=[{"path": "a.py", "op": "modified"}]),
        ev(3, 3, "file.changed", paths=[{"path": "a.py", "op": "modified"}, {"path": "b.py"}]),
    ]
    session = snapshot(reduce_events(events), now=T0 + timedelta(seconds=4)).sessions[0]
    agent = session.agents[0]
    assert session.compactions == 1 and agent.files_changed == 2
    assert agent.last_context_usage_percent == 85.0


def test_token_budget_is_reported_unknown_everywhere() -> None:
    fleet = snapshot(reduce_events([ev(1, 1, "session.started")]), now=T0 + timedelta(seconds=2))
    assert fleet.sessions[0].token_budget == BUDGET_UNKNOWN
    assert all(a.token_budget == BUDGET_UNKNOWN for a in fleet.sessions[0].agents)


def test_tasks_group_by_issue_ref() -> None:
    events = [
        ev(1, 1, "tool.started", tool_name="Write", issue_ref="o/r#1"),
        ev(2, 2, "tool.started", tool_name="Write", issue_ref="o/r#1", session="s2"),
        ev(3, 3, "tool.started", tool_name="Write", issue_ref="o/r#2", session="s2"),
    ]
    fleet = snapshot(reduce_events(events), now=T0 + timedelta(seconds=4))
    assert [(t.issue_ref, t.session_ids) for t in fleet.tasks] == [
        ("o/r#1", ["s1", "s2"]),
        ("o/r#2", ["s2"]),
    ]


# ------------------------------------------------------------------ ordering contract


def test_apply_event_rejects_out_of_order_input() -> None:
    state = apply_event(None, ev(2, 5, "session.started"))
    with pytest.raises(ValueError, match="order"):
        apply_event(state, ev(1, 1, "tool.started", tool_name="Read"))
    with pytest.raises(ValueError, match="order"):
        apply_event(state, ev(2, 5, "session.started"))  # exact duplicate is also rejected


def test_ties_break_by_event_id_then_content() -> None:
    a, b = ev(1, 5, "tool.started", tool_name="Read"), ev(2, 5, "tool.started", tool_name="Write")
    assert [e.event_id for e in dedupe_and_sort([b, a])] == [a.event_id, b.event_id]
    assert sort_key(a) < sort_key(b)


def test_conflicting_duplicates_resolve_deterministically() -> None:
    first = ev(1, 5, "tool.started", tool_name="Read")
    clash = Event.model_validate({**first.model_dump(mode="json"), "tool_name": "Write"})
    assert dedupe_and_sort([first, clash]) == dedupe_and_sort([clash, first])


# ------------------------------------------------------------------ Hypothesis properties


@PROFILE
@given(data=st.data(), events=event_lists)
def test_reduction_is_order_independent(data: st.DataObject, events: list[Event]) -> None:
    shuffled = data.draw(st.permutations(events))
    assert digest(reduce_events(shuffled)) == digest(reduce_events(events))


@PROFILE
@given(data=st.data(), events=event_lists, picks=st.lists(st.integers(0, 39), max_size=20))
def test_duplicates_by_event_id_are_idempotent(
    data: st.DataObject, events: list[Event], picks: list[int]
) -> None:
    mixed = data.draw(st.permutations([*events, *(events[i % len(events)] for i in picks)]))
    assert canonical_json(reduce_events(mixed)) == canonical_json(reduce_events(events))


@PROFILE
@given(events=event_lists)
def test_incremental_equals_batch(events: list[Event]) -> None:
    sessions: dict[str, Any] = {}
    for event in dedupe_and_sort(events):
        sessions[event.session_id] = apply_event(sessions.get(event.session_id), event)
    assert canonical_json(dict(sorted(sessions.items()))) == canonical_json(reduce_events(events))


@PROFILE
@given(events=event_lists, cut=st.integers(0, 40))
def test_split_batches_are_equivalent_when_ordered(events: list[Event], cut: int) -> None:
    ordered = dedupe_and_sort(events)
    head, tail = ordered[:cut], ordered[cut:]
    sessions = reduce_events(head)
    for event in tail:
        sessions[event.session_id] = apply_event(sessions.get(event.session_id), event)
    assert canonical_json(dict(sorted(sessions.items()))) == canonical_json(reduce_events(ordered))


@PROFILE
@given(events=event_lists, offset=st.integers(0, 10**6))
def test_snapshot_is_pure_and_never_idle(events: list[Event], offset: int) -> None:
    state = reduce_events(events)
    now = T0 + timedelta(seconds=offset)
    first, second = snapshot(state, now=now), snapshot(state, now=now)
    assert canonical_json(first) == canonical_json(second)
    allowed = {lane.value for lane in Lane}
    for session in first.sessions:
        assert session.lane in allowed and session.lane != "idle"
        for agent in session.agents:
            assert agent.lane in allowed
            assert agent.stale == (agent.lane == "stale_offline")
            assert (agent.last_lane is not None) == agent.stale


@PROFILE
@given(events=event_lists)
def test_reducer_does_not_mutate_its_input(events: list[Event]) -> None:
    before = [e.model_dump_json() for e in events]
    reduce_events(events)
    assert [e.model_dump_json() for e in events] == before
