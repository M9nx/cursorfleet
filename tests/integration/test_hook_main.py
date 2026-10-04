"""End-to-end tests of the hook entrypoint against real temp git repos (in-process)."""

from __future__ import annotations

import io
import json
import os
import stat
from pathlib import Path
from typing import Any

import pytest

from cursorfleet.adapters.cursor import hook_main
from cursorfleet.adapters.cursor.hook_policy import (
    ALLOWED_V01_HOOKS,
    FORBIDDEN_HOOKS,
    PERMISSION_HOOKS,
    fail_open_response,
)
from cursorfleet.events.ids import worktree_id_for
from cursorfleet.events.models import Event
from m2_helpers import (
    ALL_HOOKS,
    FIXED_NS,
    doc_payload,
    git,
    paths_of,
    run_hook,
    spool_bytes,
    spool_events,
    spool_files,
)

ALLOW = '{"permission":"allow"}'


def payload_for(hook: str, repo_root: Path) -> dict[str, Any]:
    payload = doc_payload(hook)
    payload["workspace_roots"] = [str(repo_root)]
    for key in ("file_path", "cwd"):
        if isinstance(payload.get(key), str):
            payload[key] = payload[key].replace("/project", str(repo_root))
    return payload


@pytest.mark.parametrize("hook", ALL_HOOKS)
def test_reply_is_correct_and_exit_is_zero(hook: str, repo: Path) -> None:
    code, out = run_hook(payload_for(hook, repo))
    assert code == 0
    assert out == (ALLOW if hook in PERMISSION_HOOKS else "{}")
    assert out == fail_open_response(hook)


@pytest.mark.parametrize("hook", ALL_HOOKS)
def test_events_are_written_and_valid(hook: str, repo: Path) -> None:
    run_hook(payload_for(hook, repo))
    events = spool_events(repo)
    assert events, hook
    for raw in events:
        event = Event.model_validate(raw)
        assert event.session_id == "doc-example-conversation"


def test_full_session_roundtrip_through_all_hooks(repo: Path) -> None:
    for index, hook in enumerate(ALL_HOOKS):
        run_hook(payload_for(hook, repo), now_ns=FIXED_NS + index * 10_000_000)
    kinds = {e["kind"] for e in spool_events(repo)}
    assert {"session.started", "session.stopped", "tool.started", "tool.completed"} <= kinds
    assert {"subagent.started", "subagent.stopped", "file.changed", "context.compacted"} <= kinds


@pytest.mark.parametrize(
    "garbage",
    [b"", b"   ", b"not json", b"[1,2,3]", b'"str"', b"\xff\xfe\x00bin", b"{" * 5000, b"null"],
)
def test_garbage_stdin_fails_open_and_records_nothing(garbage: bytes, repo: Path) -> None:
    for argv in (["cursorfleet-hook"], ["cursorfleet-hook", "preToolUse"]):
        code, out = run_hook(garbage, argv=argv)
        assert code == 0
        assert out in {"{}", ALLOW}
    assert spool_files(repo) == []


def test_hint_argument_selects_permission_reply_when_payload_is_unreadable(repo: Path) -> None:
    assert run_hook(b"junk", argv=["x", "preToolUse"]) == (0, ALLOW)
    assert run_hook(b"junk", argv=["x", "stop"]) == (0, "{}")
    assert run_hook(b"junk", argv=["x", "../../etc"]) == (0, ALLOW)  # unknown => allow-shaped


def test_oversized_stdin_is_dropped_but_drained(repo: Path) -> None:
    big = b'{"hook_event_name":"stop","x":"' + b"a" * (hook_main.MAX_STDIN_BYTES + 10) + b'"}'
    code, out = run_hook(big)
    assert (code, out) == (0, ALLOW)  # hook unknown because payload was not parsed
    assert spool_files(repo) == []


@pytest.mark.parametrize("hook", sorted(FORBIDDEN_HOOKS))
def test_forbidden_hooks_record_nothing(hook: str, repo: Path) -> None:
    payload = {"hook_event_name": hook, "conversation_id": "c1", "prompt": "SECRET PROMPT"}
    code, out = run_hook(payload)
    assert code == 0
    assert out in {"{}", ALLOW}
    assert spool_files(repo) == []


def test_unregistered_and_unknown_hooks_record_nothing(repo: Path) -> None:
    for name in ("beforeMCPExecution", "afterMCPExecution", "totallyNew", "", 5):
        code, out = run_hook({"hook_event_name": name, "conversation_id": "c1"})
        assert code == 0 and out in {"{}", ALLOW}
    assert spool_files(repo) == []
    # PROVISIONAL: a named-but-unknown hook gets "{}", a nameless one the allow shape.
    assert run_hook({"hook_event_name": "totallyNew"})[1] == "{}"
    assert run_hook({"no": "name"})[1] == ALLOW


def test_not_a_git_repo_records_nothing(outside_git: Path, tmp_path: Path) -> None:
    payload = doc_payload("sessionStart")
    payload["workspace_roots"] = [str(outside_git)]
    code, out = run_hook(payload)
    assert (code, out) == (0, "{}")
    assert not any(tmp_path.rglob("cursorfleet"))


def test_internal_errors_fail_open(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: object, **_k: object) -> int:
        raise RuntimeError("boom")

    monkeypatch.setattr(hook_main, "record", boom)
    assert run_hook(payload_for("preToolUse", repo)) == (0, ALLOW)
    assert run_hook(payload_for("stop", repo)) == (0, "{}")


def test_clock_failure_still_fails_open(repo: Path) -> None:
    def bad_clock() -> int:
        raise OSError("no clock")

    out = io.StringIO()
    code = hook_main.main(
        ["x"],
        stdin=io.BytesIO(b"{}"),
        stdout=out,
        environ={},
        clock_ns=bad_clock,
    )
    assert code == 0 and out.getvalue().strip() == ALLOW


