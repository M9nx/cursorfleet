"""Pure view builders: ``FleetData`` + ``UiState`` -> rows and detail text.

No Textual here, so every screen can be asserted as plain text. All untrusted strings go
through :func:`~cursorfleet.tui.theme.safe` and end up in ``rich.text.Text`` (never markup).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from rich.text import Text

from cursorfleet.events.models import Event
from cursorfleet.state.artifact_scan import ArtifactRecord
from cursorfleet.state.event_store import EventPage
from cursorfleet.tui import gates as gate_logic
from cursorfleet.tui.data import AgentBundle, Card, FleetData
from cursorfleet.tui.filters import matches_text
from cursorfleet.tui.theme import (
    BASIS_TAG,
    LANE_MARK,
    LANE_ORDER,
    LANE_TAG,
    SELF_REPORTED_NOTE,
    UNKNOWN_BUDGET,
    Theme,
    fmt_age,
    fmt_duration,
    fmt_ts,
    plural,
    safe,
    short_sha,
)

VIEWS: tuple[str, ...] = ("overview", "timeline", "worktrees", "gates", "evidence", "violations")
VIEW_TITLE = {
    "overview": "Workflow overview",
    "timeline": "Timeline",
    "worktrees": "Worktrees",
    "gates": "Gates",
    "evidence": "Evidence",
    "violations": "Policy violations",
}
MAX_CARDS_PER_LANE = 100
MAX_LIST = 40

INIT_HINT = "cursorfleet init --cursor"
DOCTOR_HINT = "cursorfleet doctor"
GUIDANCE_NO_TELEMETRY = (
    f"No hook telemetry yet. Run `{INIT_HINT}` to install the observe-only hooks, then use "
    f"Cursor in this repo. `{DOCTOR_HINT}` diagnoses the setup."
)
VIOLATIONS_PLACEHOLDER = "policy engine arrives in v0.2"


@dataclass(frozen=True)
class Row:
    key: str
    label: Text
    search: str = ""
    header: bool = False  # headers are shown but cannot be selected


@dataclass
class UiState:
    theme: Theme = field(default_factory=Theme)
    pinned: set[str] = field(default_factory=set)
    filter_text: str = ""
    timeline_limit: int = 200
    selected: dict[str, str] = field(default_factory=dict)  # remembered key per view


def _t(*parts: str | tuple[str, str]) -> Text:
    return Text.assemble(*parts)


def _header(key: str, text: str, style: str = "bold") -> Row:
    return Row(key, Text(text, style=style), header=True)


def _note(key: str, text: str) -> Row:
    return Row(key, Text(text, style="dim"), header=True)


def _visible(rows: Sequence[Row], ui: UiState) -> list[Row]:
    if not ui.filter_text.strip():
        return list(rows)
    keep: list[Row] = []
    for row in rows:
        if row.header or matches_text(row.search, ui.filter_text):
            keep.append(row)
    return keep


# ---------------------------------------------------------------------------- overview


def _card_sort(card: Card, ui: UiState) -> tuple[int, int, float]:
    stamp = card.last_ts.timestamp() if card.last_ts else 0.0
    # pinned first, then blockers (most first), then recency (newest first); never raw activity
    return (0 if card.key in ui.pinned else 1, -card.blockers, -stamp)


def card_label(card: Card, data: FleetData, ui: UiState) -> Text:
    mark = LANE_MARK.get(card.lane, "[?]")
    pin = "* " if card.key in ui.pinned else ""
    basis = BASIS_TAG.get(card.basis, card.basis)
    bundle = data.bundles.get(card.key)
    tail: list[str] = [basis]
    if card.kind == "agent" and card.lane == "stale_offline":
        last = bundle.view.last_lane if bundle and bundle.view else None
        tail.append(f"silent, was {last or '?'} (not idle)")
    if card.kind != "worktree" or card.last_ts:
        tail.append(
            ("declared " if card.kind == "declared" else "") + fmt_age(data.now, card.last_ts)
        )
    if card.blockers:
        tail.append(
            f"BLOCKERS:{card.blockers}" + (" (self-reported)" if card.declared_blockers else "")
        )
    return _t(
        pin,
        (mark, ui.theme.lane(card.lane)),
        " ",
        (safe(card.title, 40), "bold"),
        "  ",
        (safe(card.detail, 60), "dim"),
        "  ",
        "  ".join(tail),
    )


def overview_rows(data: FleetData, ui: UiState) -> list[Row]:
    by_lane: dict[str, list[Card]] = {lane: [] for lane in LANE_ORDER}
    for card in data.cards:
        by_lane.setdefault(card.lane if card.lane in by_lane else "unknown", []).append(card)
    rows: list[Row] = []
    for lane in LANE_ORDER:
        cards = sorted(by_lane[lane], key=lambda c: _card_sort(c, ui))
        shown: list[Row] = []
        for card in cards[:MAX_CARDS_PER_LANE]:
            search = f"{card.title} {card.detail} {LANE_TAG[lane]} {card.basis} {card.kind}"
            shown.append(Row(card.key, card_label(card, data, ui), search.lower()))
        visible = _visible(shown, ui)
        count = f"{len(visible)}" if not ui.filter_text.strip() else f"{len(visible)}/{len(cards)}"
        rows.append(
            Row(
                f"lane:{lane}",
                _t(
                    (
                        f"{LANE_MARK[lane]} {LANE_TAG[lane]} ({count})",
                        ui.theme.lane(lane) or "bold",
                    ),
                ),
                header=True,
            )
        )
        rows.extend(visible)
        if len(cards) > MAX_CARDS_PER_LANE:
            rows.append(
                _note(f"more:{lane}", f"  +{len(cards) - MAX_CARDS_PER_LANE} older (filter with /)")
            )
        if lane == "unknown":
            rows.extend(_guidance_rows(data))
    return rows


def _guidance_rows(data: FleetData) -> list[Row]:
    rows: list[Row] = []
    if data.repo_root is None:
        rows.append(_note("g:repo", "Not inside a git repository. Run from a repo or pass --path."))
        rows.append(_note("g:repo2", f"Setup: `{INIT_HINT}`, check with `{DOCTOR_HINT}`."))
    elif data.telemetry == "none":
        rows.append(_note("g:none", GUIDANCE_NO_TELEMETRY))
        rows.append(
            _note(
                "g:honest",
                "Without telemetry the state is UNKNOWN; CursorFleet never infers inactivity.",
            )
        )
    return rows


def _declared_lines(records: Sequence[ArtifactRecord]) -> dict[str, list[ArtifactRecord]]:
    out: dict[str, list[ArtifactRecord]] = {}
    for record in sorted(records, key=lambda r: (r.created, r.path)):
        out.setdefault(record.kind, []).append(record)
    return out


class _Doc:
    """Tiny builder for the detail pane."""

    def __init__(self, theme: Theme) -> None:
        self.theme = theme
        self.text = Text()

    def title(self, text: str, style: str = "") -> None:
        self.text.append(text + "\n", style=style or self.theme.accent)

    def line(self, label: str, value: str, style: str = "") -> None:
        self.text.append(f"{label:<13}", style="dim")
        self.text.append(value + "\n", style=style)

    def raw(self, value: str, style: str = "") -> None:
        self.text.append(value + "\n", style=style)

    def blank(self) -> None:
        self.text.append("\n")


def agent_detail(
    data: FleetData, ui: UiState, key: str, tools: Sequence[Event] | None = None
) -> Text:
    bundle = data.bundles.get(key)
    if bundle is None:
        return Text("Select an agent to see its detail.", style="dim")
    doc = _Doc(ui.theme)
    acc, view = bundle.acc, bundle.view
    declared_only = view is None
    lane = view.lane if view else acc.lane.value
    title = safe(acc.role or ("main agent" if acc.key == "main" else acc.key), 60)
    doc.title(f"AGENT {title}")
    doc.line(
        "Lane",
        f"{LANE_MARK.get(lane, '[?]')} {LANE_TAG.get(lane, lane)}",
        ui.theme.lane(lane),
    )
    if view is not None:
        basis = BASIS_TAG.get(view.lane_basis, view.lane_basis)
        doc.line("Lane basis", f"{basis} (heuristic over events; {view.attribution} attribution)")
        if view.stale:
            doc.line(
                "Silent",
                f"no live event for {fmt_age(data.now, bundle.acc.last_live_ts)}; "
                f"last lane was {view.last_lane or '?'}. Silence is not idleness.",
                "bold",
            )
    else:
        doc.line("Lane basis", "SELF-REPORTED by artifact only; no hook telemetry for this role")
    doc.line("Role", safe(acc.role or "-"))
    if bundle.session is not None and not declared_only:
        doc.line("Session", safe(bundle.session.session_id, 80))
        doc.line("Agent key", safe(acc.key, 80))
        if acc.instance_id:
            doc.line("Instance", safe(acc.instance_id, 80))
    _task_lines(doc, bundle)
    _worktree_lines(doc, data, bundle)
    if view is not None:
        _activity_lines(doc, data, bundle, tools)
        _gate_lines(doc, data, bundle)
    doc.line("Token/cost", UNKNOWN_BUDGET)
    _declared_lines_into(doc, bundle)
    return doc.text


def _task_lines(doc: _Doc, bundle: AgentBundle) -> None:
    records = bundle.records
    tasks = sorted({r.task for r in records})
    if tasks:
        doc.line(
            "Task", f"{', '.join(safe(t, 40) for t in tasks[:4])}  [SELF-REPORTED, by role name]"
        )
    else:
        doc.line("Task", "unknown (no artifact declares one for this role)")
    observed = list(bundle.acc.issue_refs)
    declared = sorted({r.issue_ref for r in records if r.issue_ref})
    refs = [f"{safe(r, 40)} (observed)" for r in observed]
    refs += [f"{safe(r, 40)} (SELF-REPORTED)" for r in declared if r not in observed]
    doc.line("Issues", ", ".join(refs[:6]) if refs else "none known")


def _worktree_lines(doc: _Doc, data: FleetData, bundle: AgentBundle) -> None:
    acc = bundle.acc
    wt = data.worktree_by_id(acc.worktree_id)
    if wt is not None:
        branch = wt.branch or ("detached" if wt.detached else "?")
        dirty = "?" if wt.dirty_count is None else str(wt.dirty_count)
        doc.line("Worktree", safe(wt.path, 100))
        doc.line("Branch", f"{safe(branch, 60)}  HEAD {short_sha(wt.head)}  dirty files: {dirty}")
    elif acc.branch or acc.commit or acc.worktree_id:
        doc.line("Worktree", f"{safe(acc.worktree_id or '?')} (not listed by git now)")
        doc.line(
            "Branch",
            f"{safe(acc.branch or '?', 60)}  commit {short_sha(acc.commit)} (as last seen)",
        )
    else:
        doc.line("Worktree", "unknown")


def _activity_lines(
    doc: _Doc, data: FleetData, bundle: AgentBundle, tools: Sequence[Event] | None
) -> None:
    acc, view = bundle.acc, bundle.view
    assert view is not None  # noqa: S101
    more = "+" if acc.files_overflow else ""
    doc.line("Files", f"{len(acc.files)}{more} changed (observed)")
    if tools:
        names = [safe(e.tool_name or e.kind.value, 24) for e in tools]
        doc.line("Last tools", ", ".join(names))
    else:
        doc.line("Last tools", safe(acc.last_tool or "none observed", 40))
    if acc.last_test is not None:
        doc.line(
            "Tests",
            f"last run {acc.last_test.outcome.value} "
            f"{fmt_age(data.now, acc.last_test.ts)} (observed)",
        )
    else:
        doc.line("Tests", "no test run observed")
    fails = f" ({view.tool_failures} failed)" if view.tool_failures else ""
    doc.line("Elapsed", fmt_duration(view.elapsed_s))
    doc.line("Tool calls", f"{view.tool_call_count}{fails}")
    ctx = (
        f", context {view.last_context_usage_percent:.0f}%"
        if view.last_context_usage_percent is not None
        else ""
    )
    doc.line("Compactions", f"{view.compactions}{ctx}")
    if view.stop_report is not None:
        sr = view.stop_report
        calls = sr.tool_call_count if sr.tool_call_count is not None else "?"
        doc.line(
            "Stop report",
            f"outcome {sr.outcome or '?'}, {calls} tool calls (reported by Cursor)",
        )


def _gate_lines(doc: _Doc, data: FleetData, bundle: AgentBundle) -> None:
    rows = data.gates.by_worktree.get(bundle.acc.worktree_id)
    if rows is None:
        doc.line("Gates", "unknown (no evidence for this worktree), display-only")
        return
    doc.line("Gates", "this worktree, display-only, independent signals:")
    for row in rows:
        doc.raw(f"  {row.label}: {row.state.upper()}", doc.theme.gate(row.state))


def _declared_lines_into(doc: _Doc, bundle: AgentBundle) -> None:
    records = bundle.records
    if not records:
        doc.line("Declared", "no artifacts for this role")
        return
    doc.blank()
    doc.title(f"DECLARED BY THE AGENT - {SELF_REPORTED_NOTE}", "bold")
    groups = _declared_lines(records)
    for kind, label in (
        ("context.loaded", "Context sources"),
        ("plan.created", "Plans"),
        ("handoff.created", "Handoffs"),
        ("blocker.raised", "Blockers"),
    ):
        items = groups.get(kind, [])
        if not items:
            continue
        if kind == "context.loaded":
            refs = sorted({ref for r in items for ref in r.context_refs})
            shown = ", ".join(safe(r, 50) for r in refs[:8]) + (
                f" (+{len(refs) - 8} more)" if len(refs) > 8 else ""
            )
            doc.line(label, f"{len(refs)} path(s): {shown or '-'}")
        elif kind == "handoff.created":
            last = items[-1]
            dest = safe(last.to_role or "unspecified", 40)
            doc.line(label, f"{len(items)}; latest destination: {dest}")
        else:
            latest = items[-1]
            doc.line(
                label,
                f"{len(items)}; latest {fmt_ts(latest.created)} UTC task {safe(latest.task, 40)}",
            )


# ---------------------------------------------------------------------------- timeline

_SRC = {"observed": "obs", "self_reported": "SELF", "derived": "drv"}
_ATTR = {"exact": "exact", "inferred": "infer", "unknown": "unk"}


def event_summary(event: Event) -> str:
    bits: list[str] = []
    if event.tool_name:
        bits.append(safe(event.tool_name, 30))
    if event.command is not None:
        shown = event.command.display or event.command.argv0
        bits.append(safe(shown, 70))
        if event.command.exit_code is not None:
            bits.append(f"exit {event.command.exit_code}")
    if event.paths:
        bits.append(
            safe(event.paths[0].path, 60)
            + (f" +{len(event.paths) - 1}" if len(event.paths) > 1 else "")
        )
    if event.outcome is not None:
        bits.append(event.outcome.value)
    if event.gate is not None:
        bits.append(f"{event.gate.name}={event.gate.state.value}")
    if event.issue_ref:
        bits.append(safe(event.issue_ref, 30))
    return " ".join(bits)


def event_label(event: Event, ui: UiState) -> Text:
    risk = f" RISK:{event.risk.value}" if event.risk.value != "none" else ""
    src = _SRC.get(event.source.value, event.source.value)
    who = safe(event.agent_id or "main/unknown", 28)
    return _t(
        (fmt_ts(event.ts), "dim"),
        " ",
        (f"{event.kind.value:<17}", "bold"),
        f" {src}/{_ATTR.get(event.attribution.value, '?')} ",
        (who, ""),
        " ",
        event_summary(event),
        (risk, "bold" if risk else ""),
    )


def timeline_rows(data: FleetData, ui: UiState, page: EventPage | None = None) -> list[Row]:
    page = page or data.timeline
    rows: list[Row] = []
    shown = len(page.events)
    note = f"Showing {shown} of {page.total} matching event(s), newest first. Times are UTC."
    rows.append(_header("tl:head", note))
    if page.total > shown:
        rows.append(_note("tl:more", "Press m to load more."))
    for err in data.timeline_errors:
        rows.append(_note(f"tl:err:{err}", f"filter problem: {err}"))
    if page.error:
        rows.append(_note("tl:error", page.error))
    if page.skipped:
        rows.append(
            _note(
                "tl:skipped", f"{page.skipped} stored event(s) no longer validate and were skipped"
            )
        )
    if not page.events:
        rows.append(
            _note(
                "tl:empty",
                "No events match." if page.total == 0 and ui.filter_text else GUIDANCE_NO_TELEMETRY,
            )
        )
    for event in page.events:
        rows.append(Row(f"ev:{event.session_id}:{event.event_id}", event_label(event, ui)))
    return rows


def _attr_explain(event: Event) -> str:
    return {
        "exact": "identity came in the Cursor payload itself",
        "inferred": "linked by tool_use_id or worktree (PROVISIONAL)",
        "unknown": "Cursor did not say which agent (PROVISIONAL, ADR 0001 Q1)",
    }.get(event.attribution.value, "")


def event_detail(event: Event | None, ui: UiState) -> Text:
    if event is None:
        return Text("Select an event to see its sanitized fields.", style="dim")
    doc = _Doc(ui.theme)
    doc.title(f"EVENT {event.kind.value}")
    src = event.source.value
    note = "  [SELF-REPORTED: a claim, not evidence]" if src == "self_reported" else ""
    doc.line("Source", f"{src}{note}")
    doc.line("Attribution", f"{event.attribution.value}: {_attr_explain(event)}")
    doc.line("Time", f"{fmt_ts(event.ts)} UTC")
    doc.line("Producer", f"{event.producer.value} {safe(event.producer_version, 30)}")
    doc.line("Risk", f"{event.risk.value} (informational only; v0.1 never acts on it)")
    doc.line("Session", safe(event.session_id, 100))
    doc.line("Agent", safe(event.agent_id or "none (main agent or unattributed)", 100))
    for label, value in (
        ("Worktree", event.worktree_id),
        ("Branch", event.branch),
        ("Commit", event.commit),
        ("Issue", event.issue_ref),
        ("Tool", event.tool_name),
        ("Hook", event.hook),
        ("Outcome", event.outcome.value if event.outcome else None),
        ("Status", event.status.value if event.status else None),
    ):
        if value:
            doc.line(label, safe(value, 100))
    if event.gate is not None:
        doc.line("Gate", f"{event.gate.name} = {event.gate.state.value}")
    if event.command is not None:
        cmd = event.command
        doc.line(
            "Command",
            safe(cmd.display or cmd.argv0, 200)
            + ("  (truncated)" if cmd.display_truncated else ""),
        )
        extra = [f"argv0 {safe(cmd.argv0, 40)}"]
        if cmd.subcommand:
            extra.append(f"sub {safe(cmd.subcommand, 40)}")
        if cmd.exit_code is not None:
            extra.append(f"exit {cmd.exit_code}")
        if cmd.duration_ms is not None:
            extra.append(f"{cmd.duration_ms} ms")
        doc.line("", "  ".join(extra))
    if event.paths:
        doc.line("Paths", plural(len(event.paths), "path") + " (workspace-relative):")
        for item in event.paths[:MAX_LIST]:
            doc.raw(f"  {safe(item.path, 120)} ({item.op.value})")
        if len(event.paths) > MAX_LIST:
            doc.raw(f"  ... +{len(event.paths) - MAX_LIST} more")
    if event.metrics is not None:
        parts = [f"{k}={v}" for k, v in event.metrics.model_dump(exclude_none=True).items()]
        doc.line("Metrics", ", ".join(parts))
    return doc.text


# ---------------------------------------------------------------------------- worktrees


def worktree_rows(data: FleetData, ui: UiState) -> list[Row]:
    rows: list[Row] = []
    if data.git is None:
        reason = "git collection is disabled (--no-git)" if not data.git_enabled else "no data yet"
        return [_header("wt:none", f"No worktree data: {reason}.")]
    if not data.git.available:
        return [
            _header("wt:down", f"git data unavailable: {safe(data.git.error, 100)}"),
            _note("wt:hint", f"Run from inside a git repository, then `{DOCTOR_HINT}`."),
        ]
    rows.append(
        _header(
            "wt:head",
            f"{plural(len(data.git.worktrees), 'worktree')} (read-only; r re-reads, "
            "CursorFleet never fetches, so ahead/behind can lag the remote).",
        )
    )
    for index, wt in enumerate(data.git.worktrees):
        branch = wt.branch or ("detached" if wt.detached else "?")
        dirty = "dirty ?" if wt.dirty_count is None else f"dirty {wt.dirty_count}"
        sync = "no upstream" if wt.ahead is None else f"ahead {wt.ahead}/behind {wt.behind}"
        marks = [f"STALE({','.join(wt.stale_reasons)})"] if wt.stale else []
        owners = _owner_names(data, wt.worktree_id)
        label = _t(
            ("[main] " if wt.is_main else "[wt]   ", "bold"),
            (safe(branch, 40), "bold"),
            f"  HEAD {short_sha(wt.head)}  {dirty}  {sync}  ",
            ("  ".join(marks), "bold" if marks else ""),
            f"  owner: {owners}" if owners else "  owner: unknown (no telemetry)",
            f"  last commit {fmt_age(data.now, wt.last_commit_ts)}",
        )
        search = f"{wt.path} {branch} {' '.join(marks)} {owners}".lower()
        rows.append(Row(f"wt:{index}:{wt.path}", label, search))
    return [rows[0], *_visible(rows[1:], ui)]


def _owner_names(data: FleetData, worktree_id: str | None) -> str:
    if worktree_id is None:
        return ""
    names: list[str] = []
    for bundle in data.bundles.values():
        if bundle.acc.worktree_id == worktree_id and bundle.view is not None:
            names.append(safe(bundle.acc.role or bundle.acc.key, 30))
    return ", ".join(sorted(set(names)))


def worktree_detail(data: FleetData, ui: UiState, key: str) -> Text:
    if data.git is None:
        return Text("No worktree data.", style="dim")
    wt = next((w for i, w in enumerate(data.git.worktrees) if key == f"wt:{i}:{w.path}"), None)
    if wt is None:
        return Text("Select a worktree.", style="dim")
    doc = _Doc(ui.theme)
    doc.title(f"WORKTREE {'(main) ' if wt.is_main else ''}{safe(_base_name(wt.path), 60)}")
    doc.line("Path", safe(wt.path, 200))
    doc.line("Branch", safe(wt.branch or ("detached HEAD" if wt.detached else "?"), 100))
    doc.line("HEAD", wt.head or "-")
    dirty = "unknown" if wt.dirty_count is None else f"{wt.dirty_count} file(s)"
    doc.line("Dirty", dirty)
    if wt.ahead is None:
        doc.line("Ahead/behind", "unknown (no upstream, detached HEAD or unreadable ref)")
    else:
        doc.line(
            "Ahead/behind", f"+{wt.ahead} / -{wt.behind} vs the existing upstream ref (no fetch)"
        )
    doc.line(
        "State",
        ", ".join(
            s
            for s, on in (
                ("locked", wt.locked),
                ("prunable", wt.prunable),
                ("bare", wt.bare),
                ("missing", not wt.exists),
            )
            if on
        )
        or "normal",
    )
    doc.line("Stale", ", ".join(wt.stale_reasons) if wt.stale else "no")
    owners = _owner_names(data, wt.worktree_id)
    doc.line("Owner", owners or "unknown (no hook telemetry links an agent to this worktree)")
    doc.line(
        "Last commit", f"{fmt_ts(wt.last_commit_ts)} UTC ({fmt_age(data.now, wt.last_commit_ts)})"
    )
    if wt.error:
        doc.line("Problem", safe(wt.error, 100))
    doc.blank()
    doc.raw("Cursor creates and deletes worktrees itself; this list is a snapshot.", "dim")
    return doc.text


def _base_name(path: str) -> str:
    return path.rstrip("/\\").rsplit("/", 1)[-1].rsplit("\\", 1)[-1] or path


# ---------------------------------------------------------------------------- gates


def _gate_board(data: FleetData) -> list[tuple[str | None, str, list[gate_logic.GateStatus]]]:
    """``(worktree_id, title, statuses)`` for each worktree, plus unlinked evidence."""
    boards: list[tuple[str | None, str, list[gate_logic.GateStatus]]] = []
    seen: set[str | None] = set()
    if data.git is not None:
        for wt in data.git.worktrees:
            statuses = data.gates.by_worktree.get(wt.worktree_id)
            if statuses is None:
                statuses = gate_logic.evaluate([], worktree_id=wt.worktree_id, head=wt.head)
            branch = wt.branch or ("detached" if wt.detached else "?")
            boards.append((wt.worktree_id, f"{safe(branch, 40)} @ {short_sha(wt.head)}", statuses))
            seen.add(wt.worktree_id)
    for wt_id, statuses in data.gates.by_worktree.items():
        if wt_id not in seen:
            title = f"worktree {safe(wt_id or 'unlinked', 30)} (not listed by git; HEAD unknown)"
            boards.append((wt_id, title, statuses))
    if not boards:
        boards.append(
            (
                None,
                "no git data (gates cannot be bound to a commit)",
                gate_logic.evaluate([], worktree_id=None, head=None),
            )
        )
    return boards


def gate_rows(data: FleetData, ui: UiState) -> list[Row]:
    rows: list[Row] = [
        _header(
            "gt:head", f"GATES - {gate_logic.DISPLAY_ONLY}. Independent signals; no overall score."
        ),
        _note(
            "gt:rule",
            "Evidence = observed test/lint/type runs bound to a commit. "
            "Self-reported claims never count.",
        ),
    ]
    for wt_id, title, statuses in _gate_board(data):
        rows.append(_header(f"gt:wt:{wt_id}", f"== {title}"))
        for status in statuses:
            label = _t(
                (f"[{status.state.upper():<7}]", ui.theme.gate(status.state)),
                f" {status.label:<19} ",
                (safe(status.detail, 80), "dim"),
            )
            rows.append(
                Row(
                    f"gt:{wt_id}:{status.gate}",
                    label,
                    f"{status.label} {status.state} {title}".lower(),
                )
            )
    return [r for r in _visible(rows, ui)]


def gate_detail(data: FleetData, ui: UiState, key: str) -> Text:
    for wt_id, title, statuses in _gate_board(data):
        for status in statuses:
            if key != f"gt:{wt_id}:{status.gate}":
                continue
            doc = _Doc(ui.theme)
            doc.title(f"GATE {status.label}")
            doc.line("State", status.state.upper(), ui.theme.gate(status.state))
            doc.line("Detail", status.detail)
            doc.line("Worktree", title)
            doc.line("HEAD", status.head or "unknown")
            item = status.evidence
            if item is None:
                doc.line(
                    "Evidence",
                    "none. In v0.1 only observed test/lint/type runs and "
                    "gate.changed events count.",
                )
            else:
                doc.line("Evidence", f"{item.origin} (observed/derived from Cursor hooks)")
                doc.line("Result", item.state)
                doc.line("Commit", item.commit or "not recorded")
                doc.line("When", f"{fmt_ts(item.ts)} UTC ({fmt_age(data.now, item.ts)})")
                doc.line("Agent", safe(item.agent or "unattributed", 60))
                if item.command:
                    doc.line("Command", safe(item.command, 160))
                if item.note:
                    doc.line("Note", item.note)
            doc.blank()
            doc.raw(gate_logic.DISPLAY_ONLY + ".", "bold")
            return doc.text
    return Text("Select a gate.", style="dim")


# ---------------------------------------------------------------------------- evidence


def evidence_rows(data: FleetData, ui: UiState) -> list[Row]:
    rows: list[Row] = [
        _header("ev:h1", "OBSERVED / DERIVED EVIDENCE (test, lint and type runs; gate events)")
    ]
    latest = sorted(data.gates.evidence, key=lambda e: (e.ts, e.session_id), reverse=True)
    if not latest:
        rows.append(_note("ev:none", "none yet: no verify-style command has been observed."))
    for index, item in enumerate(latest[:MAX_LIST]):
        label = _t(
            (f"[{item.state.upper():<7}]", ui.theme.gate(item.state)),
            f" {gate_logic.GATE_LABEL[item.gate]:<19} @{short_sha(item.commit)} ",
            (fmt_age(data.now, item.ts), "dim"),
            f"  {safe(item.command or item.origin, 60)}",
        )
        rows.append(
            Row(f"evi:{index}", label, f"{item.gate} {item.state} {item.command or ''}".lower())
        )
    rows.append(_header("ev:h2", f"DECLARED BY AGENTS - {SELF_REPORTED_NOTE}"))
    records = sorted(data.artifacts.records, key=lambda r: (r.created, r.path), reverse=True)
    if not records:
        rows.append(_note("ev:noart", "no valid artifacts under the work directory."))
    for index, rec in enumerate(records[:MAX_LIST]):
        label = _t(
            ("[SELF]", "bold"),
            f" {rec.kind:<16} {safe(rec.author_role, 24)}",
            f" -> {safe(rec.to_role, 20)}" if rec.to_role else "",
            f"  task {safe(rec.task, 30)}  ",
            (fmt_age(data.now, rec.created), "dim"),
        )
        rows.append(
            Row(
                f"art:{index}",
                label,
                f"{rec.kind} {rec.author_role} {rec.task} {rec.to_role or ''}".lower(),
            )
        )
    if data.artifacts.issues:
        rows.append(
            _header("ev:h3", "INVALID ARTIFACTS (validation problems; not shown as declarations)")
        )
        for index, issue in enumerate(data.artifacts.issues[:MAX_LIST]):
            rows.append(
                Row(
                    f"iss:{index}",
                    _t(("[INVALID]", "bold"), f" {safe(issue.path, 60)}: {issue.message}"),
                    f"{issue.path} {issue.code}".lower(),
                )
            )
    return _visible(rows, ui)


def evidence_detail(data: FleetData, ui: UiState, key: str) -> Text:
    doc = _Doc(ui.theme)
    if key.startswith("evi:"):
        latest = sorted(data.gates.evidence, key=lambda e: (e.ts, e.session_id), reverse=True)
        index = int(key[4:])
        if index < len(latest):
            item = latest[index]
            doc.title(f"EVIDENCE {gate_logic.GATE_LABEL[item.gate]}")
            doc.line("Result", item.state.upper(), ui.theme.gate(item.state))
            doc.line("Origin", f"{item.origin} (observed/derived from Cursor hooks)")
            doc.line("Commit", item.commit or "not recorded (evidence cannot be bound)")
            doc.line("Session", safe(item.session_id, 80))
            doc.line("Agent", safe(item.agent or "unattributed", 60))
            doc.line("When", f"{fmt_ts(item.ts)} UTC")
            if item.command:
                doc.line("Command", safe(item.command, 160))
            if item.note:
                doc.line("Note", item.note)
            return doc.text
    if key.startswith("art:"):
        records = sorted(data.artifacts.records, key=lambda r: (r.created, r.path), reverse=True)
        index = int(key[4:])
        if index < len(records):
            rec = records[index]
            doc.title(f"DECLARATION {rec.kind}", "bold")
            doc.raw(SELF_REPORTED_NOTE, "bold")
            doc.line("Task", safe(rec.task, 60))
            doc.line("Author role", f"{safe(rec.author_role, 40)} (claimed; can be forged)")
            doc.line("To role", safe(rec.to_role or "-", 40))
            doc.line("Issue", safe(rec.issue_ref or "-", 60))
            doc.line("Created", f"{fmt_ts(rec.created)} UTC")
            doc.line("File", safe(rec.path, 100))
            doc.line("Context", f"{len(rec.context_refs)} path(s)")
            for ref in rec.context_refs[:MAX_LIST]:
                doc.raw(f"  {safe(ref, 100)}")
            return doc.text
    if key.startswith("iss:"):
        index = int(key[4:])
        if index < len(data.artifacts.issues):
            issue = data.artifacts.issues[index]
            doc.title("INVALID ARTIFACT", "bold")
            doc.line("File", safe(issue.path, 100))
            doc.line("Problem", issue.message)
            doc.line("Code", issue.code)
            doc.raw(
                "Fix the file and run `cursorfleet validate`. The file's content is never shown.",
                "dim",
            )
            return doc.text
    return Text("Select an item to see its detail.", style="dim")


# ---------------------------------------------------------------------------- violations


def violations_rows(data: FleetData, ui: UiState) -> list[Row]:
    return [
        _header("pv:h", f"POLICY VIOLATIONS - {VIOLATIONS_PLACEHOLDER}"),
        _note("pv:1", "v0.1 observes only: nothing is allowed, denied or flagged by policy."),
        _note("pv:2", "Per-event risk labels are informational; see the timeline (l)."),
    ]


def violations_detail() -> Text:
    return Text(
        f"Policy violations: {VIOLATIONS_PLACEHOLDER}.\n\n"
        "v0.1 is Observe-only. There is no policy engine, no allow/deny decision and no "
        "approval flow, so there is nothing to list here.",
        style="",
    )


# ---------------------------------------------------------------------------- dispatch


def rows_for(view: str, data: FleetData, ui: UiState) -> list[Row]:
    if view == "timeline":
        return timeline_rows(data, ui)
    if view == "worktrees":
        return worktree_rows(data, ui)
    if view == "gates":
        return gate_rows(data, ui)
    if view == "evidence":
        return evidence_rows(data, ui)
    if view == "violations":
        return violations_rows(data, ui)
    return overview_rows(data, ui)


def detail_for(  # noqa: PLR0911 - one return per view, clearer than a table
    view: str,
    data: FleetData,
    ui: UiState,
    key: str | None,
    tools: Sequence[Event] | None = None,
) -> Text:
    if view == "violations":
        return violations_detail()
    if key is None:
        return Text("Nothing selected.", style="dim")
    if view == "timeline":
        found = next(
            (e for e in data.timeline.events if f"ev:{e.session_id}:{e.event_id}" == key), None
        )
        return event_detail(found, ui)
    if view == "worktrees":
        return worktree_detail(data, ui, key)
    if view == "gates":
        return gate_detail(data, ui, key)
    if view == "evidence":
        return evidence_detail(data, ui, key)
    return (
        agent_detail(data, ui, key, tools)
        if not key.startswith("wt:")
        else _wt_card_detail(data, ui, key)
    )


def _wt_card_detail(data: FleetData, ui: UiState, key: str) -> Text:
    """Detail for a git-only worktree card in the overview (no telemetry)."""
    if data.git is None:
        return Text("No data.", style="dim")
    for index, wt in enumerate(data.git.worktrees):
        if key == f"wt:{wt.path}":
            text = worktree_detail(data, ui, f"wt:{index}:{wt.path}")
            text.append("\nNo hook telemetry: lane is UNKNOWN, never idle.\n", style="bold")
            text.append(f"Run `{INIT_HINT}` and `{DOCTOR_HINT}` to get telemetry.\n", style="dim")
            return text
    return Text("Select an item.", style="dim")


def recent_events_text(data: FleetData, ui: UiState, count: int = 12) -> Text:
    """Tile content: the newest events, no selection."""
    text = Text("RECENT EVENTS\n", style=ui.theme.accent)
    if not data.recent.events:
        text.append("none yet\n", style="dim")
    for event in data.recent.events[:count]:
        text.append_text(event_label(event, ui))
        text.append("\n")
    return text


def side_summary_text(data: FleetData, ui: UiState) -> Text:
    """Tile content: gate state per worktree (no aggregate) and worktree facts."""
    text = Text("GATES + WORKTREES (display-only)\n", style=ui.theme.accent)
    for _wt, title, statuses in _gate_board(data)[:4]:
        text.append(f"{title}\n", style="bold")
        text.append(
            "  " + "  ".join(f"{s.label.split()[0]}:{s.state.upper()}" for s in statuses) + "\n"
        )
    return text


def card_for_key(data: FleetData, key: str) -> Card | None:
    return next((c for c in data.cards if c.key == key), None)


def first_selectable(rows: Sequence[Row]) -> str | None:
    return next((r.key for r in rows if not r.header), None)
