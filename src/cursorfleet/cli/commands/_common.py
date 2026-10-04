"""Helpers shared by the kit commands (init, uninstall, doctor, validate)."""

from __future__ import annotations

import os
import shlex
from pathlib import Path

import typer

from cursorfleet.adapters.cursor.fsutil import safe_text
from cursorfleet.adapters.cursor.installer import Plan, render_diff, summarize
from cursorfleet.adapters.cursor.workspace import WorkspaceError, resolve_workspace
from cursorfleet.state.runtime import find_git_location


def fail(message: str, code: int = 1) -> typer.Exit:
    typer.echo(safe_text(message), err=True)
    return typer.Exit(code)


def _looks_like_git_dir(path: Path) -> bool:
    return (path / "HEAD").is_file() and (path / "objects").is_dir()


def _suggested_command(command: str, root: Path) -> str:
    extra = " --cursor" if command == "init" else ""
    return f"cd {shlex.quote(str(root))} && cursorfleet {command}{extra}"


def workspace_root(path: Path, *, command: str = "init") -> Path:
    """Return ``path`` only when it is a Git repository root (ADR 0009).

    Exits 2 and writes nothing when the target is not a Git working tree or is
    an ordinary subdirectory. Does not read ``.cursorfleet/`` or build a plan.
    """
    try:
        target = path.expanduser().resolve()
    except OSError as exc:
        raise fail(f"error: cannot resolve {path}.\nNothing was changed.", 2) from exc
    if not target.is_dir():
        raise fail(
            f"error: {safe_text(str(target))} is not a directory.\nNothing was changed.",
            2,
        )
    try:
        workspace = resolve_workspace(target)
    except WorkspaceError as exc:
        loc = find_git_location(str(target))
        if loc is None and not _looks_like_git_dir(target):
            raise fail(
                f"error: Git is required. {safe_text(str(target))} is not inside a "
                "Git working tree.\nNothing was changed. Run `git init` there, or run "
                "this command from a repository root.",
                2,
            ) from exc
        first = str(exc).splitlines()[0][:200]
        raise fail(
            f"error: no usable working tree was found. {safe_text(first)}\nNothing was changed.",
            2,
        ) from exc
    target_key = os.path.normcase(os.path.realpath(str(target)))
    root_key = os.path.normcase(os.path.realpath(str(workspace.root)))
    if target_key != root_key:
        raise fail(
            f"error: {safe_text(str(target))} is not the repository root.\n"
            f"Detected repository root: {safe_text(str(workspace.root))}\n"
            f"Nothing was changed. Run:  {_suggested_command(command, workspace.root)}",
            2,
        )
    return workspace.root


def show_plan(plan: Plan) -> None:
    typer.echo(f"Workspace: {safe_text(str(plan.root))}")
    typer.echo("Planned changes:")
    for line in summarize(plan):
        typer.echo(f"  {line}")
    for note in plan.notes:
        typer.echo(f"  note: {safe_text(note)}")
    typer.echo("")
    typer.echo(render_diff(plan), nl=False)
