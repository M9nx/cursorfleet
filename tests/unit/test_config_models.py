from __future__ import annotations

from typing import get_args

import pytest
from pydantic import ValidationError

from cursorfleet.adapters.cursor.hook_policy import ALLOWED_V01_HOOKS, FORBIDDEN_HOOKS
from cursorfleet.config.io import MAX_TOML_BYTES, loads_config
from cursorfleet.config.models import FleetConfig, HookName


def test_defaults() -> None:
    cfg = FleetConfig()
    assert cfg.schema_version == "1.0"
    assert cfg.retention.max_age_days == 14
    assert cfg.retention.max_session_mb == 50
    assert cfg.work.dir == ".cursorfleet/work"
    assert cfg.cursor.validated_versions == ()
    assert set(cfg.hooks.enabled) == ALLOWED_V01_HOOKS


def test_hook_name_literal_matches_policy() -> None:
    assert set(get_args(HookName)) == ALLOWED_V01_HOOKS


@pytest.mark.parametrize("hook", sorted(FORBIDDEN_HOOKS))
def test_forbidden_hooks_not_configurable(hook: str) -> None:
    with pytest.raises(ValidationError):
        FleetConfig.model_validate({"hooks": {"enabled": [hook]}})


def test_duplicate_hooks_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicates"):
        FleetConfig.model_validate({"hooks": {"enabled": ["stop", "stop"]}})


def test_unknown_keys_rejected() -> None:
    with pytest.raises(ValidationError):
        FleetConfig.model_validate({"privacy": {"store_prompts": True}})
    with pytest.raises(ValidationError):
        FleetConfig.model_validate({"network": {"enabled": True}})


@pytest.mark.parametrize("bad", ["/abs", "../up", "a/../b", "C:/x"])
def test_work_dir_must_be_workspace_relative(bad: str) -> None:
    with pytest.raises(ValidationError):
        FleetConfig.model_validate({"work": {"dir": bad}})


def test_display_limit_capped() -> None:
    with pytest.raises(ValidationError):
        FleetConfig.model_validate({"privacy": {"command_display_max_chars": 201}})


def test_loads_config_toml() -> None:
    cfg = loads_config(
        '[retention]\nmax_age_days = 3\n\n[cursor]\nvalidated_versions = ["3.5.1"]\n'
    )
    assert cfg.retention.max_age_days == 3
    assert cfg.cursor.validated_versions == ("3.5.1",)


def test_loads_config_size_cap() -> None:
    with pytest.raises(ValueError, match="exceeds"):
        loads_config("# " + "x" * MAX_TOML_BYTES)
