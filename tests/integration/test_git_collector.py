"""Collector tests against real temporary repositories (``git worktree add`` and friends)."""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cursorfleet.events.ids import worktree_id_for
from cursorfleet.git import runner
from cursorfleet.git.collector import collect, count_status_entries
from cursorfleet.git.worktrees import parse_porcelain
from m2_helpers import git, init_repo

# git_helper commits are dated 2026-01-01T00:00:00Z
COMMIT_TS = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
NOW = COMMIT_TS + timedelta(hours=1)


def by_branch(snapshot_worktrees: tuple, branch: str):  # type: ignore[no-untyped-def]
    return next(w for w in snapshot_worktrees if w.branch == branch)


def test_plain_repo_snapshot(repo: Path) -> None:
    snap = collect(str(repo), now=NOW)
    assert snap.available and snap.error is None
    assert snap.common_dir == str(repo / ".git")
    (main,) = snap.worktrees
    sha = git(["rev-parse", "HEAD"], repo).strip()
    assert (main.is_main, main.exists, main.bare) == (True, True, False)
    assert main.branch == "main" and main.head == sha and not main.detached
    assert main.dirty_count == 0 and not main.upstream and main.ahead is None
    assert main.last_commit_ts == COMMIT_TS and not main.stale
    assert main.real_path == str(repo) and main.worktree_id == worktree_id_for(str(repo))


def test_dirty_count_covers_modified_staged_untracked_and_renamed(repo: Path) -> None:
    (repo / "README.md").write_text("changed\n", encoding="utf-8")  # modified
    (repo / "new.txt").write_text("x", encoding="utf-8")  # untracked
    (repo / "staged.txt").write_text("y", encoding="utf-8")
    git(["add", "staged.txt"], repo)  # staged add
    (repo / "docs").mkdir()
    (repo / "docs" / "a.md").write_text("a", encoding="utf-8")
    (repo / "docs" / "b.md").write_text("b", encoding="utf-8")  # one untracked dir => 1 entry
    assert collect(str(repo), now=NOW).worktrees[0].dirty_count == 4
    git(["checkout", "-q", "README.md"], repo)
    git(["mv", "README.md", "RENAMED.md"], repo)  # a pure rename: two paths, one entry
    assert collect(str(repo), now=NOW).worktrees[0].dirty_count == 4  # rename counts once


def test_count_status_entries() -> None:
    assert count_status_entries(b"") == 0
    assert count_status_entries(b" M a.py\0?? b.py\0") == 2
    assert count_status_entries(b"R  new.py\0old.py\0 M c.py\0") == 2
    assert count_status_entries(b"C  copy.py\0orig.py\0") == 1


def test_linked_worktrees_are_listed_main_first(repo: Path, tmp_path: Path) -> None:
    feature = tmp_path / "wt-feature"
    git(["worktree", "add", "-q", "-b", "feature", str(feature)], repo)
    (feature / "x.py").write_text("x", encoding="utf-8")
    other = tmp_path / "wt-other"
    git(["worktree", "add", "-q", "-b", "other", str(other)], repo)
    snap = collect(str(repo), now=NOW)
    assert [w.is_main for w in snap.worktrees] == [True, False, False]
    assert snap.worktrees[0].path == str(repo)
    wt = by_branch(snap.worktrees, "feature")
    assert wt.dirty_count == 1 and by_branch(snap.worktrees, "other").dirty_count == 0
    assert wt.worktree_id == worktree_id_for(str(feature.resolve()))
    # collecting from inside a linked worktree sees the same set
    again = collect(str(feature), now=NOW)
    assert {w.path for w in again.worktrees} == {w.path for w in snap.worktrees}
    assert again.common_dir == snap.common_dir


def test_detached_worktree(repo: Path, tmp_path: Path) -> None:
    git(["worktree", "add", "-q", "--detach", str(tmp_path / "wt-d")], repo)
    detached = next(w for w in collect(str(repo), now=NOW).worktrees if not w.is_main)
    assert detached.detached and detached.branch is None and detached.head is not None
    assert detached.ahead is None and detached.upstream is False


def test_locked_worktree(repo: Path, tmp_path: Path) -> None:
    path = tmp_path / "wt-locked"
    git(["worktree", "add", "-q", "-b", "locked-b", str(path)], repo)
    git(["worktree", "lock", "--reason", "on a usb drive", str(path)], repo)
    wt = by_branch(collect(str(repo), now=NOW).worktrees, "locked-b")
    assert wt.locked and not wt.prunable and wt.exists


