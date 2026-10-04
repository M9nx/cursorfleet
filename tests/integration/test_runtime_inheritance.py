"""Runtime inheritance for nested non-Git directories (ADR 0002 task 16)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from cursorfleet.adapters.cursor.hook_policy import PERMISSION_HOOKS
from cursorfleet.cli.main import app
from cursorfleet.state.runtime import has_install_marker
from kit_helpers import snapshot
from m2_helpers import (
    doc_payload,
    git,
    init_repo,
    plant_install_marker,
    run_hook,
    spool_events,
    spool_files,
)

ALLOW = '{"permission":"allow"}'
runner = CliRunner()


def hook_payload(
    hook: str,
    cwd: Path,
    *,
    workspace_roots: list[str] | None = None,
    file_path: Path | None = None,
) -> dict[str, Any]:
    payload = doc_payload(hook)
    payload["cwd"] = str(cwd)
    payload["workspace_roots"] = workspace_roots if workspace_roots is not None else [str(cwd)]
    if file_path is not None:
        payload["file_path"] = str(file_path)
    elif isinstance(payload.get("file_path"), str):
        payload["file_path"] = str(cwd / "src" / "auth.ts")
    return payload


def fleet_rels(base: Path) -> set[str]:
    found: set[str] = set()
    if not base.exists():
        return found
    for item in base.rglob("*"):
        if any(part in {".cursorfleet", "cursorfleet"} for part in item.relative_to(base).parts):
            found.add(item.relative_to(base).as_posix())
    return found


def assert_fail_open(code: int, out: str, hook: str) -> None:
    assert code == 0
    expected = ALLOW if hook in PERMISSION_HOOKS else "{}"
    assert out == expected


def assert_no_new_fleet_writes(before: set[str], after: set[str]) -> None:
    assert after == before


@pytest.mark.parametrize("hook", ["sessionStart", "preToolUse"])
def test_initialized_root_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hook: str
) -> None:
    root = init_repo(tmp_path / "repo")
    plant_install_marker(root)
    monkeypatch.chdir(root)
    code, out = run_hook(hook_payload(hook, root))
    assert_fail_open(code, out, hook)
    assert spool_events(root)
    assert (root / ".git" / "cursorfleet" / "spool").is_dir()
    assert {p.name for p in (root / ".cursorfleet").iterdir()} == {"config.toml"}


def test_ordinary_descendant_inherits_enclosing_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = init_repo(tmp_path / "repo")
    plant_install_marker(root)
    nested = root / "src" / "pkg"
    nested.mkdir(parents=True)
    target = nested / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.chdir(nested)
    before_nested = fleet_rels(nested)
    code, out = run_hook(
        hook_payload("afterFileEdit", nested, file_path=target, workspace_roots=[str(nested)])
    )
    assert_fail_open(code, out, "afterFileEdit")
    events = spool_events(root)
    assert events
    assert events[0]["paths"] == [{"path": "src/pkg/mod.py", "op": "unknown"}]
    assert str(root) not in str(events[0]["paths"])
    assert (root / ".git" / "cursorfleet" / "spool").is_dir()
    assert not (nested / ".cursorfleet").exists()
    assert not (nested / ".git").exists()
    assert fleet_rels(nested) == before_nested


def test_missing_marker_records_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = init_repo(tmp_path / "repo")
    nested = root / "src"
    nested.mkdir()
    monkeypatch.chdir(nested)
    before = fleet_rels(tmp_path)
    code, out = run_hook(hook_payload("preToolUse", nested))
    assert_fail_open(code, out, "preToolUse")
    assert_no_new_fleet_writes(before, fleet_rels(tmp_path))
    assert spool_files(root) == []
    assert not (root / ".git" / "cursorfleet").exists()
    assert not (root / ".cursorfleet").exists()
    assert not has_install_marker(str(root))


def test_initialized_nested_repository_uses_inner_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outer = init_repo(tmp_path / "outer")
    plant_install_marker(outer)
    inner = init_repo(outer / "vendor" / "lib")
    plant_install_marker(inner)
    monkeypatch.chdir(inner)
    code, out = run_hook(hook_payload("sessionStart", inner))
    assert_fail_open(code, out, "sessionStart")
    assert spool_events(inner)
    assert spool_files(outer) == []
    assert not (outer / ".git" / "cursorfleet").exists()
    assert (inner / ".git" / "cursorfleet" / "spool").is_dir()


def test_uninitialized_nested_repository_does_not_fall_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outer = init_repo(tmp_path / "outer")
    plant_install_marker(outer)
    inner = init_repo(outer / "vendor" / "lib")
    nested = inner / "src"
    nested.mkdir()
    monkeypatch.chdir(nested)
    before = fleet_rels(tmp_path)
    code, out = run_hook(hook_payload("preToolUse", nested))
    assert_fail_open(code, out, "preToolUse")
    assert_no_new_fleet_writes(before, fleet_rels(tmp_path))
    assert spool_files(outer) == []
    assert spool_files(inner) == []
    assert not (outer / ".git" / "cursorfleet").exists()
    assert not (inner / ".git" / "cursorfleet").exists()
    assert not (nested / ".cursorfleet").exists()


def test_submodule_is_its_own_boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outer = init_repo(tmp_path / "outer")
    plant_install_marker(outer)
    lib = init_repo(tmp_path / "lib")
    git(
        ["-c", "protocol.file.allow=always", "submodule", "add", "-q", str(lib), "vendor/lib"],
        outer,
    )
    inner = (outer / "vendor" / "lib").resolve()
    monkeypatch.chdir(inner)
    before = fleet_rels(tmp_path)
    code, out = run_hook(hook_payload("sessionStart", inner))
    assert_fail_open(code, out, "sessionStart")
    assert_no_new_fleet_writes(before, fleet_rels(tmp_path))
    assert spool_files(outer) == []
    assert not (outer / ".git" / "cursorfleet").exists()
    assert not (inner / ".cursorfleet").exists()


def test_gitfile_boundary_does_not_inherit_outer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outer = init_repo(tmp_path / "outer")
    plant_install_marker(outer)
    other = init_repo(tmp_path / "other")
    nested = outer / "nested-gitfile"
    nested.mkdir()
    (nested / ".git").write_text(f"gitdir: {other / '.git'}\n", encoding="utf-8")
    monkeypatch.chdir(nested)
    before = fleet_rels(tmp_path)
    code, out = run_hook(hook_payload("preToolUse", nested))
    assert_fail_open(code, out, "preToolUse")
    assert_no_new_fleet_writes(before, fleet_rels(tmp_path))
    assert spool_files(outer) == []
    assert spool_files(other) == []
    assert not (nested / ".cursorfleet").exists()


def test_external_symlink_records_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = init_repo(tmp_path / "repo")
    plant_install_marker(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "escape"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    monkeypatch.chdir(root)
    before = fleet_rels(tmp_path)
    code, out = run_hook(hook_payload("preToolUse", link))
    assert_fail_open(code, out, "preToolUse")
    assert_no_new_fleet_writes(before, fleet_rels(tmp_path))
    assert spool_files(root) == []
    assert not (outside / ".cursorfleet").exists()
    assert not (outside / "cursorfleet").exists()
    assert not (root / ".git" / "cursorfleet").exists()


def test_ambiguous_multi_root_records_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = init_repo(tmp_path / "repo")
    other = init_repo(tmp_path / "other")
    plant_install_marker(root)
    plant_install_marker(other)
    monkeypatch.chdir(root)
    before = fleet_rels(tmp_path)
    payload = hook_payload("preToolUse", root, workspace_roots=[str(root), str(other)])
    code, out = run_hook(payload)
    assert_fail_open(code, out, "preToolUse")
    assert_no_new_fleet_writes(before, fleet_rels(tmp_path))
    assert spool_files(root) == []
    assert spool_files(other) == []


def test_non_git_workspace_records_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.chdir(plain)
    before = fleet_rels(tmp_path)
    code, out = run_hook(hook_payload("preToolUse", plain))
    assert_fail_open(code, out, "preToolUse")
    assert_no_new_fleet_writes(before, fleet_rels(tmp_path))
    assert not any(tmp_path.rglob("cursorfleet"))
    assert not (plain / ".cursorfleet").exists()


def test_cursor_project_dir_inherits_when_cwd_unusable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = init_repo(tmp_path / "repo")
    plant_install_marker(root)
    nested = root / "docs"
    nested.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    def boom() -> str:
        raise OSError("no cwd")

    monkeypatch.setattr(os, "getcwd", boom)
    payload = doc_payload("sessionStart")
    payload.pop("cwd", None)
    payload["workspace_roots"] = [str(elsewhere)]
    code, out = run_hook(payload, environ={"CURSOR_PROJECT_DIR": str(nested)})
    assert_fail_open(code, out, "sessionStart")
    assert spool_events(root)
    assert not (nested / ".cursorfleet").exists()
    assert not (elsewhere / ".cursorfleet").exists()


def test_symlink_marker_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = init_repo(tmp_path / "repo")
    cfg = root / ".cursorfleet"
    cfg.mkdir()
    real = tmp_path / "elsewhere.toml"
    real.write_text("# planted\n", encoding="utf-8")
    try:
        os.symlink(real, cfg / "config.toml")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    assert not has_install_marker(str(root))
    monkeypatch.chdir(root)
    before = fleet_rels(tmp_path)
    code, out = run_hook(hook_payload("preToolUse", root))
    assert_fail_open(code, out, "preToolUse")
    assert_no_new_fleet_writes(before, fleet_rels(tmp_path))
    assert not (root / ".git" / "cursorfleet").exists()


def test_init_from_subdirectory_exits_2_hook_still_inherits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = init_repo(tmp_path / "repo")
    plant_install_marker(root)
    nested = root / "src"
    nested.mkdir()
    before_tree = snapshot(root)
    result = runner.invoke(app, ["init", "--cursor", "--yes", "--path", str(nested)])
    assert result.exit_code == 2
    assert "Nothing was changed" in result.output
    assert snapshot(root) == before_tree
    monkeypatch.chdir(nested)
    code, out = run_hook(hook_payload("sessionStart", nested))
    assert_fail_open(code, out, "sessionStart")
    assert spool_events(root)
    assert not (nested / ".cursorfleet").exists()


def test_init_in_non_git_directory_exits_2_without_writes(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    before = snapshot(plain)
    result = runner.invoke(app, ["init", "--cursor", "--yes", "--path", str(plain)])
    assert result.exit_code == 2
    assert "Git is required" in result.output
    assert "Nothing was changed" in result.output
    assert snapshot(plain) == before
    assert fleet_rels(plain) == set()
