"""Versioned event model (schema_version "1.0"): the source of truth for event.schema.json.

The stdlib-only hook hot path does NOT import this module. It re-implements
validation with the stdlib and is contract-tested against these models
(docs/architecture.md). Every model forbids extra keys, so an unlisted field
(a prompt, an email, a transcript path) can never ride along in a valid event.

PROVISIONAL (ADR 0001 Q1, Q2): ``agent_role``, ``agent_instance_id``,
``agent_id`` and ``attribution`` depend on what subagent tool hooks reveal.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Self

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from cursorfleet.events.ids import AGENT_ID_PATTERN, SAFE_ID_PATTERN, ULID_PATTERN, derive_agent_id
from cursorfleet.events.kinds import (
    COMMAND_DISPLAY_MAX_CHARS,
    MAX_PATHS_PER_EVENT,
    SCHEMA_VERSION,
    SELF_REPORT_ONLY_KINDS,
    SELF_REPORTABLE_KINDS,
    AgentStatus,
    Attribution,
    EventKind,
    GateState,
    Outcome,
    PathOp,
    Producer,
    Risk,
    Source,
)
from cursorfleet.events.pathcheck import check_relative_posix


def _printable(value: str) -> str:
    if not value.isprintable():
        msg = "must not contain control, bidi-override or other non-printable characters"
        raise ValueError(msg)
    return value


def _relative_or_external(value: str) -> str:
    return check_relative_posix(value, allow_external=True)


SafeId = Annotated[str, Field(pattern=SAFE_ID_PATTERN, max_length=128)]
AgentId = Annotated[str, Field(pattern=AGENT_ID_PATTERN, max_length=257)]
Ulid = Annotated[str, Field(pattern=ULID_PATTERN, min_length=26, max_length=26)]
VersionStr = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._+\-]{0,63}$", max_length=64)]
Printable = Annotated[str, AfterValidator(_printable)]
NonNegInt = Annotated[int, Field(ge=0, le=10**12, strict=True)]
EventPath = Annotated[str, AfterValidator(_relative_or_external)]

_STRICT = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=False)


class SanitizedPath(BaseModel):
    """A path reduced to a workspace-relative POSIX string, or ``<external>``."""

    model_config = _STRICT

    path: EventPath = Field(
        description="Workspace-relative, symlink-resolved, '/' separated; "
        "'<external>' for anything outside the workspace roots."
    )
    op: PathOp = PathOp.UNKNOWN


class SanitizedCommand(BaseModel):
    """A shell command reduced to non-sensitive facts. Never the raw command line."""

    model_config = _STRICT

    argv0: Annotated[str, Field(pattern=r"^[A-Za-z0-9_][A-Za-z0-9._+\-]{0,63}$")] = Field(
        description="Executable basename only (no directory)."
    )
    subcommand: Annotated[str, Field(pattern=r"^[a-z][a-z0-9:_\-]{0,63}$")] | None = Field(
        default=None, description="First non-flag word for known multi-command tools."
    )
    exit_code: Annotated[int, Field(ge=-1024, le=1024, strict=True)] | None = None
    duration_ms: NonNegInt | None = None
    display: Annotated[Printable, Field(max_length=COMMAND_DISPLAY_MAX_CHARS)] | None = Field(
        default=None,
        description="Redacted and truncated single-line display string (best effort, "
        "not a security guarantee).",
    )
    display_truncated: bool = False
    command_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{16,64}$")] | None = Field(
        default=None,
        description="Keyed (HMAC) hash of the normalized argv for dedupe; key is local.",
    )


class GateRef(BaseModel):
    """Display-only gate signal (v0.1 never enforces gates)."""

    model_config = _STRICT

    name: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_\-]{0,31}$")]
    state: GateState


class Metrics(BaseModel):
    """Bounded counters Cursor exposes. Token usage appears only via compaction."""

    model_config = _STRICT

    duration_ms: NonNegInt | None = None
    tool_call_count: NonNegInt | None = None
    message_count: NonNegInt | None = None
    loop_count: NonNegInt | None = None
    context_usage_percent: Annotated[float, Field(ge=0, le=1000)] | None = None
    context_tokens: NonNegInt | None = None
    context_window_size: NonNegInt | None = None


class Event(BaseModel):
    """One normalized CursorFleet event (schema_version "1.0")."""

    model_config = _STRICT

    schema_version: Literal["1.0"] = SCHEMA_VERSION  # type: ignore[assignment]
    event_id: Ulid = Field(description="ULID-style id (26 Crockford base32 chars).")
    ts: AwareDatetime = Field(description="Timezone-aware event time.")
    producer: Producer
    producer_version: VersionStr
    cursor_version: VersionStr | None = Field(
        default=None, description="Cursor version from the payload; absent for non-hook producers."
    )
    source: Source = Field(description="observed | self_reported | derived. Show it in the UI.")
    kind: EventKind

    session_id: SafeId = Field(description="Cursor conversation_id.")
    generation_id: SafeId | None = None
    agent_role: SafeId | None = Field(
        default=None,
        description="Roster id when subagent_type maps to it, else the raw subagent_type. "
        "PROVISIONAL (ADR 0001 Q2).",
    )
    agent_instance_id: SafeId | None = Field(
        default=None, description="Cursor subagent_id. PROVISIONAL (ADR 0001 Q1)."
    )
    agent_id: AgentId | None = Field(
        default=None,
        description="Derived as 'role#instance'; if given it must equal the derived value.",
    )
    attribution: Attribution = Attribution.UNKNOWN

    risk: Risk = Risk.NONE
    worktree_id: SafeId | None = None
    branch: Annotated[Printable, Field(min_length=1, max_length=255)] | None = None
    commit: Annotated[str, Field(pattern=r"^[0-9a-f]{7,64}$")] | None = None
    issue_ref: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.\-/#]{1,100}$")] | None = None

    tool_name: Annotated[str, Field(pattern=r"^[A-Za-z0-9_:.\-]{1,128}$")] | None = None
    tool_use_id: SafeId | None = Field(
        default=None,
        description="Opaque Cursor tool_use_id (tool hooks) or tool_call_id (subagentStart); "
        "pairs started/completed and is the candidate Task-to-subagent link. "
        "PROVISIONAL (ADR 0001 section B).",
    )
    hook: Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9]{0,63}$")] | None = Field(
        default=None,
        description="Cursor hook_event_name that produced the event; lets the reducer "
        "de-duplicate overlapping hooks (preToolUse vs beforeShellExecution).",
    )
    outcome: Outcome | None = None
    status: AgentStatus | None = None
    gate: GateRef | None = None
    command: SanitizedCommand | None = None
    paths: Annotated[tuple[SanitizedPath, ...], Field(max_length=MAX_PATHS_PER_EVENT)] = ()
    metrics: Metrics | None = None

    @model_validator(mode="before")
    @classmethod
    def _fill_agent_id(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("agent_id") is None:
            derived = derive_agent_id(data.get("agent_role"), data.get("agent_instance_id"))
            if derived is not None:
                return {**data, "agent_id": derived}
        return data

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        derived = derive_agent_id(self.agent_role, self.agent_instance_id)
        if self.agent_id != derived:
            msg = "agent_id must equal the value derived from agent_role and agent_instance_id"
            raise ValueError(msg)
        if self.kind in SELF_REPORT_ONLY_KINDS and self.source is not Source.SELF_REPORTED:
            msg = f"{self.kind.value} is not observable by Cursor hooks; use source=self_reported"
            raise ValueError(msg)
        if self.source is Source.SELF_REPORTED and self.kind not in SELF_REPORTABLE_KINDS:
            msg = f"{self.kind.value} cannot be self-reported"
            raise ValueError(msg)
        if (self.kind is EventKind.GATE_CHANGED) != (self.gate is not None):
            msg = "gate is required for, and only allowed on, gate.changed"
            raise ValueError(msg)
        if self.kind is EventKind.FILE_CHANGED and not self.paths:
            msg = "file.changed requires at least one path"
            raise ValueError(msg)
        return self


__all__ = [
    "Event",
    "GateRef",
    "Metrics",
    "SanitizedCommand",
    "SanitizedPath",
]
