"""Read-only git/worktree collector. No fetch, no mutation, argv lists, timeouts everywhere.

Produces a :class:`GitSnapshot` that is useful with ZERO hook telemetry ("git-only"):
branch, HEAD, dirty file count, ahead/behind versus the EXISTING upstream ref (we never
fetch, so it can lag the remote), stale detection and the last commit time. Linking a
worktree to an owning session/task is done by the caller from state (``activity`` and
``worktree_id``), never by this module guessing.

Cursor creates, discovers and deletes worktrees itself (ADR 0001 A8), so a worktree may
vanish between two calls; every field degrades to ``None`` instead of raising.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from cursorfleet.events.ids import worktree_id_for
from cursorfleet.git.runner import (
    DEFAULT_TIMEOUT_S,
    GitResult,
    GitUnavailable,
    NotAGitRepo,
    git_common_dir,
    run_git,
)
from cursorfleet.git.worktrees import WorktreeEntry, parse_porcelain

DEFAULT_STALE_AFTER_HOURS = 72


@dataclass(frozen=True)
class WorktreeSnapshot:
    path: str  # as reported by git
    real_path: str | None  # realpath if it exists
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
    upstream: bool  # an upstream ref is configured and resolvable
    ahead: int | None
    behind: int | None
    last_commit_ts: datetime | None
    stale: bool
    stale_reasons: tuple[str, ...]
    error: str | None = None


@dataclass(frozen=True)
class GitSnapshot:
    available: bool
    error: str | None
    common_dir: str | None
    collected_at: datetime
    worktrees: tuple[WorktreeSnapshot, ...] = field(default_factory=tuple)


def _empty(now: datetime, error: str, common_dir: str | None = None) -> GitSnapshot:
    return GitSnapshot(False, error, common_dir, now)


def count_status_entries(raw: bytes) -> int:
    """Count entries in ``git status --porcelain=v1 -z`` output (rename/copy have 2 fields)."""
    fields = raw.split(b"\0")
    count = 0
    index = 0
    while index < len(fields):
        entry = fields[index]
        index += 1
        if not entry:
            continue
        count += 1
        if len(entry) >= 2 and (entry[:1] in b"RC" or entry[1:2] in b"RC"):
            index += 1  # the original path follows as a separate field
    return count


def _safe_run(args: list[str], cwd: str, timeout: float) -> GitResult | None:
    try:
        return run_git(args, cwd, timeout=timeout)
    except GitUnavailable:
        return None


def _parse_ahead_behind(text: str) -> tuple[int, int] | None:
    parts = text.split()
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        return None
    behind, ahead = int(parts[0]), int(parts[1])  # left = upstream-only, right = HEAD-only
    return ahead, behind


def _probe(  # noqa: PLR0913
    entry: WorktreeEntry,
    *,
    is_main: bool,
    now: datetime,
    stale_after: timedelta,
    activity: datetime | None,
    timeout: float,
    ahead_behind: bool,
) -> WorktreeSnapshot:
    reasons: list[str] = []
    error: str | None = None
    exists = os.path.isabs(entry.path) and os.path.isdir(entry.path)
    real = os.path.realpath(entry.path) if exists else None
    dirty = ahead = behind = None
    upstream = False
    last_commit: datetime | None = None
    if not exists:
        reasons.append("missing_path")
    if entry.prunable:
        reasons.append("prunable")
    probe = exists and not entry.bare and not entry.prunable and real is not None
    if probe and real is not None:
        status = _safe_run(
            ["status", "--porcelain=v1", "-z", "--untracked-files=normal"], real, timeout
        )
        if status is not None and status.ok:
            dirty = count_status_entries(status.stdout)
        else:
            error = "status_failed"
        if ahead_behind and not entry.detached:
            counts = _safe_run(
                ["rev-list", "--left-right", "--count", "@{upstream}...HEAD"], real, timeout
            )
            if counts is not None and counts.ok:
                parsed = _parse_ahead_behind(counts.text())
                if parsed is not None:
                    upstream = True
                    ahead, behind = parsed
        stamp = _safe_run(["log", "-1", "--format=%ct", "HEAD"], real, timeout)
        if stamp is not None and stamp.ok and stamp.text().strip().isdigit():
            last_commit = datetime.fromtimestamp(int(stamp.text().strip()), UTC)
    latest = max((t for t in (activity, last_commit) if t is not None), default=None)
    if probe and latest is not None and now - latest > stale_after:
        reasons.append("inactive")
    return WorktreeSnapshot(
        path=entry.path,
        real_path=real,
        worktree_id=worktree_id_for(real) if real is not None else None,
        is_main=is_main,
        exists=exists,
        branch=entry.branch,
        head=entry.head,
        detached=entry.detached,
        bare=entry.bare,
        locked=entry.locked,
        prunable=entry.prunable,
        dirty_count=dirty,
        upstream=upstream,
        ahead=ahead,
        behind=behind,
        last_commit_ts=last_commit,
        stale=bool(reasons),
        stale_reasons=tuple(reasons),
        error=error,
    )


def collect(  # noqa: PLR0913
    repo: str,
    *,
    now: datetime,
    stale_after_hours: int = DEFAULT_STALE_AFTER_HOURS,
    activity: Mapping[str, datetime] | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
    ahead_behind: bool = True,
    max_workers: int = 6,
) -> GitSnapshot:
    """Snapshot every worktree of the repo containing ``repo``. Never raises.

    ``activity`` maps ``worktree_id`` to the last observed hook activity, used only for the
    ``inactive`` stale reason. ``now`` is injected for deterministic tests.
    """
    now = now.astimezone(UTC)
    try:
        common = git_common_dir(repo, timeout=timeout)
    except NotAGitRepo as exc:
        return _empty(now, f"not_a_git_repo: {exc}")
    except GitUnavailable:
        return _empty(now, "git_unavailable")
    start = os.path.realpath(repo)
    try:
        listing = run_git(["worktree", "list", "--porcelain", "-z"], start, timeout=timeout)
        nul = True
        if listing is None or not listing.ok:
            listing = run_git(["worktree", "list", "--porcelain"], start, timeout=timeout)
            nul = False
    except GitUnavailable:
        return _empty(now, "git_unavailable", common)
    if listing is None or not listing.ok:
        return _empty(now, "worktree_list_failed", common)
    entries = parse_porcelain(listing.text(), nul=nul)
    stale_after = timedelta(hours=stale_after_hours)
    activity = activity or {}

    def probe(item: tuple[int, WorktreeEntry]) -> WorktreeSnapshot:
        index, entry = item
        real = os.path.realpath(entry.path) if os.path.isdir(entry.path) else None
        wt_id = worktree_id_for(real) if real is not None else None
        return _probe(
            entry,
            is_main=index == 0,
            now=now,
            stale_after=stale_after,
            activity=activity.get(wt_id) if wt_id is not None else None,
            timeout=timeout,
            ahead_behind=ahead_behind,
        )

    if not entries:
        return GitSnapshot(True, None, common, now, ())
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(entries)))) as pool:
        snapshots = list(pool.map(probe, enumerate(entries)))
    snapshots.sort(key=lambda s: (not s.is_main, s.path))
    return GitSnapshot(True, None, common, now, tuple(snapshots))