def test_read_only_runtime_dir_fails_open(repo: Path) -> None:
    if os.name == "nt" or os.geteuid() == 0:
        pytest.skip("needs POSIX permissions and a non-root user")
    run_hook(payload_for("sessionStart", repo))
    root = Path(paths_of(repo).root)
    os.chmod(root, 0o500)
    try:
        code, out = run_hook(payload_for("stop", repo))
    finally:
        os.chmod(root, 0o700)
    assert (code, out) == (0, "{}")


def test_commands_are_reduced_and_redacted(repo: Path) -> None:
    payload = payload_for("preToolUse", repo)
    payload["tool_input"] = {
        "command": "curl -H 'Authorization: Bearer tok_ABCDEF1234567890' x.test"
    }
    run_hook(payload)
    (event,) = spool_events(repo)
    assert event["command"]["argv0"] == "curl"
    assert "tok_ABCDEF" not in json.dumps(event)
    assert len(event["command"]["command_hash"]) == 32


def test_shell_hooks_carry_the_hook_name(repo: Path) -> None:
    run_hook(payload_for("beforeShellExecution", repo))
    run_hook(payload_for("afterShellExecution", repo))
    hooks = sorted({e["hook"] for e in spool_events(repo)})
    assert hooks == ["afterShellExecution", "beforeShellExecution"]


def test_paths_in_events_are_relative(repo: Path) -> None:
    run_hook(payload_for("afterFileEdit", repo))
    (event,) = spool_events(repo)
    assert event["paths"] == [{"path": "src/auth.ts", "op": "unknown"}]
    assert str(repo) not in spool_bytes(repo).decode()


def test_branch_and_commit_come_from_head(repo: Path) -> None:
    sha = git(["rev-parse", "HEAD"], repo).strip()
    run_hook(payload_for("sessionStart", repo))
    (event,) = spool_events(repo)
    assert event["commit"] == sha
    assert event["branch"] == git(["symbolic-ref", "--short", "HEAD"], repo).strip()


def test_detached_head_has_commit_but_no_branch(repo: Path) -> None:
    sha = git(["rev-parse", "HEAD"], repo).strip()
    git(["checkout", "-q", "--detach"], repo)
    run_hook(payload_for("sessionStart", repo))
    (event,) = spool_events(repo)
    assert event["commit"] == sha and "branch" not in event


def test_runtime_lives_in_git_common_dir_not_the_working_tree(repo: Path) -> None:
    run_hook(payload_for("sessionStart", repo))
    assert (repo / ".git" / "cursorfleet" / "spool").is_dir()
    assert not (repo / "cursorfleet").exists() and not (repo / ".cursorfleet").exists()
    status = git(["status", "--porcelain", "--untracked-files=all"], repo)
    assert status.strip() == ""  # nothing appeared in the working tree


def test_linked_worktree_shares_the_main_spool(repo: Path, tmp_path: Path) -> None:
    linked = tmp_path / "wt-feature"
    git(["worktree", "add", "-q", "-b", "feature", str(linked)], repo)
    linked = linked.resolve()
    os.chdir(linked)
    payload = payload_for("sessionStart", linked)
    run_hook(payload)
    (event,) = spool_events(repo)
    assert event["branch"] == "feature"
    assert event["worktree_id"] == worktree_id_for(str(linked))
    assert (repo / ".git" / "cursorfleet" / "spool").is_dir()
    assert not (linked / ".git" / "cursorfleet").exists()


def test_posix_permissions_are_private(repo: Path) -> None:
    if os.name == "nt":
        pytest.skip("POSIX permission bits")
    run_hook(payload_for("preToolUse", repo))
    paths = paths_of(repo)
    for directory in (paths.root, paths.spool):
        assert stat.S_IMODE(os.stat(directory).st_mode) == 0o700
    for sub, _dirs, files in os.walk(paths.spool):
        assert stat.S_IMODE(os.stat(sub).st_mode) == 0o700
        for name in files:
            assert stat.S_IMODE(os.stat(os.path.join(sub, name)).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(paths.hmac_key).st_mode) == 0o600


def test_privacy_config_can_disable_display_and_hash(repo: Path) -> None:
    cfg = repo / ".cursorfleet"
    cfg.mkdir()
    (cfg / "config.toml").write_text(
        "[privacy]\nstore_command_display = false\nhash_commands = false\n", encoding="utf-8"
    )
    run_hook(payload_for("preToolUse", repo))
    (event,) = spool_events(repo)
    assert set(event["command"]) <= {"argv0", "subcommand"}


def test_broken_privacy_config_fails_toward_less_storage(repo: Path) -> None:
    cfg = repo / ".cursorfleet"
    cfg.mkdir()
    (cfg / "config.toml").write_text("[privacy\nstore = = =", encoding="utf-8")
    run_hook(payload_for("preToolUse", repo))
    (event,) = spool_events(repo)
    assert "display" not in event["command"]


def test_capped_marker_stops_recording(repo: Path) -> None:
    run_hook(payload_for("preToolUse", repo))
    before = spool_bytes(repo)
    (Path(spool_files(repo)[0]).parent / ".capped").write_text("", encoding="utf-8")
    run_hook(payload_for("preToolUse", repo), now_ns=FIXED_NS + 10**10)
    assert spool_bytes(repo) == before


def test_allowed_hook_set_is_what_the_contract_says() -> None:
    assert "beforeSubmitPrompt" not in ALLOWED_V01_HOOKS
    for hook in ("afterAgentThought", "afterAgentResponse", "beforeReadFile"):
        assert hook in FORBIDDEN_HOOKS and hook not in ALLOWED_V01_HOOKS
