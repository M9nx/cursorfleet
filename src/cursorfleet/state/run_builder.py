"""Build task/run snapshots from sessions, artifacts, and optional run metadata."""

from __future__ import annotations

from datetime import datetime

from cursorfleet.state.artifact_scan import ArtifactRecord
from cursorfleet.state.models import Lane, SessionAcc, SessionView, utc
from cursorfleet.state.run_model import (
    Confidence,
    ParticipantGroup,
    ParticipantInstance,
    RunSnapshot,
)

DEFAULT_STALE_AFTER_S = 900


def _is_stale(view: SessionView, now: datetime, stale_after_s: int) -> bool:
    if view.lane in (Lane.DONE.value, Lane.UNKNOWN.value):
        return False
    if view.last_ts is None:
        return True
    return (utc(now) - utc(view.last_ts)).total_seconds() > stale_after_s


def build_active_run(  # noqa: PLR0913, PLR0912
    *,
    task_slug: str,
    run_id: str,
    sessions: dict[str, SessionAcc],
    session_views: dict[str, SessionView],
    records: list[ArtifactRecord],
    linked_session_ids: frozenset[str] | None = None,
    now: datetime,
    stale_after_s: int = DEFAULT_STALE_AFTER_S,
) -> RunSnapshot:
    """In-memory Active Run for one task slug (B1 prototype)."""
    task_records = [r for r in records if r.task == task_slug]
    roles_from_declared = {r.author_role for r in task_records}

    groups: dict[str, ParticipantGroup] = {}
    unassociated: list[str] = []
    suggested: list[str] = []

    for sid, sview in session_views.items():
        if _is_stale(sview, now, stale_after_s) and sid not in (linked_session_ids or ()):
            continue
        matched = False
        for aview in sview.agents:
            acc = sessions[sid].agents[aview.key]
            role = acc.role or aview.key
            if role in roles_from_declared or sid in (linked_session_ids or ()):
                matched = True
                inst = ParticipantInstance(
                    session_id=sid,
                    agent_key=aview.key,
                    role=acc.role,
                    lane=aview.lane,
                    lane_basis=aview.lane_basis,
                    last_ts=aview.last_ts,
                    stale=aview.stale,
                )
                grp = groups.get(role)
                if grp is None:
                    groups[role] = ParticipantGroup(
                        role=role,
                        summary_lane=aview.lane,
                        confidence="explicit" if sid in (linked_session_ids or ()) else "inferred",
                        instances=[inst],
                    )
                else:
                    grp.instances.append(inst)
                    if aview.lane == Lane.BLOCKED.value or grp.summary_lane != aview.lane:
                        grp.conflict = True
        if not matched and not _is_stale(sview, now, stale_after_s):
            if roles_from_declared:
                suggested.append(sid)
            else:
                unassociated.append(sid)

    for role in roles_from_declared:
        if role not in groups:
            blockers = sum(
                1 for r in task_records if r.author_role == role and r.kind == "blocker.raised"
            )
            groups[role] = ParticipantGroup(
                role=role,
                summary_lane=Lane.UNKNOWN.value,
                confidence="declared",
                declared_blockers=blockers,
            )

    if linked_session_ids:
        confidence: Confidence = "explicit"
    elif task_records:
        confidence = "declared"
    else:
        confidence = "inferred"
    primary_wt = None
    branch = None
    commit = None
    for sview in session_views.values():
        if sview.worktree_ids:
            primary_wt = sview.worktree_ids[0]
        branch = sview.branch or branch
        commit = sview.commit or commit

    return RunSnapshot(
        run_id=run_id,
        task_slug=task_slug,
        confidence=confidence,
        primary_worktree_id=primary_wt,
        branch=branch,
        commit=commit,
        groups=sorted(groups.values(), key=lambda g: g.role),
        unassociated_session_ids=sorted(unassociated),
        suggested_session_ids=sorted(suggested),
    )


def pick_primary_task(records: list[ArtifactRecord], *, now: datetime) -> str | None:
    """Most recently declared task slug, if any."""
    if not records:
        return None
    latest = max(records, key=lambda r: (r.created, r.path))
    return latest.task
