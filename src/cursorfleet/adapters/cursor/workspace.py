"""Resolve the workspace root and the shared runtime directory via git (ADR 0002).

Every subprocess uses an argv list and an explicit timeout.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from cursorfleet.git.runner import git_env
from cursorfleet.safeexe import find_executable

GIT_TIMEOUT_S = 10.0


class WorkspaceError(RuntimeError):
    """The path is not inside a usable git repository."""


@dataclass(frozen=True)
class Workspace:
    root: Path  # top level of the working tree (a worktree root inside a worktree)
    common_dir: Path  # absolute, realpath-resolved ``git rev-parse --git-common-dir``

    @property
    def runtime_dir(self) -> Path:
        """``<git-common-dir>/cursorfleet`` (shared by all worktrees; PROVISIONAL, ADR 0002 Q4)."""
        return self.common_dir / "cursorfleet"


def run_git(args: list[str], cwd: Path, *, timeout: float = GIT_TIMEOUT_S) -> str:
    """Run ``git <args>`` read-only in ``cwd`` and return stdout. Raises ``WorkspaceError``."""
    git = find_executable("git")  # never the current directory (hostile repositories)
    if git is None:
        msg = "git was not found on PATH"
        raise WorkspaceError(msg)
    try:
        proc = subprocess.run(  # noqa: S603
            [git, "--no-optional-locks", "-c", "core.fsmonitor=false", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            env=git_env(),
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as exc:
        msg = f"git {args[0]} timed out after {timeout:g}s"
        raise WorkspaceError(msg) from exc
    except OSError as exc:
        msg = f"cannot run git: {exc.strerror or exc}"
        raise WorkspaceError(msg) from exc
    if proc.returncode != 0:
        first = (proc.stderr.strip().splitlines() or ["unknown error"])[0]
        msg = f"git {args[0]} failed: {first[:200]}"
        raise WorkspaceError(msg)
    return proc.stdout


def resolve_workspace(path: Path) -> Workspace:
    """Return the :class:`Workspace` containing ``path``. Raises ``WorkspaceError``."""
    start = path.resolve()
    if not start.is_dir():
        msg = f"{path} is not a directory"
        raise WorkspaceError(msg)
    out = run_git(["rev-parse", "--show-toplevel", "--git-common-dir"], start)
    lines = out.splitlines()
    if len(lines) != 2:
        msg = "unexpected output from git rev-parse"
        raise WorkspaceError(msg)
    top = Path(lines[0])
    common = Path(lines[1])
    if not common.is_absolute():
        common = start / common
    return Workspace(root=top.resolve(), common_dir=common.resolve())
