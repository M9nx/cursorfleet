"""``cursorfleet replay <session-id> [--json]``: rebuild from the spool, prove determinism."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from cursorfleet.adapters.cursor.fsutil import safe_text
from cursorfleet.git.runner import NotAGitRepo
from cursorfleet.state.context import parse_now, resolve_repo
from cursorfleet.state.reducer import digest, reduce_events, session_view
from cursorfleet.state.spool_read import read_all


def register(app: typer.Typer) -> None:
    @app.command("replay")
    def replay(
        session_id: Annotated[str, typer.Argument(help="Cursor conversation/session id.")],
        json_output: Annotated[
            bool, typer.Option("--json", help="Machine-readable output.")
        ] = False,
        repo: Annotated[
            Path, typer.Option("--repo", help="Directory inside the git repo (default: cwd).")
        ] = Path(),
        stale_after_minutes: Annotated[int, typer.Option("--stale-after-minutes", min=1)] = 15,
        now: Annotated[
            str | None, typer.Option("--now", hidden=True, help="ISO-8601 clock for tests.")
        ] = None,
    ) -> None:
        """Rebuild one session's state from the spool, twice, and check both runs agree.

        Exit 0 if the two replays are identical, 1 if the session is unknown or the
        replays differ (a bug), 2 on usage errors. Corrupt spool lines are counted, never fatal.
        """
        try:
            clock = parse_now(now)
        except ValueError as exc:
            typer.echo(f"error: {safe_text(str(exc))}", err=True)
            raise typer.Exit(2) from exc
        try:
            ctx = resolve_repo(repo)
        except NotAGitRepo as exc:
            typer.echo(f"error: {safe_text(str(exc))}", err=True)
            raise typer.Exit(1) from exc
        events_a, corruption, files = read_all(ctx.paths, session_id)
        events_b, _c, _f = read_all(ctx.paths, session_id)
        first = reduce_events(events_a).get(session_id)
        second = reduce_events(reversed(events_b)).get(session_id)
        if first is None or second is None:
            typer.echo(f"error: no events for session {session_id!r} in the spool", err=True)
            raise typer.Exit(1)
        deterministic = digest(first) == digest(second)
        view = session_view(first, clock, stale_after_minutes * 60)
        if json_output:
            payload = {
                "schema": "cursorfleet.replay/1",
                "session_id": session_id,
                "deterministic": deterministic,
                "digest": digest(first),
                "spool_files": files,
                "events": len(events_a),
                "corruption": corruption.to_dict(),
                "state": json.loads(view.model_dump_json()),
            }
            typer.echo(json.dumps(payload, indent=2))
        else:
            typer.echo(
                f"session {session_id}: {len(events_a)} event(s) from {files} file(s); "
                f"lane={view.lane}; corrupt/skipped={corruption.total}"
            )
            typer.echo(f"digest {digest(first)}  deterministic={str(deterministic).lower()}")
        if not deterministic:
            raise typer.Exit(1)
