from __future__ import annotations

import json
from pathlib import Path

import pytest

from cursorfleet.adapters.cursor.hook_policy import (
    ALLOWED_V01_HOOKS,
    FORBIDDEN_HOOKS,
    PERMISSION_HOOKS,
    UNREGISTERED_V01_HOOKS,
    fail_open_response,
    is_registrable,
)

SPIKE_HOOKS_EXAMPLE = Path(__file__).resolve().parents[2] / "spike" / "hooks.json.example"


def test_forbidden_hooks_exact_set() -> None:
    assert {
        "afterAgentThought",
        "afterAgentResponse",
        "beforeSubmitPrompt",
        "beforeReadFile",
    } == FORBIDDEN_HOOKS


def test_allowed_hooks_are_the_twelve_passive_hooks() -> None:
    assert len(ALLOWED_V01_HOOKS) == 12
    assert {"sessionStart", "stop", "afterFileEdit", "preCompact"} <= ALLOWED_V01_HOOKS


def test_allowed_and_forbidden_do_not_overlap() -> None:
    assert ALLOWED_V01_HOOKS.isdisjoint(FORBIDDEN_HOOKS)
    assert ALLOWED_V01_HOOKS.isdisjoint(UNREGISTERED_V01_HOOKS)
    assert FORBIDDEN_HOOKS.isdisjoint(UNREGISTERED_V01_HOOKS)


@pytest.mark.parametrize("hook", sorted(FORBIDDEN_HOOKS | UNREGISTERED_V01_HOOKS))
def test_not_registrable(hook: str) -> None:
    assert not is_registrable(hook)


@pytest.mark.parametrize("hook", sorted(ALLOWED_V01_HOOKS))
def test_registrable(hook: str) -> None:
    assert is_registrable(hook)


def test_permission_hooks_are_registered_hooks() -> None:
    assert PERMISSION_HOOKS <= ALLOWED_V01_HOOKS


@pytest.mark.parametrize("hook", sorted(ALLOWED_V01_HOOKS))
def test_fail_open_response_is_valid_json_and_never_blocks(hook: str) -> None:
    reply = json.loads(fail_open_response(hook))
    if hook in PERMISSION_HOOKS:
        assert reply == {"permission": "allow"}
    else:
        assert reply == {}


def test_spike_example_registers_exactly_the_allowed_hooks() -> None:
    declared = set(json.loads(SPIKE_HOOKS_EXAMPLE.read_text("utf-8"))["hooks"])
    assert declared == ALLOWED_V01_HOOKS
    assert declared.isdisjoint(FORBIDDEN_HOOKS)
