"""``cursorfleet run`` — observe-only run metadata (runtime dir only)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from cursorfleet.git.runner import NotAGitRepo
from cursorfleet.state.context import resolve_repo
from cursorfleet.state.run_store import RunRecord, attach_session, list_runs, load_run, save_run

run_app = typer.Typer(name="run", help="Local run bookkeeping (does not modify git or hooks).")


def register(app: typer.Typer) -> None:
    app.add_typer(run_app)

    @run_app.command("start")
    def start(
        task: Annotated[
            str, typer.Option("--task", help="Task slug under .cursorfleet/work/<task>/")
        ],
        path: Annotated[
            Path, typer.Option("--path", help="Repository root or inside it.")
        ] = Path(),
        run_id: Annotated[
            str | None, typer.Option("--run-id", help="Optional stable id; default: random.")
        ] = None,
    ) -> None:
        try:
            ctx = resolve_repo(path.resolve())
        except NotAGitRepo:
            typer.echo("error: not a git repository", err=True)
            raise typer.Exit(2) from None
        rid = run_id or f"run-{uuid.uuid4().hex[:12]}"
        record = RunRecord(
            run_id=rid,
            task_slug=task,
            created_at=datetime.now(tz=UTC).isoformat(),
        )
        save_run(ctx.paths.root, record)
        typer.echo(rid)

    @run_app.command("list")
    def list_cmd(
        path: Annotated[Path, typer.Option("--path")] = Path(),
    ) -> None:
        try:
            ctx = resolve_repo(path.resolve())
        except NotAGitRepo:
            typer.echo("error: not a git repository", err=True)
            raise typer.Exit(2) from None
        rows = list_runs(ctx.paths.root)
        if not rows:
            typer.echo("no runs")
            return
        for row in rows:
            flag = "archived" if row.archived else "active"
            typer.echo(f"{row.run_id}\t{row.task_slug}\t{flag}\tsessions={len(row.session_ids)}")

    @run_app.command("attach")
    def attach(
        run_id: Annotated[str, typer.Argument(help="Run id from run start")],
        session: Annotated[str, typer.Option("--session", help="Cursor session_id to attach.")],
        path: Annotated[Path, typer.Option("--path")] = Path(),
    ) -> None:
        try:
            ctx = resolve_repo(path.resolve())
        except NotAGitRepo:
            typer.echo("error: not a git repository", err=True)
            raise typer.Exit(2) from None
        if not attach_session(ctx.paths.root, run_id, session):
            typer.echo("attach failed (unknown or archived run)", err=True)
            raise typer.Exit(1)
        typer.echo("attached")

    @run_app.command("archive")
    def archive(
        run_id: Annotated[str, typer.Argument()],
        path: Annotated[Path, typer.Option("--path")] = Path(),
    ) -> None:
        try:
            ctx = resolve_repo(path.resolve())
        except NotAGitRepo:
            typer.echo("error: not a git repository", err=True)
            raise typer.Exit(2) from None
        record = load_run(ctx.paths.root, run_id)
        if record is None:
            typer.echo("run not found", err=True)
            raise typer.Exit(1)
        record.archived = True
        save_run(ctx.paths.root, record)
        typer.echo("archived")
