"""Textual Pilot tests: keys, filters, layouts, every screen, resilience. No sleeps."""

from __future__ import annotations

import asyncio
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from rich.style import Style
from textual.widgets import Input

from cursorfleet.tui.app import CursorFleetApp
from cursorfleet.tui.help import KEYS, HelpScreen
from cursorfleet.tui.theme import LANE_TAG
from cursorfleet.tui.views import VIEW_TITLE
from m2_helpers import git, paths_of
from tui_helpers import (
    Fleet,
    build_fleet,
    make_app,
    make_source,
    new_repo,
    screen_text,
    settle,
    write_artifact,
)

VIEW_KEYS = {
    "o": "overview",
    "l": "timeline",
    "w": "worktrees",
    "g": "gates",
    "e": "evidence",
    "v": "violations",
}


async def goto(app: CursorFleetApp, pilot: object, key: str) -> None:
    """Move the highlight to the row with ``key`` using only j/k."""
    keys = app.row_keys()
    target, current = keys.index(key), keys.index(app.selected_key or keys[0])
    for _ in range(abs(target - current)):
        await pilot.press("j" if target > current else "k")  # type: ignore[attr-defined]
    await settle(app, pilot)
    assert app.selected_key == key


@pytest.fixture
def fleet_repo(tmp_path: Path) -> Path:
    repo = new_repo(tmp_path)
    build_fleet(repo)
    return repo


# ------------------------------------------------------------------------ navigation


async def test_navigation_keys_move_the_selection(fleet_repo: Path) -> None:
    app = make_app(fleet_repo)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)
        keys = app.row_keys()
        assert app.selected_key == keys[0]
        await pilot.press("j")
        await settle(app, pilot)
        assert app.selected_key == keys[1]
        await pilot.press("k")
        await settle(app, pilot)
        assert app.selected_key == keys[0]
        await pilot.press("down")
        await settle(app, pilot)
        assert app.selected_key == keys[1]
        await pilot.press("up")
        await settle(app, pilot)
        assert app.selected_key == keys[0]
        assert "AGENT" in app.rendered_text()


async def test_enter_opens_detail_split_layout(fleet_repo: Path) -> None:
    app = make_app(fleet_repo)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)
        await pilot.press("j", "enter")
        await settle(app, pilot)
        assert app.focused is not None and app.focused.id == "detail"
        assert "AGENT reviewer" in app.rendered_text()
        await pilot.press("escape")
        await settle(app, pilot)
        assert app.focused is not None and app.focused.id == "list"


async def test_single_pane_enter_and_escape(fleet_repo: Path) -> None:
    app = make_app(fleet_repo)
    async with app.run_test(size=(80, 24)) as pilot:
        await settle(app, pilot)
        assert app.layout_mode == "single"
        assert app.query_one("#list").display and not app.query_one("#detail").display
        await pilot.press("enter")
        await settle(app, pilot)
        assert not app.query_one("#list").display and app.query_one("#detail").display
        await pilot.press("escape")
        await settle(app, pilot)
        assert app.query_one("#list").display and not app.query_one("#detail").display


# ------------------------------------------------------------------------ filter / pin


async def test_text_filter_narrows_and_escape_clears(fleet_repo: Path) -> None:
    app = make_app(fleet_repo)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)
        everything = app.row_keys()
        assert len(everything) > 3
        await pilot.press("slash")
        assert app.query_one("#filter", Input).has_class("open")
        assert app.focused is app.query_one("#filter")
        await pilot.press(*"scout")
        await settle(app, pilot)
        assert [k.split(":")[-1] for k in app.row_keys()] == ["scout#sc1"]
        await pilot.press("enter")  # apply and return to the list
        await settle(app, pilot)
        assert app.focused is not None and app.focused.id == "list"
        assert "filter: scout" in screen_text(app)
        await pilot.press("slash", "escape")
        await settle(app, pilot)
        assert app.row_keys() == everything


async def test_timeline_filter_is_structured_and_queries_the_store(fleet_repo: Path) -> None:
    app = make_app(fleet_repo)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("l")
        await settle(app, pilot)
        total = app.data.timeline.total
        assert total == 9
        await pilot.press("slash")
        app.query_one("#filter", Input).value = "kind:tool risk:medium"
        await settle(app, pilot)
        assert [e.kind.value for e in app.data.timeline.events] == ["tool.started"]
        assert "tool.started" in app.rendered_text() and "RISK:medium" in app.rendered_text()
        app.query_one("#filter", Input).value = "since:nonsense"
        await settle(app, pilot)
        assert "filter problem" in app.rendered_text()
        await pilot.press("escape")
        await settle(app, pilot)
        assert app.data.timeline.total == total


