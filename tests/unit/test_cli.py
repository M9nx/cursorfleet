from typer.testing import CliRunner

import cursorfleet
from cursorfleet.cli.main import app

runner = CliRunner()


def test_version_constant() -> None:
    assert cursorfleet.__version__


def test_cli_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert cursorfleet.__version__ in result.output


def test_cli_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Cursor agent teams" in result.output
