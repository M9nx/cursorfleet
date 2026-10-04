"""Contract: the hook's file-walk resolution equals ``git rev-parse`` (ADR 0002)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from cursorfleet.git.runner import git_common_dir, git_toplevel
from cursorfleet.state.runtime import find_git_location, runtime_paths, safe_realpath
from m2_helpers import git, init_repo


def assert_matches_git(start: Path) -> None:
    location = find_git_location(str(start))
    assert location is not None, start
    assert location.common_dir == git_common_dir(str(start))
    assert location.top_level == git_toplevel(str(start))
    expected_git_dir = os.path.realpath(git(["rev-parse", "--absolute-git-dir"], start).strip())
    assert location.git_dir == expected_git_dir


def test_main_checkout_and_subdirectories(repo: Path) -> None:
    (repo / "a" / "b").mkdir(parents=True)
    for start in (repo, repo / "a", repo / "a" / "b"):
        assert_matches_git(start)


def test_linked_worktree_shares_the_main_common_dir(repo: Path, tmp_path: Path) -> None:
    linked = tmp_path / "linked"
    git(["worktree", "add", "-q", "-b", "f", str(linked)], repo)
    assert_matches_git(linked)
    (linked / "sub").mkdir()
    assert_matches_git(linked / "sub")
    found = find_git_location(str(linked))
    assert found is not None and found.common_dir == str(repo / ".git")
    assert found.git_dir != found.common_dir and found.top_level == str(linked.resolve())


def test_submodule_has_its_own_common_dir(repo: Path, tmp_path: Path) -> None:
    lib = init_repo(tmp_path / "lib")
    git(
        ["-c", "protocol.file.allow=always", "submodule", "add", "-q", str(lib), "vendor/lib"], repo
    )
    assert_matches_git(repo / "vendor" / "lib")
    inner = find_git_location(str(repo / "vendor" / "lib"))
    outer = find_git_location(str(repo))
    assert inner is not None and outer is not None and inner.common_dir != outer.common_dir


def test_symlinked_start_resolves_to_the_real_repo(repo: Path, tmp_path: Path) -> None:
    link = tmp_path / "alias"
    try:
        os.symlink(repo, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    via = find_git_location(str(link))
    assert via is not None and via.top_level == str(repo)
    assert via.common_dir == git_common_dir(str(link))


def test_safe_realpath_survives_getcwd_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = os.path.abspath(str(tmp_path))

    def boom() -> str:
        raise OSError("no cwd")

    monkeypatch.setattr(os, "getcwd", boom)
    assert os.path.normcase(safe_realpath(raw)) == os.path.normcase(os.path.normpath(raw))


def test_not_a_repo_is_none(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    assert find_git_location(str(plain)) is None
    assert find_git_location(str(tmp_path / "missing" / "deeper")) is None
    assert find_git_location("") is None
    assert find_git_location("relative/dir") is None


def test_malformed_gitfile_is_not_followed(tmp_path: Path) -> None:
    fake = tmp_path / "fake"
    fake.mkdir()
    (fake / ".git").write_text("gitdir:\n", encoding="utf-8")
    assert find_git_location(str(fake)) is None
    (fake / ".git").write_text("not a gitfile", encoding="utf-8")
    assert find_git_location(str(fake)) is None


def test_relative_gitdir_in_gitfile_is_resolved(tmp_path: Path) -> None:
    real = tmp_path / "real.git"
    real.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    (work / ".git").write_text("gitdir: ../real.git\n", encoding="utf-8")
    found = find_git_location(str(work))
    assert found is not None and found.common_dir == str(real.resolve())


def test_runtime_dir_is_under_the_common_dir_for_every_checkout(repo: Path, tmp_path: Path) -> None:
    linked = tmp_path / "linked"
    git(["worktree", "add", "-q", "-b", "f", str(linked)], repo)
    main = find_git_location(str(repo))
    other = find_git_location(str(linked))
    assert main is not None and other is not None
    assert runtime_paths(main.common_dir).root == runtime_paths(other.common_dir).root
    assert runtime_paths(main.common_dir).root == str(repo / ".git" / "cursorfleet")
