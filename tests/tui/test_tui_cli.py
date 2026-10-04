"""CLI wiring, layout thresholds and help content (no Textual app needed)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from cursorfleet.cli.main import app as cli_app
from cursorfleet.tui.app import CursorFleetApp, build_app
from cursorfleet.tui.help import HONESTY, KEYS, help_text
from cursorfleet.tui.layout import layout_for
from cursorfleet.tui.watch import watchfiles_available

runner = CliRunner()
DOCUMENTED_KEYS = ["/", "j", "k", "Enter", "p", "t", "g", "w", "v", "e", "r", "?", "q", "o", "l"]


def test_tui_command_is_registered() -> None:
    result = runner.invoke(cli_app, ["--help"])
    assert result.exit_code == 0 and "tui" in result.output
    sub = runner.invoke(cli_app, ["tui", "--help"])
    assert sub.exit_code == 0
    for option in ("--path", "--refresh", "--no-git"):
        assert option in sub.output


def test_tui_refuses_non_interactive_terminals() -> None:
    result = runner.invoke(cli_app, ["tui"])  # CliRunner stdin/stdout are not TTYs
    assert result.exit_code == 2
    assert "interactive terminal" in result.output and "status" in result.output


@pytest.mark.parametrize("value", ["0.1", "0", "-1", "61", "abc"])
def test_tui_rejects_bad_refresh(value: str) -> None:
    result = runner.invoke(cli_app, ["tui", "--refresh", value])
    assert result.exit_code == 2


def test_build_app_options(tmp_path: Path) -> None:
    built = build_app(tmp_path, refresh_s=0.01, with_git=False, watch=False)
    assert isinstance(built, CursorFleetApp)
    assert built.refresh_s == 0.25  # clamped: never a busy loop
    assert built.source._with_git is False
    slow = build_app(tmp_path, refresh_s=30.0)
    assert slow.source._git_every == 1


@pytest.mark.parametrize(
    ("width", "tile", "mode"),
    [
        (1, False, "single"),
        (80, False, "single"),
        (99, True, "single"),
        (100, False, "split"),
        (159, True, "split"),
        (160, False, "split"),
        (160, True, "tiled"),
        (400, True, "tiled"),
    ],
)
def test_layout_thresholds(width: int, tile: bool, mode: str) -> None:
    assert layout_for(width, tile) == mode


def test_every_key_is_documented_in_help() -> None:
    text = help_text().plain
    listed = {key.split()[0].split("/")[0] for key, _ in KEYS}
    joined = " ".join(key for key, _ in KEYS)
    for key in DOCUMENTED_KEYS:
        assert key in joined or key in listed, key
    assert "placeholder until v0.2" in text
    assert "cursorfleet init --cursor" in text and "cursorfleet doctor" in text
    assert HONESTY and all(line in text for line in HONESTY)


def test_watchfiles_probe_never_raises() -> None:
    assert isinstance(watchfiles_available(), bool)
