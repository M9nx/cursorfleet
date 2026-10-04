"""Pure, deterministic reducer: events -> session/agent/task state and fleet views.

Guarantees (tested, including with Hypothesis):

- ``reduce_events`` is a function of the SET of events: input order and exact duplicates
  (same ``event_id``) do not change the result. Events are folded in the total order
  ``(ts UTC, event_id)``.
- ``apply_event`` is the incremental form; it requires events in that order (the indexer
  checks the watermark and rebuilds a session from the spool when an event arrives late).
- No clock reads: stale detection takes an injected ``now``. Staleness never turns into
  "idle": a silent agent becomes ``stale_offline`` (with the previous lane kept in
  ``last_lane``), and an agent with no telemetry at all is ``unknown``.

Lane semantics are heuristics (PROVISIONAL, ADR 0001 Q1: tool hooks may not identify the
agent). We do NOT attribute unattributed events to a running subagent by timing; they
accumulate on the ``main`` entry, labelled ``attribution: unknown``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime, timedelta

from cursorfleet.adapters.cursor.hook_sanitize import is_verify_command
from cursorfleet.events.kinds import (
    AgentStatus,
    Attribution,
    EventKind,
    Outcome,
    Source,
)
from cursorfleet.events.models import Event
from cursorfleet.state.models import (
    BUDGET_UNKNOWN,
    MAX_FILES_PER_AGENT,
    AgentAcc,
    AgentView,
    FleetView,
    GateAcc,
    GateView,
    Lane,
    LastTest,
    LastTestView,
    SessionAcc,
    SessionView,
    StopReport,
    StopReportView,
    TaskView,
    utc,
)

DEFAULT_STALE_AFTER_S = 900
MAIN = "main"

_ATTRIBUTION_RANK = {Attribution.UNKNOWN: 0, Attribution.INFERRED: 1, Attribution.EXACT: 2}
_PLANNING_TOOLS = frozenset({"todowrite", "todo_write", "createplan", "create_plan", "switchmode"})
_READ_TOOLS = frozenset(
    {
        "read", "readfile", "grep", "glob", "semanticsearch", "codebase_search", "readlints",
        "listdir", "ls", "websearch", "webfetch", "fetchmcpresource", "getdynamictools",
    }
)  # fmt: skip
_WRITE_TOOLS = frozenset(
    {"write", "strreplace", "edit", "delete", "applypatch", "editnotebook", "multiedit"}
)
_EARLY_LANES = frozenset({Lane.UNKNOWN, Lane.QUEUED, Lane.LOADING_CONTEXT})
_ACTIVE_LANES = frozenset({Lane.PLANNING, Lane.WORKING, Lane.VERIFYING, Lane.PATCHING})


def sort_key(event: Event) -> tuple[datetime, str]:
    return utc(event.ts), event.event_id


def watermark_of(session: SessionAcc) -> tuple[datetime, str]:
    return session.watermark_ts, session.watermark_id


# ---------------------------------------------------------------- folding


def _new_session(event: Event) -> SessionAcc:
    ts = utc(event.ts)
    return SessionAcc(
        session_id=event.session_id,
        first_ts=ts,
        last_ts=ts,
        watermark_ts=ts,
        watermark_id=event.event_id,
    )


def _set_lane(agent: AgentAcc, lane: Lane, event: Event) -> None:
    if agent.lane is not lane:
        agent.lane_since = utc(event.ts)
    agent.lane = lane
    agent.lane_source = event.source
    if event.source is not Source.SELF_REPORTED:
        agent.lifecycle_only = False  # real activity replaces lifecycle-only evidence


def _touch_agent(agent: AgentAcc, event: Event) -> None:
    ts = utc(event.ts)
    agent.last_ts = max(agent.last_ts, ts)
    agent.events += 1
    if event.source is not Source.SELF_REPORTED:
        agent.last_live_ts = ts if agent.last_live_ts is None else max(agent.last_live_ts, ts)
    rank = _ATTRIBUTION_RANK
    if agent.events == 1 or rank[event.attribution] < rank[agent.attribution]:
        agent.attribution = event.attribution
    if event.agent_role is not None:
        agent.role = event.agent_role
    if event.agent_instance_id is not None:
        agent.instance_id = event.agent_instance_id
    if event.worktree_id is not None:
        agent.worktree_id = event.worktree_id
    if event.branch is not None:
        agent.branch = event.branch
    if event.commit is not None:
        agent.commit = event.commit
    if event.issue_ref is not None and event.issue_ref not in agent.issue_refs:
        agent.issue_refs = sorted([*agent.issue_refs, event.issue_ref])


def _get_agent(session: SessionAcc, key: str, event: Event) -> AgentAcc:
    agent = session.agents.get(key)
    if agent is None:
        ts = utc(event.ts)
        agent = AgentAcc(key=key, first_ts=ts, last_ts=ts)
        session.agents[key] = agent
    return agent


def _is_verify(event: Event) -> bool:
    command = event.command
    if command is None:
        return False
    return is_verify_command(command.argv0, command.subcommand, command.display)


def _tool_lane(agent: AgentAcc, event: Event) -> Lane:
    name = (event.tool_name or "").lower()
    if _is_verify(event):
        return Lane.VERIFYING
    if name in _PLANNING_TOOLS:
        return Lane.PLANNING if agent.lane in (_EARLY_LANES | {Lane.PLANNING}) else Lane.WORKING
    if name in _READ_TOOLS:
        if agent.lane in _EARLY_LANES:
            return Lane.LOADING_CONTEXT
        return agent.lane if agent.lane in (_ACTIVE_LANES) else Lane.WORKING
    if agent.reviewed and name in _WRITE_TOOLS:
        return Lane.PATCHING
    return Lane.WORKING


def _add_file(agent: AgentAcc, path: str) -> None:
    if path in agent.files:
        return
    if len(agent.files) >= MAX_FILES_PER_AGENT:
        agent.files_overflow = True
        return
    agent.files = sorted([*agent.files, path])


def _on_session_started(s: SessionAcc, a: AgentAcc, e: Event) -> None:
    s.started_ts = utc(e.ts) if s.started_ts is None else min(s.started_ts, utc(e.ts))
    s.ended = False
    s.ended_ts = None
    s.end_outcome = None
    if a.lane is Lane.UNKNOWN:
        _set_lane(a, Lane.QUEUED, e)


def _on_session_stopped(s: SessionAcc, a: AgentAcc, e: Event) -> None:
    s.ended = True
    s.ended_ts = utc(e.ts)
    s.end_outcome = e.outcome
    _set_lane(a, Lane.DONE, e)


def _on_status(s: SessionAcc, a: AgentAcc, e: Event) -> None:
    status = e.status
    if status is AgentStatus.WAITING:
        a.reviewed = True
        _set_lane(a, Lane.AWAITING_REVIEW, e)
    elif status in (AgentStatus.ERROR, AgentStatus.BLOCKED):
        _set_lane(a, Lane.BLOCKED, e)
    elif status is AgentStatus.WORKING:
        _set_lane(a, Lane.WORKING, e)
    elif status is AgentStatus.DONE:
        _set_lane(a, Lane.DONE, e)
    # idle/unknown: keep the lane; a silent agent turns stale at snapshot time


def _on_tool_started(s: SessionAcc, a: AgentAcc, e: Event) -> None:
    shell = (e.tool_name or "").lower() in {"shell", "bash", "terminal"}
    if e.hook == "beforeShellExecution":
        a.before_shell_calls += 1
    else:
        a.pre_calls += 1
        if shell:
            a.pre_shell_calls += 1
    a.last_tool = e.tool_name or a.last_tool
    _set_lane(a, _tool_lane(a, e), e)


def _on_tool_completed(s: SessionAcc, a: AgentAcc, e: Event) -> None:
    a.last_tool = e.tool_name or a.last_tool


def _on_tool_failed(s: SessionAcc, a: AgentAcc, e: Event) -> None:
    a.tool_failures += 1
    a.last_tool = e.tool_name or a.last_tool


def _on_test(s: SessionAcc, a: AgentAcc, e: Event) -> None:
    a.last_test = LastTest(outcome=e.outcome or Outcome.UNKNOWN, ts=utc(e.ts))
    _set_lane(a, Lane.VERIFYING, e)


def _on_file_changed(s: SessionAcc, a: AgentAcc, e: Event) -> None:
    for path in e.paths:
        _add_file(a, path.path)
    _set_lane(a, Lane.PATCHING if a.reviewed else Lane.WORKING, e)


def _on_compacted(s: SessionAcc, a: AgentAcc, e: Event) -> None:
    a.compactions += 1
    if e.metrics is not None:
        a.last_context_usage_percent = e.metrics.context_usage_percent
        a.last_context_tokens = e.metrics.context_tokens
        a.last_context_window = e.metrics.context_window_size


def _on_plan(s: SessionAcc, a: AgentAcc, e: Event) -> None:
    a.plans += 1
    if a.lane in (_EARLY_LANES | {Lane.PLANNING}):
        _set_lane(a, Lane.PLANNING, e)


def _on_context_loaded(s: SessionAcc, a: AgentAcc, e: Event) -> None:
    a.contexts_loaded += 1
    if a.lane in _EARLY_LANES:
        _set_lane(a, Lane.LOADING_CONTEXT, e)


def _on_handoff(s: SessionAcc, a: AgentAcc, e: Event) -> None:
    a.handoffs += 1
    a.reviewed = True
    _set_lane(a, Lane.AWAITING_REVIEW, e)


def _on_blocker(s: SessionAcc, a: AgentAcc, e: Event) -> None:
    a.blockers += 1
    _set_lane(a, Lane.BLOCKED, e)


def _on_gate(s: SessionAcc, a: AgentAcc, e: Event) -> None:
    if e.gate is not None:
        s.gates[e.gate.name] = GateAcc(state=e.gate.state.value, ts=utc(e.ts), commit=e.commit)


def _on_subagent_started(s: SessionAcc, a: AgentAcc, e: Event) -> None:
    a.lifecycle = "running"
    a.started_ts = utc(e.ts)
    a.stopped_ts = None
    a.spawn_link = e.tool_use_id or a.spawn_link
    _set_lane(a, Lane.WORKING, e)
    # Running, but nothing attributed to it yet: shown as lifecycle-only evidence.
    a.lifecycle_only = a.events <= 1


_HANDLERS: dict[EventKind, Callable[[SessionAcc, AgentAcc, Event], None]] = {
    EventKind.SESSION_STARTED: _on_session_started,
    EventKind.SESSION_STOPPED: _on_session_stopped,
    EventKind.STATUS_CHANGED: _on_status,
    EventKind.TOOL_STARTED: _on_tool_started,
    EventKind.TOOL_COMPLETED: _on_tool_completed,
    EventKind.TOOL_FAILED: _on_tool_failed,
    EventKind.TEST_COMPLETED: _on_test,
    EventKind.VERIFICATION_OBSERVED: _on_test,
    EventKind.FILE_CHANGED: _on_file_changed,
    EventKind.CONTEXT_COMPACTED: _on_compacted,
    EventKind.PLAN_CREATED: _on_plan,
    EventKind.CONTEXT_LOADED: _on_context_loaded,
    EventKind.HANDOFF_CREATED: _on_handoff,
    EventKind.BLOCKER_RAISED: _on_blocker,
    EventKind.GATE_CHANGED: _on_gate,
    EventKind.SUBAGENT_STARTED: _on_subagent_started,
}

# Events after which a previously blocked/awaiting agent is demonstrably active again are
# handled by _set_lane in the handlers above (any tool/file lane overrides blocked).


def _pair_stop(session: SessionAcc, event: Event) -> AgentAcc | None:
    """Find the running subagent a ``subagent.stopped`` belongs to (PROVISIONAL pairing).

    Exact: the event carries an instance id. Otherwise the open subagents of the same
    role are candidates; choose the one whose start time best matches
    ``stop_ts - duration_ms`` (earliest start when no duration is known).
    """
    if event.agent_id is not None and event.agent_instance_id is not None:
        found = session.agents.get(event.agent_id)
        if found is not None and found.lifecycle == "running":
            return found
    candidates = [
        agent
        for key, agent in sorted(session.agents.items())
        if agent.lifecycle == "running" and agent.role == event.agent_role and key != MAIN
    ]
    if not candidates:
        return None
    duration = event.metrics.duration_ms if event.metrics is not None else None
    if duration is None:
        return min(candidates, key=lambda a: (a.started_ts or a.first_ts, a.key))
    expected_start = utc(event.ts) - timedelta(milliseconds=duration)
    return min(
        candidates,
        key=lambda a: (abs((a.started_ts or a.first_ts) - expected_start), a.key),
    )


def _on_subagent_stopped(session: SessionAcc, event: Event) -> AgentAcc:
    agent = _pair_stop(session, event)
    if agent is None:
        session.unpaired_stops += 1
        key = event.agent_id or event.agent_role or "unknown-subagent"
        agent = _get_agent(session, key, event)
        agent.role = agent.role or event.agent_role
    _touch_agent(agent, event)
    agent.lifecycle = "stopped"
    agent.stopped_ts = utc(event.ts)
    agent.lifecycle_only = False
    metrics = event.metrics
    agent.stop_report = StopReport(
        outcome=event.outcome,
        duration_ms=metrics.duration_ms if metrics else None,
        tool_call_count=metrics.tool_call_count if metrics else None,
        message_count=metrics.message_count if metrics else None,
        loop_count=metrics.loop_count if metrics else None,
    )
    _set_lane(agent, Lane.BLOCKED if event.outcome is Outcome.FAILED else Lane.DONE, event)
    return agent


def apply_event(session: SessionAcc | None, event: Event) -> SessionAcc:
    """Fold one event (in ``sort_key`` order) into ``session``; returns the session."""
    key = sort_key(event)
    if session is None:
        session = _new_session(event)
    elif key <= watermark_of(session) and session.events > 0:
        msg = "apply_event requires events in (ts, event_id) order; rebuild the session"
        raise ValueError(msg)
    ts = utc(event.ts)
    session.events += 1
    session.last_ts = max(session.last_ts, ts)
    session.first_ts = min(session.first_ts, ts)
    if event.source is not Source.SELF_REPORTED:
        live = session.last_live_ts
        session.last_live_ts = ts if live is None else max(live, ts)
    session.by_source[event.source.value] = session.by_source.get(event.source.value, 0) + 1
    session.watermark_ts, session.watermark_id = key
    if event.cursor_version is not None:
        session.cursor_version = event.cursor_version
    if event.branch is not None:
        session.branch = event.branch
    if event.commit is not None:
        session.commit = event.commit
    if event.worktree_id is not None and event.worktree_id not in session.worktree_ids:
        session.worktree_ids = sorted([*session.worktree_ids, event.worktree_id])

    if event.kind is EventKind.SUBAGENT_STOPPED:
        _on_subagent_stopped(session, event)
        return session
    agent = _get_agent(session, event.agent_id or MAIN, event)
    _touch_agent(agent, event)
    handler = _HANDLERS.get(event.kind)
    if handler is not None:
        handler(session, agent, event)
    return session


def dedupe_and_sort(events: Iterable[Event]) -> list[Event]:
    """Total order ``(ts, event_id, content)`` with one event per ``event_id``."""
    ordered = sorted(events, key=lambda e: (*sort_key(e), e.model_dump_json()))
    seen: set[str] = set()
    unique: list[Event] = []
    for event in ordered:
        if event.event_id in seen:
            continue
        seen.add(event.event_id)
        unique.append(event)
    return unique


def reduce_events(events: Iterable[Event]) -> dict[str, SessionAcc]:
    """Fold any collection of events into per-session accumulators (order-independent)."""
    sessions: dict[str, SessionAcc] = {}
    for event in dedupe_and_sort(events):
        sessions[event.session_id] = apply_event(sessions.get(event.session_id), event)
    return dict(sorted(sessions.items()))


# ---------------------------------------------------------------- views


def _live_ts(agent: AgentAcc, session: SessionAcc) -> datetime | None:
    live = agent.last_live_ts
    if agent.lifecycle == "running" and agent.lifecycle_only and session.last_live_ts is not None:
        # A running subagent that emits no attributed telemetry is as alive as its session.
        return session.last_live_ts if live is None else max(live, session.last_live_ts)
    return live


def _basis(agent: AgentAcc) -> str:
    if agent.lane is Lane.UNKNOWN or agent.lane_source is None:
        return "none"
    if agent.lifecycle_only:
        return "lifecycle_only"
    return {
        Source.OBSERVED: "observed_activity",
        Source.SELF_REPORTED: "self_reported",
        Source.DERIVED: "derived",
    }[agent.lane_source]


def agent_view(
    agent: AgentAcc, session: SessionAcc, now: datetime, stale_after_s: int
) -> AgentView:
    lane = agent.lane
    stale = False
    last_lane: str | None = None
    live = _live_ts(agent, session)
    if lane not in (Lane.DONE, Lane.UNKNOWN):
        age = (now - live).total_seconds() if live is not None else None
        if age is None or age > stale_after_s:
            stale = True
            last_lane = lane.value
            lane = Lane.STALE_OFFLINE
    end = agent.stopped_ts or agent.last_ts
    return AgentView(
        key=agent.key,
        role=agent.role,
        instance_id=agent.instance_id,
        attribution=agent.attribution.value,
        lane=lane.value,
        lane_source=agent.lane_source.value if agent.lane_source else None,
        lane_basis=_basis(agent),
        stale=stale,
        last_lane=last_lane,
        lifecycle=agent.lifecycle,
        lifecycle_only=agent.lifecycle_only,
        first_ts=agent.first_ts,
        last_ts=agent.last_ts,
        elapsed_s=round(max((end - agent.first_ts).total_seconds(), 0.0), 3),
        tool_call_count=agent.tool_call_count,
        tool_failures=agent.tool_failures,
        compactions=agent.compactions,
        last_context_usage_percent=agent.last_context_usage_percent,
        files_changed=len(agent.files),
        reviewed=agent.reviewed,
        last_test=(
            LastTestView(outcome=agent.last_test.outcome.value, ts=agent.last_test.ts)
            if agent.last_test
            else None
        ),
        stop_report=(
            StopReportView(
                outcome=agent.stop_report.outcome.value if agent.stop_report.outcome else None,
                duration_ms=agent.stop_report.duration_ms,
                tool_call_count=agent.stop_report.tool_call_count,
                message_count=agent.stop_report.message_count,
            )
            if agent.stop_report
            else None
        ),
        issue_refs=list(agent.issue_refs),
        worktree_id=agent.worktree_id,
        branch=agent.branch,
        token_budget=BUDGET_UNKNOWN,
    )


def _session_lane(session: SessionAcc, agents: Sequence[AgentView]) -> str:
    if session.ended:
        return Lane.DONE.value
    if not agents:
        return Lane.UNKNOWN.value
    for view in agents:
        if view.key == MAIN:
            return view.lane
    latest = max(agents, key=lambda v: (v.last_ts, v.key))
    return latest.lane


def session_view(session: SessionAcc, now: datetime, stale_after_s: int) -> SessionView:
    agents = [
        agent_view(agent, session, now, stale_after_s)
        for _key, agent in sorted(session.agents.items())
    ]
    end = session.ended_ts or session.last_ts
    return SessionView(
        session_id=session.session_id,
        lane=_session_lane(session, agents),
        ended=session.ended,
        end_outcome=session.end_outcome.value if session.end_outcome else None,
        first_ts=session.first_ts,
        last_ts=session.last_ts,
        started_ts=session.started_ts,
        ended_ts=session.ended_ts,
        elapsed_s=round(max((end - session.first_ts).total_seconds(), 0.0), 3),
        tool_call_count=sum(a.tool_call_count for a in session.agents.values()),
        compactions=sum(a.compactions for a in session.agents.values()),
        event_count=session.events,
        by_source=dict(sorted(session.by_source.items())),
        cursor_version=session.cursor_version,
        branch=session.branch,
        commit=session.commit,
        worktree_ids=list(session.worktree_ids),
        unpaired_stops=session.unpaired_stops,
        token_budget=BUDGET_UNKNOWN,
        agents=agents,
        gates=[
            GateView(name=name, state=gate.state, ts=gate.ts, commit=gate.commit)
            for name, gate in sorted(session.gates.items())
        ],
    )


def _task_views(sessions: Sequence[SessionAcc], views: dict[str, SessionView]) -> list[TaskView]:
    grouped: dict[str, list[tuple[SessionAcc, AgentAcc]]] = {}
    for session in sessions:
        for _key, agent in sorted(session.agents.items()):
            for ref in agent.issue_refs:
                grouped.setdefault(ref, []).append((session, agent))
    tasks: list[TaskView] = []
    for ref in sorted(grouped):
        members = grouped[ref]
        lead_session, lead_agent = max(
            members, key=lambda m: (m[1].last_ts, m[0].session_id, m[1].key)
        )
        lane = next(
            v.lane for v in views[lead_session.session_id].agents if v.key == lead_agent.key
        )
        tasks.append(
            TaskView(
                issue_ref=ref,
                lane=lane,
                session_ids=sorted({s.session_id for s, _ in members}),
                agent_keys=sorted({a.key for _, a in members}),
                first_ts=min(a.first_ts for _, a in members),
                last_ts=max(a.last_ts for _, a in members),
                plans=sum(a.plans for _, a in members),
                handoffs=sum(a.handoffs for _, a in members),
                blockers=sum(a.blockers for _, a in members),
            )
        )
    return tasks


def snapshot(
    sessions: dict[str, SessionAcc], *, now: datetime, stale_after_s: int = DEFAULT_STALE_AFTER_S
) -> FleetView:
    """Derive the fleet view at ``now`` (injected). Pure and deterministic."""
    now = utc(now)
    ordered = [sessions[key] for key in sorted(sessions)]
    views = {s.session_id: session_view(s, now, stale_after_s) for s in ordered}
    return FleetView(
        generated_at=now,
        stale_after_s=stale_after_s,
        sessions=[views[s.session_id] for s in ordered],
        tasks=_task_views(ordered, views),
    )


def canonical_json(model: FleetView | SessionAcc | dict[str, SessionAcc]) -> str:
    """Stable JSON text for determinism checks and digests (sorted keys, no whitespace)."""
    if isinstance(model, dict):
        data: object = {k: json.loads(v.model_dump_json()) for k, v in sorted(model.items())}
    else:
        data = json.loads(model.model_dump_json())
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(model: FleetView | SessionAcc | dict[str, SessionAcc]) -> str:
    return hashlib.sha256(canonical_json(model).encode("ascii")).hexdigest()
