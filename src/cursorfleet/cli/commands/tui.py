"""``cursorfleet tui``: the Textual dashboard (read-only; no network)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

DEFAULT_REFRESH_S = 2.0


def register(app: typer.Typer) -> None:
    @app.command("tui")
    def tui(
        path: Annotated[
            Path, typer.Option("--path", help="A directory inside the git repo (default: cwd).")
        ] = Path(),
        refresh: Annotated[
            float,
            typer.Option(
                "--refresh", min=0.25, max=60.0, help="Seconds between re-reads of the spool."
            ),
        ] = DEFAULT_REFRESH_S,
        no_git: Annotated[
            bool, typer.Option("--no-git", help="Do not run the read-only git collector.")
        ] = False,
        no_watch: Annotated[
            bool, typer.Option("--no-watch", help="Poll only; ignore watchfiles if installed.")
        ] = False,
    ) -> None:
        """Open the dashboard: workflow lanes, agents, timeline, worktrees and gates.

        Observe-only: it reads the SQLite projection and read-only git state, never fetches,
        never enforces anything and never shows prompts, thinking or file contents.
        """
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            typer.echo(
                "error: `cursorfleet tui` needs an interactive terminal. "
                "Use `cursorfleet status` (or `status --json`) in scripts.",
                err=True,
            )
            raise typer.Exit(2)
        from cursorfleet.tui.app import build_app  # noqa: PLC0415 - lazy: keeps --help fast

        build_app(path.resolve(), refresh_s=refresh, with_git=not no_git, watch=not no_watch).run()
