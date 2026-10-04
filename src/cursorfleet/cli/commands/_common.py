"""Helpers shared by the kit commands (init, uninstall, doctor, validate)."""

from __future__ import annotations

from pathlib import Path

import typer

from cursorfleet.adapters.cursor.fsutil import safe_text
from cursorfleet.adapters.cursor.installer import Plan, render_diff, summarize
from cursorfleet.adapters.cursor.workspace import WorkspaceError, resolve_workspace


def fail(message: str, code: int = 1) -> typer.Exit:
    typer.echo(safe_text(message), err=True)
    return typer.Exit(code)


def workspace_root(path: Path) -> Path:
    """Return the git top level for ``path`` or exit with a clear message."""
    try:
        return resolve_workspace(path).root
    except WorkspaceError as exc:
        raise fail(
            f"error: {exc}\nCursorFleet v0.1 needs a git repository (see ADR 0002). "
            "Run inside one or pass --path."
        ) from exc


def show_plan(plan: Plan) -> None:
    typer.echo(f"Workspace: {safe_text(str(plan.root))}")
    typer.echo("Planned changes:")
    for line in summarize(plan):
        typer.echo(f"  {line}")
    for note in plan.notes:
        typer.echo(f"  note: {safe_text(note)}")
    typer.echo("")
    typer.echo(render_diff(plan), nl=False)
