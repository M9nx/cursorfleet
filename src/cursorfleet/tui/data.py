"""Data layer for the TUI: everything the screens show, gathered without Textual.

Sources (all read-only, no network):

- the SQLite projection, kept fresh by tailing the spool with the single-writer indexer
  (:class:`~cursorfleet.state.indexer.Indexer`); events for the timeline come from the
  projection's ``events`` table;
- the read-only git collector (never fetches, never mutates);
- the artifact scanner over ``.cursorfleet/work`` (SELF-REPORTED declarations).

:meth:`DataSource.load` is blocking and meant for a worker thread. It never raises: every
failure becomes a line in :attr:`FleetData.problems` so a corrupt database, a damaged spool
or a missing repository degrades the display instead of crashing it.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from cursorfleet.adapters.cursor.kit_probe import HooksKitState, probe_hooks_kit
from cursorfleet.config.io import loads_config
from cursorfleet.events.kinds import EventKind
from cursorfleet.events.models import Event
from cursorfleet.git.collector import (
    DEFAULT_STALE_AFTER_HOURS,
    GitSnapshot,
    WorktreeSnapshot,
    collect,
)
from cursorfleet.git.runner import GitError
from cursorfleet.state.artifact_scan import (
    DEFAULT_WORK_DIR,
    ArtifactRecord,
    ArtifactScan,
    ArtifactScanner,
)
from cursorfleet.state.context import RepoContext, resolve_repo
from cursorfleet.state.event_store import (
    EventFilter,
    EventPage,
    matches_filter,
    query_events,
)
from cursorfleet.state.indexer import Indexer, replay_session_state
from cursorfleet.state.models import AgentAcc, AgentView, FleetView, Lane, SessionAcc, SessionView
from cursorfleet.state.reducer import DEFAULT_STALE_AFTER_S, MAIN, reduce_events, snapshot
from cursorfleet.state.run_builder import build_active_run, pick_primary_task
from cursorfleet.state.run_model import RunSnapshot
from cursorfleet.state.run_store import RunRecord, list_runs
from cursorfleet.state.spool_read import Corruption, list_spool_files
from cursorfleet.state.status_doc import worktree_activity
from cursorfleet.tui import gates as gate_logic

MAX_WORKTREE_ROOTS = 25
RECENT_EVENTS = 40
GATE_EVIDENCE_EVENTS = 400


@dataclass(frozen=True)
class Card:
    """One item in the workflow overview."""

    key: str
    kind: str  # "agent" | "declared" | "worktree"
    lane: str
    title: str
    detail: str
    basis: str  # observed_activity | lifecycle_only | self_reported | derived | none
    last_ts: datetime | None
    blockers: int = 0
    declared_blockers: int = 0
    stale: bool = False
    session_id: str | None = None
    agent_key: str | None = None
    worktree_path: str | None = None


@dataclass
class AgentBundle:
    """Everything known about one agent card (a hook-observed agent or a declared role)."""

    key: str
    session: SessionAcc | None
    acc: AgentAcc
    view: AgentView | None  # None for declared-only roles (no live telemetry)
    session_view: SessionView | None
    records: list[ArtifactRecord] = field(default_factory=list)  # self-reported, by role

    @property
    def role(self) -> str | None:
        return self.acc.role


@dataclass
class GateBoard:
    """Gate statuses per worktree id (``None`` = evidence tied to no known worktree)."""

    by_worktree: dict[str | None, list[gate_logic.GateStatus]] = field(default_factory=dict)
    evidence: list[gate_logic.GateEvidence] = field(default_factory=list)


@dataclass
class FleetData:
    now: datetime
    repo_root: str | None = None
    runtime_dir: str | None = None
    db_path: str | None = None
    sessions: dict[str, SessionAcc] = field(default_factory=dict)
    fleet: FleetView | None = None
    git: GitSnapshot | None = None
    git_enabled: bool = True
    artifacts: ArtifactScan = field(default_factory=ArtifactScan)
    cards: list[Card] = field(default_factory=list)
    bundles: dict[str, AgentBundle] = field(default_factory=dict)
    gates: GateBoard = field(default_factory=GateBoard)
    corruption: Corruption = field(default_factory=Corruption)
    spool_files: int = 0
    telemetry: str = "none"  # "hooks" | "none"
    hooks_kit: HooksKitState = HooksKitState.MISSING
    problems: list[str] = field(default_factory=list)
    recent: EventPage = field(default_factory=EventPage)
    timeline: EventPage = field(default_factory=EventPage)
    timeline_errors: tuple[str, ...] = ()
    primary_run: RunSnapshot | None = None
    run_snapshots: list[RunSnapshot] = field(default_factory=list)
    run_records: list[RunRecord] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.cards and not self.artifacts.records

    def worktree_by_id(self, worktree_id: str | None) -> WorktreeSnapshot | None:
        if self.git is None or worktree_id is None:
            return None
        return next((w for w in self.git.worktrees if w.worktree_id == worktree_id), None)

    def blocked_count(self) -> int:
        return sum(1 for c in self.cards if c.blockers > 0)


def _work_dir(top_level: str | None) -> str:
    """The configured work dir (``.cursorfleet/config.toml``), or the default."""
    if top_level is None:
        return DEFAULT_WORK_DIR
    config = Path(top_level, ".cursorfleet", "config.toml")
    try:
        if config.is_file() and config.stat().st_size < 256 * 1024:
            return loads_config(config.read_text(encoding="utf-8")).work.dir
    except (OSError, ValueError):
        pass
    return DEFAULT_WORK_DIR


def _owners(snap: WorktreeSnapshot, fleet: FleetView) -> list[str]:
    out: list[str] = []
    for session in fleet.sessions:
        for agent in session.agents:
            if snap.worktree_id and agent.worktree_id == snap.worktree_id:
                out.append(f"{session.session_id}/{agent.key}")
    return sorted(out)


class DataSource:
    """Stateful loader (caches the projection, git snapshot and artifact scan)."""

    def __init__(
        self,
        repo: str | os.PathLike[str],
        *,
        with_git: bool = True,
        clock: Callable[[], datetime] | None = None,
        stale_after_s: int = DEFAULT_STALE_AFTER_S,
        git_every: int = 5,
    ) -> None:
        self._repo = os.fspath(repo)
        self._with_git = with_git
        self._clock = clock or (lambda: datetime.now(UTC))
        self._stale_after_s = stale_after_s
        self._git_every = max(1, git_every)
        self._ctx: RepoContext | None = None
        self._ctx_error: str | None = None
        self._indexer: Indexer | None = None
        self._sessions: dict[str, SessionAcc] = {}
        self._corruption = Corruption()
        self._git: GitSnapshot | None = None
        self._ticks = 0
        self._loaded = False
        self._scanner: ArtifactScanner | None = None
        self._evidence: list[gate_logic.GateEvidence] = []
        self._evidence_dirty = True

    # ------------------------------------------------------------------ public

    def now(self) -> datetime:
        return self._clock().astimezone(UTC)

    def load(
        self,
        flt: EventFilter | None = None,
        *,
        limit: int = 200,
        force_git: bool = False,
    ) -> FleetData:
        """Blocking snapshot for the screens. Never raises."""
        now = self.now()
        data = FleetData(now=now, git_enabled=self._with_git)
        try:
            self._load(data, flt, limit, force_git)
        except Exception as exc:
            data.problems.append(f"data load failed ({type(exc).__name__}); showing what is known")
        return data

    def recent_tools(self, session_id: str, agent_key: str, limit: int = 6) -> list[Event]:
        """Newest tool events for one agent, for the detail pane."""
        if self._ctx is None:
            return []
        page = query_events(
            self._ctx.paths.db, EventFilter(session=session_id, kind="tool.started"), limit=200
        )
        wanted = None if agent_key == MAIN else agent_key
        return [e for e in page.events if e.agent_id == wanted][:limit]

    # ------------------------------------------------------------------ internals

    def _resolve(self) -> RepoContext | None:
        if self._ctx is not None:
            return self._ctx
        try:
            self._ctx = resolve_repo(self._repo)
        except GitError as exc:
            self._ctx_error = type(exc).__name__
            return None
        self._indexer = Indexer(self._ctx.paths)
        return self._ctx

    def _load(self, data: FleetData, flt: EventFilter | None, limit: int, force_git: bool) -> None:
        ctx = self._resolve()
        if ctx is None:
            data.problems.append("not a git repository (or git is unavailable)")
            data.fleet = snapshot({}, now=data.now, stale_after_s=self._stale_after_s)
            return
        data.repo_root = ctx.top_level or ctx.common_dir
        data.runtime_dir = ctx.paths.root
        data.db_path = ctx.paths.db
        data.hooks_kit = probe_hooks_kit(data.repo_root).state
        self._refresh_projection(data)
        data.sessions = self._sessions
        data.corruption = self._corruption
        data.telemetry = "hooks" if self._sessions else "none"
        fleet = snapshot(self._sessions, now=data.now, stale_after_s=self._stale_after_s)
        data.fleet = fleet
        self._refresh_git(data, force_git)
        self._scan_artifacts(data, ctx)
        data.recent = query_events(ctx.paths.db, limit=RECENT_EVENTS)
        data.timeline = query_events(ctx.paths.db, flt, limit=limit)
        self._merge_artifact_events(data, flt, limit)
        self._refresh_evidence(data)
        _build_cards(data)
        self._build_gates(data)
        self._build_runs(data, ctx)
        self._add_problems(data)

    def _build_runs(self, data: FleetData, ctx: RepoContext) -> None:
        if data.fleet is None:
            return
        session_views = {s.session_id: s for s in data.fleet.sessions}
        records = data.artifacts.records
        all_records = list_runs(ctx.paths.root)
        data.run_records = all_records
        active_meta = sorted(
            (r for r in all_records if not r.archived),
            key=lambda r: r.created_at,
            reverse=True,
        )
        snapshots: list[RunSnapshot] = []
        for meta in active_meta:
            snapshots.append(
                build_active_run(
                    task_slug=meta.task_slug,
                    run_id=meta.run_id,
                    sessions=data.sessions,
                    session_views=session_views,
                    records=records,
                    linked_session_ids=frozenset(meta.session_ids),
                    now=data.now,
                    stale_after_s=self._stale_after_s,
                )
            )
        data.run_snapshots = snapshots
        if snapshots:
            data.primary_run = snapshots[0]
            return
        task = pick_primary_task(records, now=data.now)
        if task is None and not session_views:
            data.primary_run = None
            return
        slug = task or "unscoped"
        data.primary_run = build_active_run(
            task_slug=slug,
            run_id=f"inferred:{slug}",
            sessions=data.sessions,
            session_views=session_views,
            records=records,
            linked_session_ids=frozenset(),
            now=data.now,
            stale_after_s=self._stale_after_s,
        )

    def _refresh_projection(self, data: FleetData) -> None:
        assert self._indexer is not None  # noqa: S101 - set together with the context
        assert self._ctx is not None  # noqa: S101
        try:
            data.spool_files = len(list_spool_files(self._ctx.paths))
        except OSError:
            data.spool_files = 0
        if data.spool_files == 0 and not os.path.exists(self._ctx.paths.db):
            return
        try:
            stats = self._indexer.try_sync()
        except Exception as exc:
            data.problems.append(
                f"indexing failed ({type(exc).__name__}); showing last known state"
            )
            stats = None
        changed = (
            not self._loaded
            or stats is None
            or stats.events_new > 0
            or stats.sessions_pruned > 0
            or stats.db_recovered
        )
        if stats is not None and stats.db_recovered:
            data.problems.append("the projection was damaged: it was moved aside and rebuilt")
        if not changed:
            return
        sessions = self._indexer.load_sessions()
        corruption = self._indexer.corruption()
        if not sessions and data.spool_files:
            try:
                sessions, corruption, _n = replay_session_state(self._ctx.paths)
            except Exception as exc:
                data.problems.append(f"spool replay failed ({type(exc).__name__})")
        self._sessions = sessions
        self._corruption = corruption
        self._loaded = True
        self._evidence_dirty = True

    def _refresh_git(self, data: FleetData, force: bool) -> None:
        if not self._with_git:
            return
        due = force or self._git is None or self._ticks % self._git_every == 0
        self._ticks += 1
        if due and data.repo_root is not None:
            self._git = collect(
                data.repo_root,
                now=data.now,
                stale_after_hours=DEFAULT_STALE_AFTER_HOURS,
                activity=worktree_activity(self._sessions),
            )
            self._evidence_dirty = True
        data.git = self._git

    def _scan_artifacts(self, data: FleetData, ctx: RepoContext) -> None:
        if self._scanner is None:
            self._scanner = ArtifactScanner(_work_dir(ctx.top_level))
        roots: list[str] = [ctx.top_level] if ctx.top_level else []
        if data.git is not None:
            for wt in data.git.worktrees:
                if wt.real_path and wt.exists and not wt.bare:
                    roots.append(wt.real_path)
        data.artifacts = self._scanner.scan(roots[:MAX_WORKTREE_ROOTS])

    @staticmethod
    def _merge_artifact_events(data: FleetData, flt: EventFilter | None, limit: int) -> None:
        """Self-reported artifact events are not in the database; merge them by time."""
        extra = [e for e in data.artifacts.events if matches_filter(e, flt or EventFilter())]
        if not extra:
            return
        merged = sorted(
            [*data.timeline.events, *extra], key=lambda e: (e.ts, e.event_id), reverse=True
        )
        data.timeline.events = merged[:limit]
        data.timeline.total += len(extra)

    def _refresh_evidence(self, data: FleetData) -> None:
        if not self._evidence_dirty or self._ctx is None:
            return
        events: list[Event] = []
        for kind in (
            EventKind.VERIFICATION_OBSERVED,
            EventKind.TEST_COMPLETED,
            EventKind.GATE_CHANGED,
        ):
            page = query_events(
                self._ctx.paths.db, EventFilter(kind=kind.value), limit=GATE_EVIDENCE_EVENTS
            )
            events.extend(page.events)
        self._evidence = gate_logic.evidence_from_events(events)
        self._evidence_dirty = False

    def _build_gates(self, data: FleetData) -> None:
        heads: dict[str | None, str | None] = {}
        if data.git is not None:
            for wt in data.git.worktrees:
                if wt.worktree_id is not None:
                    heads[wt.worktree_id] = wt.head
        # Evidence for worktrees git does not list (deleted, or git disabled) is judged with
        # an unknown HEAD, which keeps it "unknown" rather than pretending it is current.
        for item in self._evidence:
            heads.setdefault(item.worktree_id, None)
        board = GateBoard(evidence=list(self._evidence))
        board.by_worktree = gate_logic.evaluate_all(self._evidence, heads)
        data.gates = board

    def _add_problems(self, data: FleetData) -> None:
        if data.corruption.total:
            data.problems.append(
                f"{data.corruption.total} corrupt or skipped spool line(s) were ignored"
            )
        if data.artifacts.issues:
            data.problems.append(
                f"{len(data.artifacts.issues)} invalid artifact file(s): see the evidence view"
            )
        if data.git_enabled and data.git is not None and not data.git.available:
            data.problems.append(f"git data unavailable: {data.git.error}")
        if data.timeline.error and (data.spool_files or data.sessions):
            data.problems.append(data.timeline.error)


# ---------------------------------------------------------------- cards


def _declared_for_role(records: list[ArtifactRecord], role: str) -> list[ArtifactRecord]:
    """Task-scoped declared records for a hook-observed role (avoid cross-task bleed)."""
    matched = [r for r in records if r.author_role == role]
    tasks = {r.task for r in matched}
    if len(tasks) == 1:
        return matched
    return []


def _hook_cards(data: FleetData, records_by_role: dict[str, list[ArtifactRecord]]) -> None:
    fleet = data.fleet
    assert fleet is not None  # noqa: S101
    for sview in fleet.sessions:
        acc_session = data.sessions[sview.session_id]
        for aview in sview.agents:
            acc = acc_session.agents[aview.key]
            all_records = data.artifacts.records
            records = _declared_for_role(all_records, acc.role) if acc.role else []
            declared_blockers = sum(1 for r in records if r.kind == "blocker.raised")
            observed_blockers = acc.blockers or (1 if aview.lane == Lane.BLOCKED.value else 0)
            key = f"agent:{sview.session_id}:{aview.key}"
            title = acc.role or ("main" if aview.key == MAIN else aview.key)
            card = Card(
                key=key,
                kind="agent",
                lane=aview.lane,
                title=title,
                detail=f"session {sview.session_id}",
                basis=aview.lane_basis,
                last_ts=aview.last_ts,
                blockers=observed_blockers + declared_blockers,
                declared_blockers=declared_blockers,
                stale=aview.stale,
                session_id=sview.session_id,
                agent_key=aview.key,
            )
            data.cards.append(card)
            data.bundles[key] = AgentBundle(key, acc_session, acc, aview, sview, records)


def _declared_cards(data: FleetData, matched_roles: set[str]) -> None:
    """Roles that only exist as artifact authors (no hook telemetry matches their role)."""
    sessions = reduce_events(data.artifacts.events)
    for session_id, session in sessions.items():
        task = session_id.split(":", 1)[1]
        for agent_key, acc in sorted(session.agents.items()):
            role = acc.role or agent_key
            if role in matched_roles:
                continue
            records = [
                r for r in data.artifacts.records if r.task == task and r.author_role == role
            ]
            key = f"declared:{task}:{role}"
            blockers = sum(1 for r in records if r.kind == "blocker.raised")
            data.cards.append(
                Card(
                    key=key,
                    kind="declared",
                    lane=acc.lane.value,
                    title=role,
                    detail=f"task {task}",
                    basis="self_reported",
                    last_ts=acc.last_ts,
                    blockers=blockers,
                    declared_blockers=blockers,
                    agent_key=agent_key,
                )
            )
            data.bundles[key] = AgentBundle(key, session, acc, None, None, records)


def _worktree_cards(data: FleetData) -> None:
    if data.git is None:
        return
    assert data.fleet is not None  # noqa: S101
    for wt in data.git.worktrees:
        if _owners(wt, data.fleet):
            continue
        name = Path(wt.path).name or wt.path
        branch = wt.branch or ("detached" if wt.detached else "?")
        if data.hooks_kit == HooksKitState.INSTALLED:
            tail = "no telemetry yet (open Cursor here)"
        else:
            tail = "no hook telemetry"
        data.cards.append(
            Card(
                key=f"wt:{wt.path}",
                kind="worktree",
                lane=Lane.UNKNOWN.value,
                title=name,
                detail=f"branch {branch}, {tail}",
                basis="none",
                last_ts=wt.last_commit_ts,
                worktree_path=wt.path,
            )
        )


def _build_cards(data: FleetData) -> None:
    records_by_role: dict[str, list[ArtifactRecord]] = {}
    for record in data.artifacts.records:
        records_by_role.setdefault(record.author_role, []).append(record)
    data.cards = []
    data.bundles = {}
    if data.fleet is not None:
        _hook_cards(data, records_by_role)
    matched = {b.acc.role for b in data.bundles.values() if b.acc.role}
    _declared_cards(data, matched)
    _worktree_cards(data)
