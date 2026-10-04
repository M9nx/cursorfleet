"""Read-only git invocation: argv lists, explicit timeouts, no fetch, no mutation.

Hardening for hostile repositories (threat model, "Malicious repository"):

- ``core.fsmonitor`` is forced off, because a repo-local fsmonitor hook would otherwise run
  an arbitrary program when we call ``git status``.
- ``--no-optional-locks`` / ``GIT_OPTIONAL_LOCKS=0`` stop ``status`` from refreshing (writing)
  the index.
- Inherited ``GIT_DIR``/``GIT_WORK_TREE``/``GIT_INDEX_FILE`` are dropped so a hook context
  cannot redirect us, and prompts/pagers are disabled.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass

from cursorfleet.safeexe import find_executable

DEFAULT_TIMEOUT_S = 10.0
MAX_OUTPUT_BYTES = 8 * 1024 * 1024

_DROP_ENV = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
    "GIT_EXTERNAL_DIFF",
    "GIT_ASKPASS",
    "GIT_SSH_COMMAND",
)
_BASE_ARGS = ("--no-optional-locks", "-c", "core.fsmonitor=false")


class GitError(Exception):
    """Base class for collector failures."""


class GitUnavailable(GitError):
    """The ``git`` executable could not be run."""


class NotAGitRepo(GitError):
    """The path is not inside a git repository."""


@dataclass(frozen=True)
class GitResult:
    returncode: int
    stdout: bytes

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def text(self) -> str:
        return self.stdout.decode("utf-8", "replace")


def git_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in _DROP_ENV}
    env.update(
        {
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_PAGER": "cat",
            "LC_ALL": "C",
            "LANG": "C",
        }
    )
    return env


def run_git(
    args: Sequence[str], cwd: str, *, timeout: float = DEFAULT_TIMEOUT_S
) -> GitResult | None:
    """Run ``git <args>`` in ``cwd``. Returns ``None`` on timeout or OS-level failure.

    Raises :class:`GitUnavailable` only when the executable itself is missing.
    """
    exe = find_executable("git")  # never the current directory (hostile repositories)
    if exe is None:
        msg = "git executable not found"
        raise GitUnavailable(msg)
    argv = [exe, *_BASE_ARGS, *args]
    try:
        completed = subprocess.run(  # noqa: S603 - argv list, fixed executable, no shell
            argv,
            cwd=cwd,
            capture_output=True,
            timeout=timeout,
            check=False,
            env=git_env(),
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError as exc:
        if not os.path.isdir(cwd):
            return None
        msg = "git executable not found"
        raise GitUnavailable(msg) from exc
    except (subprocess.TimeoutExpired, OSError):
        return None
    return GitResult(completed.returncode, completed.stdout[:MAX_OUTPUT_BYTES])


def git_common_dir(start: str, *, timeout: float = DEFAULT_TIMEOUT_S) -> str:
    """``git rev-parse --git-common-dir`` from ``start``, absolute and realpath-resolved.

    The contract of ADR 0002; the hook hot path uses an equivalent file walk instead and
    a contract test compares the two.
    """
    start = os.path.realpath(start)
    result = run_git(["rev-parse", "--git-common-dir"], start, timeout=timeout)
    if result is None or not result.ok:
        msg = f"not a git repository (or git failed): {start}"
        raise NotAGitRepo(msg)
    value = result.text().strip()
    if not value:
        msg = "git returned an empty common dir"
        raise NotAGitRepo(msg)
    return os.path.realpath(value if os.path.isabs(value) else os.path.join(start, value))


def git_toplevel(start: str, *, timeout: float = DEFAULT_TIMEOUT_S) -> str | None:
    """``git rev-parse --show-toplevel`` (realpath), or ``None`` for bare repos / non-repos."""
    real = os.path.realpath(start)
    result = run_git(["rev-parse", "--show-toplevel"], real, timeout=timeout)
    if result is None or not result.ok:
        return None
    value = result.text().strip()
    return os.path.realpath(value) if value else None
