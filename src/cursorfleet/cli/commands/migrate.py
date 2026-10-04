"""``cursorfleet migrate`` — offline migrations (artifacts, etc.)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from cursorfleet.state.artifact_scan import DEFAULT_WORK_DIR, ArtifactScanner
from cursorfleet.workflow.artifacts import ARTIFACT_SCHEMA, ARTIFACT_SCHEMA_LEGACY

migrate_app = typer.Typer(name="migrate", help="Inspect or migrate local CursorFleet data.")


def register(app: typer.Typer) -> None:
    app.add_typer(migrate_app)

    @migrate_app.command("artifacts")
    def artifacts(
        path: Annotated[Path, typer.Option("--path", help="Repository root.")] = Path(),
        dry_run: Annotated[
            bool, typer.Option("--dry-run", help="Report only; write nothing.")
        ] = True,
        yes: Annotated[
            bool, typer.Option("--yes", help="Apply migrations (not implemented).")
        ] = False,
    ) -> None:
        """List legacy YAML artifacts vs TOML 0.1 (dry-run by default)."""
        root = path.resolve()
        work = root / DEFAULT_WORK_DIR
        if not work.is_dir():
            typer.echo("no work directory")
            return
        scan = ArtifactScanner(str(work))
        result = scan.scan([str(root)])
        typer.echo(f"valid artifacts: {len(result.records)} issues: {len(result.issues)}")
        typer.echo(f"target schema: {ARTIFACT_SCHEMA}")
        typer.echo(f"legacy accepted: {ARTIFACT_SCHEMA_LEGACY}")
        if dry_run or not yes:
            typer.echo("dry-run: no files changed (TOML rewrite is manual or future --yes)")
            return
        typer.echo("nothing to apply yet")
