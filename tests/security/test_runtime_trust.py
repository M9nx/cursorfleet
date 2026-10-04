"""SR-02: the runtime directory is only used when it is private to the current user.

A shared repository (group-writable ``.git``) would otherwise let another account pre-create
``.git/cursorfleet`` with symlinks, a forged spool or a planted database.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cursorfleet.cli.main import app
from cursorfleet.state.indexer import Indexer, UntrustedRuntime
from cursorfleet.state.runtime import untrusted_reason
from cursorfleet.state.spool import append_event, writer_file
from cursorfleet.state.spool_read import list_spool_files
from m2_helpers import doc_payload, dump, make_event, paths_of, run_hook

POSIX_ONLY = pytest.mark.skipif(os.name != "posix", reason="owner and group/other write bits")


def test_missing_and_private_directories_are_trusted(tmp_path: Path) -> None:
    assert untrusted_reason(str(tmp_path / "absent")) is None
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    assert untrusted_reason(str(private)) is None


@POSIX_ONLY
def test_group_writable_and_world_writable_roots_are_refused(tmp_path: Path) -> None:
    root = tmp_path / "shared"
    root.mkdir()
    root.chmod(0o770)
    assert "writable" in str(untrusted_reason(str(root)))
    root.chmod(0o707)
    assert "writable" in str(untrusted_reason(str(root)))


def test_symlinked_root_is_refused(tmp_path: Path) -> None:
    target = tmp_path / "elsewhere"
    target.mkdir(mode=0o700)
    link = tmp_path / "cursorfleet"
    try:
        os.symlink(target, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not permitted here (Windows without privileges)")
    assert untrusted_reason(str(link)) == "is a symbolic link"


def test_root_that_is_a_file_is_refused(tmp_path: Path) -> None:
    file = tmp_path / "cursorfleet"
    file.write_text("x", encoding="utf-8")
    assert untrusted_reason(str(file)) == "is not a directory"


@POSIX_ONLY
def test_hook_never_writes_into_an_untrusted_runtime_dir(repo: Path) -> None:
    paths = paths_of(repo)
    os.makedirs(paths.root, mode=0o700)
    os.chmod(paths.root, 0o777)  # noqa: S103 - the hostile state under test
    code, reply = run_hook({**doc_payload("preToolUse"), "workspace_roots": [str(repo)]})
    assert code == 0 and reply == '{"permission":"allow"}'  # still fails open
    assert os.listdir(paths.root) == []  # no spool, no key, nothing created


@POSIX_ONLY
def test_hook_does_not_follow_a_symlinked_runtime_root(repo: Path, tmp_path: Path) -> None:
    paths = paths_of(repo)
    decoy = tmp_path / "decoy"
    decoy.mkdir(mode=0o700)
    os.symlink(decoy, paths.root, target_is_directory=True)
    code, _reply = run_hook({**doc_payload("preToolUse"), "workspace_roots": [str(repo)]})
    assert code == 0
    assert list(decoy.iterdir()) == []


@POSIX_ONLY
def test_readers_and_indexer_ignore_an_untrusted_runtime_dir(repo: Path) -> None:
    paths = paths_of(repo)
    event = make_event("s1", 1, kind="session.started")
    assert append_event(paths, "s1", "main", dump(event), now_ms=1)
    assert list_spool_files(paths)
    assert Indexer(paths).sync().events_new == 1
    os.chmod(paths.root, 0o770)  # noqa: S103 - the hostile state under test
    assert list_spool_files(paths) == []
    assert Indexer(paths).load_sessions() == {}
    with pytest.raises(UntrustedRuntime):
        Indexer(paths).sync()
    assert Indexer(paths).try_sync() is None
    assert not append_event(paths, "s1", "main", dump(make_event("s1", 2)), now_ms=2)
    assert os.path.isfile(writer_file(paths, "s1", "main"))  # existing data was left alone


@POSIX_ONLY
def test_cli_reports_an_untrusted_runtime_dir_without_a_traceback(repo: Path) -> None:
    paths = paths_of(repo)
    assert append_event(paths, "s1", "main", dump(make_event("s1", 1)), now_ms=1)
    os.chmod(paths.root, 0o770)  # noqa: S103 - the hostile state under test
    runner = CliRunner()
    index = runner.invoke(app, ["index", "--repo", str(repo)])
    assert index.exit_code == 1 and "refusing to index" in index.output
    doctor = runner.invoke(app, ["doctor", "--path", str(repo), "--no-probe-cursor", "--json"])
    assert '"runtime.permissions"' in doctor.output and "writable by group" in doctor.output
    status = runner.invoke(app, ["status", "--json", "--repo", str(repo), "--no-git"])
    assert status.exit_code == 0 and '"sessions": []' in status.output