async def test_timeline_shows_source_and_attribution(fleet_repo: Path) -> None:
    write_artifact(fleet_repo, "t1", "01-plan-architect.md", "plan.created", "architect")
    app = make_app(fleet_repo)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.press("l")
        await settle(app, pilot)
        text = app.rendered_text()
        assert "obs/exact" in text and "obs/unk" in text and "SELF/unk" in text
        assert "drv/exact" in text  # derived test.completed


async def test_pin_moves_agent_to_top_of_lane_and_toggles(fleet_repo: Path) -> None:
    app = make_app(fleet_repo)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)
        keys = app.row_keys()
        main_old = next(k for k in keys if k.endswith("s-old:main"))
        scout = next(k for k in keys if k.endswith("scout#sc1"))
        assert keys.index(scout) < keys.index(main_old)  # newer first by default
        await goto(app, pilot, main_old)
        await pilot.press("p")
        await settle(app, pilot)
        assert app.ui.pinned == {main_old}
        keys = app.row_keys()
        assert keys.index(main_old) < keys.index(scout)
        assert "* [~] main" in app.rendered_text()
        await pilot.press("p")
        await settle(app, pilot)
        assert app.ui.pinned == set()


async def test_pin_outside_overview_explains(fleet_repo: Path) -> None:
    app = make_app(fleet_repo)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("w")
        await settle(app, pilot)
        await pilot.press("p")
        assert "pin works on agents" in app.flash_message and app.ui.pinned == set()


async def test_refresh_key_picks_up_new_events(fleet_repo: Path) -> None:
    app = make_app(fleet_repo)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)
        assert "latecomer" not in app.rendered_text()
        helper = Fleet(fleet_repo, paths_of(fleet_repo), "wt-x", "0" * 40, n=500)
        helper.add(
            "s-active",
            "subagent.started",
            "2026-10-04T12:04:30.000Z",
            agent_role="latecomer",
            agent_instance_id="l1",
            attribution="exact",
        )
        count = app.refresh_count
        await pilot.press("r")
        await settle(app, pilot)
        assert app.refresh_count > count
        assert "latecomer" in app.rendered_text()


# ------------------------------------------------------------------------ screens


@pytest.mark.parametrize(("key", "view"), list(VIEW_KEYS.items()))
async def test_every_screen_renders_with_fixture_data(
    fleet_repo: Path, key: str, view: str
) -> None:
    write_artifact(fleet_repo, "t1", "01-handoff-architect.md", "handoff.created", "architect")
    app = make_app(fleet_repo)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)
        await pilot.press(key)
        await settle(app, pilot)
        assert app.view == view
        assert VIEW_TITLE[view] in screen_text(app)
        text = app.rendered_text()
        expected = {
            "overview": "UNKNOWN / NO TELEMETRY",
            "timeline": "matching event(s)",
            "worktrees": "[main]",
            "gates": "display-only: v0.1 does not enforce gates",
            "evidence": "DECLARED BY AGENTS",
            "violations": "policy engine arrives in v0.2",
        }[view]
        assert expected in text


@pytest.mark.parametrize(("key", "view"), list(VIEW_KEYS.items()))
async def test_every_screen_renders_empty(tmp_path: Path, key: str, view: str) -> None:
    app = make_app(new_repo(tmp_path))
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(app, pilot)
        await pilot.press(key)
        await settle(app, pilot)
        assert app.view == view
        text = app.rendered_text()
        if view in ("overview", "timeline"):
            assert "cursorfleet init --cursor" in text and "cursorfleet doctor" in text
        if view == "overview":
            assert "UNKNOWN / NO TELEMETRY (1)" in text  # the git-only worktree
        if view == "gates":
            assert text.count("UNKNOWN") >= 10
        if view == "evidence":
            assert "none yet" in text


async def test_not_a_git_repo_shows_guidance(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    app = make_app(plain)
    async with app.run_test(size=(80, 24)) as pilot:
        await settle(app, pilot)
        text = app.rendered_text()
        assert "Not inside a git repository" in text
        assert "cursorfleet init --cursor" in text and "cursorfleet doctor" in text
        for key in VIEW_KEYS:
            await pilot.press(key)
            await settle(app, pilot)  # no screen may raise on an empty, repo-less state


async def test_unknown_telemetry_is_never_rendered_as_idle(tmp_path: Path) -> None:
    app = make_app(new_repo(tmp_path))
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)
        text = (app.rendered_text() + screen_text(app)).lower()
        assert "no telemetry" in text and "unknown" in text
        assert "idle" not in text.replace("not idle", "").replace("never idle", "")
        await pilot.press("j", "enter")
        await settle(app, pilot)
        assert "no hook telemetry" in app.rendered_text().lower()


