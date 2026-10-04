"""``cursorfleet init --cursor``: install the Cursor kit with a diff and confirmation."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from cursorfleet.adapters.cursor import installer
from cursorfleet.adapters.cursor.fsutil import UnsafePathError, safe_text
from cursorfleet.adapters.cursor.hooksjson import HOOK_COMMAND
from cursorfleet.cli.commands._common import fail, show_plan, workspace_root


def register(app: typer.Typer) -> None:
    @app.command("init")
    def init(
        cursor: Annotated[
            bool, typer.Option("--cursor", help="Install the kit for Cursor (the only target).")
        ] = False,
        dry_run: Annotated[
            bool, typer.Option("--dry-run", help="Print the diff and write nothing.")
        ] = False,
        yes: Annotated[
            bool,
            typer.Option("--yes", "-y", help="Skip the prompt (the diff is still printed)."),
        ] = False,
        path: Annotated[
            Path,
            typer.Option("--path", help="Repository root (default: current directory)."),
        ] = Path(),
    ) -> None:
        """Generate subagents, skills, rules, AGENTS.md blocks and observe-only hooks.

        Prints an exact diff of every file (including .cursor/hooks.json), then asks for
        confirmation. Existing hooks and AGENTS.md content are preserved. Undo with
        `cursorfleet uninstall`.
        """
        if not cursor:
            raise fail("error: choose a target, e.g. `cursorfleet init --cursor`.", 2)
        root = workspace_root(path, command="init")
        plan = installer.build_install_plan(root)
        if plan.conflicts:
            typer.echo(
                "Cannot install; resolve these conflicts first (nothing was written):", err=True
            )
            for conflict in plan.conflicts:
                typer.echo(f"  - {safe_text(conflict)}", err=True)
            raise typer.Exit(1)
        if plan.noop:
            typer.echo("Already up to date: nothing to do.")
            return
        show_plan(plan)
        if plan.touches_hooks:
            typer.echo(
                f"\nWARNING: this edits .cursor/hooks.json. Cursor runs `{HOOK_COMMAND}` on the "
                "registered events (observe-only: it records sanitized metadata and always "
                "exits 0). Review the hooks.json diff above."
            )
        if dry_run:
            typer.echo("\nDry run: no files were written.")
            return
        if not yes and not typer.confirm("\nApply these changes?", default=False):
            typer.echo("Aborted; nothing was written.")
            raise typer.Exit(1)
        try:
            installer.apply_plan(plan)
        except (OSError, UnsafePathError) as exc:
            raise fail(f"error while writing: {exc}\nRun `cursorfleet doctor` to inspect.") from exc
        typer.echo("\nInstalled. Next: `cursorfleet doctor`. Undo with `cursorfleet uninstall`.")
