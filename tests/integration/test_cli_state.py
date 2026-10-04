"""CLI-level tests: status (golden JSON), replay, index, events purge/export."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from cursorfleet.cli.main import app
from cursorfleet.events.ids import worktree_id_for
from cursorfleet.state.models import BUDGET_UNKNOWN
from cursorfleet.state.status_doc import json_abs_path
from m2_helpers import FIXED_NS, doc_payload, git, paths_of, run_hook, spool_files

runner = CliRunner()
GOLDEN = Path(__file__).resolve().parents[1] / "fixtures" / "status" / "status.v1.golden.json"
START = datetime.fromtimestamp(FIXED_NS / 1e9, UTC)
NOW = (START + timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
LATE = (START + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")


def feed(repo: Path, hook: str, step: int, **overrides: Any) -> None:
    payload = doc_payload(hook)
    payload["workspace_roots"] = [str(repo)]
    for key in ("file_path", "cwd"):
        if isinstance(payload.get(key), str):
            payload[key] = payload[key].replace("/project", str(repo))
    payload.update(overrides)
    run_hook(payload, now_ns=FIXED_NS + step * 10_000_000_000)


def populate(repo: Path) -> None:
    """A deterministic session: start, subagent, tools, edit, compaction, stop (no sessionEnd)."""
    feed(repo, "sessionStart", 0)
    feed(repo, "subagentStart", 1)
    feed(repo, "preToolUse", 2)
    feed(repo, "postToolUse", 3)
    feed(repo, "afterFileEdit", 4)
    feed(repo, "preCompact", 5)
    feed(repo, "subagentStop", 6)
    feed(repo, "stop", 7)
    # a second, long-silent session that must show as stale_offline
    feed(repo, "preToolUse", -3600 * 2, conversation_id="old-session")


def invoke(*args: str) -> Any:
    return runner.invoke(app, list(args))


def _path_spellings(path: Path) -> tuple[str, ...]:
    """Native, POSIX, and JSON-escaped forms so Windows golden snapshots stay stable."""
    raw = str(path)
    posix = path.as_posix()
    found = {raw, posix, os.path.normpath(raw), raw.replace("\\", "/"), raw.replace("/", "\\")}
    found.add(raw.replace("\\", "\\\\"))
    found.add(posix.replace("\\", "\\\\"))
    return tuple(spelling for spelling in found if spelling)


def normalize(text: str, repo: Path, extra: Path | None = None) -> str:
    wt = worktree_id_for(str(repo))
    sha = git(["rev-parse", "HEAD"], repo).strip()
    out = text
    for spelling in _path_spellings(repo):
        out = out.replace(spelling, "<REPO>")
    out = out.replace(wt, "<WT>").replace(sha, "<SHA>")
    if extra is not None:
        for spelling in _path_spellings(extra):
            out = out.replace(spelling, "<WT2>")
        out = out.replace(worktree_id_for(str(extra)), "<WT2-ID>")
    return out


# ------------------------------------------------------------------ status


def test_json_abs_path_uses_posix_separators() -> None:
    assert json_abs_path(None) is None
    assert json_abs_path(r"C:\repo\.git\cursorfleet") == "C:/repo/.git/cursorfleet"
    assert "\\" not in (json_abs_path(os.path.join("repo", ".git")) or "")


def test_status_json_matches_the_golden_snapshot(repo: Path, tmp_path: Path) -> None:
    populate(repo)
    extra = tmp_path / "wt-no-telemetry"
    git(["worktree", "add", "-q", "-b", "idle-branch", str(extra)], repo)
    extra = extra.resolve()
    result = invoke("status", "--json", "--repo", str(repo), "--now", NOW)
    assert result.exit_code == 0, result.output
    text = normalize(result.stdout, repo, extra)
    document = json.loads(text)
    # volatile-by-environment values are pinned so the snapshot is stable across machines
    for wt in document["worktrees"]:
        wt["last_commit_ts"] = "<COMMIT-TS>" if wt["last_commit_ts"] else None
    rendered = json.dumps(document, indent=2, sort_keys=False) + "\n"
    if os.environ.get("UPDATE_GOLDEN") == "1":
        GOLDEN.write_text(rendered, encoding="utf-8")
    assert rendered == GOLDEN.read_text("utf-8"), (
        "status JSON changed: if intentional, bump nothing for additive changes "
        "(see docs/status-json.md) and rerun with UPDATE_GOLDEN=1"
    )


def test_status_schema_is_versioned_and_keys_are_stable(repo: Path) -> None:
    populate(repo)
    document = json.loads(invoke("status", "--json", "--repo", str(repo), "--now", NOW).stdout)
    assert document["schema"] == "cursorfleet.status/0.2"
    assert list(document) == [
        "schema",
        "generated_at",
        "repo",
        "telemetry",
        "limits",
        "git",
        "sessions",
        "tasks",
        "worktrees",
        "runs",
    ]
    assert document["runs"]
    assert document["limits"] == {
        "token_budget": "unknown",
        "cloud_agents": "not_visible",
        "enforcement": "none",
    }
    session = document["sessions"][0]
    assert session["token_budget"] == BUDGET_UNKNOWN and "tokens" not in json.dumps(document)
    assert {"elapsed_s", "tool_call_count", "compactions"} <= set(session)


def test_status_without_any_telemetry_is_explicit_about_it(repo: Path) -> None:
    document = json.loads(invoke("status", "--json", "--repo", str(repo), "--now", NOW).stdout)
    assert document["telemetry"]["state"] == "none" and document["sessions"] == []
    assert any("no hook telemetry" in note for note in document["telemetry"]["notes"])
    (wt,) = document["worktrees"]
    assert (wt["telemetry"], wt["lane"], wt["owners"]) == ("none", "unknown", [])
    assert wt["branch"] == "main" and wt["dirty_count"] == 0  # git-only view still works


def test_status_marks_silent_sessions_stale_not_idle(repo: Path) -> None:
    populate(repo)
    document = json.loads(invoke("status", "--json", "--repo", str(repo), "--now", LATE).stdout)
    lanes = {s["session_id"]: s["lane"] for s in document["sessions"]}
    assert lanes["old-session"] == "stale_offline"
    assert "idle" not in json.dumps(lanes)


def test_status_no_git_flag_and_text_output(repo: Path) -> None:
    populate(repo)
    document = json.loads(
        invoke("status", "--json", "--no-git", "--repo", str(repo), "--now", NOW).stdout
    )
    assert document["worktrees"] == [] and document["git"]["available"] is False
    text = invoke("status", "--repo", str(repo), "--now", NOW).stdout
    assert "token budget: unknown" in text and "doc-example-conversation" in text


def test_status_outside_a_repo_fails_cleanly(outside_git: Path) -> None:
    result = invoke("status", "--repo", str(outside_git))
    assert result.exit_code == 1
    assert "Traceback" not in result.output


def test_status_does_not_write_into_the_working_tree(repo: Path) -> None:
    populate(repo)
    invoke("status", "--json", "--repo", str(repo), "--now", NOW)
    assert git(["status", "--porcelain", "--untracked-files=all"], repo).strip() == ""


# ------------------------------------------------------------------ replay / index


def test_replay_is_deterministic_and_reports_counts(repo: Path) -> None:
    populate(repo)
    first = invoke("replay", "doc-example-conversation", "--json", "--repo", str(repo))
    second = invoke("replay", "doc-example-conversation", "--json", "--repo", str(repo))
    assert first.exit_code == 0, first.output
    a, b = json.loads(first.stdout), json.loads(second.stdout)
    assert a == b and a["deterministic"] is True and re.fullmatch(r"[0-9a-f]{64}", a["digest"])
    assert a["events"] >= 8 and a["corruption"]["total"] == 0


def test_replay_digest_survives_a_rebuilt_projection(repo: Path) -> None:
    populate(repo)
    before = json.loads(
        invoke("replay", "doc-example-conversation", "--json", "--repo", str(repo)).stdout
    )
    assert invoke("index", "--rebuild", "--repo", str(repo)).exit_code == 0
    after = json.loads(
        invoke("replay", "doc-example-conversation", "--json", "--repo", str(repo)).stdout
    )
    assert before["digest"] == after["digest"]


def test_replay_unknown_session_exits_one(repo: Path) -> None:
    populate(repo)
    result = invoke("replay", "no-such-session", "--repo", str(repo))
    assert result.exit_code == 1


def test_replay_counts_but_survives_corrupt_lines(repo: Path) -> None:
    populate(repo)
    victim = next(f for f in spool_files(repo) if "doc-example-conversation" in f)
    with open(victim, "ab") as handle:
        handle.write(b"torn partial line without newline")
    with open(victim, "r+b") as handle:
        handle.write(b"ffffffff")  # break the first line's CRC
    result = invoke("replay", "doc-example-conversation", "--json", "--repo", str(repo))
    assert result.exit_code == 0
    report = json.loads(result.stdout)
    assert report["corruption"]["total"] >= 2 and report["deterministic"] is True


def test_index_command_syncs_and_status_reads_the_projection(repo: Path) -> None:
    populate(repo)
    assert not os.path.exists(paths_of(repo).db)
    assert invoke("index", "--repo", str(repo)).exit_code == 0
    assert os.path.exists(paths_of(repo).db)
    document = json.loads(invoke("status", "--json", "--repo", str(repo), "--now", NOW).stdout)
    assert document["telemetry"]["source"] == "projection"


# ------------------------------------------------------------------ events purge / export


def test_export_requires_sanitized_and_revalidates(repo: Path) -> None:
    populate(repo)
    assert invoke("events", "export", "--repo", str(repo)).exit_code == 2
    out = invoke("events", "export", "--sanitized", "--repo", str(repo))
    assert out.exit_code == 0
    lines = [json.loads(line) for line in out.stdout.splitlines() if line.strip()]
    assert len(lines) >= 9
    assert [e["ts"] for e in lines] == sorted(e["ts"] for e in lines)
    for event in lines:
        assert event["schema_version"] == "1.0"
        assert not {"prompt", "user_email", "transcript_path"} & set(event)


def test_export_skips_corrupt_lines_and_writes_files(repo: Path, tmp_path: Path) -> None:
    populate(repo)
    victim = spool_files(repo)[0]
    with open(victim, "ab") as handle:
        handle.write(b"junk\n")
    target = tmp_path / "out.jsonl"
    result = invoke("events", "export", "--sanitized", "-o", str(target), "--repo", str(repo))
    assert result.exit_code == 0 and "skipped 1" in result.output
    assert target.read_text("utf-8").count("\n") >= 9


def test_purge_dry_run_then_session_then_all(repo: Path) -> None:
    populate(repo)
    n_files = len(spool_files(repo))
    dry = invoke("events", "purge", "--all", "--dry-run", "--repo", str(repo))
    assert dry.exit_code == 0 and "would remove" in dry.output
    assert len(spool_files(repo)) == n_files
    refused = invoke("events", "purge", "--all", "--repo", str(repo))  # non-interactive, no --yes
    assert refused.exit_code == 2 and len(spool_files(repo)) == n_files
    one = invoke("events", "purge", "--session", "old-session", "--yes", "--repo", str(repo))
    assert one.exit_code == 0 and len(spool_files(repo)) < n_files
    assert not any("old-session" in f for f in spool_files(repo))
    everything = invoke("events", "purge", "--all", "--yes", "--repo", str(repo))
    assert everything.exit_code == 0 and spool_files(repo) == []
    assert not os.path.exists(paths_of(repo).hmac_key)  # key rotated


def test_purge_older_than_uses_the_injected_clock(repo: Path) -> None:
    populate(repo)
    future = "2027-01-01T00:00:00Z"
    kept = invoke(
        "events", "purge", "--older-than", "999d", "--yes", "--now", future, "--repo", str(repo)
    )
    assert kept.exit_code == 0 and "nothing to purge" in kept.output
    gone = invoke(
        "events", "purge", "--older-than", "1d", "--yes", "--now", future, "--repo", str(repo)
    )
    assert gone.exit_code == 0 and spool_files(repo) == []


def test_purge_usage_errors(repo: Path) -> None:
    assert invoke("events", "purge", "--older-than", "banana", "--repo", str(repo)).exit_code == 2
    both = invoke("events", "purge", "--all", "--session", "x", "--repo", str(repo))
    assert both.exit_code == 2


@pytest.mark.parametrize(
    "command", [["status"], ["replay", "x"], ["events", "purge", "--all", "--yes"]]
)
def test_commands_outside_git_exit_one(command: list[str], outside_git: Path) -> None:
    assert invoke(*command, "--repo", str(outside_git)).exit_code == 1