async def test_agent_detail_has_required_fields(fleet_repo: Path) -> None:
    write_artifact(
        fleet_repo,
        "add-login",
        "01-handoff-implementer.md",
        "handoff.created",
        "implementer",
        to_role="reviewer",
        issue_ref="'#12'",
    )
    write_artifact(
        fleet_repo, "add-login", "02-context-implementer.md", "context.loaded", "implementer"
    )
    app = make_app(fleet_repo)
    async with app.run_test(size=(140, 60)) as pilot:
        await settle(app, pilot)
        key = next(k for k in app.row_keys() if k.endswith("implementer#i1"))
        await goto(app, pilot, key)
        text = app.rendered_text()
    for needle in (
        "Role         implementer",
        "Task         add-login",
        "#12 (SELF-REPORTED)",
        "Branch       main",
        "Files        2 changed",
        "Last tools   Shell",
        "last run ok",
        "Elapsed",
        "Tool calls   1",
        "Compactions  1",
        "destination: reviewer",
        "Token/cost   unknown (not exposed by Cursor hooks)",
        "Unit tests: PASS",
        "DECLARED BY THE AGENT",
    ):
        assert needle in text, needle


async def test_gates_screen_marks_stale_and_never_scores(fleet_repo: Path) -> None:
    app = make_app(fleet_repo)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("g")
        await settle(app, pilot)
        text = app.rendered_text()
        assert "[PASS   ] Unit tests" in text
        assert "Independent review" in text and "CI status" in text and "Merge readiness" in text
        lowered = text.lower()
        assert "no overall score" in lowered
        for banned in ("ready to merge", "/10", "% pass", "gates passed"):
            assert banned not in lowered
        (fleet_repo / "more.txt").write_text("x", encoding="utf-8")
        git(["add", "more.txt"], fleet_repo)
        git(["commit", "-q", "-m", "advance"], fleet_repo)
        await pilot.press("r")
        await settle(app, pilot)
        text = app.rendered_text()
        assert "[STALE  ] Unit tests" in text and "STALE: was pass" in text


async def test_worktrees_screen_and_refresh_is_read_only(
    fleet_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    real = subprocess.run

    def spy(args: list[str], *a: object, **kw: object) -> object:
        calls.append(list(args))
        return real(args, *a, **kw)  # type: ignore[call-overload]

    monkeypatch.setattr(subprocess, "run", spy)
    app = make_app(fleet_repo)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.press("w")
        await settle(app, pilot)
        text = app.rendered_text()
        assert "[main]" in text and "dirty" in text and "no upstream" in text
        assert "owner: " in text
        before = len(calls)
        await pilot.press("r")
        await settle(app, pilot)
        assert len(calls) > before  # re-read happened
    git_words = {a for args in calls for a in args}
    assert not git_words & {"fetch", "pull", "push", "clone", "commit", "checkout", "reset"}


async def test_violations_placeholder(fleet_repo: Path) -> None:
    app = make_app(fleet_repo)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("v")
        await settle(app, pilot)
        assert "policy engine arrives in v0.2" in app.rendered_text()
        assert "policy engine arrives in v0.2" in screen_text(app)


async def test_help_screen_open_close_and_q_does_not_quit(fleet_repo: Path) -> None:
    app = make_app(fleet_repo)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)
        await pilot.press("question_mark")
        await settle(app, pilot)
        assert isinstance(app.screen, HelpScreen)
        painted = screen_text(app)
        assert "CursorFleet help" in painted and "does not enforce" in painted
        for key, _meaning in KEYS[:6]:
            assert key.split()[0] in painted
        await pilot.press("escape")
        await settle(app, pilot)
        assert not isinstance(app.screen, HelpScreen)
        await pilot.press("question_mark", "q")
        await settle(app, pilot)
        assert not isinstance(app.screen, HelpScreen) and not app._exit


async def test_quit_key(fleet_repo: Path) -> None:
    app = make_app(fleet_repo)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)
        await pilot.press("q")
        await settle(app, pilot)
        assert app._exit


# ------------------------------------------------------------------------ layouts


