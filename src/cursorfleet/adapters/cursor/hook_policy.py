"""Which Cursor hooks CursorFleet v0.1 may register. Stdlib only (hot-path safe).

This module is the single source of truth for the installer and for tests.
Policy: see ``docs/adr/0004-no-chain-of-thought-and-hook-policy.md``.

PROVISIONAL: the inventory and the permission-hook classification come from the
Cursor docs (ADR 0001, section A); no live capture has confirmed them.
"""

from __future__ import annotations

# The 12 passive hooks v0.1 registers. They never block and always fail open.
ALLOWED_V01_HOOKS: frozenset[str] = frozenset(
    {
        "sessionStart",
        "sessionEnd",
        "preToolUse",
        "postToolUse",
        "postToolUseFailure",
        "subagentStart",
        "subagentStop",
        "beforeShellExecution",
        "afterShellExecution",
        "afterFileEdit",
        "preCompact",
        "stop",
    }
)

# Hooks whose payload carries prompts, thinking, responses or file contents.
# The installer must NEVER emit them: the content would reach our process even
# if the parser discarded it. Do not remove entries without a superseding ADR.
FORBIDDEN_HOOKS: frozenset[str] = frozenset(
    {
        "afterAgentThought",
        "afterAgentResponse",
        "beforeSubmitPrompt",
        "beforeReadFile",
    }
)

# Other content-bearing or unneeded hooks that v0.1 also does not register.
# Registering one needs an ADR amendment plus a threat-model review.
UNREGISTERED_V01_HOOKS: frozenset[str] = frozenset(
    {
        "beforeTabFileRead",
        "afterTabFileEdit",
        "beforeMCPExecution",
        "afterMCPExecution",
        "workspaceOpen",
    }
)

# Registered hooks that Cursor treats as permission hooks: invalid or
# schema-mismatching output blocks the action, so the fail-open reply must be
# ``{"permission": "allow"}`` rather than ``{}`` (ADR 0001, A2 and A3).
PERMISSION_HOOKS: frozenset[str] = frozenset(
    {
        "preToolUse",
        "subagentStart",
        "beforeShellExecution",
    }
)

_PERMISSION_ALLOW = '{"permission":"allow"}'
_EMPTY = "{}"


def is_registrable(hook_name: str) -> bool:
    """Return True only for hooks on the v0.1 allowlist (and not forbidden)."""
    return hook_name in ALLOWED_V01_HOOKS and hook_name not in FORBIDDEN_HOOKS


def fail_open_response(hook_name: str) -> str:
    """JSON text a hook prints when it cannot or should not do anything else."""
    return _PERMISSION_ALLOW if hook_name in PERMISSION_HOOKS else _EMPTY
