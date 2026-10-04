"""Helpers for kit tests: throwaway git repos and byte-exact tree snapshots."""

from __future__ import annotations

import subprocess
from pathlib import Path

GIT_TIMEOUT_S = 30


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_S,
        check=True,
    )
    return proc.stdout


def make_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q")
    return path.resolve()


def snapshot(root: Path) -> dict[str, bytes | None]:
    """Map every path under ``root`` (excluding .git) to its bytes; directories map to None."""
    result: dict[str, bytes | None] = {}
    for item in sorted(root.rglob("*")):
        rel = item.relative_to(root).as_posix()
        if rel == ".git" or rel.startswith(".git/"):
            continue
        result[rel] = item.read_bytes() if item.is_file() else None
    return result


def write(root: Path, rel: str, text: str) -> Path:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(text.encode("utf-8"))
    return target
