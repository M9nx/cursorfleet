"""``cursorfleet uninstall``: remove exactly what the install lockfile recorded."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from cursorfleet.adapters.cursor import installer
from cursorfleet.adapters.cursor.fsutil import UnsafePathError, safe_text
from cursorfleet.cli.commands._common import fail, show_plan, workspace_root


def register(app: typer.Typer) -> None:
    @app.command("uninstall")
    def uninstall(
        dry_run: Annotated[
            bool, typer.Option("--dry-run", help="Print the diff and write nothing.")
        ] = False,
        yes: Annotated[
            bool, typer.Option("--yes", "-y", help="Skip the prompt (the diff is still printed).")
        ] = False,
        force: Annotated[
            bool,
            typer.Option("--force", help="Also remove installed items that were modified since."),
        ] = False,
        path: Annotated[
            Path, typer.Option("--path", help="Repository root (default: current directory).")
        ] = Path(),
    ) -> None:
        """Remove the files, AGENTS.md blocks and hook entries CursorFleet installed.

        Only items listed in .cursorfleet/install.lock.json are touched, and only if
        they still match their recorded hash. Modified items are reported and skipped
        (unless --force). Your own hooks and AGENTS.md content are left as they were.
        """
        root = workspace_root(path, command="uninstall")
        plan = installer.build_uninstall_plan(root, force=force)
        if plan.conflicts:
            typer.echo("Cannot uninstall (nothing was written):", err=True)
            for conflict in plan.conflicts:
                typer.echo(f"  - {safe_text(conflict)}", err=True)
            raise typer.Exit(1)
        if plan.noop and not plan.drift:
            for note in plan.notes:
                typer.echo(safe_text(note))
            if not plan.notes:
                typer.echo("Nothing to remove.")
            return
        if not plan.noop:
            show_plan(plan)
        for item in plan.drift:
            typer.echo(f"drift: {safe_text(item)}", err=True)
        if dry_run:
            typer.echo("\nDry run: no files were written.")
            raise typer.Exit(1 if plan.drift else 0)
        if not plan.noop:
            if not yes and not typer.confirm("\nApply these changes?", default=False):
                typer.echo("Aborted; nothing was written.")
                raise typer.Exit(1)
            try:
                installer.apply_plan(plan)
            except (OSError, UnsafePathError) as exc:
                raise fail(f"error while writing: {exc}") from exc
        if plan.drift:
            typer.echo(
                "\nUninstalled everything that still matched. Drifted items remain and stay "
                "listed in the lockfile; fix them or re-run with --force.",
                err=True,
            )
            raise typer.Exit(1)
        typer.echo("\nUninstalled.")
