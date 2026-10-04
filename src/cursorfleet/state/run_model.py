"""Task/run view models (M2.5). Pure data; no I/O."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

Confidence = Literal["explicit", "declared", "inferred"]


@dataclass(frozen=True)
class ParticipantInstance:
    session_id: str
    agent_key: str
    role: str | None
    lane: str
    lane_basis: str
    last_ts: datetime | None
    stale: bool = False


@dataclass
class ParticipantGroup:
    role: str
    summary_lane: str
    confidence: Confidence
    instances: list[ParticipantInstance] = field(default_factory=list)
    declared_blockers: int = 0
    conflict: bool = False


@dataclass
class RunSnapshot:
    run_id: str
    task_slug: str
    confidence: Confidence
    primary_worktree_id: str | None
    branch: str | None
    commit: str | None
    groups: list[ParticipantGroup] = field(default_factory=list)
    unassociated_session_ids: list[str] = field(default_factory=list)
    suggested_session_ids: list[str] = field(default_factory=list)
