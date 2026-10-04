"""Hooks kit probe (installed vs missing)."""

from __future__ import annotations

import json
from pathlib import Path

from cursorfleet.adapters.cursor.hooksjson import HOOK_COMMAND
from cursorfleet.adapters.cursor.kit_probe import HooksKitState, probe_hooks_kit
from m2_helpers import init_repo


def test_probe_missing_without_kit(tmp_path: Path) -> None:
    root = init_repo(tmp_path / "repo")
    probe = probe_hooks_kit(str(root))
    assert probe.state == HooksKitState.MISSING
    assert probe.cursorfleet_hook_entries == 0


def test_probe_installed_with_lock_and_hooks(tmp_path: Path) -> None:
    root = init_repo(tmp_path / "repo")
    (root / ".cursorfleet").mkdir()
    (root / ".cursorfleet/install.lock.json").write_text('{"lock_version":"1"}\n', encoding="utf-8")
    hooks = {
        "version": 1,
        "hooks": {"sessionStart": [{"command": HOOK_COMMAND, "timeout": 5}]},
    }
    (root / ".cursor").mkdir()
    (root / ".cursor/hooks.json").write_text(json.dumps(hooks), encoding="utf-8")
    probe = probe_hooks_kit(str(root))
    assert probe.state == HooksKitState.INSTALLED
    assert probe.cursorfleet_hook_entries == 1


def test_probe_partial_lock_only(tmp_path: Path) -> None:
    root = init_repo(tmp_path / "repo")
    (root / ".cursorfleet").mkdir()
    (root / ".cursorfleet/install.lock.json").write_text('{"lock_version":"1"}\n', encoding="utf-8")
    assert probe_hooks_kit(str(root)).state == HooksKitState.PARTIAL
