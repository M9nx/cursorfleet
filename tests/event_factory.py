"""Shared builders for valid event payloads (plain dicts, as a producer would write them)."""

from __future__ import annotations

import copy
from typing import Any

_BASE: dict[str, Any] = {
    "schema_version": "1.0",
    "event_id": "01J9ZK3Q7M8N2P4R6S8T0V1W2X",
    "ts": "2026-10-04T00:44:00.123Z",
    "producer": "cursor_hook",
    "producer_version": "0.0.1.dev0",
    "cursor_version": "0.0.0-doc-example",
    "source": "observed",
    "kind": "tool.completed",
    "session_id": "doc-example-conversation",
    "generation_id": "doc-example-generation",
    "agent_role": "reviewer",
    "agent_instance_id": "abc-123",
    "attribution": "exact",
    "risk": "low",
    "worktree_id": "wt-0123456789ab",
    "branch": "feature/auth",
    "commit": "0123456789abcdef0123456789abcdef01234567",
    "issue_ref": "M9nx/cursorfleet#12",
    "tool_name": "Shell",
    "outcome": "ok",
    "command": {
        "argv0": "git",
        "subcommand": "status",
        "exit_code": 0,
        "duration_ms": 42,
        "display": "git status --short",
        "display_truncated": False,
        "command_hash": "0123456789abcdef0123456789abcdef",
    },
    "paths": [{"path": "src/cursorfleet/cli/main.py", "op": "modified"}, {"path": "<external>"}],
    "metrics": {"duration_ms": 42, "tool_call_count": 3},
}


def valid_event() -> dict[str, Any]:
    """A fresh, fully-populated valid event dict (safe to mutate)."""
    return copy.deepcopy(_BASE)
