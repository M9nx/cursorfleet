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


def start(
    sub_id: str = SUB,
    kind: str = "cf-writer",
    t: float = 1000,
    extra_ids: dict[str, Any] | None = None,
) -> Rec:
    ids = {"subagent_id": sub_id, "subagent_type": kind, "parent_conversation_id": PARENT}
    ids.update(extra_ids or {})
    keys = {"subagent_id": "str", "subagent_type": "str", "parent_conversation_id": "str"}
    for k in extra_ids or {}:
        keys[k] = "str"
    return rec("subagentStart", t, ids, keys)


def stop(kind: str = "cf-writer", t: float = 2000, extra_ids: dict[str, Any] | None = None) -> Rec:
    ids: dict[str, Any] = {"subagent_type": kind}
    ids.update(extra_ids or {})
    keys = {"subagent_type": "str"}
    for k in extra_ids or {}:
        keys[k] = "str"
    return rec("subagentStop", t, ids, keys)


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
        window(tool(extra_keys={"agent_run_id": "str", "worker_uuid": "str"}))
    )
    assert set(res["unclassified_identity_candidates"]) == {
        "agent_run_id",
        "worker_uuid",
    }
    assert res["direct_current_identity"] == {}
    assert res["role_only_identity"] == {}
    # the shared parent conversation is still reported, but the candidates win: OPEN, not REFUTED
    assert res["verdict_code"] == "OPEN"


def test_session_id_is_session_correlation_not_agent_identity(az: ModuleType) -> None:
    res = az.identity_analysis(
        window(
            tool(
                extra_keys={"session_id": "str"},
                extra_ids={"session_id": "ses_synthetic_1"},
            )
        )
    )
    for bucket in (
        "direct_current_identity",
        "role_only_identity",
        "parent_only_identity",
        "unclassified_identity_candidates",
    ):
        assert "session_id" not in res[bucket]
    assert az.classify_key("session_id", "preToolUse") is None
    assert az.classify_key("session_id", "sessionStart") is None
    sc = res["session_correlation"]
    assert "not agent identity" in sc["note"]
    tool_vs_conv = sc["tool_session_id_vs_tool_conversation_id"]
    assert tool_vs_conv["observed"] == 1
    assert tool_vs_conv["comparable"] == 1
    assert tool_vs_conv["mismatches"] == 1  # ses_synthetic_1 != conv-main
    # parent conversation only; session_id is not a candidate
    assert res["verdict_code"] == "REFUTED"


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


# -------------------------------- parent_tool_call_id is a link candidate


TC = "tc_synthetic_1"
CHILD = "ses_synthetic_child"
SUB_B = "sub-synthetic-b"
TC_B = "tc_synthetic_2"
CHILD_B = "ses_synthetic_child_b"


def linked_start(
    sub_id: str = SUB, kind: str = "cf-writer", t: float = 1000, tool_call_id: str = TC
) -> Rec:
    return start(sub_id=sub_id, kind=kind, t=t, extra_ids={"tool_call_id": tool_call_id})


def linked_stop(
    kind: str = "cf-writer",
    t: float = 2000,
    subagent_id: str | None = None,
    child_conversation_id: str | None = None,
) -> Rec:
    extra: dict[str, Any] = {}
    if subagent_id is not None:
        extra["subagent_id"] = subagent_id
    if child_conversation_id is not None:
        extra["child_conversation_id"] = child_conversation_id
    return stop(kind=kind, t=t, extra_ids=extra or None)


def inner_tool(
    t: float = 1500,
    conversation_id: str = CHILD,
    parent_tool_call_id: str | None = TC,
) -> Rec:
    extra_keys = {"parent_tool_call_id": "str"} if parent_tool_call_id is not None else {}
    extra_ids: dict[str, Any] = {}
    if parent_tool_call_id is not None:
        extra_ids["parent_tool_call_id"] = parent_tool_call_id
    return tool(
        t=t,
        conversation_id=conversation_id,
        extra_keys=extra_keys,
        extra_ids=extra_ids,
    )


