"""Event vocabulary: enums and constants. Stdlib only (shared with the hook hot path).

There is deliberately no kind for thoughts, prompts or responses
(ADR 0004). Adding one needs a superseding ADR.
"""

from __future__ import annotations

from enum import StrEnum

SCHEMA_VERSION = "1.0"

# Stored in place of any path outside the workspace roots.
EXTERNAL_PATH = "<external>"

# Hard bounds shared by the models and the stdlib sanitizer.
COMMAND_DISPLAY_MAX_CHARS = 200
MAX_PATHS_PER_EVENT = 200


class EventKind(StrEnum):
    SESSION_STARTED = "session.started"
    SESSION_STOPPED = "session.stopped"
    STATUS_CHANGED = "status.changed"
    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"
    FILE_CHANGED = "file.changed"
    TEST_COMPLETED = "test.completed"
    SUBAGENT_STARTED = "subagent.started"
    SUBAGENT_STOPPED = "subagent.stopped"
    CONTEXT_COMPACTED = "context.compacted"
    PLAN_CREATED = "plan.created"
    HANDOFF_CREATED = "handoff.created"
    BLOCKER_RAISED = "blocker.raised"
    GATE_CHANGED = "gate.changed"
    CONTEXT_LOADED = "context.loaded"


class Source(StrEnum):
    """How we know an event happened. Never display self_reported as fact."""

    OBSERVED = "observed"  # directly from a Cursor hook payload
    SELF_REPORTED = "self_reported"  # declared by an agent (artifact or emit CLI)
    DERIVED = "derived"  # computed by CursorFleet from observed events or git


class Producer(StrEnum):
    CURSOR_HOOK = "cursor_hook"
    WORK_ARTIFACT = "work_artifact"
    EMIT_CLI = "emit_cli"
    INDEXER = "indexer"


class Risk(StrEnum):
    """Informational label only; v0.1 never acts on it."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Attribution(StrEnum):
    """How confidently the event is tied to ``agent_role``/``agent_instance_id``.

    PROVISIONAL (ADR 0001 Q1): tool hooks may not identify the subagent, so most
    tool events may legitimately be ``unknown`` or ``inferred``.
    """

    EXACT = "exact"  # identity present in the payload itself
    INFERRED = "inferred"  # temporal window, worktree or tool_use_id linkage
    UNKNOWN = "unknown"


class Outcome(StrEnum):
    OK = "ok"
    FAILED = "failed"
    TIMEOUT = "timeout"
    PERMISSION_DENIED = "permission_denied"
    INTERRUPTED = "interrupted"
    UNKNOWN = "unknown"


class AgentStatus(StrEnum):
    IDLE = "idle"
    WORKING = "working"
    WAITING = "waiting"
    BLOCKED = "blocked"
    DONE = "done"
    ERROR = "error"
    UNKNOWN = "unknown"


class GateState(StrEnum):
    PASSING = "passing"
    FAILING = "failing"
    STALE = "stale"
    UNKNOWN = "unknown"


class PathOp(StrEnum):
    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"
    UNKNOWN = "unknown"


# Kinds Cursor cannot observe: they may only come from an agent declaration.
SELF_REPORT_ONLY_KINDS: frozenset[EventKind] = frozenset(
    {
        EventKind.PLAN_CREATED,
        EventKind.HANDOFF_CREATED,
        EventKind.BLOCKER_RAISED,
        EventKind.CONTEXT_LOADED,
    }
)

# Kinds an agent may declare. Tool, file and subagent facts cannot be self-reported.
SELF_REPORTABLE_KINDS: frozenset[EventKind] = SELF_REPORT_ONLY_KINDS | {EventKind.STATUS_CHANGED}
