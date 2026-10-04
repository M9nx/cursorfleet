"""``cursorfleet status [--json]``: fleet snapshot from the projection plus read-only git."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from cursorfleet.adapters.cursor.kit_probe import probe_hooks_kit
from cursorfleet.git.collector import DEFAULT_STALE_AFTER_HOURS, GitSnapshot, collect
from cursorfleet.git.runner import NotAGitRepo
from cursorfleet.state.context import RepoContext, parse_now, resolve_repo
from cursorfleet.state.indexer import Indexer, replay_session_state
from cursorfleet.state.models import SessionAcc
from cursorfleet.state.reducer import snapshot
from cursorfleet.state.spool_read import Corruption, list_spool_files
from cursorfleet.state.status_doc import STATUS_SCHEMA, StatusDoc, build_status, worktree_activity


def _safe(text: object) -> str:
    """Make untrusted strings safe for a terminal (no control or bidi characters)."""
    return "".join(c if c.isprintable() else "?" for c in str(text))


def _load(ctx: RepoContext) -> tuple[dict[str, SessionAcc], Corruption, int, str]:
    """Return (sessions, corruption, spool file count, source)."""
    files = len(list_spool_files(ctx.paths))
    if files == 0:
        return {}, Corruption(), 0, "none"
    indexer = Indexer(ctx.paths)
    indexer.try_sync()  # another indexer may be running; then we just read its projection
    sessions = indexer.load_sessions()
    if sessions:
        return sessions, indexer.corruption(), files, "projection"
    replayed, corruption, _n = replay_session_state(ctx.paths)
    return replayed, corruption, files, "replay"


def build(ctx: RepoContext, *, now: datetime, stale_after_s: int, with_git: bool) -> StatusDoc:
    sessions, corruption, files, source = _load(ctx)
    fleet = snapshot(sessions, now=now, stale_after_s=stale_after_s)
    git: GitSnapshot | None = None
    if with_git:
        git = collect(
            ctx.top_level or ctx.common_dir,
            now=now,
            stale_after_hours=DEFAULT_STALE_AFTER_HOURS,
            activity=worktree_activity(sessions),
        )
    repo_root = ctx.top_level or ctx.common_dir
    return build_status(
        now=now,
        fleet=fleet,
        git=git,
        common_dir=ctx.common_dir,
        runtime_dir=ctx.paths.root,
        corruption=corruption,
        spool_files=files,
        source=source,
        hooks_kit=probe_hooks_kit(repo_root).state,
    )


def _render_text(doc: StatusDoc) -> str:
    lines = [
        f"CursorFleet status  ({doc.generated_at.isoformat()})",
        f"telemetry: {doc.telemetry.state} | sessions {doc.telemetry.sessions} | "
        f"events {doc.telemetry.events} | token budget: {doc.limits.token_budget}",
    ]
    lines.extend(f"note: {_safe(n)}" for n in doc.telemetry.notes)
    lines.append("")
    lines.append("SESSIONS")
    if not doc.sessions:
        awaiting = any("hooks installed" in n for n in doc.telemetry.notes)
        hint = "await Cursor session" if awaiting else "no hook telemetry"
        lines.append(f"  (none: {hint})")
    for s in doc.sessions:
        lines.append(
            f"  {_safe(s.session_id)}  lane={s.lane}  tools={s.tool_call_count}  "
            f"compactions={s.compactions}  elapsed={s.elapsed_s:.0f}s  events={s.event_count}"
        )
        for a in s.agents:
            lines.append(
                f"    - {_safe(a.key)}  lane={a.lane} ({a.lane_basis})  "
                f"attribution={a.attribution}  tools={a.tool_call_count}"
            )
    lines.append("")
    lines.append("WORKTREES")
    if not doc.worktrees:
        lines.append(f"  (none: {_safe(doc.git.error or 'git disabled')})")
    for w in doc.worktrees:
        marks = ",".join(w.stale_reasons)
        sync = "" if w.ahead is None else f" +{w.ahead}/-{w.behind}"
        lines.append(
            f"  {_safe(w.path)}  [{_safe(w.branch or 'detached')}]  "
            f"dirty={w.dirty_count if w.dirty_count is not None else '?'}{sync}  "
            f"lane={w.lane}  telemetry={w.telemetry}" + (f"  STALE({marks})" if marks else "")
        )
    return "\n".join(lines)


def register(app: typer.Typer) -> None:
    @app.command("status")
    def status(
        json_output: Annotated[bool, typer.Option("--json", help="Stable JSON output.")] = False,
        repo: Annotated[
            Path, typer.Option("--repo", help="Directory inside the git repo (default: cwd).")
        ] = Path(),
        stale_after_minutes: Annotated[
            int, typer.Option("--stale-after-minutes", min=1, help="Silence before stale_offline.")
        ] = 15,
        no_git: Annotated[bool, typer.Option("--no-git", help="Skip the git collector.")] = False,
        now: Annotated[
            str | None, typer.Option("--now", hidden=True, help="ISO-8601 clock for tests.")
        ] = None,
    ) -> None:
        """Show the fleet: sessions, agents, lanes and worktrees. Read-only; no network."""
        try:
            clock = parse_now(now)
        except ValueError as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(2) from exc
        try:
            ctx = resolve_repo(repo)
        except NotAGitRepo as exc:
            if json_output:
                typer.echo(
                    json.dumps({"schema": STATUS_SCHEMA, "error": {"code": "not_a_git_repo"}})
                )
            else:
                typer.echo(f"error: {_safe(exc)}", err=True)
            raise typer.Exit(1) from exc
        doc = build(ctx, now=clock, stale_after_s=stale_after_minutes * 60, with_git=not no_git)
        if json_output:
            typer.echo(json.dumps(doc.to_json_dict(), indent=2, sort_keys=False))
        else:
            typer.echo(_render_text(doc))