def test_parent_tool_call_id_is_unclassified_not_parent_only_or_exact(az: ModuleType) -> None:
    recs = [linked_start(), inner_tool(), linked_stop(subagent_id=TC, child_conversation_id=CHILD)]
    res = az.identity_analysis(recs)
    assert "parent_tool_call_id" in res["unclassified_identity_candidates"]
    assert "parent_tool_call_id" not in res["parent_only_identity"]
    assert "parent_tool_call_id" not in res["direct_current_identity"]
    assert res["verdict_code"] == "OPEN"
    assert (
        az.classify_key("parent_tool_call_id", "preToolUse") == "unclassified_identity_candidates"
    )
    assert az.classify_key("parent_conversation_id", "preToolUse") == "parent_only_identity"


def test_parent_conversation_id_still_parent_only_when_tool_call_candidate_absent(
    az: ModuleType,
) -> None:
    assert az.classify_key("parent_subagent_id", "preToolUse") == "parent_only_identity"


# -------------------------------- linkage evidence (matches / mismatches / unavailable)


def _link(res: dict[str, Any], name: str) -> dict[str, int]:
    return res["linkage"][name]  # type: ignore[no-any-return]


def test_task_tool_use_id_equals_subagent_start_tool_call_id(az: ModuleType) -> None:
    task = tool(
        t=900,
        extra_ids={"tool_name": "Task", "tool_use_id": TC},
        extra_keys={"tool_name": "str"},
    )
    recs = [task, linked_start(), linked_stop()]
    res = az.identity_analysis(recs)
    ev = _link(res, "task_tool_use_id_vs_subagentStart_tool_call_id")
    assert ev["observed"] == 1
    assert ev["comparable"] == 1
    assert ev["matches"] == 1
    assert ev["mismatches"] == 0
    assert ev["unavailable"] == 0
    assert ev["collisions"] == 0
    assert res["task_tool_events"] == 1


def test_inner_parent_tool_call_id_equals_subagent_start_tool_call_id(az: ModuleType) -> None:
    recs = [linked_start(), inner_tool(), linked_stop(child_conversation_id=CHILD)]
    res = az.identity_analysis(recs)
    ev = _link(res, "innerTool_parent_tool_call_id_vs_subagentStart_tool_call_id")
    assert ev["comparable"] == 1
    assert ev["matches"] == 1
    assert ev["unavailable"] == 0
    assert res["inner_tool_association"]["parent_tool_call_id"] == 1
    assert res["tool_events_inside_subagent_windows"] == 1


def test_stop_subagent_id_equals_start_subagent_id_and_tool_call_id(az: ModuleType) -> None:
    match_sid = az.identity_analysis(
        [linked_start(), linked_stop(subagent_id=SUB, child_conversation_id=CHILD)]
    )
    sid_vs_sid = _link(match_sid, "subagentStop_subagent_id_vs_subagentStart_subagent_id")
    sid_vs_call = _link(match_sid, "subagentStop_subagent_id_vs_subagentStart_tool_call_id")
    assert sid_vs_sid["matches"] == 1
    assert sid_vs_sid["mismatches"] == 0
    assert sid_vs_call["mismatches"] == 1
    assert sid_vs_call["matches"] == 0
    assert match_sid["windows_paired_by_subagent_id"] == 1

    match_call = az.identity_analysis(
        [linked_start(), linked_stop(subagent_id=TC, child_conversation_id=CHILD)]
    )
    sid_vs_sid = _link(match_call, "subagentStop_subagent_id_vs_subagentStart_subagent_id")
    sid_vs_call = _link(match_call, "subagentStop_subagent_id_vs_subagentStart_tool_call_id")
    assert sid_vs_sid["mismatches"] == 1
    assert sid_vs_sid["matches"] == 0
    assert sid_vs_call["matches"] == 1
    assert match_call["windows_paired_by_subagent_id"] == 1


