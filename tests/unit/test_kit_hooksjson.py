from __future__ import annotations

import json

import pytest

from cursorfleet.adapters.cursor import hooksjson
from cursorfleet.adapters.cursor.hook_policy import ALLOWED_V01_HOOKS, FORBIDDEN_HOOKS

ALL = sorted(ALLOWED_V01_HOOKS)


def test_entry_is_exactly_the_contract() -> None:
    assert hooksjson.managed_entry() == {"command": "cursorfleet-hook", "timeout": 5}


def test_new_file_registers_exactly_allowed_hooks_without_matcher_or_fail_closed() -> None:
    result = hooksjson.merge(None, ALL)
    data = json.loads(result.text)
    assert data["version"] == 1
    assert set(data["hooks"]) == ALLOWED_V01_HOOKS
    for entries in data["hooks"].values():
        assert entries == [{"command": "cursorfleet-hook", "timeout": 5}]
    assert not (set(data["hooks"]) & FORBIDDEN_HOOKS)
    assert "failClosed" not in result.text
    assert "matcher" not in result.text


@pytest.mark.parametrize("name", [*sorted(FORBIDDEN_HOOKS), "workspaceOpen", "madeUp"])
def test_refuses_forbidden_and_unknown_hooks(name: str) -> None:
    with pytest.raises(hooksjson.HooksJsonError):
        hooksjson.merge(None, ["stop", name])
    with pytest.raises(hooksjson.HooksJsonError):
        hooksjson.assert_registrable([name])


def test_preserves_user_entries_other_keys_and_order() -> None:
    original = json.dumps(
        {
            "extra": {"keep": True},
            "version": 1,
            "hooks": {
                "stop": [{"command": "./mine.sh", "failClosed": True}],
                "beforeSubmitPrompt": [{"command": "./theirs.sh"}],
            },
        },
        indent=2,
    )
    merged = hooksjson.merge(original + "\n", ["stop", "preToolUse"])
    data = json.loads(merged.text)
    assert list(data) == ["extra", "version", "hooks"]
    assert data["hooks"]["stop"][0] == {"command": "./mine.sh", "failClosed": True}
    assert data["hooks"]["stop"][1] == {"command": "cursorfleet-hook", "timeout": 5}
    assert data["hooks"]["beforeSubmitPrompt"] == [{"command": "./theirs.sh"}]  # not ours to touch
    assert merged.reproducible


def test_merge_is_idempotent() -> None:
    first = hooksjson.merge(None, ALL)
    second = hooksjson.merge(
        first.text,
        ALL,
        previous=first.state.entries,
        previous_state=first.state,
    )
    assert second.text == first.text
    assert not second.conflicts


def test_unmerge_restores_original_bytes_for_common_styles() -> None:
    for indent in (2, 4, None):
        original = json.dumps({"version": 1, "hooks": {"stop": [{"command": "x"}]}}, indent=indent)
        original += "\n"
        merged = hooksjson.merge(original, ALL)
        assert merged.reproducible
        result = hooksjson.unmerge(merged.text, merged.state, merged.style, created=False)
        assert result.text == original


def test_unmerge_removes_added_version_and_hooks_key() -> None:
    original = '{\n  "other": 1\n}\n'
    merged = hooksjson.merge(original, ["stop"])
    result = hooksjson.unmerge(merged.text, merged.state, merged.style, created=False)
    assert result.text == original


def test_created_file_becomes_empty_on_unmerge() -> None:
    merged = hooksjson.merge(None, ALL)
    result = hooksjson.unmerge(merged.text, merged.state, merged.style, created=True)
    assert result.now_empty


def test_modified_own_entry_is_conflict_and_drift() -> None:
    first = hooksjson.merge(None, ["stop"])
    tampered = first.text.replace('"timeout": 5', '"timeout": 99')
    again = hooksjson.merge(
        tampered, ["stop"], previous=first.state.entries, previous_state=first.state
    )
    assert again.conflicts
    result = hooksjson.unmerge(tampered, first.state, first.style, created=True)
    assert result.drift and not result.now_empty
    forced = hooksjson.unmerge(tampered, first.state, first.style, created=True, force=True)
    assert forced.now_empty


def test_shrinking_enabled_hooks_removes_stale_entries() -> None:
    first = hooksjson.merge(None, ["stop", "sessionStart"])
    second = hooksjson.merge(
        first.text, ["stop"], previous=first.state.entries, previous_state=first.state
    )
    assert set(json.loads(second.text)["hooks"]) == {"stop"}


@pytest.mark.parametrize(
    "text",
    ["not json", "[]", '{"hooks": []}', '{"hooks": {"stop": {}}}', '{"version": 2}'],
)
def test_invalid_or_unsupported_files_are_refused(text: str) -> None:
    with pytest.raises(hooksjson.HooksJsonError):
        hooksjson.merge(text, ["stop"])


def test_duplicate_own_entries_conflict() -> None:
    text = json.dumps({"version": 1, "hooks": {"stop": [{"command": "cursorfleet-hook"}] * 2}})
    assert hooksjson.merge(text, ["stop"]).conflicts


def test_crlf_and_unusual_format_round_trip_via_style() -> None:
    original = '{\r\n  "version": 1,\r\n  "hooks": {}\r\n}\r\n'
    merged = hooksjson.merge(original, ["stop"])
    assert merged.reproducible and "\r\n" in merged.text
    assert (
        hooksjson.unmerge(merged.text, merged.state, merged.style, created=False).text == original
    )
