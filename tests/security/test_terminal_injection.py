"""SR-04: untrusted strings (worktree paths, branches, hooks.json keys) never drive a terminal.

Escape sequences, bidi overrides and Rich/Textual markup in repository-controlled names
must be neutralised by the CLI renderers and shown literally by the TUI.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cursorfleet.cli.main import app as cli_app
from m2_helpers import git
from tui_helpers import build_fleet, make_app, new_repo, screen_text, settle

BIDI = "\u202e"
ESC = "\x1b"
runner = CliRunner()


def add_hostile_worktree(repo: Path, tmp_path: Path, *, escape: bool) -> Path:
    name = "wt[bold red]X" + BIDI + "Y" + (ESC + "]0;pwned\x07" if escape else "")
    target = tmp_path / name
    git(["worktree", "add", "-q", "-b", "feat/" + BIDI + "evil", str(target)], repo)
    return target


def test_status_text_escapes_hostile_worktree_names(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    build_fleet(repo)
    try:
        add_hostile_worktree(repo, tmp_path, escape=os.name == "posix")
    except (OSError, subprocess.CalledProcessError) as exc:  # filesystem rejects the name
        pytest.skip(f"filesystem refused the hostile name: {exc}")
    result = runner.invoke(
        cli_app, ["status", "--repo", str(repo), "--now", "2026-10-04T12:05:00Z"]
    )
    assert result.exit_code == 0
    assert ESC not in result.output and "\x07" not in result.output and BIDI not in result.output
    assert "[bold red]" in result.output  # shown literally, not interpreted

    as_json = runner.invoke(
        cli_app, ["status", "--json", "--repo", str(repo), "--now", "2026-10-04T12:05:00Z"]
    )
    assert as_json.exit_code == 0
    assert ESC not in as_json.output and BIDI not in as_json.output  # JSON escapes them
    json.loads(as_json.output)


async def test_tui_shows_hostile_names_literally(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    build_fleet(repo)
    try:
        add_hostile_worktree(repo, tmp_path, escape=os.name == "posix")
    except (OSError, subprocess.CalledProcessError) as exc:
        pytest.skip(f"filesystem refused the hostile name: {exc}")
    tui = make_app(repo)
    async with tui.run_test(size=(160, 45)) as pilot:
        await settle(tui, pilot)
        for key in ("o", "w", "g"):
            await pilot.press(key)
            await settle(tui, pilot)
            painted = screen_text(tui)
            assert ESC not in painted and BIDI not in painted and "\x07" not in painted
        await pilot.press("w", "j")  # select the hostile worktree to show its detail
        await settle(tui, pilot)
        assert "wt[bold red]X" in screen_text(tui)  # markup is text, not styling


def test_doctor_escapes_hostile_hooks_json_keys_and_commands(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    hostile_event = "evil" + ESC + "]0;pwned\x07" + BIDI
    hostile_command = "run" + ESC + "[2J" + BIDI + "[bold red]x"
    (repo / ".cursor").mkdir()
    (repo / ".cursor" / "hooks.json").write_text(
        json.dumps({"version": 1, "hooks": {hostile_event: [{"command": hostile_command}]}}),
        encoding="utf-8",
    )
    result = runner.invoke(cli_app, ["doctor", "--path", str(repo), "--no-probe-cursor"])
    assert ESC not in result.output and "\x07" not in result.output and BIDI not in result.output
    assert "evil" in result.output