def test_inner_conversation_id_equals_stop_child_conversation_id(az: ModuleType) -> None:
    recs = [
        linked_start(),
        inner_tool(parent_tool_call_id=None),
        linked_stop(child_conversation_id=CHILD),
    ]
    res = az.identity_analysis(recs)
    ev = _link(res, "innerTool_conversation_id_vs_subagentStop_child_conversation_id")
    assert ev["matches"] == 1
    assert ev["unavailable"] == 0
    assert res["inner_tool_association"]["child_conversation_id"] == 1
    assert res["tool_events_inside_subagent_windows"] == 1
    assert "conversation_id==parent_conversation_id" not in res["parent_only_identity"]
    assert res["tool_conversation_id_relation"] == {
        "conversation_id==subagentStop.child_conversation_id": 1
    }


# -------------------------------- missing fields and pairing fallback


def test_missing_optional_stop_fields_fall_back_to_type_order(az: ModuleType) -> None:
    recs = [start(), tool(), stop()]
    res = az.identity_analysis(recs)
    assert res["windows_paired_by_type_order"] == 1
    assert res["windows_paired_by_subagent_id"] == 0
    # start() has no tool_call_id; stop() has no subagent_id / child_conversation_id
    stop_vs_sid = _link(res, "subagentStop_subagent_id_vs_subagentStart_subagent_id")
    stop_vs_call = _link(res, "subagentStop_subagent_id_vs_subagentStart_tool_call_id")
    ptc = _link(res, "innerTool_parent_tool_call_id_vs_subagentStart_tool_call_id")
    child = _link(res, "innerTool_conversation_id_vs_subagentStop_child_conversation_id")
    assert stop_vs_sid["unavailable"] == 1 and stop_vs_sid["matches"] == 0
    assert stop_vs_call["unavailable"] == 1 and stop_vs_call["comparable"] == 0
    assert ptc["unavailable"] == 1 and ptc["comparable"] == 0
    assert child["unavailable"] == 1 and child["comparable"] == 0
    assert res["tool_events_inside_subagent_windows"] == 1
    assert res["inner_tool_association"]["temporal"] == 1
    assert res["temporal_association_is_not_exact"] is True


def test_stop_with_nonmatching_subagent_id_is_not_stolen_by_type_order(az: ModuleType) -> None:
    recs = [
        linked_start(sub_id=SUB, tool_call_id=TC),
        linked_stop(subagent_id="sub_synthetic_other"),
    ]
    res = az.identity_analysis(recs)
    assert res["windows_paired_by_subagent_id"] == 0
    assert res["windows_paired_by_type_order"] == 0
    assert res["windows_without_matching_stop"] == 1


def test_pairing_prefers_matching_subagent_id_over_type_order(az: ModuleType) -> None:
    # Same type, crossed times: id pairing still attaches the matching stop.
    recs = [
        linked_start(sub_id=SUB, t=1000, tool_call_id=TC),
        linked_start(sub_id=SUB_B, kind="cf-writer", t=1100, tool_call_id=TC_B),
        linked_stop(t=1800, subagent_id=SUB_B, child_conversation_id=CHILD_B),
        linked_stop(t=1900, subagent_id=SUB, child_conversation_id=CHILD),
    ]
    windows, collisions = az.pair_start_stop(
        [r for r in recs if r["hook_event_name"] == "subagentStart"],
        [r for r in recs if r["hook_event_name"] == "subagentStop"],
    )
    assert collisions == 0
    assert windows[0]["stop_subagent_id"] == SUB
    assert windows[0]["child_conversation_id"] == CHILD
    assert windows[0]["pair_method"] == "subagent_id"
    assert windows[1]["stop_subagent_id"] == SUB_B
    assert windows[1]["pair_method"] == "subagent_id"


# -------------------------------- collisions and ambiguous links


