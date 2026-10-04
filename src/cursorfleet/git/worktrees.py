"""Parse ``git worktree list --porcelain`` output (NUL- or newline-separated)."""

from __future__ import annotations

from dataclasses import dataclass

MAX_WORKTREES = 500


@dataclass(frozen=True)
class WorktreeEntry:
    """One record of the porcelain listing (git's own view; nothing is verified here)."""

    path: str
    head: str | None = None
    branch: str | None = None  # short name for refs/heads/*, else the ref without ``refs/``
    detached: bool = False
    bare: bool = False
    locked: bool = False
    prunable: bool = False


def _branch_name(ref: str) -> str:
    if ref.startswith("refs/heads/"):
        return ref[len("refs/heads/") :]
    return ref.removeprefix("refs/")


def parse_porcelain(text: str, *, nul: bool) -> list[WorktreeEntry]:
    """Parse porcelain text. ``nul=True`` for ``-z`` output, else newline-separated."""
    separator = "\0" if nul else "\n"
    entries: list[WorktreeEntry] = []
    current: dict[str, str | bool] = {}

    def flush() -> None:
        path = current.get("path")
        if isinstance(path, str) and path:
            head = current.get("head")
            branch = current.get("branch")
            entries.append(
                WorktreeEntry(
                    path=path,
                    head=head if isinstance(head, str) and head else None,
                    branch=branch if isinstance(branch, str) and branch else None,
                    detached=current.get("detached") is True,
                    bare=current.get("bare") is True,
                    locked=current.get("locked") is True,
                    prunable=current.get("prunable") is True,
                )
            )
        current.clear()

    for line in text.split(separator):
        if not line:
            flush()
            continue
        key, _, value = line.partition(" ")
        if key == "worktree":
            if current:
                flush()
            current["path"] = value
        elif key == "HEAD":
            current["head"] = value
        elif key == "branch":
            current["branch"] = _branch_name(value)
        elif key in {"bare", "detached", "locked", "prunable"}:
            current[key] = True  # the optional reason text is free text and is dropped
        if len(entries) >= MAX_WORKTREES:
            break
    flush()
    return entries[:MAX_WORKTREES]