def test_missing_directory_is_prunable_and_stale(repo: Path, tmp_path: Path) -> None:
    path = tmp_path / "wt-gone"
    git(["worktree", "add", "-q", "-b", "gone", str(path)], repo)
    shutil.rmtree(path)
    wt = by_branch(collect(str(repo), now=NOW).worktrees, "gone")
    assert not wt.exists and wt.stale and "missing_path" in wt.stale_reasons
    assert wt.dirty_count is None and wt.real_path is None and wt.worktree_id is None
    assert wt.prunable is True
    assert "prunable" in wt.stale_reasons
    assert path.name not in os.listdir(tmp_path)  # the collector did not recreate or prune it
    assert (repo / ".git" / "worktrees" / "wt-gone").exists()


def test_bare_repo_with_worktree(tmp_path: Path, repo: Path) -> None:
    bare = tmp_path / "bare.git"
    git(["clone", "-q", "--bare", str(repo), str(bare)], tmp_path)
    git(["worktree", "add", "-q", str(tmp_path / "from-bare"), "main"], bare)
    snap = collect(str(bare), now=NOW)
    assert snap.available
    first = snap.worktrees[0]
    assert first.bare and first.is_main and first.dirty_count is None
    child = next(w for w in snap.worktrees if not w.bare)
    assert child.branch == "main" and child.dirty_count == 0


def test_ahead_behind_uses_existing_refs_and_never_fetches(repo: Path, tmp_path: Path) -> None:
    origin = tmp_path / "origin.git"
    git(["clone", "-q", "--bare", str(repo), str(origin)], tmp_path)
    clone = tmp_path / "clone"
    git(["clone", "-q", str(origin), str(clone)], tmp_path)
    for name in ("a", "b"):
        (clone / f"{name}.txt").write_text(name, encoding="utf-8")
        git(["add", "."], clone)
        git(["commit", "-q", "-m", name], clone)
    main = collect(str(clone), now=NOW).worktrees[0]
    assert (main.upstream, main.ahead, main.behind) == (True, 2, 0)
    # Someone else pushes to origin; we have not fetched, so the collector must not see it.
    other = tmp_path / "other"
    git(["clone", "-q", str(origin), str(other)], tmp_path)
    (other / "c.txt").write_text("c", encoding="utf-8")
    git(["add", "."], other)
    git(["commit", "-q", "-m", "c"], other)
    git(["push", "-q", "origin", "HEAD:main"], other)
    refs_before = git(["for-each-ref"], clone)
    still = collect(str(clone), now=NOW).worktrees[0]
    assert (still.ahead, still.behind) == (2, 0)
    assert git(["for-each-ref"], clone) == refs_before
    git(["fetch", "-q"], clone)  # the user fetching makes it visible
    fetched = collect(str(clone), now=NOW).worktrees[0]
    assert (fetched.ahead, fetched.behind) == (2, 1)
    assert collect(str(clone), now=NOW, ahead_behind=False).worktrees[0].ahead is None


