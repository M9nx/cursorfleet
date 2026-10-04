"""Privacy: forbidden content must never reach any rendered screen. No network either."""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

import pytest

from cursorfleet.cli.commands import tui as tui_cmd
from cursorfleet.state.spool import encode_line, writer_file
from cursorfleet.tui import app as app_mod
from cursorfleet.tui import data as data_mod
from m2_helpers import doc_payload, dump, make_event, paths_of, run_hook
from tui_helpers import (
    SECRET,
    build_fleet,
    make_app,
    new_repo,
    screen_text,
    settle,
    write_artifact,
)

VIEW_KEYS = ["o", "l", "w", "g", "e", "v"]
FORBIDDEN_KEYS = {
    "prompt": SECRET,
    "thinking": SECRET,
    "response_text": SECRET,
    "file_content": SECRET,
    "output": SECRET,
    "tool_output": SECRET,
    "user_email": f"{SECRET}@example.test",
    "transcript_path": f"/home/x/{SECRET}.jsonl",
    "env": {"TOKEN": SECRET},
}


def hostile_hook_payloads(repo: Path) -> list[dict[str, Any]]:
    """Real hook payloads whose forbidden fields all carry the canary."""
    out: list[dict[str, Any]] = []
    for hook in (
        "sessionStart",
        "preToolUse",
        "postToolUse",
        "beforeShellExecution",
        "afterShellExecution",
        "afterFileEdit",
        "subagentStart",
        "subagentStop",
        "preCompact",
        "stop",
    ):
        payload = doc_payload(hook)
        payload["workspace_roots"] = [str(repo)]
        payload["conversation_id"] = "hostile-session"
        payload.update(FORBIDDEN_KEYS)
        payload["user_email"] = f"{SECRET}@example.test"
        payload["tool_output"] = f"{SECRET} " * 5
        if hook in {"beforeShellExecution", "afterShellExecution"}:
            payload["command"] = f"API_TOKEN={SECRET} ./build.sh --password {SECRET}"
        elif "tool_input" in payload or hook in {"preToolUse", "postToolUse"}:
            payload["tool_input"] = {
                "command": f"API_TOKEN={SECRET} ./build.sh",
                "contents": SECRET,
                "working_directory": str(repo),
            }
        out.append(payload)
    return out


def seed_hostile_state(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    build_fleet(repo)
    monkeypatch.chdir(repo)
    for payload in hostile_hook_payloads(repo):
        run_hook(payload)
    # Raw spool lines that carry forbidden extra keys: the closed event model must reject them.
    paths = paths_of(repo)
    target = Path(writer_file(paths, "s-raw", "w9"))
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("ab") as handle:
        for n, key in enumerate(("prompt", "thinking", "file_content", "output"), start=900):
            handle.write(encode_line(dump(make_event("s-raw", n, **{key: SECRET}))))
        handle.write(encode_line(dump(make_event("s-raw", 950, command_display=f"x {SECRET}"))))
    # Artifacts: secrets in the body, in forbidden frontmatter keys and in an invalid role.
    base = repo / ".cursorfleet" / "work" / "t-priv"
    base.mkdir(parents=True)
    (base / "01-handoff-implementer.md").write_text(
        "---\nschema: cursorfleet.artifact/1\nkind: handoff.created\ntask: t-priv\n"
        "author_role: implementer\ncreated: 2026-10-04T12:04:30Z\n"
        f"to_role: reviewer\nprompt: {SECRET}\nsummary: {SECRET}\n---\n{SECRET}\n",
        encoding="utf-8",
    )
    (base / "02-plan-architect.md").write_text(
        "---\nschema: cursorfleet.artifact/1\nkind: plan.created\ntask: t-priv\n"
        f"author_role: {SECRET} !!\ncreated: 2026-10-04T12:04:31Z\n---\n{SECRET}\n",
        encoding="utf-8",
    )
    write_artifact(repo, "t-ok", "01-blocker-implementer.md", "blocker.raised", "implementer")
    (repo / ".cursorfleet" / "work" / "t-ok" / "01-blocker-implementer.md").write_text(
        "---\nschema: cursorfleet.artifact/1\nkind: blocker.raised\ntask: t-ok\n"
        f"author_role: implementer\ncreated: 2026-10-04T12:04:30Z\n---\n{SECRET}\n",
        encoding="utf-8",
    )


async def collect_everything(app: Any, pilot: Any) -> str:
    """All text reachable from every view, every row detail, tiles and help."""
    chunks: list[str] = []
    for key in VIEW_KEYS:
        await pilot.press(key)
        await settle(app, pilot)
        chunks.append(app.rendered_text())
        chunks.append(screen_text(app))
        for _ in range(len(app.row_keys()) + 1):
            chunks.append(app.rendered_text())
            await pilot.press("j")
            await settle(app, pilot)
        chunks.append(app.export_screenshot())
    await pilot.press("question_mark")
    await settle(app, pilot)
    chunks.append(screen_text(app))
    await pilot.press("escape")
    return "\n".join(chunks)


async def test_secrets_in_forbidden_places_never_render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = new_repo(tmp_path)
    seed_hostile_state(repo, monkeypatch)
    app = make_app(repo)
    async with app.run_test(size=(170, 50)) as pilot:
        await settle(app, pilot)
        await pilot.press("t")
        await settle(app, pilot)
        assert app.layout_mode == "tiled"
        everything = await collect_everything(app, pilot)
        # the seeded data really was ingested, so the assertion below is not vacuous
        assert "hostile-session" in everything or "tool.completed" in everything
        assert "t-priv" in everything and "invalid artifact" in everything.lower()
    assert SECRET not in everything
    assert "SYNTH-SECRET" not in everything
    assert f"{SECRET}@example.test" not in everything
    assert ".jsonl" not in everything.replace("jsonl)", "")  # no transcript path leaks


async def test_secrets_are_absent_from_the_projection_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = new_repo(tmp_path)
    seed_hostile_state(repo, monkeypatch)
    app = make_app(repo)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)
    db = Path(paths_of(repo).db)
    assert db.exists()
    for candidate in db.parent.glob(db.name + "*"):
        assert SECRET.encode() not in candidate.read_bytes()


async def test_markup_in_data_renders_verbatim_and_cannot_crash(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    fleet = build_fleet(repo)
    fleet.add(
        "s-active",
        "tool.started",
        "2026-10-04T12:04:40.000Z",
        tool_name="Shell",
        command={
            "argv0": "echo",
            "display": "echo [bold red]boom[/] [link=http://evil.test]x[/link]",
        },
        risk="low",
    )
    app = make_app(repo)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.press("l")
        await settle(app, pilot)
        text = app.rendered_text()
        assert "echo [bold red]boom[/]" in text
        assert "echo [bold red]boom[/]" in screen_text(app)
        await pilot.press("o")
        await settle(app, pilot)


async def test_no_network_is_ever_used(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = new_repo(tmp_path)
    build_fleet(repo)

    def refuse(*_a: object, **_k: object) -> None:
        msg = "network access attempted"
        raise AssertionError(msg)

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    app = make_app(repo)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)
        for key in VIEW_KEYS:
            await pilot.press(key)
            await settle(app, pilot)
        await pilot.press("r")
        await settle(app, pilot)
        assert app.last_refresh_error is None


def test_tui_module_imports_no_network_libraries() -> None:
    for mod in (app_mod, data_mod, tui_cmd):
        names = set(vars(mod))
        assert not names & {"requests", "httpx", "urllib", "aiohttp", "socket", "http"}
