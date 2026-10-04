"""Spool retention and purge (docs/privacy.md, "Retention" and "Purge command contract").

Defaults: 14 days or 50 MB per session, whichever comes first. Everything here touches only
``<git-common-dir>/cursorfleet/``; committed ``.cursorfleet/`` and ``.cursor/`` are never
reachable from these functions. Deletion is ordinary file removal, not secure wiping.
Planning is separate from applying so ``--dry-run`` shares the exact same code path.
"""

from __future__ import annotations

import os
import re
import shutil
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from cursorfleet.events.ids import fs_name_for
from cursorfleet.state.runtime import RuntimePaths
from cursorfleet.state.spool import CAPPED_MARKER, SPOOL_SUFFIX

DEFAULT_MAX_AGE_DAYS = 14
DEFAULT_MAX_SESSION_MB = 50

_DURATION = re.compile(r"^(\d{1,6})([smhdw])$")
_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def parse_duration(text: str) -> timedelta:
    """Parse ``30m``, ``12h``, ``7d``, ``2w`` (and ``s``). Raises ``ValueError`` otherwise."""
    match = _DURATION.match(text.strip().lower())
    if match is None:
        msg = f"invalid duration {text!r}; use e.g. 90m, 12h, 7d, 2w"
        raise ValueError(msg)
    return timedelta(seconds=int(match.group(1)) * _UNITS[match.group(2)])


@dataclass
class PurgePlan:
    """What would be removed. Paths are absolute and under the runtime root."""

    files: list[str] = field(default_factory=list)
    file_bytes: int = 0
    session_dirs: list[str] = field(default_factory=list)  # removed entirely (incl. markers)
    partial_sessions: int = 0  # sessions that survive but lose some segments
    clear_markers: list[str] = field(default_factory=list)
    remove_projection: bool = False
    rotate_key: bool = False
    remove_quarantine: bool = False

    @property
    def sessions(self) -> int:
        return len(self.session_dirs) + self.partial_sessions

    @property
    def empty(self) -> bool:
        return not (
            self.files
            or self.session_dirs
            or self.clear_markers
            or self.remove_projection
            or self.rotate_key
            or self.remove_quarantine
        )


@dataclass
class PurgeReport:
    sessions: int = 0
    files: int = 0
    bytes: int = 0
    projection_removed: bool = False
    key_rotated: bool = False
    needs_reindex: bool = False
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _SessionDir:
    path: str
    files: tuple[tuple[str, int, float], ...]  # (path, size, mtime), oldest first

    @property
    def size(self) -> int:
        return sum(size for _p, size, _m in self.files)

    @property
    def newest(self) -> float:
        return max((m for _p, _s, m in self.files), default=0.0)


def _scan_sessions(paths: RuntimePaths) -> list[_SessionDir]:
    found: list[_SessionDir] = []
    try:
        with os.scandir(paths.spool) as entries:
            directories = sorted(e.path for e in entries if e.is_dir(follow_symlinks=False))
    except OSError:
        return found
    for directory in directories:
        files: list[tuple[str, int, float]] = []
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if entry.name.endswith(SPOOL_SUFFIX) and entry.is_file(follow_symlinks=False):
                        stat = entry.stat(follow_symlinks=False)
                        files.append((entry.path, stat.st_size, stat.st_mtime))
        except OSError:
            continue
        files.sort(key=lambda f: (f[2], f[0]))
        found.append(_SessionDir(directory, tuple(files)))
    return found


def _whole_session(plan: PurgePlan, session: _SessionDir) -> None:
    plan.session_dirs.append(session.path)
    plan.files.extend(p for p, _s, _m in session.files)
    plan.file_bytes += session.size


def plan_purge(  # noqa: PLR0913
    paths: RuntimePaths,
    *,
    now: datetime,
    older_than: timedelta | None = None,
    session: str | None = None,
    everything: bool = False,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    max_session_mb: int = DEFAULT_MAX_SESSION_MB,
) -> PurgePlan:
    """Plan a purge. With no selector the configured retention is applied."""
    plan = PurgePlan()
    sessions = _scan_sessions(paths)
    if everything:
        for item in sessions:
            _whole_session(plan, item)
        plan.remove_projection = os.path.isdir(paths.index_dir)
        plan.rotate_key = os.path.exists(paths.hmac_key)
        plan.remove_quarantine = os.path.isdir(paths.quarantine)
        return plan
    if session is not None:
        target = os.path.join(paths.spool, fs_name_for(session))
        for item in sessions:
            if item.path == target:
                _whole_session(plan, item)
        return plan
    now_ts = now.timestamp()
    cap = max_session_mb * 1024 * 1024
    age_limit = older_than if older_than is not None else timedelta(days=max_age_days)
    for item in sessions:
        if item.files and now_ts - item.newest > age_limit.total_seconds():
            _whole_session(plan, item)
            continue
        if older_than is None and item.size > cap:
            _plan_over_cap(plan, item, cap)
        elif older_than is None and os.path.lexists(os.path.join(item.path, CAPPED_MARKER)):
            plan.clear_markers.append(os.path.join(item.path, CAPPED_MARKER))
    return plan


def _plan_over_cap(plan: PurgePlan, item: _SessionDir, cap: int) -> None:
    remaining = item.size
    removed_any = False
    for path, size, _mtime in item.files:  # oldest first; active files are newest anyway
        if remaining <= cap:
            break
        plan.files.append(path)
        plan.file_bytes += size
        remaining -= size
        removed_any = True
    if removed_any:
        plan.partial_sessions += 1
    marker = os.path.join(item.path, CAPPED_MARKER)
    if remaining < cap and os.path.lexists(marker):
        plan.clear_markers.append(marker)


def _remove_file(path: str, report: PurgeReport) -> bool:
    try:
        os.remove(path)
    except FileNotFoundError:
        return True
    except OSError as exc:
        report.errors.append(f"{os.path.basename(path)}: {exc.strerror or exc}")
        return False
    return True


def apply_plan(paths: RuntimePaths, plan: PurgePlan) -> PurgeReport:
    """Execute ``plan``. Best effort: failures are collected, never raised."""
    report = PurgeReport()
    root = os.path.realpath(paths.root)
    for path in plan.files:
        if not os.path.realpath(path).startswith(root + os.sep):
            report.errors.append("refused path outside the runtime directory")
            continue
        try:
            size = os.lstat(path).st_size
        except OSError:
            size = 0
        if _remove_file(path, report):
            report.files += 1
            report.bytes += size
    for marker in plan.clear_markers:
        _remove_file(marker, report)
    for directory in plan.session_dirs:
        _remove_file(os.path.join(directory, CAPPED_MARKER), report)
        with suppress(OSError):  # not empty (e.g. a hook recreated a file): leave it
            os.rmdir(directory)
    report.sessions = plan.sessions
    report.needs_reindex = bool(plan.files) or plan.remove_projection
    if plan.remove_projection:
        shutil.rmtree(paths.index_dir, ignore_errors=True)
        report.projection_removed = True
    if plan.rotate_key:
        report.key_rotated = _remove_file(paths.hmac_key, report)
    if plan.remove_quarantine:
        shutil.rmtree(paths.quarantine, ignore_errors=True)
    return report