def test_duplicate_start_tool_call_id_is_ambiguous_not_unique_link(az: ModuleType) -> None:
    recs = [
        linked_start(sub_id=SUB, t=1000, tool_call_id=TC),
        linked_start(sub_id=SUB_B, kind="cf-reviewer", t=1100, tool_call_id=TC),
        inner_tool(t=1500),
        linked_stop(kind="cf-writer", t=2000, subagent_id=SUB, child_conversation_id=CHILD),
        linked_stop(kind="cf-reviewer", t=2100, subagent_id=SUB_B, child_conversation_id=CHILD_B),
    ]
    res = az.identity_analysis(recs)
    assert res["ambiguous_links"].get("ambiguous_parent_tool_call_id") == 1
    # child conversation is unique, so association falls through and still links
    assert res["inner_tool_association"].get("child_conversation_id") == 1
    assert "parent_tool_call_id" in res["unclassified_identity_candidates"]
    assert res["verdict_code"] == "OPEN"
    ptc = _link(res, "innerTool_parent_tool_call_id_vs_subagentStart_tool_call_id")
    assert ptc["collisions"] == 1
    assert ptc["matches"] == 0
    assert ptc["comparable"] == 1


def test_shared_child_conversation_id_is_ambiguous(az: ModuleType) -> None:
    recs = [
        linked_start(sub_id=SUB, t=1000, tool_call_id=TC),
        linked_start(sub_id=SUB_B, kind="cf-reviewer", t=1100, tool_call_id=TC_B),
        inner_tool(t=1500, parent_tool_call_id=None),
        linked_stop(kind="cf-writer", t=2000, child_conversation_id=CHILD),
        linked_stop(kind="cf-reviewer", t=2100, child_conversation_id=CHILD),
    ]
    res = az.identity_analysis(recs)
    assert res["ambiguous_links"].get("ambiguous_child_conversation_id") == 1
    # overlapping sequential windows: 1500 is inside both 1000-2000 and 1100-2100
    assert res["ambiguous_links"].get("ambiguous_temporal") == 1
    assert res["tool_events_inside_subagent_windows"] == 0
    assert res["inner_tool_association"].get("unassociated") == 1


def test_overlapping_windows_without_ids_do_not_silently_count_as_exact(az: ModuleType) -> None:
    recs = [
        start(sub_id=SUB, kind="cf-writer", t=1000),
        start(sub_id=SUB_B, kind="cf-reviewer", t=1100),
        tool(t=1500, conversation_id=PARENT),
        stop(kind="cf-writer", t=2000),
        stop(kind="cf-reviewer", t=2100),
    ]
    res = az.identity_analysis(recs)
    assert res["tool_events_inside_subagent_windows"] == 0
    assert res["ambiguous_links"].get("ambiguous_temporal") == 1
    assert res["direct_current_identity"] == {}
    assert res["temporal_association_is_not_exact"] is True
    assert res["verdict_code"] == "OPEN"


def test_association_prefers_parent_tool_call_id_over_child_and_temporal(
    az: ModuleType,
) -> None:
    # Child conversation and time would point at window B; parent_tool_call_id points at A.
    recs = [
        linked_start(sub_id=SUB, t=1000, tool_call_id=TC),
        linked_start(sub_id=SUB_B, kind="cf-reviewer", t=3000, tool_call_id=TC_B),
        inner_tool(t=3500, conversation_id=CHILD_B, parent_tool_call_id=TC),
        linked_stop(kind="cf-writer", t=2000, subagent_id=TC, child_conversation_id=CHILD),
        linked_stop(kind="cf-reviewer", t=4000, subagent_id=TC_B, child_conversation_id=CHILD_B),
    ]
    res = az.identity_analysis(recs)
    assert res["inner_tool_association"] == {"parent_tool_call_id": 1}
    assert res["tool_events_inside_subagent_windows"] == 1
    assert res["temporal_association_is_not_exact"] is True
    assert res["verdict_code"] == "OPEN"


def test_child_conversation_beats_temporal_when_parent_tool_call_id_missing(
    az: ModuleType,
) -> None:
    recs = [
        linked_start(sub_id=SUB, t=1000, tool_call_id=TC),
        linked_start(sub_id=SUB_B, kind="cf-reviewer", t=3000, tool_call_id=TC_B),
        inner_tool(t=3500, conversation_id=CHILD, parent_tool_call_id=None),
        linked_stop(kind="cf-writer", t=2000, child_conversation_id=CHILD),
        linked_stop(kind="cf-reviewer", t=4000, child_conversation_id=CHILD_B),
    ]
    res = az.identity_analysis(recs)
    assert res["inner_tool_association"] == {"child_conversation_id": 1}
    assert res["tool_events_inside_subagent_windows"] == 1


