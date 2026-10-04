"""Shared CLI plumbing: resolve a repo to its runtime directory, parse an injected ``now``."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime

from cursorfleet.git.runner import NotAGitRepo, git_common_dir, git_toplevel
from cursorfleet.state.runtime import RuntimePaths, runtime_paths


@dataclass(frozen=True)
class RepoContext:
    common_dir: str
    top_level: str | None
    paths: RuntimePaths


def resolve_repo(repo: str | os.PathLike[str]) -> RepoContext:
    """Resolve via ``git rev-parse --git-common-dir`` (ADR 0002). Raises ``NotAGitRepo``."""
    start = os.fspath(repo)
    common = git_common_dir(start)
    return RepoContext(common, git_toplevel(start), runtime_paths(common))


def parse_now(text: str | None) -> datetime:
    """Return the injected clock value (ISO 8601 with offset) or the current UTC time."""
    if text is None:
        return datetime.now(UTC)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        msg = "--now must include a timezone offset (for example 2026-10-04T12:00:00Z)"
        raise ValueError(msg)
    return parsed.astimezone(UTC)


__all__ = ["NotAGitRepo", "RepoContext", "parse_now", "resolve_repo"]