def test_symlinked_repo_path_resolves_to_the_real_one(repo: Path, tmp_path: Path) -> None:
    link = tmp_path / "alias"
    try:
        os.symlink(repo, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    snap = collect(str(link), now=NOW)
    assert snap.worktrees[0].real_path == str(repo)
    assert snap.worktrees[0].worktree_id == worktree_id_for(str(repo))


def test_traversal_style_paths_and_subdirectories_work(repo: Path) -> None:
    (repo / "sub" / "deeper").mkdir(parents=True)
    assert collect(str(repo / "sub" / ".." / "sub" / "deeper"), now=NOW).available


def test_non_repo_and_missing_paths_degrade_without_raising(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    for target in (plain, tmp_path / "does-not-exist"):
        snap = collect(str(target), now=NOW)
        assert not snap.available and snap.error is not None and snap.worktrees == ()


def test_missing_git_executable_degrades(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(repo / "no-bin"))
    snap = collect(str(repo), now=NOW)
    assert not snap.available and snap.error == "git_unavailable"


def test_timeouts_degrade(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def hang(*_a: object, **kw: object) -> None:
        assert kw.get("timeout") is not None  # every subprocess call carries a timeout
        raise subprocess.TimeoutExpired(cmd="git", timeout=0.01)

    monkeypatch.setattr(runner.subprocess, "run", hang)
    snap = collect(str(repo), now=NOW, timeout=0.01)
    assert not snap.available and snap.worktrees == ()


def test_every_git_call_uses_argv_list_and_timeout(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    git(["worktree", "add", "-q", "-b", "f", str(tmp_path / "wt")], repo)
    calls: list[tuple[object, dict[str, object]]] = []
    real = subprocess.run

    def spy(argv: object, **kw: object) -> subprocess.CompletedProcess[bytes]:
        calls.append((argv, kw))
        return real(argv, **kw)  # type: ignore[call-overload, no-any-return]

    monkeypatch.setattr(runner.subprocess, "run", spy)
    collect(str(repo), now=NOW)
    assert calls
    for argv, kw in calls:
        assert isinstance(argv, list) and all(isinstance(a, str) for a in argv)
        assert os.path.basename(argv[0]).lower() in {"git", "git.exe"}
        assert os.path.isabs(argv[0])  # resolved without the current directory (SR-05)
        assert argv[1] == "--no-optional-locks"
        assert kw.get("shell") in (None, False) and kw.get("timeout")
        forbidden = {"fetch", "pull", "push", "checkout", "reset", "clean", "gc", "prune", "add"}
        assert not forbidden & set(argv[4:5])


def test_collector_does_not_mutate_the_repository(repo: Path, tmp_path: Path) -> None:
    git(["worktree", "add", "-q", "-b", "f", str(tmp_path / "wt")], repo)
    (repo / "README.md").write_text("touched so the index looks stale\n", encoding="utf-8")

    def fingerprint() -> list[tuple[str, int, int]]:
        found = []
        for root, _dirs, files in os.walk(repo / ".git"):
            for name in files:
                stat = os.lstat(os.path.join(root, name))
                found.append((os.path.join(root, name), stat.st_size, stat.st_mtime_ns))
        return sorted(found)

    before = fingerprint()
    collect(str(repo), now=NOW)
    assert fingerprint() == before


def test_repo_local_fsmonitor_is_not_executed(repo: Path, tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("POSIX shell script hook")
    marker = tmp_path / "pwned"
    hook = tmp_path / "fsmonitor.sh"
    hook.write_text(f"#!/bin/sh\ntouch '{marker}'\n", encoding="utf-8")
    hook.chmod(0o755)
    git(["config", "core.fsmonitor", str(hook)], repo)
    git(["status", "--porcelain"], repo, check=False)  # a plain git would run the hook
    if not marker.exists():
        pytest.skip("this git does not run fsmonitor hooks for status")
    marker.unlink()
    collect(str(repo), now=NOW)
    assert not marker.exists()


def test_stale_detection_uses_commit_time_and_injected_activity(repo: Path) -> None:
    late = COMMIT_TS + timedelta(hours=100)
    stale = collect(str(repo), now=late).worktrees[0]
    assert stale.stale and stale.stale_reasons == ("inactive",)
    wt_id = worktree_id_for(str(repo))
    active = collect(str(repo), now=late, activity={wt_id: late - timedelta(hours=1)})
    assert not active.worktrees[0].stale
    assert not collect(str(repo), now=late, stale_after_hours=200).worktrees[0].stale


def test_empty_repository_without_commits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    empty = init_repo(tmp_path / "empty", commit=False)
    monkeypatch.chdir(empty)
    snap = collect(str(empty), now=NOW)
    assert snap.available
    assert snap.worktrees[0].last_commit_ts is None and snap.worktrees[0].dirty_count == 0


def test_snapshot_is_deterministic(repo: Path, tmp_path: Path) -> None:
    git(["worktree", "add", "-q", "-b", "f", str(tmp_path / "wt")], repo)
    assert collect(str(repo), now=NOW) == collect(str(repo), now=NOW)


# ------------------------------------------------------------------ porcelain parser


def test_parse_porcelain_newline_format() -> None:
    text = (
        "worktree /r\nHEAD aaaa\nbranch refs/heads/main\n\n"
        "worktree /w1\nHEAD bbbb\ndetached\nlocked because reasons\n\n"
        "worktree /w2\nHEAD cccc\nbranch refs/heads/feat/x\nprunable gitdir file points to...\n\n"
        "worktree /b\nbare\n\n"
    )
    r, w1, w2, bare = parse_porcelain(text, nul=False)
    assert (r.branch, r.head) == ("main", "aaaa")
    assert w1.detached and w1.locked and w1.branch is None
    assert w2.branch == "feat/x" and w2.prunable
    assert bare.bare and bare.head is None


def test_parse_porcelain_nul_format_handles_odd_paths() -> None:
    text = "worktree /srv/a path\nwith newline\0HEAD aaaa\0branch refs/heads/m\0\0worktree /x\0\0"
    entries = parse_porcelain(text, nul=True)
    assert [e.path for e in entries] == ["/srv/a path\nwith newline", "/x"]


@pytest.mark.parametrize("junk", ["", "\n\n\n", "nonsense", "worktree", "HEAD abc\n\n"])
def test_parse_porcelain_tolerates_junk(junk: str) -> None:
    assert parse_porcelain(junk, nul=False) in ([], [])  # never raises; no valid entries
