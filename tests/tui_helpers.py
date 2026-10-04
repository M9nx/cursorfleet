"""Deterministic fixtures for the TUI tests: a real git repo, spool events, a fixed clock."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cursorfleet.events.ids import worktree_id_for
from cursorfleet.state.runtime import RuntimePaths
from cursorfleet.state.spool import append_event
from cursorfleet.tui.app import CursorFleetApp
from cursorfleet.tui.data import DataSource
from m2_helpers import dump, git, init_repo, make_event, paths_of, plant_install_marker

NOW = datetime(2026, 10, 4, 12, 5, 0, tzinfo=UTC)
SECRET = "SYNTH-SECRET-9f8e7d6c5b4a"  # noqa: S105 - synthetic canary, appears nowhere legitimate


def fixed_clock() -> datetime:
    return NOW


@dataclass
class Fleet:
    root: Path
    paths: RuntimePaths
    wt_id: str
    head: str
    n: int = 0

    def add(self, session: str, kind: str, ts: str, **extra: Any) -> None:
        self.n += 1
        event = make_event(session, self.n, kind=kind, ts=ts, **extra)
        assert append_event(
            self.paths, session, "w1", dump(event), now_ms=1_790_000_000_000 + self.n
        )


def build_fleet(repo: Path) -> Fleet:
    """Two sessions: an active one with two subagents and an older, silent one."""
    root = repo.resolve()
    head = git(["rev-parse", "HEAD"], root).strip()
    fleet = Fleet(root, paths_of(root), worktree_id_for(os.path.realpath(root)), head)
    common = {"worktree_id": fleet.wt_id, "branch": "main", "commit": head}
    fleet.add("s-active", "session.started", "2026-10-04T12:00:00.000Z", **common)
    fleet.add(
        "s-active",
        "subagent.started",
        "2026-10-04T12:00:05.000Z",
        agent_role="implementer",
        agent_instance_id="i1",
        attribution="exact",
        **common,
    )
    fleet.add(
        "s-active",
        "tool.started",
        "2026-10-04T12:01:00.000Z",
        tool_name="Shell",
        agent_role="implementer",
        agent_instance_id="i1",
        attribution="exact",
        risk="medium",
        command={"argv0": "git", "subcommand": "status", "display": "git status --short"},
        **common,
    )
    fleet.add(
        "s-active",
        "file.changed",
        "2026-10-04T12:02:00.000Z",
        agent_role="implementer",
        agent_instance_id="i1",
        attribution="exact",
        paths=[{"path": "src/app.py", "op": "modified"}, {"path": "tests/test_app.py"}],
        **common,
    )
    fleet.add(
        "s-active",
        "test.completed",
        "2026-10-04T12:03:00.000Z",
        source="derived",
        outcome="ok",
        tool_name="Shell",
        agent_role="implementer",
        agent_instance_id="i1",
        attribution="exact",
        command={
            "argv0": "uv",
            "display": "uv run pytest -q",
            "exit_code": 0,
        },
        **common,
    )
    fleet.add(
        "s-active",
        "context.compacted",
        "2026-10-04T12:03:30.000Z",
        agent_role="implementer",
        agent_instance_id="i1",
        attribution="exact",
        metrics={"context_usage_percent": 81.5},
        **common,
    )
    fleet.add(
        "s-active",
        "subagent.started",
        "2026-10-04T12:04:00.000Z",
        agent_role="reviewer",
        agent_instance_id="r1",
        attribution="exact",
        **common,
    )
    fleet.add("s-old", "session.started", "2026-10-04T09:00:00.000Z", **common)
    fleet.add(
        "s-old",
        "tool.started",
        "2026-10-04T09:01:00.000Z",
        tool_name="Read",
        agent_role="scout",
        agent_instance_id="sc1",
        attribution="exact",
        **common,
    )
    return fleet


def write_artifact(root: Path, task: str, name: str, kind: str, role: str, **fields: str) -> Path:
    extra = "".join(f"{k}: {v}\n" for k, v in fields.items())
    path = root / ".cursorfleet" / "work" / task / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        "schema: cursorfleet.artifact/1\n"
        f"kind: {kind}\n"
        f"task: {task}\n"
        f"author_role: {role}\n"
        "created: 2026-10-04T12:04:30Z\n"
        f"{extra}"
        "---\n"
        "Body text that must never be shown.\n",
        encoding="utf-8",
    )
    return path


def make_source(repo: Path, *, with_git: bool = True) -> DataSource:
    return DataSource(repo, with_git=with_git, clock=fixed_clock)


def make_app(
    repo: Path,
    *,
    with_git: bool = True,
    initial_view: str | None = "overview",
    **kwargs: Any,
) -> CursorFleetApp:
    return CursorFleetApp(
        make_source(repo, with_git=with_git),
        refresh_s=3600,
        watch=False,
        initial_view=initial_view,
        **kwargs,
    )


def new_repo(tmp_path: Path, name: str = "repo") -> Path:
    root = init_repo(tmp_path / name)
    plant_install_marker(root)
    return root


async def settle(app: CursorFleetApp, pilot: Any, rounds: int = 200) -> None:
    """Wait (without sleeping) until queued messages are handled and no load is running."""
    for _ in range(rounds):
        await pilot.pause()
        if not app.loading:
            await pilot.pause()
            return
    msg = "app did not settle"
    raise AssertionError(msg)


def screen_text(app: CursorFleetApp) -> str:
    """What is actually painted: the compositor's rows as plain text."""
    strips = app.screen._compositor.render_strips()
    return "\n".join(strip.text.rstrip() for strip in strips)
