"""Unit tests for the throwaway spike analyzer's Q1 identity classification.

`spike/analyze.py` is stdlib-only spike tooling (excluded from ruff and mypy) that lives
outside the package, so it is loaded from its path. Every capture record below is
**SYNTHETIC**: hand-built to exercise the classifier. None of it was captured from Cursor,
and nothing here says anything about how Cursor behaves (all ADR 0001 results stay OPEN).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SPIKE_DIR = Path(__file__).resolve().parents[2] / "spike"

PARENT = "conv-main"
SUB = "sub-1"

Rec = dict[str, Any]


@pytest.fixture(scope="module")
def az() -> ModuleType:
    saved_path = list(sys.path)
    try:
        spec = importlib.util.spec_from_file_location("spike_analyze", SPIKE_DIR / "analyze.py")
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = saved_path  # analyze.py prepends the spike dir; do not leak it
    return module


def rec(
    event: str, t: float, ids: dict[str, Any] | None = None, keys: dict[str, Any] | None = None
) -> Rec:
    return {
        "hook_event_name": event,
        "start_epoch_ms": t,
        "end_epoch_ms": t + 1,
        "pid": 1,
        "ids": ids or {},
        "keys": keys or {},
    }


def start(sub_id: str = SUB, kind: str = "cf-writer", t: float = 1000) -> Rec:
    return rec(
        "subagentStart",
        t,
        {"subagent_id": sub_id, "subagent_type": kind, "parent_conversation_id": PARENT},
        {"subagent_id": "str", "subagent_type": "str", "parent_conversation_id": "str"},
    )


def stop(kind: str = "cf-writer", t: float = 2000) -> Rec:
    return rec("subagentStop", t, {"subagent_type": kind}, {"subagent_type": "str"})


def tool(
    t: float = 1500,
    conversation_id: str = PARENT,
    extra_keys: dict[str, str] | None = None,
    extra_ids: dict[str, Any] | None = None,
    event: str = "preToolUse",
) -> Rec:
    keys = {
        "conversation_id": "str",
        "generation_id": "str",
        "tool_name": "str",
        "tool_use_id": "str",
    }
    keys.update(extra_keys or {})
    ids = {"conversation_id": conversation_id, "generation_id": "gen-1", "tool_use_id": "tu-1"}
    ids.update(extra_ids or {})
    return rec(event, t, ids, keys)


def window(*tools: Rec) -> list[Rec]:
    """One subagent window (1000..2000) with the given tool hooks."""
    return [start(), *tools, stop()]


# ------------------------------------------------------------ direct_current_identity


def test_subagent_id_on_tool_hook_linked_to_a_start_is_direct(az: ModuleType) -> None:
    res = az.identity_analysis(
        window(tool(extra_keys={"subagent_id": "str"}, extra_ids={"subagent_id": SUB}))
    )
    assert res["direct_current_identity"] == {"subagent_id": 1}
    assert res["role_only_identity"] == {}
    assert res["unclassified_identity_candidates"] == {}
    assert res["verdict_code"] == "CONFIRMED"


def test_conversation_id_equal_to_a_subagent_id_is_direct(az: ModuleType) -> None:
    res = az.identity_analysis(window(tool(conversation_id=SUB)))
    assert res["direct_current_identity"] == {"conversation_id==subagent_id": 1}
    assert res["verdict_code"] == "CONFIRMED"


def test_subagent_id_matching_no_start_is_unclassified_not_direct(az: ModuleType) -> None:
    res = az.identity_analysis(
        window(tool(extra_keys={"subagent_id": "str"}, extra_ids={"subagent_id": "sub-ghost"}))
    )
    assert res["direct_current_identity"] == {}
    assert res["unclassified_identity_candidates"] == {"subagent_id": 1}
    assert res["verdict_code"] == "OPEN"


def test_partially_linked_subagent_id_is_not_promoted_to_direct(az: ModuleType) -> None:
    linked = tool(t=1400, extra_keys={"subagent_id": "str"}, extra_ids={"subagent_id": SUB})
    ghost = tool(t=1600, extra_keys={"subagent_id": "str"}, extra_ids={"subagent_id": "sub-ghost"})
    res = az.identity_analysis(window(linked, ghost))
    assert res["direct_current_identity"] == {}
    assert res["unclassified_identity_candidates"] == {"subagent_id": 2}
    assert res["verdict_code"] == "OPEN"


# --------------------------------------------------------------- role_only_identity


def test_subagent_type_alone_is_role_only(az: ModuleType) -> None:
    res = az.identity_analysis(
        window(tool(extra_keys={"subagent_type": "str"}, extra_ids={"subagent_type": "cf-writer"}))
    )
    assert res["role_only_identity"] == {"subagent_type": 1}
    assert res["direct_current_identity"] == {}
    assert res["verdict_code"] == "PARTIAL"


def test_role_only_never_reports_as_direct_even_with_other_role_keys(az: ModuleType) -> None:
    res = az.identity_analysis(window(tool(extra_keys={"agent_type": "str", "agent_role": "str"})))
    assert set(res["role_only_identity"]) == {"agent_type", "agent_role"}
    assert res["direct_current_identity"] == {}
    assert res["verdict_code"] == "PARTIAL"


# -------------------------------------------------------------- parent_only_identity


def test_parent_key_never_confirms_identity(az: ModuleType) -> None:
    res = az.identity_analysis(
        window(
            tool(
                extra_keys={"parent_conversation_id": "str", "parent_subagent_id": "str"},
                extra_ids={"parent_conversation_id": PARENT},
            )
        )
    )
    assert set(res["parent_only_identity"]) >= {"parent_conversation_id", "parent_subagent_id"}
    assert res["direct_current_identity"] == {}
    assert res["role_only_identity"] == {}
    assert res["verdict_code"] == "REFUTED"
    assert not res["verdict"].startswith(("CONFIRMED", "PARTIAL"))


def test_parent_conversation_id_on_tool_hook_equal_to_parent_is_parent_only(az: ModuleType) -> None:
    # No identity keys at all; the hook inside the window just shares the parent's conversation.
    res = az.identity_analysis(window(tool()))
    assert res["tool_events_inside_subagent_windows"] == 1
    assert res["parent_only_identity"] == {"conversation_id==parent_conversation_id": 1}
    assert res["direct_current_identity"] == {}
    assert res["verdict_code"] == "REFUTED"


# --------------------------------------------------- unclassified_identity_candidates


def test_undocumented_id_like_key_goes_to_unclassified_and_is_never_promoted(
    az: ModuleType,
) -> None:
    res = az.identity_analysis(
        window(tool(extra_keys={"agent_run_id": "str", "worker_uuid": "str", "session_id": "str"}))
    )
    assert set(res["unclassified_identity_candidates"]) == {
        "agent_run_id",
        "worker_uuid",
        "session_id",
    }
    assert res["direct_current_identity"] == {}
    assert res["role_only_identity"] == {}
    # the shared parent conversation is still reported, but the candidates win: OPEN, not REFUTED
    assert res["verdict_code"] == "OPEN"


def test_documented_tool_hook_keys_are_not_candidates(az: ModuleType) -> None:
    res = az.identity_analysis(window(tool(extra_keys={"agent_message": "str", "cwd": "str"})))
    assert res["unclassified_identity_candidates"] == {}


# ----------------------------------------------------------------------- mixed cases


def test_all_four_categories_are_reported_separately_in_a_mixed_capture(az: ModuleType) -> None:
    mixed = tool(
        extra_keys={
            "subagent_id": "str",
            "subagent_type": "str",
            "parent_conversation_id": "str",
            "agent_run_id": "str",
        },
        extra_ids={"subagent_id": SUB, "subagent_type": "cf-writer"},
    )
    res = az.identity_analysis(window(mixed))
    assert res["direct_current_identity"] == {"subagent_id": 1}
    assert res["role_only_identity"] == {"subagent_type": 1}
    assert "parent_conversation_id" in res["parent_only_identity"]
    assert res["unclassified_identity_candidates"] == {"agent_run_id": 1}
    assert res["verdict_code"] == "CONFIRMED"


def test_role_plus_parent_is_partial_with_parent_kept_apart(az: ModuleType) -> None:
    res = az.identity_analysis(
        window(tool(extra_keys={"subagent_type": "str", "parent_conversation_id": "str"}))
    )
    assert res["role_only_identity"] == {"subagent_type": 1}
    assert "parent_conversation_id" in res["parent_only_identity"]
    assert res["direct_current_identity"] == {}
    assert res["verdict_code"] == "PARTIAL"


def test_role_beats_unclassified_but_unclassified_beats_parent(az: ModuleType) -> None:
    role_and_unknown = az.identity_analysis(
        window(tool(extra_keys={"subagent_type": "str", "agent_run_id": "str"}))
    )
    assert role_and_unknown["verdict_code"] == "PARTIAL"
    unknown_and_parent = az.identity_analysis(
        window(tool(extra_keys={"parent_conversation_id": "str", "agent_run_id": "str"}))
    )
    assert unknown_and_parent["verdict_code"] == "OPEN"


# ------------------------------------------------------------------- verdict mapping


def buckets(**filled: dict[str, int]) -> dict[str, dict[str, int]]:
    return {
        name: dict(filled.get(name, {}))
        for name in (
            "direct_current_identity",
            "role_only_identity",
            "parent_only_identity",
            "unclassified_identity_candidates",
        )
    }


@pytest.mark.parametrize(
    ("filled", "starts", "in_win", "code"),
    [
        ({"direct_current_identity": {"subagent_id": 3}}, [1], 3, "CONFIRMED"),
        (
            {"direct_current_identity": {"subagent_id": 3}, "parent_only_identity": {"p": 1}},
            [1],
            3,
            "CONFIRMED",
        ),
        ({"role_only_identity": {"subagent_type": 3}}, [1], 3, "PARTIAL"),
        (
            {
                "role_only_identity": {"subagent_type": 3},
                "unclassified_identity_candidates": {"x_id": 1},
            },
            [1],
            3,
            "PARTIAL",
        ),
        ({"parent_only_identity": {"parent_conversation_id": 3}}, [1], 3, "REFUTED"),
        ({}, [1], 3, "REFUTED"),
        ({"unclassified_identity_candidates": {"x_id": 1}}, [1], 3, "OPEN"),
        (
            {"unclassified_identity_candidates": {"x_id": 1}, "parent_only_identity": {"p": 1}},
            [1],
            3,
            "OPEN",
        ),
        ({}, [], 0, "OPEN"),
        ({}, [1], 0, "OPEN"),
    ],
)
def test_verdict_mapping(
    az: ModuleType, filled: dict[str, dict[str, int]], starts: list[int], in_win: int, code: str
) -> None:
    got, text = az.identity_verdict(buckets(**filled), starts, in_win)
    assert got == code
    assert text.startswith(code + ":")
    assert "manual classification" in text
    assert "docs/empirical-test-plan.md row 8" in text


def test_verdict_text_says_it_is_a_hint(az: ModuleType) -> None:
    res = az.identity_analysis(window(tool(extra_keys={"subagent_type": "str"})))
    assert "hint only" in res["verdict"]
    assert "requires manual classification" in res["verdict"]


# -------------------------------------------------------------- robustness to odd data


def test_empty_and_non_subagent_captures_are_open_not_errors(az: ModuleType) -> None:
    assert az.identity_analysis([])["verdict_code"] == "OPEN"
    only_tools = az.identity_analysis([tool(), tool(t=1600)])
    assert only_tools["verdict_code"] == "OPEN"
    assert only_tools["subagent_starts"] == 0


def test_start_without_tool_hooks_in_a_window_is_open(az: ModuleType) -> None:
    res = az.identity_analysis([start(), stop()])
    assert res["verdict_code"] == "OPEN"


def test_odd_records_do_not_raise(az: ModuleType) -> None:
    odd: list[Any] = [
        "not a dict",
        None,
        {"hook_event_name": "subagentStart"},  # no ids, no time
        {"hook_event_name": "subagentStart", "ids": ["x"], "start_epoch_ms": "soon"},
        {"hook_event_name": "subagentStop", "ids": None, "start_epoch_ms": True},
        {"hook_event_name": "preToolUse", "keys": "oops", "ids": {"conversation_id": ["a"]}},
        {
            "hook_event_name": "preToolUse",
            "keys": {"subagent_id": "str", 7: "int"},
            "ids": {"subagent_id": {"a": 1}},
        },
        {
            "hook_event_name": "postToolUse",
            "keys": {"<odd-key>": "str", "agent_run_id": "str"},
            "ids": {"subagent_id": 5},
        },
        {"hook_event_name": "preToolUse", "start_epoch_ms": None},
    ]
    res = az.identity_analysis(odd)
    assert res["verdict_code"] in {"OPEN", "PARTIAL", "REFUTED", "CONFIRMED"}
    assert res["direct_current_identity"] == {}
    assert "agent_run_id" in res["unclassified_identity_candidates"]
    assert res["verdict_code"] == "OPEN"


# ------------------------------------------------------- end to end (text and JSON)


def write_capture(tmp_path: Path, records: list[Rec]) -> Path:
    lines = [json.dumps(r) for r in records]
    lines.insert(1, '{"torn": ')  # a torn line must be skipped, not fatal
    path = tmp_path / "captures.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_render_and_json_list_all_four_categories(
    az: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    records = window(tool(extra_keys={"subagent_type": "str", "parent_conversation_id": "str"}))
    path = write_capture(tmp_path, records)

    analysis = az.analyze(str(path))
    assert analysis["corrupt_lines_skipped"] == 1
    text = az.render(analysis)
    for name in (
        "direct_current_identity",
        "role_only_identity",
        "parent_only_identity",
        "unclassified_identity_candidates",
    ):
        assert name in text
        assert name in analysis["agent_identity"]
    assert "VERDICT: PARTIAL" in text
    assert "manual classification" in text

    assert az.main(["analyze.py", str(path), "--json"]) == 0
    printed = json.loads(capsys.readouterr().out)
    identity = printed["agent_identity"]
    assert identity["verdict_code"] == "PARTIAL"
    assert identity["role_only_identity"] == {"subagent_type": 1}
    assert identity["direct_current_identity"] == {}


def test_load_tolerates_odd_timestamps(az: ModuleType, tmp_path: Path) -> None:
    lines = [
        json.dumps({"hook_event_name": "stop", "start_epoch_ms": "later"}),
        json.dumps({"hook_event_name": "stop", "start_epoch_ms": 5}),
        json.dumps({"hook_event_name": "stop"}),
        json.dumps([1, 2]),
    ]
    path = tmp_path / "captures.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _, recs, bad = az.load(str(path))
    assert len(recs) == 3
    assert bad == 1
