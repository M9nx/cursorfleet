"""SR-03/05/06/07/08: a hostile repository or environment must not get code executed.

Covers hostile git configuration and GIT_* variables, executable lookup that never trusts
the current directory, lockfile/config paths aimed at ``.git``, planted databases, FIFOs,
Windows reparse points, and traceback hygiene.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import textwrap
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from cursorfleet.adapters.cursor import hook_main
from cursorfleet.adapters.cursor.diagnostics import run_doctor
from cursorfleet.adapters.cursor.fsutil import UnsafePathError, ensure_inside, is_link_like
from cursorfleet.adapters.cursor.lock import InstallLock, LockFile, loads_lock
from cursorfleet.adapters.cursor.workspace import resolve_workspace
from cursorfleet.cli.main import app as cli_app
from cursorfleet.config.io import loads_config
from cursorfleet.git.collector import collect
from cursorfleet.git.runner import git_env, run_git
from cursorfleet.safeexe import find_executable
from cursorfleet.state.artifact_scan import ArtifactScanner
from cursorfleet.state.indexer import Indexer
from cursorfleet.state.spool import append_event
from m2_helpers import dump, git, init_repo, make_event, paths_of

POSIX = pytest.mark.skipif(os.name != "posix", reason="needs POSIX shell scripts and symlinks")
NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)


def marker_script(directory: Path, marker: Path, name: str = "evil.sh") -> Path:
    script = directory / name
    script.write_text(f"#!/bin/sh\necho ran > '{marker}'\nexit 1\n", encoding="utf-8")
    script.chmod(0o755)
    return script


# ------------------------------------------------------------------ hostile git config / env


@POSIX
def test_hostile_git_config_never_executes_anything(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    marker = tmp_path / "pwned"
    evil = marker_script(tmp_path, marker)
    for key, value in {
        "core.fsmonitor": str(evil),
        "core.sshCommand": str(evil),
        "core.pager": str(evil),
        "core.editor": str(evil),
        "core.askpass": str(evil),
        "core.hooksPath": str(tmp_path),
        "diff.external": str(evil),
        "credential.helper": f"!{evil}",
        "gpg.program": str(evil),
        "alias.status": f"!{evil}",
        "alias.worktree": f"!{evil}",
        "alias.log": f"!{evil}",
        "alias.rev-parse": f"!{evil}",
    }.items():
        git(["config", "--local", key, value], repo)
    for hook in ("post-index-change", "post-checkout", "post-commit", "reference-transaction"):
        marker_script(repo / ".git" / "hooks", marker, hook)

    resolve_workspace(repo)
    snapshot = collect(str(repo), now=NOW)
    assert snapshot.available and snapshot.worktrees
    assert run_git(["status", "--porcelain=v1"], str(repo)) is not None
    assert not marker.exists(), "a repository-controlled program was executed"


@POSIX
def test_inherited_git_environment_cannot_redirect_or_execute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = init_repo(tmp_path / "repo")
    decoy = init_repo(tmp_path / "decoy")
    marker = tmp_path / "pwned"
    evil = marker_script(tmp_path, marker)
    monkeypatch.setenv("GIT_DIR", str(decoy / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(decoy))
    monkeypatch.setenv("GIT_INDEX_FILE", str(decoy / ".git" / "index"))
    monkeypatch.setenv("GIT_EXTERNAL_DIFF", str(evil))
    monkeypatch.setenv("GIT_ASKPASS", str(evil))
    monkeypatch.setenv("GIT_SSH_COMMAND", str(evil))
    env = git_env()
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_EXTERNAL_DIFF", "GIT_ASKPASS"):
        assert name not in env
    assert "GIT_SSH_COMMAND" not in env and env["GIT_TERMINAL_PROMPT"] == "0"
    # The workspace helper uses the same sanitised environment, so GIT_DIR cannot redirect it.
    assert resolve_workspace(repo).root == repo.resolve()
    assert not marker.exists()


# ------------------------------------------------------------------ executable lookup


def make_tool(directory: Path, name: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    full = directory / (name + (".EXE" if os.name == "nt" else ""))
    full.write_text("#!/bin/sh\n", encoding="utf-8")
    full.chmod(0o755)
    return full


@pytest.mark.parametrize("entry", ["", ".", "relative/bin"])
def test_find_executable_ignores_empty_dot_and_relative_path_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, entry: str
) -> None:
    hostile = tmp_path / "hostile"
    make_tool(hostile, "tool")
    make_tool(hostile / "relative" / "bin", "tool")
    monkeypatch.chdir(hostile)
    real = make_tool(tmp_path / "real", "tool")
    path_env = os.pathsep.join([entry, str(real.parent)])
    assert find_executable("tool", path_env=path_env, pathext=".EXE") == str(real)


def test_find_executable_skips_the_current_directory_even_when_on_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hostile = tmp_path / "hostile"
    make_tool(hostile, "tool")
    real = make_tool(tmp_path / "real", "tool")
    monkeypatch.chdir(hostile)
    path_env = os.pathsep.join([str(hostile), str(real.parent)])
    assert find_executable("tool", path_env=path_env, pathext=".EXE") == str(real)
    assert find_executable("absent", path_env=path_env, pathext=".EXE") is None
    assert find_executable("../tool", path_env=path_env, pathext=".EXE") is None


@POSIX
def test_a_git_shim_in_the_repository_is_never_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = init_repo(tmp_path / "repo")
    marker = tmp_path / "pwned"
    marker_script(repo, marker, "git")
    monkeypatch.chdir(repo)
    monkeypatch.setenv("PATH", os.pathsep.join(["", ".", os.environ["PATH"]]))
    result = run_git(["rev-parse", "--git-dir"], str(repo))
    assert result is not None and result.ok
    assert resolve_workspace(repo).root == repo.resolve()
    assert not marker.exists()


# ------------------------------------------------------------------ lockfile and config paths


@pytest.mark.parametrize(
    "path", [".git/hooks/pre-commit", ".GIT/config", ".cursorfleet/.git/x", ".cursor/rules/../x"]
)
def test_lockfile_cannot_name_git_internals(path: str) -> None:
    with pytest.raises(ValidationError):
        LockFile(path=path, sha256="0" * 64)
    with pytest.raises(ValidationError):
        InstallLock(dirs_created=[path])


def test_lockfile_dirs_created_cannot_point_at_git(tmp_path: Path) -> None:
    text = json.dumps({"lock_version": "1", "cursorfleet_version": "x", "dirs_created": [".git"]})
    with pytest.raises(ValueError, match=r"inside \.git"):
        loads_lock(text)


@pytest.mark.parametrize("work_dir", [".git/hooks", ".git", "x/.GIT/y", "../outside", "/abs"])
def test_config_work_dir_cannot_target_git_or_escape(work_dir: str) -> None:
    with pytest.raises(ValueError, match=r"\.git|relative|segments"):
        loads_config(f'schema_version = "1.0"\n[work]\ndir = "{work_dir}"\n')


def test_reparse_points_count_as_links(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    junction = tmp_path / "junction"
    junction.mkdir()
    real_lstat = Path.lstat

    def fake_lstat(self: Path, *args: object, **kwargs: object) -> object:
        info = real_lstat(self, *args, **kwargs)  # type: ignore[arg-type]
        if self == junction:
            return SimpleNamespace(
                st_mode=stat.S_IFDIR | 0o755, st_file_attributes=0x400, st_size=info.st_size
            )
        return info

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    assert is_link_like(junction)
    assert not is_link_like(tmp_path)
    with pytest.raises(UnsafePathError):
        ensure_inside(tmp_path, "junction/file.txt")


# ------------------------------------------------------------------ doctor shadow check


def test_doctor_warns_about_a_file_shadowing_the_hook_command(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    (repo / "cursorfleet-hook.cmd").write_text("@echo off\n", encoding="utf-8")
    report = run_doctor(repo, home=tmp_path / "home", probe_cursor=False)
    shadow = [c for c in report.checks if c.id == "hook.shadow"]
    assert shadow and shadow[0].status == "warn" and "cursorfleet-hook.cmd" in shadow[0].message


def test_doctor_has_no_shadow_warning_in_a_clean_repo(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    report = run_doctor(repo, home=tmp_path / "home", probe_cursor=False)
    assert not [c for c in report.checks if c.id == "hook.shadow"]


# ------------------------------------------------------------------ hot path details


def test_hook_head_reader_refuses_drive_letter_refs(tmp_path: Path) -> None:
    git_dir = tmp_path / "gitdir"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/C:/evil\n", encoding="utf-8")
    location = SimpleNamespace(git_dir=str(git_dir), common_dir=str(git_dir))
    assert hook_main.read_head(location) == (None, None)  # type: ignore[arg-type]


@POSIX
def test_a_fifo_planted_as_a_spool_file_does_not_hang_the_hook(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    paths = paths_of(repo)
    assert append_event(paths, "s1", "main", dump(make_event("s1", 1)), now_ms=1)
    from cursorfleet.state.spool import writer_file  # noqa: PLC0415

    target = writer_file(paths, "s2", "main")
    os.makedirs(os.path.dirname(target), mode=0o700)
    os.mkfifo(target, 0o600)
    assert append_event(paths, "s2", "main", dump(make_event("s2", 2)), now_ms=2) is False


@POSIX
def test_artifact_reader_refuses_a_symlink_swapped_in_after_the_scan(tmp_path: Path) -> None:
    secret = tmp_path / "outside.md"
    secret.write_text("---\nschema: cursorfleet.artifact/1\n---\nsecret\n", encoding="utf-8")
    link = tmp_path / "task" / "01-plan-architect.md"
    link.parent.mkdir()
    link.symlink_to(secret)
    assert ArtifactScanner._read(str(link), "task/01-plan-architect.md", 10) == [
        "artifact.unreadable"
    ]


# ------------------------------------------------------------------ database and tracebacks


def test_planted_projection_row_is_quarantined_and_rebuilt(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    paths = paths_of(repo)
    assert append_event(
        paths, "s1", "main", dump(make_event("s1", 1, kind="session.started")), now_ms=1
    )
    assert Indexer(paths).sync().events_new == 1

    import sqlite3  # noqa: PLC0415

    conn = sqlite3.connect(paths.db)
    try:
        conn.execute('UPDATE sessions SET state = \'{"not": "a session"}\'')
        conn.commit()
    finally:
        # Windows cannot rename the projection while this handle (or its WAL) is open.
        conn.close()
    assert append_event(paths, "s1", "main", dump(make_event("s1", 2)), now_ms=2)
    stats = Indexer(paths).sync()
    assert stats.db_recovered
    assert os.listdir(paths.quarantine)
    sessions = Indexer(paths).load_sessions()
    assert set(sessions) == {"s1"} and sessions["s1"].events == 2


def test_cli_apps_do_not_print_local_variables_in_tracebacks(tmp_path: Path) -> None:
    assert cli_app.pretty_exceptions_show_locals is False
    repo = init_repo(tmp_path / "repo")
    code = textwrap.dedent(
        """
        import sys
        from cursorfleet.cli.commands import status

        def boom(*args, **kwargs):
            canary = "CANARY-LOCAL-VALUE-1234"
            raise RuntimeError("boom " + str(len(canary)))

        status.build = boom
        sys.argv = ["cursorfleet", "status", "--no-git"]
        from cursorfleet.cli.main import app
        app()
        """
    )
    done = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode != 0
    assert "RuntimeError" in done.stderr + done.stdout
    assert "CANARY-LOCAL-VALUE-1234" not in done.stderr + done.stdout