@pytest.mark.parametrize(
    ("size", "mode"), [((80, 24), "single"), ((100, 30), "split"), ((160, 50), "split")]
)
async def test_layout_by_size_and_no_overflow(
    fleet_repo: Path, size: tuple[int, int], mode: str
) -> None:
    app = make_app(fleet_repo)
    async with app.run_test(size=size) as pilot:
        await settle(app, pilot)
        assert app.layout_mode == mode
        lines = screen_text(app).splitlines()
        assert len(lines) <= size[1]
        assert max(len(line) for line in lines) <= size[0]
        assert "CursorFleet" in lines[0] and "help" in lines[-1]
        list_w, detail_w = app.query_one("#list"), app.query_one("#detail")
        if mode == "single":
            assert list_w.display and not detail_w.display
            assert list_w.region.width == size[0]
        else:
            assert detail_w.region.x > list_w.region.x
            assert not app.query_one("#tile_recent").display


async def test_tiling_toggle_is_2x2_never_four_columns(fleet_repo: Path) -> None:
    app = make_app(fleet_repo)
    async with app.run_test(size=(170, 50)) as pilot:
        await settle(app, pilot)
        await pilot.press("t")
        await settle(app, pilot)
        assert app.layout_mode == "tiled"
        panes = [app.query_one(sel) for sel in ("#list", "#detail", "#tile_recent", "#tile_side")]
        assert all(p.display for p in panes)
        xs = sorted({p.region.x for p in panes})
        ys = sorted({p.region.y for p in panes})
        assert len(xs) == 2 and len(ys) == 2  # a 2x2 grid
        assert all(p.region.width >= 70 for p in panes)
        assert "Recent events" in screen_text(app)
        await pilot.press("t")
        await settle(app, pilot)
        assert app.layout_mode == "split" and not app.query_one("#tile_recent").display


async def test_tile_key_below_160_columns_only_explains(fleet_repo: Path) -> None:
    app = make_app(fleet_repo)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)
        await pilot.press("t")
        assert app.layout_mode == "split" and "160+" in app.flash_message


async def test_resize_transitions(fleet_repo: Path) -> None:
    app = make_app(fleet_repo)
    async with app.run_test(size=(170, 50)) as pilot:
        await settle(app, pilot)
        await pilot.press("t")
        assert app.layout_mode == "tiled"
        await pilot.resize_terminal(130, 40)
        await settle(app, pilot)
        assert app.layout_mode == "split"
        await pilot.resize_terminal(90, 30)
        await settle(app, pilot)
        assert app.layout_mode == "single"
        assert app.query_one("#list").display and not app.query_one("#detail").display
        await pilot.resize_terminal(165, 50)
        await settle(app, pilot)
        assert app.layout_mode == "tiled"  # the tile preference survived the round trip
        await pilot.resize_terminal(100, 24)
        await settle(app, pilot)
        assert app.layout_mode == "split"


async def test_readable_at_80x24(fleet_repo: Path) -> None:
    app = make_app(fleet_repo)
    async with app.run_test(size=(80, 24)) as pilot:
        await settle(app, pilot)
        painted = screen_text(app)
        assert "QUEUED (1)" in painted and "WORKING (1)" in painted
        for key in VIEW_KEYS:
            await pilot.press(key)
            await settle(app, pilot)
            lines = screen_text(app).splitlines()
            assert max(len(line) for line in lines) <= 80
        await pilot.press("question_mark")
        await settle(app, pilot)
        assert "KEYS" in screen_text(app)


# ------------------------------------------------------------------------ colour / a11y


def _colour_free(style: str) -> bool:
    parsed = Style.parse(style) if style else Style()
    return parsed.color is None and parsed.bgcolor is None


async def test_no_color_mode_uses_text_labels_and_no_colours(
    fleet_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_artifact(fleet_repo, "t1", "01-blocker-implementer.md", "blocker.raised", "implementer")
    monkeypatch.setenv("NO_COLOR", "1")
    app = make_app(fleet_repo)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)
        assert app.ui.theme.mono and app.no_color
        for key in VIEW_KEYS:
            await pilot.press(key)
            await settle(app, pilot)
            for row in app._rows:
                for span in row.label.spans:
                    assert _colour_free(str(span.style)), (row.key, span.style)
        await pilot.press("o")
        await settle(app, pilot)
        text = app.rendered_text()
        assert "[V] VERIFYING" in text and "BLOCKERS:1" in text and "STALE / OFFLINE" in text


