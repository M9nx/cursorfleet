from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from cursorfleet.events.kinds import (
    SELF_REPORT_ONLY_KINDS,
    SELF_REPORTABLE_KINDS,
    EventKind,
    Source,
)
from cursorfleet.events.models import Event
from event_factory import valid_event


def test_valid_event_roundtrip() -> None:
    event = Event.model_validate(valid_event())
    assert event.schema_version == "1.0"
    assert event.agent_id == "reviewer#abc-123"
    again = Event.model_validate_json(event.model_dump_json())
    assert again == event


def test_minimal_event() -> None:
    event = Event.model_validate(
        {
            "event_id": "01J9ZK3Q7M8N2P4R6S8T0V1W2X",
            "ts": "2026-10-04T00:44:00Z",
            "producer": "cursor_hook",
            "producer_version": "0.1.0",
            "source": "observed",
            "kind": "session.started",
            "session_id": "s1",
        }
    )
    assert event.agent_id is None
    assert event.paths == ()
    assert event.attribution.value == "unknown"


def test_kind_enum_contents() -> None:
    assert {k.value for k in EventKind} == {
        "session.started",
        "session.stopped",
        "status.changed",
        "tool.started",
        "tool.completed",
        "tool.failed",
        "file.changed",
        "test.completed",
        "subagent.started",
        "subagent.stopped",
        "context.compacted",
        "plan.created",
        "handoff.created",
        "blocker.raised",
        "gate.changed",
        "context.loaded",
    }


@pytest.mark.parametrize(
    "kind",
    ["thought", "agent.thought", "prompt.submitted", "agent.response", "tool.output", "", "TOOL.X"],
)
def test_unknown_kinds_rejected(kind: str) -> None:
    data = valid_event()
    data["kind"] = kind
    with pytest.raises(ValidationError):
        Event.model_validate(data)


@pytest.mark.parametrize("field", ["prompt", "user_email", "transcript_path", "tool_output", "zzz"])
def test_extra_top_level_field_rejected(field: str) -> None:
    data = valid_event()
    data[field] = "x"
    with pytest.raises(ValidationError, match="Extra inputs"):
        Event.model_validate(data)


@pytest.mark.parametrize(("where", "field"), [("command", "output"), ("metrics", "text")])
def test_extra_nested_field_rejected(where: str, field: str) -> None:
    data = valid_event()
    data[where][field] = "x"
    with pytest.raises(ValidationError, match="Extra inputs"):
        Event.model_validate(data)


def test_extra_field_in_path_rejected() -> None:
    data = valid_event()
    data["paths"][0]["contents"] = "x"
    with pytest.raises(ValidationError, match="Extra inputs"):
        Event.model_validate(data)


def test_schema_version_must_be_1_0() -> None:
    data = valid_event()
    data["schema_version"] = "2.0"
    with pytest.raises(ValidationError):
        Event.model_validate(data)


def test_naive_timestamp_rejected() -> None:
    data = valid_event()
    data["ts"] = "2026-10-04T00:44:00"
    with pytest.raises(ValidationError):
        Event.model_validate(data)


@pytest.mark.parametrize(
    "path",
    [
        "/etc/passwd",
        "C:/Users/x",
        "C:\\x",
        "a/../b",
        "../x",
        "a//b",
        "./a",
        "",
        "a\\b",
        "a\nb",
        "a\u202eb",
    ],
)
def test_bad_paths_rejected(path: str) -> None:
    data = valid_event()
    data["paths"] = [{"path": path}]
    with pytest.raises(ValidationError):
        Event.model_validate(data)


def test_external_path_allowed() -> None:
    data = valid_event()
    data["paths"] = [{"path": "<external>"}]
    assert Event.model_validate(data).paths[0].path == "<external>"


@pytest.mark.parametrize("display", ["a\nb", "a\x1b[31mred", "a\u202eb"])
def test_command_display_must_be_printable(display: str) -> None:
    data = valid_event()
    data["command"]["display"] = display
    with pytest.raises(ValidationError):
        Event.model_validate(data)


def test_command_display_length_capped() -> None:
    data = valid_event()
    data["command"]["display"] = "x" * 201
    with pytest.raises(ValidationError):
        Event.model_validate(data)


@pytest.mark.parametrize("argv0", ["/bin/git", "bin/git", "git status", ""])
def test_argv0_must_be_basename(argv0: str) -> None:
    data = valid_event()
    data["command"]["argv0"] = argv0
    with pytest.raises(ValidationError):
        Event.model_validate(data)


def test_agent_id_mismatch_rejected() -> None:
    data = valid_event()
    data["agent_id"] = "someone-else"
    with pytest.raises(ValidationError, match="agent_id"):
        Event.model_validate(data)


def test_agent_id_explicit_matching_accepted() -> None:
    data = valid_event()
    data["agent_id"] = "reviewer#abc-123"
    assert Event.model_validate(data).agent_id == "reviewer#abc-123"


def test_agent_identity_is_optional() -> None:
    data = valid_event()
    for key in ("agent_role", "agent_instance_id"):
        del data[key]
    event = Event.model_validate(data)
    assert event.agent_id is None


@pytest.mark.parametrize("kind", sorted(SELF_REPORT_ONLY_KINDS, key=str))
def test_self_report_only_kinds_cannot_be_observed(kind: EventKind) -> None:
    data = valid_event()
    data["kind"] = kind.value
    data["source"] = "observed"
    with pytest.raises(ValidationError, match="self_reported"):
        Event.model_validate(data)
    data["source"] = "self_reported"
    assert Event.model_validate(data).source is Source.SELF_REPORTED


@pytest.mark.parametrize("kind", [k for k in EventKind if k not in SELF_REPORTABLE_KINDS])
def test_observed_facts_cannot_be_self_reported(kind: EventKind) -> None:
    data: dict[str, Any] = valid_event()
    data["kind"] = kind.value
    data["source"] = "self_reported"
    data["gate"] = {"name": "tests", "state": "passing"} if kind is EventKind.GATE_CHANGED else None
    with pytest.raises(ValidationError):
        Event.model_validate(data)


def test_gate_required_exactly_on_gate_changed() -> None:
    data = valid_event()
    data["kind"] = "gate.changed"
    data["source"] = "derived"
    with pytest.raises(ValidationError, match="gate"):
        Event.model_validate(data)
    data["gate"] = {"name": "tests", "state": "stale"}
    assert Event.model_validate(data).gate is not None
    data["kind"] = "tool.completed"
    with pytest.raises(ValidationError, match="gate"):
        Event.model_validate(data)


def test_file_changed_requires_paths() -> None:
    data = valid_event()
    data["kind"] = "file.changed"
    data["paths"] = []
    with pytest.raises(ValidationError, match="path"):
        Event.model_validate(data)


def test_events_are_immutable() -> None:
    event = Event.model_validate(valid_event())
    with pytest.raises(ValidationError):
        event.session_id = "other"  # type: ignore[misc]


@pytest.mark.parametrize("bad", [True, 1.5, "3"])
def test_counters_are_strict_ints(bad: object) -> None:
    data = valid_event()
    data["metrics"]["tool_call_count"] = bad
    with pytest.raises(ValidationError):
        Event.model_validate(data)
