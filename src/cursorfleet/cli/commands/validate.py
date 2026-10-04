"""``cursorfleet validate``: config, roster, generated kit, rules and artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from cursorfleet.adapters.cursor.fsutil import safe_text
from cursorfleet.adapters.cursor.validation import Finding, validate_workspace
from cursorfleet.cli.commands._resolution import (
    build_resolution,
    render_resolution_text,
    resolution_as_dict,
)


def register(app: typer.Typer) -> None:
    @app.command("validate")
    def validate(
        json_output: Annotated[
            bool, typer.Option("--json", help="Machine-readable output.")
        ] = False,
        path: Annotated[
            Path, typer.Option("--path", help="Directory inside the git repo (default: current).")
        ] = Path(),
    ) -> None:
        """Validate .cursorfleet config and roster, the generated kit and work artifacts.

        Exit code 1 if any error is found; warnings do not fail the command.
        """
        resolution = build_resolution(path)
        root = Path(resolution.top_level) if resolution.top_level else path.expanduser().resolve()
        findings, stats = validate_workspace(root)
        if resolution.status == "fail":
            findings.insert(
                0,
                Finding(
                    "error",
                    "repo.resolution",
                    resolution.reason,
                    hint="doctor and validate never walk past an inner Git boundary "
                    "and never write.",
                ),
            )
        errors = sum(1 for f in findings if f.severity == "error")
        warnings = len(findings) - errors
        if json_output:
            payload = {
                "schema": "cursorfleet.validate/1",
                "ok": errors == 0,
                "counts": {"error": errors, "warning": warnings},
                "stats": stats,
                "resolution": resolution_as_dict(resolution),
                "findings": [f.as_dict() for f in findings],
            }
            typer.echo(json.dumps(payload, indent=2))
        else:
            typer.echo(render_resolution_text(resolution))
            for f in findings:
                where = f" {safe_text(f.path)}" if f.path else ""
                typer.echo(f"[{f.severity}] {f.code}{where}: {safe_text(f.message)}")
                if f.hint:
                    typer.echo(f"        fix: {safe_text(f.hint)}")
            typer.echo(f"{errors} error(s), {warnings} warning(s)")
        if errors:
            raise typer.Exit(1)
