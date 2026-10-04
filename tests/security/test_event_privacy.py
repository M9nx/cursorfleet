from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pydantic import BaseModel, ValidationError

import cursorfleet
from cursorfleet.events.forbidden import FORBIDDEN_EVENT_FIELD_NAMES
from cursorfleet.events.kinds import EventKind
from cursorfleet.events.models import Event, GateRef, Metrics, SanitizedCommand, SanitizedPath
from event_factory import valid_event

MODELS: list[type[BaseModel]] = [Event, SanitizedCommand, SanitizedPath, GateRef, Metrics]
KNOWN_TOP_LEVEL = set(Event.model_fields)
HOOK_PAYLOAD_NAMES = [
    "afterAgentThought",
    "afterAgentResponse",
    "beforeSubmitPrompt",
    "beforeReadFile",
]
JSON_SCALARS = st.one_of(
    st.none(), st.booleans(), st.integers(), st.text(max_size=40), st.floats(allow_nan=False)
)
JSON_VALUES = st.recursive(
    JSON_SCALARS,
    lambda inner: st.one_of(
        st.lists(inner, max_size=3), st.dictionaries(st.text(max_size=10), inner, max_size=3)
    ),
    max_leaves=6,
)
_SETTINGS = settings(
    max_examples=200, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)


def test_no_model_declares_a_forbidden_field() -> None:
    for model in MODELS:
        leaked = set(model.model_fields) & FORBIDDEN_EVENT_FIELD_NAMES
        assert not leaked, f"{model.__name__} declares forbidden fields: {sorted(leaked)}"


def test_no_event_kind_names_thoughts_prompts_or_responses() -> None:
    for kind in EventKind:
        for word in ("thought", "thinking", "prompt", "response", "reasoning", "transcript"):
            assert word not in kind.value


@pytest.mark.parametrize("model", MODELS)
def test_every_model_forbids_extras(model: type[BaseModel]) -> None:
    assert model.model_config.get("extra") == "forbid"


@_SETTINGS
@given(key=st.text(min_size=1, max_size=30), value=JSON_VALUES)
def test_arbitrary_extra_top_level_key_cannot_be_smuggled(key: str, value: Any) -> None:
    if key in KNOWN_TOP_LEVEL:
        return
    data = valid_event()
    data[key] = value
    with pytest.raises(ValidationError):
        Event.model_validate(data)


@_SETTINGS
@given(
    key=st.one_of(st.sampled_from(sorted(FORBIDDEN_EVENT_FIELD_NAMES)), st.text(max_size=20)),
    value=JSON_VALUES,
    where=st.sampled_from(["command", "metrics", "paths", "gate", "top"]),
)
def test_forbidden_field_cannot_be_smuggled_at_any_depth(key: str, value: Any, where: str) -> None:
    data = valid_event()
    data["gate"] = None
    if where == "top":
        if key in KNOWN_TOP_LEVEL:
            return
        data[key] = value
    elif where == "paths":
        if key in {"path", "op"}:
            return
        data["paths"][0][key] = value
    else:
        target = data.get(where) or {}
        if where == "gate":
            target = {"name": "tests", "state": "passing"}
            data["kind"] = "gate.changed"
            data["source"] = "derived"
        if key in Event.model_fields and where == "top":
            return
        sub_fields = {"command": SanitizedCommand, "metrics": Metrics, "gate": GateRef}[where]
        if key in sub_fields.model_fields:
            return
        target[key] = value
        data[where] = target
    with pytest.raises(ValidationError):
        Event.model_validate(data)


@_SETTINGS
@given(kind=st.text(max_size=40))
def test_arbitrary_kind_outside_enum_is_rejected(kind: str) -> None:
    data = valid_event()
    data["kind"] = kind
    if kind in {k.value for k in EventKind}:
        return
    with pytest.raises(ValidationError):
        Event.model_validate(data)


@pytest.mark.parametrize("name", HOOK_PAYLOAD_NAMES)
def test_hook_event_names_are_not_event_kinds(name: str) -> None:
    data = valid_event()
    data["kind"] = name
    with pytest.raises(ValidationError):
        Event.model_validate(data)


@_SETTINGS
@given(
    display=st.text(max_size=300),
    path=st.text(max_size=80),
)
def test_unprintable_or_unsafe_strings_never_validate(display: str, path: str) -> None:
    data = valid_event()
    data["command"]["display"] = display
    data["paths"] = [{"path": path}]
    try:
        event = Event.model_validate(data)
    except ValidationError:
        return
    # Anything accepted must be single-line printable text and a safe relative path.
    assert event.command is not None
    assert event.command.display is not None
    assert event.command.display.isprintable()
    assert len(event.command.display) <= 200
    accepted = event.paths[0].path
    assert accepted == "<external>" or not (accepted.startswith("/") or ".." in accepted.split("/"))


@pytest.mark.parametrize(
    "module",
    [
        "cursorfleet.adapters.cursor.hook_policy",
        "cursorfleet.events",
        "cursorfleet.events.kinds",
        "cursorfleet.events.ids",
        "cursorfleet.events.forbidden",
        "cursorfleet.events.pathcheck",
        "cursorfleet.config",
    ],
)
def test_hot_path_modules_do_not_import_heavy_dependencies(module: str) -> None:
    code = (
        f"import sys, {module}\n"
        "bad = {'pydantic', 'pydantic_core', 'typer', 'textual', 'rich'} & set(sys.modules)\n"
        "sys.exit(1 if bad else 0)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60, check=False
    )
    assert result.returncode == 0, f"{module} pulled in a heavy dependency: {result.stderr}"


def test_hot_path_modules_import_no_network_libraries() -> None:
    code = (
        "import sys\n"
        "import cursorfleet.events.kinds, cursorfleet.events.ids, cursorfleet.events.forbidden\n"
        "import cursorfleet.events.pathcheck, cursorfleet.adapters.cursor.hook_policy\n"
        "net = {'socket', 'http', 'urllib', 'ssl', 'requests', 'httpx', 'asyncio'}\n"
        "sys.exit(1 if net & set(sys.modules) else 0)\n"
    )
    src = str(Path(cursorfleet.__file__).resolve().parent.parent)
    result = subprocess.run(
        [sys.executable, "-S", "-c", code],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env={"PYTHONPATH": src},
    )
    assert result.returncode == 0, result.stderr
