"""Shared helpers for the M2 (hook hot path, spool, state, git) tests."""

from __future__ import annotations

import io
import json
import os
import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from cursorfleet.adapters.cursor import hook_main
from cursorfleet.state.runtime import RuntimePaths, runtime_paths
from cursorfleet.state.spool import append_event
from cursorfleet.state.spool_read import list_spool_files

DOC_DIR = Path(__file__).resolve().parents[1] / "spike" / "doc_examples"
FIXED_NS = 1_790_000_000_123_000_000  # 2026-09-21T14:13:20.123Z
ALL_HOOKS = [
    "sessionStart",
    "sessionEnd",
    "preToolUse",
    "postToolUse",
    "postToolUseFailure",
    "subagentStart",
    "subagentStop",
    "beforeShellExecution",
    "afterShellExecution",
    "afterFileEdit",
    "preCompact",
    "stop",
]


def doc_payload(hook: str) -> dict[str, Any]:
    """A doc-derived (NOT captured) payload, minus the marker key."""
    data: dict[str, Any] = json.loads((DOC_DIR / f"{hook}.doc-derived.json").read_text("utf-8"))
    data.pop("_doc_derived_not_captured", None)
    return data


def git(args: list[str], cwd: Path | str, check: bool = True) -> str:
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.invalid",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.invalid",
        "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
        "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00",
    }
    done = subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "-c", "commit.gpgsign=false", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
        check=check,
        env=env,
    )
    return done.stdout


def same_path(left: str | Path, right: str | Path) -> bool:
    """True when two paths name the same location (slash and drive spelling ignored)."""
    return os.path.normcase(os.path.normpath(os.fspath(left))) == os.path.normcase(
        os.path.normpath(os.fspath(right))
    )


def init_repo(path: Path, *, commit: bool = True) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    git(["init", "-q"], path)
    if commit:
        (path / "README.md").write_text("hello\n", encoding="utf-8")
        git(["add", "README.md"], path)
        git(["commit", "-q", "-m", "init"], path)
    return path.resolve()


def plant_install_marker(root: Path) -> Path:
    """Write the v0.1 install marker ``.cursorfleet/config.toml`` (a regular file)."""
    cfg = root / ".cursorfleet"
    cfg.mkdir(exist_ok=True)
    marker = cfg / "config.toml"
    if not marker.exists():
        marker.write_text("# cursorfleet test marker\n", encoding="utf-8")
    return marker


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A fresh git repo that is also the process cwd (so hooks can never hit the real repo)."""
    root = init_repo(tmp_path / "repo")
    plant_install_marker(root)
    git(["add", ".cursorfleet/config.toml"], root)
    git(["commit", "-q", "-m", "cursorfleet marker"], root)
    monkeypatch.chdir(root)
    yield root


@pytest.fixture(autouse=False)
def outside_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A cwd that is not inside any git repo."""
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.chdir(plain)
    return plain


def counter_entropy(start: int = 1) -> Callable[[], bytes]:
    state = {"n": start}

    def _next() -> bytes:
        state["n"] += 1
        return state["n"].to_bytes(10, "big")

    return _next


def run_hook(
    payload: dict[str, Any] | bytes,
    *,
    now_ns: int = FIXED_NS,
    environ: dict[str, str] | None = None,
    entropy: Callable[[], bytes] | None = None,
    argv: list[str] | None = None,
) -> tuple[int, str]:
    """Invoke the hook entrypoint in-process with injected clock, entropy, stdin and stdout."""
    raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
    out = io.StringIO()
    code = hook_main.main(
        argv or ["cursorfleet-hook"],
        stdin=io.BytesIO(raw),
        stdout=out,
        environ=environ if environ is not None else {},
        clock_ns=lambda: now_ns,
        entropy=entropy or counter_entropy(),
    )
    return code, out.getvalue().strip()


def paths_of(repo_root: Path) -> RuntimePaths:
    common = Path(git(["rev-parse", "--git-common-dir"], repo_root).strip())
    if not common.is_absolute():
        common = repo_root / common
    return runtime_paths(common.resolve())


def spool_files(repo_root: Path) -> list[str]:
    return list_spool_files(paths_of(repo_root))


def spool_bytes(repo_root: Path) -> bytes:
    return b"".join(Path(f).read_bytes() for f in spool_files(repo_root))


def spool_events(repo_root: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in spool_bytes(repo_root).splitlines():
        if line.strip():
            events.append(json.loads(line[9:]))
    return events


# ------------------------------------------------------------------ event builders


def make_event(
    session: str = "s1",
    n: int = 1,
    *,
    kind: str = "tool.completed",
    ts: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """A minimal valid event with a deterministic id derived from ``n``."""
    event: dict[str, Any] = {
        "schema_version": "1.0",
        "event_id": f"01J9ZK3Q7M8N2P4R6S8T{n:06d}",
        "ts": ts or f"2026-10-04T00:{(n // 60) % 60:02d}:{n % 60:02d}.000Z",
        "producer": "cursor_hook",
        "producer_version": "0.0.1.dev0",
        "source": "observed",
        "kind": kind,
        "session_id": session,
        "attribution": "unknown",
        "risk": "none",
    }
    event.update(extra)
    return event


def dump(event: dict[str, Any]) -> str:
    return json.dumps(event, separators=(",", ":"))


def append_worker(args: tuple[str, str, str, int, int, int]) -> int:
    """Child-process entry (spawn-safe): append ``count`` events, return how many succeeded."""
    root, session, writer, start, count, rotate = args
    paths = RuntimePaths(root)
    ok = 0
    for n in range(start, start + count):
        event = make_event(session, n, paths=[{"path": "p/" + "x" * 200 + str(n)}])
        if append_event(
            paths, session, writer, dump(event), now_ms=1_790_000_000_000 + n, rotate_bytes=rotate
        ):
            ok += 1
    return ok
