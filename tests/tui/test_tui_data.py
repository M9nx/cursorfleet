"""The TUI data layer and pure views (no Textual): honesty, ordering, resilience."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from cursorfleet.adapters.cursor.hooksjson import HOOK_COMMAND
from cursorfleet.state.event_store import EventFilter
from cursorfleet.tui import views
from cursorfleet.tui.data import DataSource, FleetData
from cursorfleet.tui.filters import matches_text, parse_time, parse_timeline_filter
from cursorfleet.tui.theme import LANE_ORDER, LANE_TAG, Theme, safe
from m2_helpers import git
from tui_helpers import NOW, build_fleet, make_source, new_repo, write_artifact

IDLE_CLAIM = re.compile(r"(?<!not )(?<!never )(?<!is not )\bidle\b", re.IGNORECASE)


def load(repo: Path, **kwargs: object) -> FleetData:
    return make_source(repo).load(**kwargs)  # type: ignore[arg-type]


def all_text(data: FleetData, ui: views.UiState | None = None) -> str:
    ui = ui or views.UiState()
    chunks: list[str] = []
    for view in views.VIEWS:
        rows = views.rows_for(view, data, ui)
        chunks.extend(r.label.plain for r in rows)
        for row in rows:
            if not row.header:
                chunks.append(views.detail_for(view, data, ui, row.key).plain)
    return "\n".join(chunks)


def test_overview_has_every_lane_in_order_and_unknown_bucket(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    build_fleet(repo)
    rows = views.overview_rows(load(repo), views.UiState())
    headers = [r.label.plain for r in rows if r.header and r.key.startswith("lane:")]
    assert [h.split("] ", 1)[1].rsplit(" (", 1)[0] for h in headers] == [
        LANE_TAG[lane] for lane in LANE_ORDER
    ]
    assert "UNKNOWN / NO TELEMETRY" in headers[-1]


def test_silent_agents_are_stale_not_idle(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    build_fleet(repo)
    data = load(repo)
    stale = [c for c in data.cards if c.lane == "stale_offline"]
    assert {c.title for c in stale} == {"scout", "main"}
    assert not IDLE_CLAIM.search(all_text(data))
    assert "not idle" in all_text(data)


def test_no_telemetry_is_unknown_never_idle(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    data = load(repo)
    assert data.telemetry == "none"
    unknown = [c for c in data.cards if c.lane == "unknown"]
    assert unknown and all(c.kind == "worktree" and c.basis == "none" for c in unknown)
    text = all_text(data)
    assert not IDLE_CLAIM.search(text)
    assert "cursorfleet init --cursor" in text and "cursorfleet doctor" in text


def test_installed_kit_without_sessions_shows_await_cursor(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    (repo / ".cursorfleet/install.lock.json").write_text('{"lock_version":"1"}\n', encoding="utf-8")
    (repo / ".cursor").mkdir(exist_ok=True)
    hooks = {
        "version": 1,
        "hooks": {"sessionStart": [{"command": HOOK_COMMAND, "timeout": 5}]},
    }
    (repo / ".cursor/hooks.json").write_text(json.dumps(hooks), encoding="utf-8")
    data = load(repo)
    assert data.telemetry == "none"
    text = all_text(data)
    assert "Open this folder in **Cursor**" in text
    assert "cursorfleet init --cursor" not in text
    wt = next(c for c in data.cards if c.kind == "worktree")
    assert "open Cursor here" in wt.detail


def test_sorted_by_blockers_then_recency_not_activity(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    fleet = build_fleet(repo)
    common = {"worktree_id": fleet.wt_id, "branch": "main", "commit": fleet.head}
    # Two more working agents: `calm` is the most recent, `stuck` has an older blocker.
    for role, ts, kind in (
        ("stuck", "2026-10-04T12:00:30.000Z", "blocker.raised"),
        ("calm", "2026-10-04T12:04:50.000Z", "tool.started"),
    ):
        fleet.add(
            "s-active",
            "subagent.started",
            ts,
            agent_role=role,
            agent_instance_id=f"{role}1",
            attribution="exact",
            **common,
        )
        if kind == "blocker.raised":
            write_artifact(repo, "t1", f"01-blocker-{role}.md", kind, role)
    data = load(repo)
    working = [c for c in data.cards if c.lane == "working"]
    ordered = [c.title for c in sorted(working, key=lambda c: views._card_sort(c, views.UiState()))]
    assert ordered.index("stuck") < ordered.index("calm")  # blockers first
    assert ordered.index("calm") < ordered.index("reviewer")  # then most recent
    rows = [r.key for r in views.overview_rows(data, views.UiState()) if not r.header]
    assert rows.index(next(c.key for c in working if c.title == "stuck")) < rows.index(
        next(c.key for c in working if c.title == "calm")
    )


def test_pinned_first_within_lane(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    build_fleet(repo)
    data = load(repo)
    old = next(c for c in data.cards if c.title == "scout")
    ui = views.UiState(pinned={old.key})
    rows = views.overview_rows(data, ui)
    stale_rows = [
        r
        for r in rows
        if not r.header and r.key in {c.key for c in data.cards if c.lane == "stale_offline"}
    ]
    assert stale_rows[0].key == old.key and stale_rows[0].label.plain.startswith("* ")


def test_self_reported_artifacts_are_labelled_and_matched_by_role(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    build_fleet(repo)
    write_artifact(
        repo, "add-login", "01-plan-architect.md", "plan.created", "architect", issue_ref="'#7'"
    )
    write_artifact(
        repo,
        "add-login",
        "02-handoff-implementer.md",
        "handoff.created",
        "implementer",
        to_role="reviewer",
    )
    write_artifact(repo, "add-login", "03-context-implementer.md", "context.loaded", "implementer")
    data = load(repo)
    declared = next(c for c in data.cards if c.kind == "declared")
    assert declared.title == "architect" and declared.basis == "self_reported"
    assert declared.lane == "planning"
    ui = views.UiState()
    impl = next(c for c in data.cards if c.title == "implementer")
    detail = views.agent_detail(data, ui, impl.key).plain
    assert "SELF-REPORTED" in detail and "destination: reviewer" in detail
    assert "Task         add-login" in detail
    assert "unknown (not exposed by Cursor hooks)" in detail
    # the card keeps its observed lane; the declaration never overrides telemetry
    assert impl.lane == "verifying"


def test_invalid_artifacts_surface_as_problems_not_cards(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    work = repo / ".cursorfleet" / "work" / "t1"
    work.mkdir(parents=True)
    (work / "01-plan-x.md").write_text("---\nbogus: 1\n---\nbody\n", encoding="utf-8")
    data = load(repo)
    assert not [c for c in data.cards if c.kind == "declared"]
    assert any("invalid artifact" in p for p in data.problems)
    assert "INVALID" in "\n".join(r.label.plain for r in views.evidence_rows(data, views.UiState()))


def test_gates_stale_after_head_moves(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    fleet = build_fleet(repo)
    source = DataSource(repo, clock=lambda: NOW, git_every=1)
    first = source.load()
    unit = next(s for s in first.gates.by_worktree[fleet.wt_id] if s.gate == "unit_tests")
    assert unit.state == "observed"
    (repo / "NEW.txt").write_text("x\n", encoding="utf-8")
    git(["add", "NEW.txt"], repo)
    git(["commit", "-q", "-m", "move head"], repo)
    second = source.load(force_git=True)
    unit = next(s for s in second.gates.by_worktree[fleet.wt_id] if s.gate == "unit_tests")
    assert unit.state == "stale" and "STALE" in unit.detail
    text = "\n".join(r.label.plain for r in views.gate_rows(second, views.UiState()))
    assert "[STALE  ]" in text and "display-only" in text


def test_gates_unknown_without_git(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    build_fleet(repo)
    data = make_source(repo, with_git=False).load()
    assert data.git is None
    states = {s.state for rows in data.gates.by_worktree.values() for s in rows}
    assert "pass" not in states  # HEAD unknown: never claim a pass
    assert not data.cards or all(c.kind != "worktree" for c in data.cards)


def test_not_a_git_repo_degrades_with_guidance(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    data = DataSource(plain, clock=lambda: NOW).load()
    assert data.repo_root is None and data.cards == []
    assert any("not a git repository" in p for p in data.problems)
    text = "\n".join(r.label.plain for r in views.overview_rows(data, views.UiState()))
    assert "cursorfleet init --cursor" in text and "cursorfleet doctor" in text


def test_corrupt_spool_lines_are_counted_not_fatal(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    fleet = build_fleet(repo)
    spool_file = next(Path(fleet.paths.spool).rglob("*.jsonl"))
    with spool_file.open("ab") as handle:
        handle.write(b"deadbeef {not json}\n")
        handle.write(b"garbage without a crc\n")
    data = load(repo)
    assert data.corruption.total >= 2
    assert any("corrupt or skipped spool line" in p for p in data.problems)
    assert data.telemetry == "hooks"


def test_corrupt_database_is_rebuilt_from_the_spool(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    fleet = build_fleet(repo)
    source = make_source(repo)
    assert source.load().telemetry == "hooks"
    Path(fleet.paths.db).write_bytes(b"not a database" * 100)
    fresh = make_source(repo).load()
    assert fresh.telemetry == "hooks" and len(fresh.sessions) == 2
    assert any("damaged" in p for p in fresh.problems)
    assert fresh.timeline.total > 0


def test_missing_spool_dir_is_an_empty_state(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    data = load(repo)
    assert data.spool_files == 0 and data.sessions == {} and data.problems == []


def test_load_never_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = new_repo(tmp_path)
    build_fleet(repo)
    source = make_source(repo)

    def boom(*_a: object, **_k: object) -> object:
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr("cursorfleet.tui.data.collect", boom)
    data = source.load()
    assert any("data load failed" in p for p in data.problems)


def test_git_usage_is_read_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = new_repo(tmp_path)
    build_fleet(repo)
    seen: list[list[str]] = []
    real = subprocess.run

    def spy(args: list[str], *a: object, **kw: object) -> object:
        seen.append(list(args))
        return real(args, *a, **kw)  # type: ignore[call-overload]

    monkeypatch.setattr(subprocess, "run", spy)
    source = DataSource(repo, clock=lambda: NOW, git_every=1)
    source.load()
    source.load(force_git=True)
    verbs = {
        next(a for a in args[1:] if not a.startswith("-") and a not in {"core.fsmonitor=false"})
        for args in seen
        if args and os.path.basename(args[0]).lower() in {"git", "git.exe"}
    }
    assert verbs and verbs <= {"rev-parse", "worktree", "status", "rev-list", "log"}
    assert not any("fetch" in a or "pull" in a or "push" in a for args in seen for a in args)


def test_filter_parsing() -> None:
    parsed = parse_timeline_filter(
        "agent:review kind:tool risk:high file:src/x source:self_reported since:15m shell git", NOW
    )
    flt = parsed.event
    assert (flt.agent, flt.kind, flt.risk, flt.file, flt.source) == (
        "review",
        "tool",
        "high",
        "src/x",
        "self_reported",
    )
    assert flt.text == "shell git" and flt.since is not None and not parsed.errors
    assert parse_timeline_filter("since:nonsense", NOW).errors
    assert parse_time("2h", NOW) < NOW
    assert parse_time("2026-10-04T10:00:00", NOW).hour == 10  # type: ignore[union-attr]
    assert matches_text("Running PYTEST now", "pytest running")
    assert not matches_text("abc", "xyz")
    assert parse_timeline_filter("", NOW).event == EventFilter()


def test_timeline_filtering_through_the_source(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    build_fleet(repo)
    source = make_source(repo)
    risky = source.load(parse_timeline_filter("risk:medium", NOW).event)
    assert [e.risk.value for e in risky.timeline.events] == ["medium"]
    by_file = source.load(parse_timeline_filter("file:tests/test_app", NOW).event)
    assert [e.kind.value for e in by_file.timeline.events] == ["file.changed"]
    old = source.load(parse_timeline_filter("until:2026-10-04T10:00:00Z", NOW).event)
    assert {e.session_id for e in old.timeline.events} == {"s-old"}


def test_self_reported_events_appear_in_timeline_with_source(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    build_fleet(repo)
    write_artifact(repo, "t1", "01-plan-architect.md", "plan.created", "architect")
    data = load(repo)
    selfs = [e for e in data.timeline.events if e.source.value == "self_reported"]
    assert len(selfs) == 1
    rows = views.timeline_rows(data, views.UiState())
    label = next(r.label.plain for r in rows if r.key.endswith(selfs[0].event_id))
    assert "SELF" in label and "plan.created" in label
    detail = views.detail_for(
        "timeline", data, views.UiState(), f"ev:{selfs[0].session_id}:{selfs[0].event_id}"
    )
    assert "SELF-REPORTED" in detail.plain
    observed = make_source(repo).load(parse_timeline_filter("source:observed", NOW).event)
    assert observed.timeline.events and {e.source.value for e in observed.timeline.events} == {
        "observed"
    }
    obs = make_source(repo).load(parse_timeline_filter("source:self_reported", NOW).event)
    assert [e.source.value for e in obs.timeline.events] == ["self_reported"]


def test_worktree_view_fields(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    build_fleet(repo)
    data = load(repo)
    ui = views.UiState()
    rows = views.worktree_rows(data, ui)
    line = next(r.label.plain for r in rows if not r.header)
    assert "[main]" in line and "HEAD" in line and "dirty" in line and "no upstream" in line
    detail = views.detail_for(
        "worktrees", data, ui, next(r.key for r in rows if not r.header)
    ).plain
    assert "Ahead/behind" in detail and "Owner" in detail and "Dirty" in detail


def test_theme_and_safe_helpers() -> None:
    assert safe("a\x1b[31mb\nc") == "a?[31mb?c"
    assert safe("x" * 300, 20).endswith("...") and len(safe("x" * 300, 20)) == 20
    assert Theme(mono=True).lane("blocked") and "red" not in Theme(mono=True).lane("blocked")
    assert "red" in Theme(mono=False).lane("blocked")