def test_inner_child_conversation_is_not_parent_only(az: ModuleType) -> None:
    recs = [linked_start(), inner_tool(), linked_stop(child_conversation_id=CHILD)]
    res = az.identity_analysis(recs)
    assert res["parent_only_identity"] == {}
    assert res["unclassified_identity_candidates"] == {"parent_tool_call_id": 1}
    assert res["verdict_code"] == "OPEN"
    assert "hint only" in res["verdict"]


def test_pairing_id_collision_is_counted(az: ModuleType) -> None:
    recs = [
        linked_start(sub_id=SUB, t=1000, tool_call_id=TC),
        linked_stop(t=1800, subagent_id=TC),
        linked_stop(t=1900, subagent_id=TC),
    ]
    res = az.identity_analysis(recs)
    assert res["pairing_id_collisions"] == 1
    assert res["windows_paired_by_subagent_id"] == 1
    assert res["windows_without_matching_stop"] == 0
    stop_vs_call = _link(res, "subagentStop_subagent_id_vs_subagentStart_tool_call_id")
    # one unique start tool_call_id: each stop is a match; pairing_id_collisions is separate
    assert stop_vs_call["matches"] == 2
    assert stop_vs_call["collisions"] == 0


def test_linkage_mismatch_when_ids_differ(az: ModuleType) -> None:
    recs = [
        linked_start(),
        inner_tool(parent_tool_call_id="tc_synthetic_other"),
        linked_stop(subagent_id="sub_synthetic_other", child_conversation_id="ses_synthetic_other"),
    ]
    res = az.identity_analysis(recs)
    ptc = _link(res, "innerTool_parent_tool_call_id_vs_subagentStart_tool_call_id")
    stop_vs_sid = _link(res, "subagentStop_subagent_id_vs_subagentStart_subagent_id")
    child = _link(res, "innerTool_conversation_id_vs_subagentStop_child_conversation_id")
    start_pair = _link(res, "subagentStart_subagent_id_vs_subagentStart_tool_call_id")
    assert ptc["comparable"] == 1 and ptc["mismatches"] == 1 and ptc["unavailable"] == 0
    assert stop_vs_sid["comparable"] == 1 and stop_vs_sid["mismatches"] == 1
    assert child["comparable"] == 1 and child["mismatches"] == 1
    # same-record start ids differ (sub-1 vs tc_synthetic_1)
    assert start_pair["comparable"] == 1 and start_pair["mismatches"] == 1


def test_old_capture_missing_new_id_fields_is_unavailable_not_zero_matches(
    az: ModuleType,
) -> None:
    # Pre-allowlist capture: start has tool_call_id, inner tool and stop lack the new fields.
    recs = [linked_start(), tool(t=1500, conversation_id=PARENT), linked_stop()]
    res = az.identity_analysis(recs)
    ptc = _link(res, "innerTool_parent_tool_call_id_vs_subagentStart_tool_call_id")
    child = _link(res, "innerTool_conversation_id_vs_subagentStop_child_conversation_id")
    stop_sid = _link(res, "subagentStop_subagent_id_vs_subagentStart_subagent_id")
    assert ptc["observed"] == 1
    assert ptc["unavailable"] == 1
    assert ptc["comparable"] == 0
    assert ptc["matches"] == 0
    assert child["unavailable"] == 1
    assert child["comparable"] == 0
    assert child["matches"] == 0
    assert stop_sid["unavailable"] == 1
    assert "unavailable" in res["linkage_note"]


def test_mixed_old_and_new_captures_split_unavailable_from_matches(az: ModuleType) -> None:
    old_inner = tool(t=1400, conversation_id=CHILD)
    new_inner = inner_tool(t=1600)
    recs = [
        linked_start(),
        old_inner,
        new_inner,
        linked_stop(subagent_id=SUB, child_conversation_id=CHILD),
    ]
    res = az.identity_analysis(recs)
    ptc = _link(res, "innerTool_parent_tool_call_id_vs_subagentStart_tool_call_id")
    child = _link(res, "innerTool_conversation_id_vs_subagentStop_child_conversation_id")
    assert ptc["observed"] == 2
    assert ptc["unavailable"] == 1
    assert ptc["matches"] == 1
    assert ptc["mismatches"] == 0
    assert ptc["comparable"] == 1
    assert child["observed"] == 2
    assert child["matches"] == 2
    assert child["unavailable"] == 0


