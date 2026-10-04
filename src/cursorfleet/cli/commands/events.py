"""``cursorfleet events purge`` and ``events export --sanitized`` (docs/privacy.md)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from cursorfleet.adapters.cursor.fsutil import safe_text
from cursorfleet.config.io import loads_config
from cursorfleet.events.models import Event
from cursorfleet.git.runner import NotAGitRepo
from cursorfleet.state.context import RepoContext, parse_now, resolve_repo
from cursorfleet.state.indexer import Indexer, IndexerBusy
from cursorfleet.state.reducer import dedupe_and_sort
from cursorfleet.state.retention import (
    DEFAULT_MAX_AGE_DAYS,
    DEFAULT_MAX_SESSION_MB,
    PurgePlan,
    apply_plan,
    parse_duration,
    plan_purge,
)
from cursorfleet.state.spool_read import read_all

RepoOption = Annotated[
    Path, typer.Option("--repo", help="Directory inside the git repo (default: cwd).")
]


def _retention(ctx: RepoContext) -> tuple[int, int]:
    """Configured (max_age_days, max_session_mb); defaults if absent or invalid."""
    if ctx.top_level is None:
        return DEFAULT_MAX_AGE_DAYS, DEFAULT_MAX_SESSION_MB
    path = Path(ctx.top_level) / ".cursorfleet" / "config.toml"
    try:
        config = loads_config(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return DEFAULT_MAX_AGE_DAYS, DEFAULT_MAX_SESSION_MB
    except (OSError, ValueError) as exc:
        typer.echo(
            f"warning: ignoring unreadable .cursorfleet/config.toml ({exc.__class__.__name__})",
            err=True,
        )
        return DEFAULT_MAX_AGE_DAYS, DEFAULT_MAX_SESSION_MB
    return config.retention.max_age_days, config.retention.max_session_mb


def _describe(plan: PurgePlan) -> str:
    extras = []
    if plan.remove_projection:
        extras.append("projection")
    if plan.rotate_key:
        extras.append("hashing key (rotated)")
    if plan.remove_quarantine:
        extras.append("quarantine")
    tail = f"; also: {', '.join(extras)}" if extras else ""
    return f"{plan.sessions} session(s), {len(plan.files)} file(s), {plan.file_bytes} byte(s){tail}"


def purge(  # noqa: PLR0913
    *,
    older_than: Annotated[
        str | None, typer.Option("--older-than", help="Duration such as 7d, 12h, 90m.")
    ] = None,
    session: Annotated[str | None, typer.Option("--session", help="One session id.")] = None,
    all_: Annotated[
        bool,
        typer.Option("--all", help="Remove every spool file and the projection; rotate the key."),
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print counts, delete nothing.")
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Do not ask for confirmation.")] = False,
    repo: RepoOption = Path(),
    now: Annotated[str | None, typer.Option("--now", hidden=True)] = None,
) -> None:
    """Delete spool data under the git common dir. Never touches committed config.

    With no selector the configured retention is applied (default 14 days or 50 MB per
    session). Exit 0 on success (including nothing to purge), 1 on error, 2 on bad usage.
    """
    if sum([older_than is not None, session is not None, all_]) > 1:
        typer.echo("error: use at most one of --older-than, --session, --all", err=True)
        raise typer.Exit(2)
    try:
        delta = parse_duration(older_than) if older_than is not None else None
        clock = parse_now(now)
    except ValueError as exc:
        typer.echo(f"error: {safe_text(str(exc))}", err=True)
        raise typer.Exit(2) from exc
    try:
        ctx = resolve_repo(repo)
    except NotAGitRepo as exc:
        typer.echo(f"error: {safe_text(str(exc))}", err=True)
        raise typer.Exit(1) from exc
    max_age, max_mb = _retention(ctx)
    plan = plan_purge(
        ctx.paths,
        now=clock,
        older_than=delta,
        session=session,
        everything=all_,
        max_age_days=max_age,
        max_session_mb=max_mb,
    )
    if plan.empty:
        typer.echo("nothing to purge")
        return
    if dry_run:
        typer.echo(f"dry run: would remove {_describe(plan)}")
        return
    _confirm(yes, plan)
    report = apply_plan(ctx.paths, plan)
    if report.needs_reindex and not report.projection_removed:
        try:
            Indexer(ctx.paths).sync(rebuild=True)
        except IndexerBusy:
            typer.echo("note: another indexer is running; run `cursorfleet index --rebuild` later")
    typer.echo(
        f"removed {report.sessions} session(s), {report.files} file(s), {report.bytes} byte(s)"
        + ("; projection removed" if report.projection_removed else "")
        + ("; hashing key rotated" if report.key_rotated else "")
    )
    for problem in report.errors:
        typer.echo(f"warning: {problem}", err=True)
    if report.errors:
        raise typer.Exit(1)


def _confirm(yes: bool, plan: PurgePlan) -> None:
    if yes:
        return
    if not sys.stdin.isatty():
        typer.echo("error: refusing to delete without --yes when not interactive", err=True)
        raise typer.Exit(2)
    if not typer.confirm(f"Remove {_describe(plan)}?", default=False):
        typer.echo("aborted")
        raise typer.Exit(1)


def export(
    *,
    sanitized: Annotated[
        bool, typer.Option("--sanitized", help="Required: export only re-validated events.")
    ] = False,
    session: Annotated[str | None, typer.Option("--session")] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    repo: RepoOption = Path(),
) -> None:
    """Export spool events as JSON Lines after re-validating each one with the Event model.

    Events are de-duplicated and ordered by (ts, event_id). Invalid or corrupt lines are
    skipped and counted on stderr. Check branch names and paths before sharing.
    """
    if not sanitized:
        typer.echo("error: only --sanitized export exists; raw export is not offered", err=True)
        raise typer.Exit(2)
    try:
        ctx = resolve_repo(repo)
    except NotAGitRepo as exc:
        typer.echo(f"error: {safe_text(str(exc))}", err=True)
        raise typer.Exit(1) from exc
    spooled, corruption, _files = read_all(ctx.paths, session)
    lines: list[str] = []
    rejected = 0
    for event in dedupe_and_sort(spooled):
        dumped = event.model_dump_json(exclude_none=True)
        try:
            Event.model_validate(json.loads(dumped))  # re-validate the exact bytes we emit
        except (ValidationError, ValueError):
            rejected += 1
            continue
        lines.append(dumped)
    text = "".join(line + "\n" for line in lines)
    if output is None:
        sys.stdout.write(text)
    else:
        with output.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    skipped = corruption.total + rejected
    typer.echo(f"exported {len(lines)} event(s); skipped {skipped} corrupt/invalid", err=True)


def register(app: typer.Typer) -> None:
    events = typer.Typer(
        name="events",
        help="Inspect, export and purge the local event spool.",
        no_args_is_help=True,
    )
    events.command("purge")(purge)
    events.command("export")(export)
    app.add_typer(events, name="events")
