"""Read-only probe: is the observe-only hook kit present in a workspace?"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from cursorfleet.adapters.cursor.hooksjson import HOOK_COMMAND, effective_events
from cursorfleet.adapters.cursor.kit import HOOKS_PATH, LOCK_PATH


class HooksKitState(StrEnum):
    """How much of ``cursorfleet init --cursor`` is visible on disk."""

    MISSING = "missing"  # no lock and no project cursorfleet-hook entries
    PARTIAL = "partial"  # lock or hooks alone, or a broken hooks.json
    INSTALLED = "installed"  # lockfile plus cursorfleet-hook entries in project hooks.json


@dataclass(frozen=True)
class HooksKitProbe:
    state: HooksKitState
    lock_present: bool
    project_hooks_path: str | None
    cursorfleet_hook_entries: int


def probe_hooks_kit(repo_root: str | None) -> HooksKitProbe:
    """Never raises; safe for the TUI worker and ``status``."""
    if not repo_root:
        return HooksKitProbe(HooksKitState.MISSING, False, None, 0)
    root = Path(repo_root)
    lock_present = (root / LOCK_PATH).is_file()
    hooks_path = root / HOOKS_PATH
    entries = 0
    project_hooks: str | None = None
    if hooks_path.is_file():
        project_hooks = HOOKS_PATH
        try:
            parsed = effective_events(hooks_path.read_text(encoding="utf-8"))
        except OSError:
            parsed = {}
        for hook_entries in parsed.values():
            for item in hook_entries:
                if item.get("command") == HOOK_COMMAND:
                    entries += 1
    if lock_present and entries > 0:
        state = HooksKitState.INSTALLED
    elif lock_present or entries > 0:
        state = HooksKitState.PARTIAL
    else:
        state = HooksKitState.MISSING
    return HooksKitProbe(state, lock_present, project_hooks, entries)