async def test_every_state_has_a_text_label_not_just_colour(fleet_repo: Path) -> None:
    app = make_app(fleet_repo)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)
        text = app.rendered_text()
        for lane, tag in LANE_TAG.items():
            assert tag in text, lane
        await pilot.press("g")
        await settle(app, pilot)
        for state in ("PASS", "UNKNOWN"):
            assert f"[{state}" in app.rendered_text()


async def test_focus_order_filter_list_detail(fleet_repo: Path) -> None:
    app = make_app(fleet_repo)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)
        assert app.focused is not None and app.focused.id == "list"
        await pilot.press("tab")
        assert app.focused is not None and app.focused.id == "detail"
        await pilot.press("tab")
        assert app.focused is not None and app.focused.id == "list"


# ------------------------------------------------------------------------ resilience


async def test_corrupt_spool_and_database_never_crash(fleet_repo: Path) -> None:
    fleet = paths_of(fleet_repo)
    spool_file = next(Path(fleet.spool).rglob("*.jsonl"))
    with spool_file.open("ab") as handle:
        handle.write(b"00000000 {broken\nnot a record at all\n")
    app = make_app(fleet_repo)
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(app, pilot)
        banner = app.query_one("#banner")
        assert banner.has_class("has-problems")
        assert "corrupt or skipped spool line" in app.rendered_text()
        Path(fleet.db).write_bytes(b"garbage" * 500)
        await pilot.press("r")
        await settle(app, pilot)
        assert app.last_refresh_error is None
        assert "WORKING" in app.rendered_text()
        for key in VIEW_KEYS:
            await pilot.press(key)
            await settle(app, pilot)


async def test_source_failure_keeps_old_data_and_ui_alive(fleet_repo: Path) -> None:
    source = make_source(fleet_repo)
    app = CursorFleetApp(source, refresh_s=3600, watch=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)

        def boom(*_a: object, **_k: object) -> object:
            raise RuntimeError("synthetic")

        source.load = boom  # type: ignore[method-assign]
        await pilot.press("r")
        await settle(app, pilot)
        assert app.last_refresh_error == "RuntimeError"
        assert "refresh failed" in app.rendered_text() and "WORKING" in app.rendered_text()


async def test_large_history_is_paginated(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    fleet = build_fleet(repo)
    for n in range(1200):
        minute, second = divmod(n, 60)
        fleet.add("s-big", "tool.completed", f"2026-10-04T11:{minute % 60:02d}:{second:02d}.000Z",
                  tool_name="Read")  # fmt: skip
    app = make_app(repo)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("l")
        await settle(app, pilot)
        assert app.data.timeline.total == 1209
        assert len(app.data.timeline.events) == 200
        assert "Showing 200 of 1209" in app.rendered_text()
        await pilot.press("m")
        await settle(app, pilot)
        assert len(app.data.timeline.events) == 400 and app.ui.timeline_limit == 400
        await pilot.press("o", "m")
        assert "loads more events in the timeline" in app.flash_message


# ------------------------------------------------------------------------ refresh / watch


async def test_poll_interval_drives_refresh_without_busy_loop(fleet_repo: Path) -> None:
    app = CursorFleetApp(make_source(fleet_repo), refresh_s=0.25, watch=False)
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(app, pilot)
        start = app.refresh_count
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 5
        while app.refresh_count == start and loop.time() < deadline:
            await pilot.pause()
        assert app.refresh_count > start


async def test_watcher_triggers_refresh_and_failures_are_contained(fleet_repo: Path) -> None:
    async def one_batch(_path: str) -> AsyncIterator[object]:
        yield {("modified", "x")}

    app = CursorFleetApp(
        make_source(fleet_repo),
        refresh_s=3600,
        watch=True,
        watch_factory=one_batch,
        spool_dir=str(fleet_repo),
    )
    async with app.run_test(size=(100, 30)) as pilot:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 5
        while app.refresh_count < 2 and loop.time() < deadline:
            await pilot.pause()
        assert app.refresh_count >= 2

    async def broken(_path: str) -> AsyncIterator[object]:
        raise OSError("watch failed")
        yield

    failing = CursorFleetApp(
        make_source(fleet_repo),
        refresh_s=3600,
        watch=True,
        watch_factory=broken,
        spool_dir=str(fleet_repo),
    )
    async with failing.run_test(size=(100, 30)) as pilot:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 5
        while "watcher stopped" not in failing.flash_message and loop.time() < deadline:
            await pilot.pause()
        assert "watcher stopped" in failing.flash_message
        await pilot.press("o")
