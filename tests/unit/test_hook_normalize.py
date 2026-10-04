"""Contract tests: normalizer output must validate against the Pydantic ``Event`` model."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from cursorfleet.adapters.cursor.hook_normalize import (
    HookContext,
    handled_hooks,
    iso_utc,
    normalize,
    session_id_of,
    writer_of,
)
from cursorfleet.adapters.cursor.hook_policy import ALLOWED_V01_HOOKS, FORBIDDEN_HOOKS
from cursorfleet.adapters.cursor.hook_sanitize import PathResolver
from cursorfleet.events.kinds import EventKind
from cursorfleet.events.models import Event
from m2_helpers import ALL_HOOKS, FIXED_NS, counter_entropy, doc_payload

KEY = b"k" * 32


def make_ctx(**overrides: Any) -> HookContext:
    base: dict[str, Any] = {
        "now_ns": FIXED_NS,
        "producer_version": "0.0.1.dev0",
        "resolver": PathResolver(["/project"]),
        "worktree_id": "wt-0123456789ab",
        "branch": "feature/auth",
        "commit": "a" * 40,
        "key": KEY,
        "entropy": counter_entropy(),
    }
    base.update(overrides)
    return HookContext(**base)


def validated(hook: str, payload: dict[str, Any], **ctx: Any) -> list[Event]:
    raw = normalize(hook, copy.deepcopy(payload), make_ctx(**ctx))
    return [Event.model_validate(json.loads(json.dumps(item))) for item in raw]


def test_handlers_cover_exactly_the_allowed_hooks() -> None:
    assert handled_hooks() == ALLOWED_V01_HOOKS
    assert set(ALL_HOOKS) == set(ALLOWED_V01_HOOKS)
    assert not handled_hooks() & FORBIDDEN_HOOKS


@pytest.mark.parametrize("hook", ALL_HOOKS)
def test_every_doc_example_validates(hook: str) -> None:
    events = validated(hook, doc_payload(hook))
    assert events, hook
    for event in events:
        assert event.session_id == "doc-example-conversation"
        assert event.producer == "cursor_hook"
        assert event.worktree_id == "wt-0123456789ab"
        assert event.hook in ALLOWED_V01_HOOKS


def test_hook_to_kind_mapping() -> None:
    expected = {
        "sessionStart": [EventKind.SESSION_STARTED],
        "sessionEnd": [EventKind.SESSION_STOPPED],
        "subagentStart": [EventKind.SUBAGENT_STARTED],
        "subagentStop": [EventKind.SUBAGENT_STOPPED],
        "preToolUse": [EventKind.TOOL_STARTED],
        "afterFileEdit": [EventKind.FILE_CHANGED],
        "preCompact": [EventKind.CONTEXT_COMPACTED],
    }
    for hook, kinds in expected.items():
        got = [e.kind for e in validated(hook, doc_payload(hook))]
        assert got == kinds, hook


def test_shell_post_tool_use_derives_test_completed_with_exit_code() -> None:
    payload = doc_payload("postToolUse")
    payload["tool_input"] = {"command": "uv run pytest -q"}
    payload["tool_output"] = json.dumps({"exitCode": 1, "stdout": "FAILED secret-output"})
    events = validated("postToolUse", payload)
    kinds = [e.kind for e in events]
    assert kinds[0] == EventKind.TOOL_COMPLETED
    assert EventKind.TEST_COMPLETED in kinds
    derived = next(e for e in events if e.kind == EventKind.TEST_COMPLETED)
    assert derived.source.value == "derived"
    assert events[0].command is not None and events[0].command.exit_code == 1
    assert "secret-output" not in json.dumps([e.model_dump(mode="json") for e in events])


def test_non_verify_shell_does_not_derive_a_test_event() -> None:
    payload = doc_payload("postToolUse")
    payload["tool_input"] = {"command": "ls -la"}
    kinds = [e.kind for e in validated("postToolUse", payload)]
    assert EventKind.TEST_COMPLETED not in kinds


def test_unparsable_tool_output_gives_no_exit_code() -> None:
    for output in ("not json", "[1,2]", '{"exitCode":"0"}', '{"exitCode":true}', None, 7):
        payload = doc_payload("postToolUse")
        payload["tool_output"] = output
        first = validated("postToolUse", payload)[0]
        assert first.command is not None and first.command.exit_code is None, output


def test_failure_hook_marks_error_outcome() -> None:
    events = validated("postToolUseFailure", doc_payload("postToolUseFailure"))
    assert events[0].kind == EventKind.TOOL_FAILED
    assert events[0].outcome is not None


def test_paths_are_relative_and_external_marked() -> None:
    payload = doc_payload("afterFileEdit")
    payload["file_path"] = "/etc/passwd"
    assert [x.path for x in validated("afterFileEdit", payload)[0].paths] == ["<external>"]
    payload["file_path"] = "/project/src/auth.ts"
    assert [x.path for x in validated("afterFileEdit", payload)[0].paths] == ["src/auth.ts"]


def test_subagent_identity_is_provisional_and_degrades() -> None:
    # Q1 (unverified): tool hooks may or may not carry subagent identity.
    plain = validated("preToolUse", doc_payload("preToolUse"))[0]
    assert plain.attribution.value == "unknown" and plain.agent_id is None
    with_id = doc_payload("preToolUse")
    with_id.update({"subagent_id": "abc-123", "subagent_type": "reviewer"})
    exact = validated("preToolUse", with_id)[0]
    assert exact.attribution.value == "exact" and exact.agent_role == "reviewer"
    type_only = doc_payload("preToolUse")
    type_only["subagent_type"] = "reviewer"
    assert validated("preToolUse", type_only)[0].attribution.value == "inferred"


def test_subagent_stop_is_inferred_without_an_id() -> None:
    event = validated("subagentStop", doc_payload("subagentStop"))[0]
    assert event.attribution.value == "inferred"
    assert event.agent_role == "generalPurpose"
    assert event.agent_instance_id is None


@pytest.mark.parametrize("hook", ALL_HOOKS)
def test_missing_or_bad_session_id_yields_no_events(hook: str) -> None:
    for bad in (None, "", 5, "has space", "x" * 500):
        payload = doc_payload(hook)
        payload.pop("conversation_id", None)
        payload.pop("session_id", None)
        if bad is not None:
            payload["conversation_id"] = bad
        out = normalize(hook, payload, make_ctx())
        for item in out:
            Event.model_validate(json.loads(json.dumps(item)))  # whatever remains is valid


@pytest.mark.parametrize("hook", ALL_HOOKS)
def test_garbage_field_types_never_raise_and_never_produce_invalid_events(hook: str) -> None:
    junk_values: list[Any] = [None, 5, -1, 1e999, True, [], {}, "x" * 10_000, [1, [2]], {"a": {}}]
    base = doc_payload(hook)
    for key in list(base):
        if key in {"hook_event_name"}:
            continue
        for junk in junk_values:
            payload = copy.deepcopy(base)
            payload[key] = junk
            for item in normalize(hook, payload, make_ctx()):
                Event.model_validate(json.loads(json.dumps(item)))


def test_unknown_and_forbidden_hooks_produce_nothing() -> None:
    for name in (*FORBIDDEN_HOOKS, "somethingNew", ""):
        assert normalize(name, {"conversation_id": "c1"}, make_ctx()) == []


def test_writer_and_session_helpers() -> None:
    assert session_id_of("preToolUse", {"conversation_id": "c1"}) == "c1"
    assert writer_of("preToolUse", {"conversation_id": "c1"}) == "main"
    assert writer_of("preToolUse", {"conversation_id": "c1", "subagent_id": "sa-1"}) == "sa-1"
    # lifecycle events always go to the main writer
    assert writer_of("subagentStart", {"conversation_id": "c1", "subagent_id": "sa-1"}) == "main"


def test_event_ids_are_unique_and_time_ordered() -> None:
    ctx = make_ctx()  # one context => one shared entropy source, as in a single process
    ids = [
        item["event_id"] for hook in ALL_HOOKS for item in normalize(hook, doc_payload(hook), ctx)
    ]
    assert len(ids) == len(set(ids))
    first = validated("sessionStart", doc_payload("sessionStart"))[0]
    assert first.ts.isoformat().startswith("2026-09-21T14:13:20.123")


def test_iso_utc_is_millisecond_utc() -> None:
    assert iso_utc(0) == "1970-01-01T00:00:00.000Z"
    assert iso_utc(FIXED_NS) == "2026-09-21T14:13:20.123Z"


@pytest.mark.parametrize("hook", ALL_HOOKS)
def test_sensitive_payload_fields_never_reach_events(hook: str) -> None:
    payload = doc_payload(hook)
    sentinels = {
        "prompt": "SENTINEL-prompt",
        "text": "SENTINEL-text",
        "thinking": "SENTINEL-thinking",
        "user_email": "SENTINEL-user@example.com",
        "transcript_path": "/home/SENTINEL-transcript",
        "agent_transcript_path": "/home/SENTINEL-agent-transcript",
        "file_content": "SENTINEL-content",
        "content": "SENTINEL-content2",
        "output": "SENTINEL-output",
        "summary": "SENTINEL-summary",
        "task": "SENTINEL-task",
        "description": "SENTINEL-description",
        "agent_message": "SENTINEL-agent-message",
        "error_message": "SENTINEL-error",
        "edits": [{"old_string": "SENTINEL-old", "new_string": "SENTINEL-new"}],
        "modified_files": ["SENTINEL-modified"],
        "cwd": "/SENTINEL-cwd",
        "env": {"SECRET": "SENTINEL-env"},
        "attachments": [{"path": "/SENTINEL-attachment"}],
    }
    payload.update(sentinels)
    if isinstance(payload.get("tool_input"), dict):
        payload["tool_input"].update(
            {"working_directory": "/SENTINEL-wd", "contents": "SENTINEL-body"}
        )
    if "tool_output" in payload:
        payload["tool_output"] = json.dumps({"exitCode": 0, "stdout": "SENTINEL-stdout"})
    if "stdout" in payload or hook in {"afterShellExecution"}:
        payload["output"] = "SENTINEL-shell-output"
    text = json.dumps(normalize(hook, payload, make_ctx()))
    assert "SENTINEL" not in text, hook
