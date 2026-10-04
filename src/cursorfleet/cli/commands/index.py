"""``cursorfleet index [--rebuild]``: run the single-writer indexer once."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from cursorfleet.adapters.cursor.fsutil import safe_text
from cursorfleet.git.runner import NotAGitRepo
from cursorfleet.state.context import resolve_repo
from cursorfleet.state.indexer import Indexer, IndexerBusy


def register(app: typer.Typer) -> None:
    @app.command("index")
    def index(
        rebuild: Annotated[
            bool,
            typer.Option("--rebuild", help="Delete the projection and rebuild from the spool."),
        ] = False,
        json_output: Annotated[bool, typer.Option("--json")] = False,
        repo: Annotated[Path, typer.Option("--repo")] = Path(),
    ) -> None:
        """Tail the spool into the SQLite projection once (the projection is rebuildable)."""
        try:
            ctx = resolve_repo(repo)
        except NotAGitRepo as exc:
            typer.echo(f"error: {safe_text(str(exc))}", err=True)
            raise typer.Exit(1) from exc
        try:
            stats = Indexer(ctx.paths).sync(rebuild=rebuild)
        except IndexerBusy as exc:
            typer.echo(f"error: {safe_text(str(exc))}", err=True)
            raise typer.Exit(1) from exc
        summary = {
            "files_scanned": stats.files_scanned,
            "events_read": stats.events_read,
            "events_new": stats.events_new,
            "sessions_updated": stats.sessions_updated,
            "sessions_rebuilt": stats.sessions_rebuilt,
            "sessions_pruned": stats.sessions_pruned,
            "db_recovered": stats.db_recovered,
            "corruption": stats.corruption.to_dict(),
        }
        if json_output:
            typer.echo(json.dumps({"schema": "cursorfleet.index/1", **summary}, indent=2))
        else:
            typer.echo(
                f"indexed {stats.events_new} new event(s) from {stats.files_scanned} file(s); "
                f"{stats.sessions_updated} updated, {stats.sessions_rebuilt} rebuilt, "
                f"{stats.corruption.total} corrupt/skipped"
            )
