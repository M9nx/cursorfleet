"""The versioned ``status --json`` document (``cursorfleet.status/1``).

Combines the reducer's fleet view (hook telemetry) with the read-only git snapshot. Shape
is stable and documented in ``docs/status-json.md``; a snapshot-style test pins it. Where
no telemetry exists the fields say so explicitly (``"unknown"``, ``telemetry: "none"``)
instead of guessing: Cursor hooks expose no token budget, and an unlinked worktree has no
known owner or lane.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from cursorfleet.adapters.cursor.kit_probe import HooksKitState
from cursorfleet.git.collector import GitSnapshot, WorktreeSnapshot
from cursorfleet.state.models import (
    BUDGET_UNKNOWN,
    FleetView,
    Lane,
    SessionAcc,
    SessionView,
    TaskView,
    utc,
)
from cursorfleet.state.run_model import RunSnapshot
from cursorfleet.state.spool_read import Corruption

STATUS_SCHEMA = "cursorfleet.status/1"
STATUS_SCHEMA_WITH_RUNS = "cursorfleet.status/0.2"


def json_abs_path(path: str | None) -> str | None:
    """Absolute path with POSIX separators for the status JSON contract.

    Windows ``os.path`` and ``git rev-parse`` emit backslashes; the document is
    compared and consumed across OSes, so stored absolute paths use ``/``.
    """
    if path is None:
        return None
    return os.path.normpath(path).replace("\\", "/")


class _Doc(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RepoInfo(_Doc):
    common_dir: str | None
    runtime_dir: str | None


class TelemetryInfo(_Doc):
    state: str  # "hooks" when any hook event was indexed, else "none"
    sessions: int
    events: int
    spool_files: int
    stale_after_s: int
    source: str  # "projection" | "replay" | "none"
    corruption: dict[str, int]
    notes: list[str]


class Limits(_Doc):
    """Constant honesty statements (docs/product-contract.md)."""

    token_budget: str = BUDGET_UNKNOWN
    cloud_agents: str = "not_visible"
    enforcement: str = "none"


class GitInfo(_Doc):
    available: bool
    error: str | None


class Owner(_Doc):
    session_id: str
    agent_key: str
    role: str | None
    lane: str
    attribution: str


class RunGroupDoc(_Doc):
    role: str
    summary_lane: str
    confidence: str
    instance_count: int
    conflict: bool


class RunDoc(_Doc):
    run_id: str
    task_slug: str
    confidence: str
    session_ids: list[str]
    groups: list[RunGroupDoc]


class WorktreeDoc(_Doc):
    path: str
    worktree_id: str | None
    is_main: bool
    exists: bool
    branch: str | None
    head: str | None
    detached: bool
    bare: bool
    locked: bool
    prunable: bool
    dirty_count: int | None
    upstream: bool
    ahead: int | None
    behind: int | None
    last_commit_ts: datetime | None
    last_event_ts: datetime | None
    stale: bool
    stale_reasons: list[str]
    telemetry: str  # "hooks" | "none"
    lane: str  # a lane value, or "unknown" when there is no telemetry
    owners: list[Owner]
    tasks: list[str]
    error: str | None


class StatusDoc(_Doc):
    schema_: str
    generated_at: datetime
    repo: RepoInfo
    telemetry: TelemetryInfo
    limits: Limits
    git: GitInfo
    sessions: list[SessionView]
    tasks: list[TaskView]
    worktrees: list[WorktreeDoc]
    runs: list[RunDoc] = []

    def to_json_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = self.model_dump(mode="json")
        schema = data.pop("schema_")
        runs = data.pop("runs", [])
        ordered: dict[str, Any] = {"schema": schema}
        ordered.update(data)
        if runs:
            ordered["runs"] = runs
        return ordered


def worktree_activity(sessions: dict[str, SessionAcc]) -> dict[str, datetime]:
    """Last hook activity per ``worktree_id`` (for the collector's ``inactive`` check)."""
    activity: dict[str, datetime] = {}
    for session in sessions.values():
        stamp = session.last_live_ts
        if stamp is None:
            continue
        for wt in session.worktree_ids:
            if wt not in activity or stamp > activity[wt]:
                activity[wt] = stamp
    return activity


def _worktree_doc(snap: WorktreeSnapshot, views: list[SessionView]) -> WorktreeDoc:
    linked = [v for v in views if snap.worktree_id and snap.worktree_id in v.worktree_ids]
    owners: list[Owner] = []
    tasks: set[str] = set()
    for view in linked:
        for agent in view.agents:
            if agent.worktree_id == snap.worktree_id:
                owners.append(
                    Owner(
                        session_id=view.session_id,
                        agent_key=agent.key,
                        role=agent.role,
                        lane=agent.lane,
                        attribution=agent.attribution,
                    )
                )
                tasks.update(agent.issue_refs)
    latest = max(linked, key=lambda v: (v.last_ts, v.session_id), default=None)
    return WorktreeDoc(
        path=json_abs_path(snap.path) or snap.path,
        worktree_id=snap.worktree_id,
        is_main=snap.is_main,
        exists=snap.exists,
        branch=snap.branch,
        head=snap.head,
        detached=snap.detached,
        bare=snap.bare,
        locked=snap.locked,
        prunable=snap.prunable,
        dirty_count=snap.dirty_count,
        upstream=snap.upstream,
        ahead=snap.ahead,
        behind=snap.behind,
        last_commit_ts=snap.last_commit_ts,
        last_event_ts=latest.last_ts if latest else None,
        stale=snap.stale,
        stale_reasons=list(snap.stale_reasons),
        telemetry="hooks" if linked else "none",
        lane=latest.lane if latest else Lane.UNKNOWN.value,
        owners=sorted(owners, key=lambda o: (o.session_id, o.agent_key)),
        tasks=sorted(tasks),
        error=snap.error,
    )


def run_docs_from_snapshots(snapshots: list[RunSnapshot]) -> list[RunDoc]:
    out: list[RunDoc] = []
    for snap in snapshots:
        groups = [
            RunGroupDoc(
                role=g.role,
                summary_lane=g.summary_lane,
                confidence=g.confidence,
                instance_count=len(g.instances),
                conflict=g.conflict,
            )
            for g in snap.groups
        ]
        session_ids = sorted({inst.session_id for g in snap.groups for inst in g.instances})
        out.append(
            RunDoc(
                run_id=snap.run_id,
                task_slug=snap.task_slug,
                confidence=snap.confidence,
                session_ids=session_ids,
                groups=groups,
            )
        )
    return out


def build_status(  # noqa: PLR0913
    *,
    now: datetime,
    fleet: FleetView,
    git: GitSnapshot | None,
    common_dir: str | None,
    runtime_dir: str | None,
    corruption: Corruption,
    spool_files: int,
    source: str,
    hooks_kit: HooksKitState | None = None,
    runs: list[RunDoc] | None = None,
) -> StatusDoc:
    """Assemble the document. Pure given its inputs (``now`` is injected)."""
    events = sum(s.event_count for s in fleet.sessions)
    notes: list[str] = []
    if not fleet.sessions:
        kit = hooks_kit if hooks_kit is not None else HooksKitState.MISSING
        if kit == HooksKitState.INSTALLED:
            notes.append(
                "hooks installed; open this repo in Cursor and start a session to record "
                "telemetry (git-only view until the first hook run)"
            )
        else:
            notes.append("no hook telemetry indexed: git-only view; agent lanes are unknown")
    if corruption.total:
        notes.append(
            f"{corruption.total} corrupt or skipped spool line(s); see telemetry.corruption"
        )
    if git is None:
        notes.append("git collection was disabled")
    elif not git.available:
        notes.append(f"git unavailable: {git.error}")
    worktrees = [_worktree_doc(w, fleet.sessions) for w in git.worktrees] if git is not None else []
    run_docs = runs or []
    schema = STATUS_SCHEMA_WITH_RUNS if run_docs else STATUS_SCHEMA
    return StatusDoc(
        schema_=schema,
        generated_at=utc(now),
        repo=RepoInfo(common_dir=json_abs_path(common_dir), runtime_dir=json_abs_path(runtime_dir)),
        telemetry=TelemetryInfo(
            state="hooks" if fleet.sessions else "none",
            sessions=len(fleet.sessions),
            events=events,
            spool_files=spool_files,
            stale_after_s=fleet.stale_after_s,
            source=source,
            corruption=corruption.to_dict(),
            notes=notes,
        ),
        limits=Limits(),
        git=GitInfo(available=bool(git and git.available), error=git.error if git else "disabled"),
        sessions=fleet.sessions,
        tasks=list(fleet.tasks),
        worktrees=worktrees,
        runs=run_docs,
    )
