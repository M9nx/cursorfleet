"""``cursorfleet doctor``: environment, install and hook diagnostics (read-only)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from cursorfleet.adapters.cursor.diagnostics import DoctorReport, run_doctor
from cursorfleet.adapters.cursor.fsutil import safe_text
from cursorfleet.cli.commands._resolution import render_resolution_text

_LABEL = {"ok": "ok  ", "warn": "WARN", "fail": "FAIL", "info": "info"}


def _render(report: DoctorReport) -> str:
    lines: list[str] = []
    if report.resolution is not None:
        lines.append(render_resolution_text(report.resolution))
        lines.append("")
    for check in report.checks:
        lines.append(f"[{_LABEL[check.status]}] {check.id}: {safe_text(check.message)}")
        if check.remediation and check.status in {"warn", "fail"}:
            lines.append(f"       fix: {safe_text(check.remediation)}")
        if check.id == "install.drift":
            for item in check.details.get("drift", []):
                lines.append(f"       - {safe_text(item['path'])}: {safe_text(item['detail'])}")
    lines.append("")
    lines.append("Effective hooks (Cursor merge order: enterprise, team, project, user):")
    for source in report.hooks:
        if source.path is None:
            lines.append(f"  {source.level:<10} {safe_text(source.note or 'n/a')}")
            continue
        state = "absent" if not source.exists else ("unreadable" if not source.readable else "ok")
        total = sum(len(v) for v in source.events.values())
        lines.append(f"  {source.level:<10} {source.path} ({state}, {total} entries)")
        if source.error:
            lines.append(f"             error: {source.error}")
        for event, entries in source.events.items():
            for entry in entries:
                tag = "cursorfleet" if entry["ours"] else "other"
                lines.append(f"             {event}: [{tag}] {entry['command']}")
    counts = report.counts()
    lines.append("")
    lines.append(
        f"{counts['ok']} ok, {counts['warn']} warnings, {counts['fail']} problems"
        + ("" if report.ok else " (exit 1)")
    )
    return "\n".join(lines)


def register(app: typer.Typer) -> None:
    @app.command("doctor")
    def doctor(
        json_output: Annotated[
            bool, typer.Option("--json", help="Machine-readable output.")
        ] = False,
        path: Annotated[
            Path, typer.Option("--path", help="Directory inside the git repo (default: current).")
        ] = Path(),
        probe_cursor: Annotated[
            bool,
            typer.Option(
                "--probe-cursor/--no-probe-cursor",
                help="Run `cursor --version` (argv, 5s timeout) to report the Cursor version.",
            ),
        ] = True,
    ) -> None:
        """Check Python, the hook binary, git, runtime dir, install drift and effective hooks.

        Exit code 0 when no check failed (warnings are fine), 1 otherwise.
        """
        report = run_doctor(path, probe_cursor=probe_cursor)
        if json_output:
            typer.echo(json.dumps(report.as_dict(), indent=2))
        else:
            typer.echo(_render(report))
        if not report.ok:
            raise typer.Exit(1)
