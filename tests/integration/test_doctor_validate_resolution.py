"""Task 15: doctor and validate print repository resolution and never write."""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from cursorfleet.adapters.cursor import diagnostics
from cursorfleet.cli.commands._resolution import RESOLUTION_KEYS
from cursorfleet.cli.main import app
from m2_helpers import git, init_repo, plant_install_marker

runner = CliRunner()
HOOK_BIN = "cursorfleet-hook"


def invoke(*args: str) -> tuple[int, str]:
    result = runner.invoke(app, list(args))
    return result.exit_code, result.output


def _transient_git_lock(rel: str) -> bool:
    """Git may create short-lived lock files under ``.git/`` during maintenance."""
    return rel.startswith(".git/") and rel.endswith(".lock")


def tree_state(root: Path) -> dict[str, str]:
    """Byte-level listing used to prove doctor/validate create nothing."""
    found: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        base = Path(dirpath)
        for name in (*dirnames, *filenames):
            path = base / name
            rel = path.relative_to(root).as_posix()
            if _transient_git_lock(rel):
                continue
            if path.is_symlink():
                found[rel] = "link:" + os.readlink(path)
            elif path.is_file():
                found[rel] = "file:" + path.read_bytes().hex()
            else:
                found[rel] = "dir"
    return found


def parse_text_resolution(output: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for line in output.splitlines():
        if not line.startswith("  ") or ": " not in line:
            continue
        key, _, value = line.strip().partition(": ")
        if key not in RESOLUTION_KEYS:
            continue
        if value == "null":
            data[key] = None
        elif value == "true":
            data[key] = True
        elif value == "false":
            data[key] = False
        else:
            data[key] = value
    return data


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.delenv("CURSOR_VERSION", raising=False)
    return fake_home


@pytest.fixture
def fake_which(monkeypatch: pytest.MonkeyPatch) -> Callable[[], None]:
    real = shutil.which

    def install() -> None:
        def which(cmd: str, *args: Any, **kwargs: Any) -> str | None:
            if cmd == HOOK_BIN:
                return "/fake/bin/cursorfleet-hook"
            if cmd == "cursor":
                return None
            return real(cmd, *args, **kwargs)

        monkeypatch.setattr(shutil, "which", which)
        monkeypatch.setattr(diagnostics, "find_executable", lambda _name, **_kw: None)

    return install


def assert_same_facts(text_out: str, payload: dict[str, Any]) -> None:
    parsed = parse_text_resolution(text_out)
    assert parsed == payload
    assert set(payload) == set(RESOLUTION_KEYS)


def run_both(
    command: str,
    target: Path,
    watch: Path,
    fake_which: Callable[[], None],
) -> tuple[int, dict[str, Any], int, str]:
    fake_which()
    before = tree_state(watch)
    extra = ["--no-probe-cursor"] if command == "doctor" else []
    json_code, json_out = invoke(command, "--json", "--path", str(target), *extra)
    text_code, text_out = invoke(command, "--path", str(target), *extra)
    assert tree_state(watch) == before
    payload = json.loads(json_out)
    resolution = payload["resolution"]
    assert_same_facts(text_out, resolution)
    return json_code, payload, text_code, text_out


def test_root_resolution(tmp_path: Path, home: Path, fake_which: Callable[[], None]) -> None:
    root = init_repo(tmp_path / "repo")
    plant_install_marker(root)
    for command in ("doctor", "validate"):
        json_code, payload, text_code, _text = run_both(command, root, tmp_path, fake_which)
        res = payload["resolution"]
        assert res["boundary"] == "repository-root"
        assert res["status"] == "ok"
        assert res["repository_root"] == root.as_posix()
        assert res["common_dir"] == (root / ".git").as_posix()
        assert res["marker_path"] == (root / ".cursorfleet" / "config.toml").as_posix()
        assert res["marker_present"] is True and res["marker_valid"] is True
        assert "Repository resolution:" in _text
        if command == "doctor":
            assert json_code == 0 and text_code == 0


def test_ordinary_descendant_uses_enclosing_root(
    tmp_path: Path, home: Path, fake_which: Callable[[], None]
) -> None:
    root = init_repo(tmp_path / "repo")
    plant_install_marker(root)
    nested = root / "src" / "pkg"
    nested.mkdir(parents=True)
    for command in ("doctor", "validate"):
        _code, payload, _tcode, _text = run_both(command, nested, tmp_path, fake_which)
        res = payload["resolution"]
        assert res["boundary"] == "ordinary-descendant"
        assert res["status"] == "ok"
        assert res["repository_root"] == root.as_posix()
        assert res["marker_valid"] is True
        assert (nested / ".cursorfleet").exists() is False
        assert (nested / ".git").exists() is False


def test_linked_worktree_root(tmp_path: Path, home: Path, fake_which: Callable[[], None]) -> None:
    root = init_repo(tmp_path / "repo")
    plant_install_marker(root)
    linked = tmp_path / "linked"
    git(["worktree", "add", "-q", "-b", "side", str(linked)], root)
    for command in ("doctor", "validate"):
        _code, payload, _tcode, _text = run_both(command, linked, tmp_path, fake_which)
        res = payload["resolution"]
        assert res["boundary"] == "linked-worktree"
        assert res["status"] == "ok"
        assert res["repository_root"] == linked.resolve().as_posix()
        assert res["common_dir"] == (root / ".git").as_posix()


def test_nested_repository_stays_at_inner_root(
    tmp_path: Path, home: Path, fake_which: Callable[[], None]
) -> None:
    outer = init_repo(tmp_path / "outer")
    plant_install_marker(outer)
    inner = init_repo(outer / "vendor" / "lib")
    plant_install_marker(inner)
    for command in ("doctor", "validate"):
        _code, payload, _tcode, _text = run_both(command, inner, tmp_path, fake_which)
        res = payload["resolution"]
        assert res["boundary"] == "nested-repository"
        assert res["status"] == "ok"
        assert res["repository_root"] == inner.as_posix()
        assert res["repository_root"] != outer.as_posix()
        assert res["marker_valid"] is True


def test_uninitialized_inner_repository_does_not_fall_back(
    tmp_path: Path, home: Path, fake_which: Callable[[], None]
) -> None:
    outer = init_repo(tmp_path / "outer")
    plant_install_marker(outer)
    inner = init_repo(outer / "vendor" / "lib")
    nested = inner / "src"
    nested.mkdir()
    for command, target in (("doctor", inner), ("validate", nested)):
        _code, payload, _tcode, _text = run_both(command, target, tmp_path, fake_which)
        res = payload["resolution"]
        assert res["repository_root"] == inner.as_posix()
        assert res["repository_root"] != outer.as_posix()
        assert res["marker_valid"] is False
        assert "will not fall back" in res["reason"]
        if target == inner:
            assert res["boundary"] == "nested-repository"
        else:
            assert res["boundary"] == "ordinary-descendant"
        assert res["status"] == "ok"


def test_submodule_gitfile_is_its_own_boundary(
    tmp_path: Path, home: Path, fake_which: Callable[[], None]
) -> None:
    outer = init_repo(tmp_path / "outer")
    plant_install_marker(outer)
    lib = init_repo(tmp_path / "lib")
    git(
        ["-c", "protocol.file.allow=always", "submodule", "add", "-q", str(lib), "vendor/lib"],
        outer,
    )
    inner = (outer / "vendor" / "lib").resolve()
    for command in ("doctor", "validate"):
        _code, payload, _tcode, _text = run_both(command, inner, tmp_path, fake_which)
        res = payload["resolution"]
        assert res["boundary"] == "submodule"
        assert res["repository_root"] == inner.as_posix()
        assert res["repository_root"] != outer.as_posix()
        assert res["marker_valid"] is False


def test_non_git_path_fails(tmp_path: Path, home: Path, fake_which: Callable[[], None]) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    for command in ("doctor", "validate"):
        json_code, payload, text_code, _text = run_both(command, plain, tmp_path, fake_which)
        res = payload["resolution"]
        assert res["boundary"] == "non-git"
        assert res["status"] == "fail"
        assert res["repository_root"] is None
        assert res["common_dir"] is None
        assert res["marker_path"] is None
        assert json_code == 1 and text_code == 1
        if command == "validate":
            assert any(f["code"] == "repo.resolution" for f in payload["findings"])


def test_external_symlink_fails(tmp_path: Path, home: Path, fake_which: Callable[[], None]) -> None:
    root = init_repo(tmp_path / "repo")
    plant_install_marker(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "escape"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation needs privileges on Windows")
    for command in ("doctor", "validate"):
        json_code, payload, text_code, _text = run_both(command, link, tmp_path, fake_which)
        res = payload["resolution"]
        assert res["boundary"] == "external-symlink"
        assert res["status"] == "fail"
        assert res["repository_root"] is None
        assert json_code == 1 and text_code == 1


def test_ambiguous_multi_root_fails(
    tmp_path: Path, home: Path, fake_which: Callable[[], None]
) -> None:
    parent = tmp_path / "multi"
    parent.mkdir()
    init_repo(parent / "a")
    init_repo(parent / "b")
    for command in ("doctor", "validate"):
        json_code, payload, text_code, _text = run_both(command, parent, tmp_path, fake_which)
        res = payload["resolution"]
        assert res["boundary"] == "ambiguous-multi-root"
        assert res["status"] == "fail"
        assert res["repository_root"] is None
        assert json_code == 1 and text_code == 1
        assert (parent / "a" / ".cursorfleet").exists() is False
        assert (parent / "b" / ".cursorfleet").exists() is False
