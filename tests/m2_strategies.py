"""Hypothesis strategies shared by the reducer and indexer property tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from hypothesis import HealthCheck, settings
from hypothesis import strategies as st

from cursorfleet.events.models import Event
from m2_helpers import make_event

T0 = datetime(2026, 10, 4, 0, 0, 0, tzinfo=UTC)


def at(seconds: int) -> str:
    return (T0 + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def ev(n: int, sec: int, kind: str, session: str = "s1", **extra: Any) -> Event:
    return Event.model_validate(make_event(session, n, kind=kind, ts=at(sec), **extra))


ROLES = ["reviewer", "tester"]
TOOLS = ["Shell", "Read", "Write", "TodoWrite", "Grep"]


@st.composite
def specs(draw: st.DrawFn) -> dict[str, Any]:
    return {
        "session": draw(st.sampled_from(["s1", "s2"])),
        "sec": draw(st.integers(0, 6)),  # tiny range => plenty of timestamp ties
        "kind": draw(
            st.sampled_from(
                [
                    "session.started",
                    "session.stopped",
                    "tool.started",
                    "tool.completed",
                    "tool.failed",
                    "file.changed",
                    "context.compacted",
                    "subagent.started",
                    "subagent.stopped",
                    "status.changed",
                    "test.completed",
                    "plan.created",
                    "blocker.raised",
                ]
            )
        ),
        "role": draw(st.sampled_from(ROLES)),
        "inst": draw(st.sampled_from(["i1", "i2"])),
        "tool": draw(st.sampled_from(TOOLS)),
        "attributed": draw(st.booleans()),
        "verify": draw(st.booleans()),
        "dur": draw(st.one_of(st.none(), st.integers(1, 5000))),
        "status": draw(st.sampled_from(["working", "waiting", "blocked", "done", "error", "idle"])),
        "hook": draw(st.sampled_from([None, "preToolUse", "beforeShellExecution"])),
    }


def build(spec: dict[str, Any], n: int) -> Event:
    kind = spec["kind"]
    extra: dict[str, Any] = {}
    if kind.startswith("tool."):
        extra["tool_name"] = spec["tool"]
        if spec["hook"]:
            extra["hook"] = spec["hook"]
        if spec["tool"] == "Shell":
            extra["command"] = (
                {"argv0": "pytest", "display": "pytest -q"}
                if spec["verify"]
                else {"argv0": "ls", "display": "ls"}
            )
    if kind == "file.changed":
        extra["paths"] = [{"path": f"f{n % 3}.py", "op": "modified"}]
    if kind == "subagent.started":
        extra.update(agent_role=spec["role"], agent_instance_id=spec["inst"], attribution="exact")
    elif kind == "subagent.stopped":
        extra.update(agent_role=spec["role"], attribution="inferred", outcome="ok")
        if spec["dur"]:
            extra["metrics"] = {"duration_ms": spec["dur"]}
    elif spec["attributed"] and kind not in {"session.started", "session.stopped"}:
        extra.update(agent_role=spec["role"], agent_instance_id=spec["inst"], attribution="exact")
    if kind == "status.changed":
        extra["status"] = spec["status"]
    if kind == "test.completed":
        extra.update(outcome="ok", source="derived")
    if kind in {"plan.created", "blocker.raised"}:
        extra["source"] = "self_reported"
    return ev(n, spec["sec"], kind, session=spec["session"], **extra)


event_lists = st.lists(specs(), min_size=1, max_size=40).map(
    lambda items: [build(spec, n) for n, spec in enumerate(items)]
)
PROFILE = settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.too_slow])