def test_render_lists_unavailable_not_a_zero_match_refutation(
    az: ModuleType, tmp_path: Path
) -> None:
    path = write_capture(tmp_path, [linked_start(), tool(), linked_stop()])
    text = az.render(az.analyze(str(path)))
    assert "unavailable" in text
    assert "session_correlation" in text
    assert "not Q1 identity" in text or "not agent identity" in text
    assert "missing = unavailable" in text


# -------------------------------- capture_hook ID allowlist (synthetic only)


def _load_capture_hook() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "spike_capture_hook", SPIKE_DIR / "capture_hook.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _record(ch: ModuleType, payload: dict[str, Any]) -> dict[str, Any]:
    rec, _event = ch.build_record(payload, None, 0, False, True, 0.0, "unused-cap-dir", "env")
    return rec  # type: ignore[no-any-return]


def test_capture_hook_retains_only_scalar_new_ids() -> None:
    ch = _load_capture_hook()
    assert "parent_tool_call_id" in ch.ID_FIELDS
    assert "child_conversation_id" in ch.ID_FIELDS
    payload = {
        "hook_event_name": "preToolUse",
        "parent_tool_call_id": "tc_synthetic_ok",
        "child_conversation_id": "ses_synthetic_ok",
        "tool_call_id": "tc_synthetic_start",
        "subagent_id": "sub_synthetic_1",
        "task": "synthetic prompt text about quarterly layoffs",
        "prompt": "synthetic chain of thought about the password",
        "tool_input": {"command": "cat /home/alice-synthetic/private/secret"},
        "tool_output": "file contents of quarterly.xlsx",
        "user_email": "alice.synthetic@example.com",
        "file_path": "/home/alice-synthetic/private/.env",
    }
    rec = _record(ch, payload)
    ids = rec["ids"]
    assert ids["parent_tool_call_id"] == "tc_synthetic_ok"
    assert ids["child_conversation_id"] == "ses_synthetic_ok"
    assert ids["tool_call_id"] == "tc_synthetic_start"
    assert ids["subagent_id"] == "sub_synthetic_1"
    dumped = json.dumps(rec)
    for leaked in (
        "quarterly layoffs",
        "chain of thought",
        "alice-synthetic",
        "alice.synthetic@example.com",
        "/home/alice-synthetic",
        "quarterly.xlsx",
        "cat /home",
    ):
        assert leaked not in dumped
    for banned in ("task", "prompt", "tool_input", "tool_output", "user_email", "file_path"):
        assert banned not in ids


def test_capture_hook_rejects_invalid_oversized_and_non_string_new_ids() -> None:
    ch = _load_capture_hook()
    cases = [
        {"parent_tool_call_id": "alice.synthetic@example.com"},
        {"parent_tool_call_id": "tc synthetic spaces"},
        {"parent_tool_call_id": "x" * 129},
        {"parent_tool_call_id": 12345},
        {"parent_tool_call_id": {"wrapped": "tc_synthetic_nested"}},
        {"child_conversation_id": ["ses_synthetic_list"]},
        {"child_conversation_id": None},
    ]
    for extra in cases:
        rec = _record(ch, {"hook_event_name": "subagentStop", **extra})
        key = next(iter(extra))
        if extra[key] is None:
            assert rec["ids"][key] is None
        else:
            assert rec["ids"][key] == "<invalid>"
        dumped = json.dumps(rec)
        assert "tc_synthetic_nested" not in dumped
        assert "ses_synthetic_list" not in dumped
        assert "alice.synthetic@example.com" not in dumped


def test_capture_hook_selftest_covers_new_ids() -> None:
    ch = _load_capture_hook()
    assert ch.selftest() == 0
