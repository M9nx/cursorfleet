"""State models: persisted accumulators (projection) and derived views (``status --json``).

Accumulators (``*Acc``) are what the reducer folds events into and what SQLite stores as
JSON. Views (``*View``) are computed from accumulators plus an injected ``now``; they carry
the stale/offline decision and are what the CLI prints.

Lanes are HEURISTICS over observed (and self-reported) events, not ground truth; every
lane carries its ``lane_source`` and the TUI must say so (docs/status-json.md).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from cursorfleet.events.kinds import Attribution, Outcome, Source

STATE_SCHEMA_VERSION = 1
MAX_FILES_PER_AGENT = 500
BUDGET_UNKNOWN = "unknown"  # Cursor hooks expose no token budget (ADR 0001 A9)


class Lane(StrEnum):
    """Workflow lane. ``unknown`` means "no telemetry"; it is never rendered as idle."""

    QUEUED = "queued"
    LOADING_CONTEXT = "loading_context"
    PLANNING = "planning"
    WORKING = "working"
    VERIFYING = "verifying"
    AWAITING_REVIEW = "awaiting_review"
    PATCHING = "patching"
    BLOCKED = "blocked"
    DONE = "done"
    STALE_OFFLINE = "stale_offline"
    UNKNOWN = "unknown"


def utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


_STRICT = ConfigDict(extra="forbid", validate_assignment=False)
UtcDatetime = Annotated[AwareDatetime, Field()]


class _Acc(BaseModel):
    model_config = _STRICT

    @field_validator("*", mode="after")
    @classmethod
    def _normalize_tz(cls, value: object) -> object:
        return utc(value) if isinstance(value, datetime) else value


class LastTest(_Acc):
    outcome: Outcome
    ts: UtcDatetime


class StopReport(_Acc):
    """What Cursor itself reported when a subagent stopped (``subagentStop``)."""

    outcome: Outcome | None = None
    duration_ms: int | None = None
    tool_call_count: int | None = None
    message_count: int | None = None
    loop_count: int | None = None


class AgentAcc(_Acc):
    key: str
    role: str | None = None
    instance_id: str | None = None
    attribution: Attribution = Attribution.UNKNOWN
    lane: Lane = Lane.UNKNOWN
    lane_source: Source | None = None
    lane_since: UtcDatetime | None = None
    first_ts: UtcDatetime
    last_ts: UtcDatetime
    last_live_ts: UtcDatetime | None = None  # last observed/derived event (not self-reported)
    events: int = 0
    lifecycle: Literal["none", "running", "stopped"] = "none"
    lifecycle_only: bool = False  # running subagent with no attributed telemetry yet
    started_ts: UtcDatetime | None = None
    stopped_ts: UtcDatetime | None = None
    spawn_link: str | None = None  # tool_use_id / tool_call_id (PROVISIONAL linkage)
    pre_calls: int = 0
    pre_shell_calls: int = 0
    before_shell_calls: int = 0
    tool_failures: int = 0
    last_tool: str | None = None
    compactions: int = 0
    last_context_usage_percent: float | None = None
    last_context_tokens: int | None = None
    last_context_window: int | None = None
    files: list[str] = Field(default_factory=list)
    files_overflow: bool = False
    reviewed: bool = False
    last_test: LastTest | None = None
    stop_report: StopReport | None = None
    plans: int = 0
    handoffs: int = 0
    blockers: int = 0
    contexts_loaded: int = 0
    issue_refs: list[str] = Field(default_factory=list)
    worktree_id: str | None = None
    branch: str | None = None
    commit: str | None = None

    @property
    def tool_call_count(self) -> int:
        """Tool calls seen. ``preToolUse`` is canonical; Shell-hook starts count only when
        no ``preToolUse`` for Shell was seen (hook set may be a subset), so overlapping
        hooks never double count."""
        shell_fallback = self.before_shell_calls if self.pre_shell_calls == 0 else 0
        return self.pre_calls + shell_fallback


class GateAcc(_Acc):
    state: str
    ts: UtcDatetime
    commit: str | None = None


class SessionAcc(_Acc):
    schema_version: int = STATE_SCHEMA_VERSION
    session_id: str
    first_ts: UtcDatetime
    last_ts: UtcDatetime
    last_live_ts: UtcDatetime | None = None
    started_ts: UtcDatetime | None = None
    ended_ts: UtcDatetime | None = None
    ended: bool = False
    end_outcome: Outcome | None = None
    cursor_version: str | None = None
    branch: str | None = None
    commit: str | None = None
    worktree_ids: list[str] = Field(default_factory=list)
    events: int = 0
    by_source: dict[str, int] = Field(default_factory=dict)
    unpaired_stops: int = 0
    agents: dict[str, AgentAcc] = Field(default_factory=dict)
    gates: dict[str, GateAcc] = Field(default_factory=dict)
    watermark_ts: UtcDatetime
    watermark_id: str


# ---------------------------------------------------------------- views


class _View(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LastTestView(_View):
    outcome: str
    ts: datetime


class StopReportView(_View):
    outcome: str | None
    duration_ms: int | None
    tool_call_count: int | None
    message_count: int | None


class AgentView(_View):
    key: str
    role: str | None
    instance_id: str | None
    attribution: str
    lane: str
    lane_source: str | None
    lane_basis: str
    stale: bool
    last_lane: str | None  # the lane before it went stale_offline
    lifecycle: str
    lifecycle_only: bool
    first_ts: datetime
    last_ts: datetime
    elapsed_s: float
    tool_call_count: int
    tool_failures: int
    compactions: int
    last_context_usage_percent: float | None
    files_changed: int
    reviewed: bool
    last_test: LastTestView | None
    stop_report: StopReportView | None
    issue_refs: list[str]
    worktree_id: str | None
    branch: str | None
    token_budget: str


class GateView(_View):
    name: str
    state: str
    ts: datetime
    commit: str | None


class SessionView(_View):
    session_id: str
    lane: str
    ended: bool
    end_outcome: str | None
    first_ts: datetime
    last_ts: datetime
    started_ts: datetime | None
    ended_ts: datetime | None
    elapsed_s: float
    tool_call_count: int
    compactions: int
    event_count: int
    by_source: dict[str, int]
    cursor_version: str | None
    branch: str | None
    commit: str | None
    worktree_ids: list[str]
    unpaired_stops: int
    token_budget: str
    agents: list[AgentView]
    gates: list[GateView]


class TaskView(_View):
    issue_ref: str
    lane: str
    session_ids: list[str]
    agent_keys: list[str]
    first_ts: datetime
    last_ts: datetime
    plans: int
    handoffs: int
    blockers: int


class FleetView(_View):
    generated_at: datetime
    stale_after_s: int
    sessions: list[SessionView]
    tasks: list[TaskView]


__all__ = [
    "BUDGET_UNKNOWN",
    "MAX_FILES_PER_AGENT",
    "STATE_SCHEMA_VERSION",
    "AgentAcc",
    "AgentView",
    "FleetView",
    "GateAcc",
    "GateView",
    "Lane",
    "LastTest",
    "LastTestView",
    "SessionAcc",
    "SessionView",
    "StopReport",
    "StopReportView",
    "TaskView",
    "utc",
]
