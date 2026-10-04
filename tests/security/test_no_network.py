"""SR-10: CursorFleet makes no network calls, anywhere (README, privacy.md).

Three independent checks: no module in the package imports a networking library, a
runtime guard turns any socket connection or DNS lookup into a failure while the whole CLI
and the TUI run, and every git subcommand the collector uses is local-only.
"""

from __future__ import annotations

import ast
import socket
from pathlib import Path
from typing import Any, NoReturn

import pytest
from typer.testing import CliRunner

from cursorfleet.cli.main import app as cli_app
from m2_helpers import doc_payload, paths_of, run_hook
from tui_helpers import build_fleet, make_app, new_repo, settle

SRC = Path(__file__).resolve().parents[2] / "src" / "cursorfleet"
# asyncio is deliberately absent: the TUI only uses asyncio.to_thread (no sockets of its own).
NETWORK_MODULES = frozenset(
    {
        "socket",
        "ssl",
        "http",
        "urllib",
        "urllib3",
        "ftplib",
        "smtplib",
        "poplib",
        "imaplib",
        "telnetlib",
        "xmlrpc",
        "requests",
        "httpx",
        "aiohttp",
        "websockets",
        "websocket",
        "paramiko",
        "grpc",
        "socketserver",
    }
)
runner = CliRunner()


def imported_roots(path: Path) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_no_module_imports_a_networking_library() -> None:
    offenders = {
        str(path.relative_to(SRC)): sorted(imported_roots(path) & NETWORK_MODULES)
        for path in SRC.rglob("*.py")
        if imported_roots(path) & NETWORK_MODULES
    }
    assert offenders == {}


def test_declared_dependencies_contain_no_http_client() -> None:
    text = (SRC.parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    block = text.split("dependencies = [", 1)[1].split("]", 1)[0]
    for client in ("requests", "httpx", "aiohttp", "urllib3", "websockets"):
        assert client not in block


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    attempts: list[str] = []

    def guard(name: str) -> Any:
        def blocked(*_args: object, **_kwargs: object) -> NoReturn:
            attempts.append(name)
            msg = f"network access attempted: {name}"
            raise AssertionError(msg)

        return blocked

    monkeypatch.setattr(socket.socket, "connect", guard("socket.connect"))
    monkeypatch.setattr(socket.socket, "connect_ex", guard("socket.connect_ex"))
    monkeypatch.setattr(socket.socket, "sendto", guard("socket.sendto"))
    monkeypatch.setattr(socket, "create_connection", guard("socket.create_connection"))
    monkeypatch.setattr(socket, "getaddrinfo", guard("socket.getaddrinfo"))
    monkeypatch.setattr(socket, "gethostbyname", guard("socket.gethostbyname"))
    return attempts


def test_every_cli_command_and_the_hook_run_without_network(
    tmp_path: Path, no_network: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = new_repo(tmp_path)
    monkeypatch.chdir(repo)
    fleet = build_fleet(repo)
    r = str(repo)
    code, _reply = run_hook({**doc_payload("postToolUse"), "workspace_roots": [r]})
    assert code == 0
    commands = [
        ["init", "--cursor", "--dry-run", "--path", r],
        ["init", "--cursor", "--yes", "--path", r],
        ["doctor", "--path", r, "--no-probe-cursor"],
        ["doctor", "--path", r, "--no-probe-cursor", "--json"],
        ["validate", "--path", r],
        ["index", "--repo", r],
        ["status", "--repo", r],
        ["status", "--json", "--repo", r],
        ["replay", "s-active", "--repo", r],
        ["events", "export", "--sanitized", "--repo", r],
        ["events", "purge", "--dry-run", "--repo", r],
        ["uninstall", "--yes", "--path", r],
    ]
    for argv in commands:
        result = runner.invoke(cli_app, argv)
        assert result.exception is None or isinstance(result.exception, SystemExit), argv
    assert fleet.paths.root == paths_of(repo).root
    assert no_network == []


async def test_the_tui_runs_without_network(tmp_path: Path, no_network: list[str]) -> None:
    repo = new_repo(tmp_path)
    build_fleet(repo)
    tui = make_app(repo)
    async with tui.run_test(size=(140, 40)) as pilot:
        await settle(tui, pilot)
        for key in ("l", "w", "g", "e", "v", "o", "r"):
            await pilot.press(key)
            await settle(tui, pilot)
    assert no_network == []


def test_git_subcommands_are_local_and_read_only() -> None:
    """The collector may only run these git verbs; none of them contacts a remote."""
    allowed = {"rev-parse", "worktree", "status", "rev-list", "log"}
    used: set[str] = set()
    for path in (SRC / "git").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") in {
                "run_git",
                "_safe_run",
            }:
                first = node.args[0] if node.args else None
                if isinstance(first, ast.List) and first.elts:
                    head = first.elts[0]
                    if isinstance(head, ast.Constant) and isinstance(head.value, str):
                        used.add(head.value)
    assert used, "no git calls found: the scan is broken"
    assert used <= allowed, f"unexpected git verbs: {sorted(used - allowed)}"
    assert not used & {"fetch", "pull", "push", "clone", "ls-remote", "remote", "submodule"}
