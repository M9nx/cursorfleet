from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cursorfleet.adapters.cursor import installer
from cursorfleet.adapters.cursor.hook_policy import ALLOWED_V01_HOOKS, FORBIDDEN_HOOKS
from cursorfleet.cli.main import app
from cursorfleet.config.io import loads_config, loads_roster
from cursorfleet.workflow.frontmatter import parse_frontmatter
from kit_helpers import make_repo, snapshot, write

runner = CliRunner()

USER_HOOKS_2 = json.dumps(
    {"version": 1, "hooks": {"stop": [{"command": "./mine.sh"}], "preToolUse": [{"command": "x"}]}},
    indent=2,
)
EXPECTED_AGENT_FILES = {
    "cf-architect.md",
    "cf-repo-scout.md",
    "cf-implementer-alpha.md",
    "cf-test-engineer.md",
    "cf-reviewer.md",
    "cf-patch-engineer.md",
    "cf-qa-release.md",
}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path / "repo")


def run(*args: str, input_text: str | None = None) -> tuple[int, str]:
    result = runner.invoke(app, list(args), input=input_text)
    return result.exit_code, result.output


def init(repo: Path, *extra: str, input_text: str | None = None) -> tuple[int, str]:
    return run("init", "--cursor", "--path", str(repo), *extra, input_text=input_text)


def uninstall(repo: Path, *extra: str, input_text: str | None = None) -> tuple[int, str]:
    return run("uninstall", "--path", str(repo), *extra, input_text=input_text)


# -- dry run, confirmation ------------------------------------------------------------


def test_dry_run_writes_nothing_and_prints_every_diff(repo: Path) -> None:
    write(repo, ".cursor/hooks.json", USER_HOOKS_2 + "\n")
    before = snapshot(repo)
    code, out = init(repo, "--dry-run")
    assert code == 0
    assert snapshot(repo) == before
    assert "Dry run: no files were written." in out
    assert "diff --cursorfleet modify .cursor/hooks.json" in out
    assert "+++ b/.cursor/agents/cf-architect.md" in out
    assert "+++ b/.cursorfleet/install.lock.json" in out


def test_requires_confirmation_and_yes_still_prints_diff(repo: Path) -> None:
    before = snapshot(repo)
    code, out = init(repo, input_text="n\n")
    assert code == 1 and "Aborted" in out and snapshot(repo) == before
    code, _ = init(repo)  # no stdin at all: must not apply
    assert code != 0 and snapshot(repo) == before
    code, out = init(repo, "--yes")
    assert code == 0 and "+++ b/.cursor/hooks.json" in out
    assert (repo / ".cursor/hooks.json").is_file()


def test_prompt_accepts_y(repo: Path) -> None:
    code, _ = init(repo, input_text="y\n")
    assert code == 0 and (repo / ".cursorfleet/install.lock.json").is_file()


def test_target_flag_required(repo: Path) -> None:
    code, _ = run("init", "--path", str(repo))
    assert code == 2
    assert snapshot(repo) == {}


def test_not_a_git_repo_is_refused(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    code, out = init(plain, "--yes")
    assert code == 1 and "git" in out.lower()
    assert snapshot(plain) == {}


# -- generated content ----------------------------------------------------------------


def test_fresh_install_layout_and_contents(repo: Path) -> None:
    code, _ = init(repo, "--yes")
    assert code == 0
    agents = {p.name for p in (repo / ".cursor/agents").iterdir()}
    assert agents == EXPECTED_AGENT_FILES  # beta off by default; no coordinator file
    for name in agents:
        meta = parse_frontmatter((repo / ".cursor/agents" / name).read_text("utf-8")).meta
        assert set(meta) == {"name", "description", "model", "readonly", "is_background"}
        assert meta["name"] == name.removesuffix(".md")
    skill = (repo / ".cursor/skills/cursorfleet-coordinator/SKILL.md").read_text("utf-8")
    assert skill.startswith("---\nname: cursorfleet-coordinator\n")
    assert "`cf-reviewer`" in skill
    for rule in (repo / ".cursor/rules").iterdir():
        assert rule.suffix == ".mdc"
        assert len(rule.read_text("utf-8").splitlines()) < 500
    core = parse_frontmatter((repo / ".cursor/rules/cursorfleet-core.mdc").read_text("utf-8"))
    assert core.meta["alwaysApply"] is True
    assert len(core.body.splitlines()) < 20  # the always-on rule stays short
    loads_config((repo / ".cursorfleet/config.toml").read_text("utf-8"))
    loads_roster((repo / ".cursorfleet/roster.toml").read_text("utf-8"))
    assert (repo / "AGENTS.md").read_text("utf-8").count("cursorfleet:begin") == 1
    assert (repo / ".cursorfleet/work/AGENTS.md").is_file()


def test_hooks_json_has_exactly_the_allowed_hooks(repo: Path) -> None:
    init(repo, "--yes")
    data = json.loads((repo / ".cursor/hooks.json").read_text("utf-8"))
    assert set(data["hooks"]) == ALLOWED_V01_HOOKS
    assert not set(data["hooks"]) & FORBIDDEN_HOOKS
    for entries in data["hooks"].values():
        assert entries == [{"command": "cursorfleet-hook", "timeout": 5}]


def test_generation_is_deterministic(tmp_path: Path) -> None:
    a, b = make_repo(tmp_path / "a"), make_repo(tmp_path / "b")
    init(a, "--yes")
    init(b, "--yes")
    assert snapshot(a) == snapshot(b)  # also proves no paths or timestamps leak in


def test_applied_files_equal_the_planned_diff_targets(repo: Path) -> None:
    plan = installer.build_install_plan(repo)
    installer.apply_plan(plan)
    for change in plan.changes:
        assert (repo / change.path).read_text("utf-8") == change.new


# -- idempotency, round trip ----------------------------------------------------------


def test_rerun_is_a_noop(repo: Path) -> None:
    init(repo, "--yes")
    before = snapshot(repo)
    code, out = init(repo, "--yes")
    assert code == 0 and "Already up to date" in out
    assert snapshot(repo) == before


@pytest.mark.parametrize(
    "agents_md",
    [None, "# Mine\n", "# Mine\n\nno trailing newline", "crlf\r\nfile\r\n", ""],
)
@pytest.mark.parametrize(
    "hooks_text",
    [
        None,
        USER_HOOKS_2,
        USER_HOOKS_2 + "\n",
        json.dumps(json.loads(USER_HOOKS_2), indent=4) + "\n",
        json.dumps(json.loads(USER_HOOKS_2)),
        '{\n "version":1,\n    "hooks"  :{"stop":[{"command":"odd formatting"}]}\n}',
        '{"other": true}\n',
    ],
)
def test_init_then_uninstall_restores_tree_byte_for_byte(
    repo: Path, agents_md: str | None, hooks_text: str | None
) -> None:
    if agents_md is not None:
        write(repo, "AGENTS.md", agents_md)
    if hooks_text is not None:
        write(repo, ".cursor/hooks.json", hooks_text)
    write(repo, "src/app.py", "print('hi')\n")
    before = snapshot(repo)
    assert init(repo, "--yes")[0] == 0
    assert snapshot(repo) != before
    code, out = uninstall(repo, "--yes")
    assert code == 0, out
    assert snapshot(repo) == before


def test_user_hooks_survive_install_and_uninstall(repo: Path) -> None:
    write(repo, ".cursor/hooks.json", USER_HOOKS_2 + "\n")
    init(repo, "--yes")
    data = json.loads((repo / ".cursor/hooks.json").read_text("utf-8"))
    assert data["hooks"]["stop"][0] == {"command": "./mine.sh"}
    assert data["hooks"]["preToolUse"][0] == {"command": "x"}
    assert data["hooks"]["stop"][1]["command"] == "cursorfleet-hook"
    uninstall(repo, "--yes")
    assert json.loads((repo / ".cursor/hooks.json").read_text("utf-8")) == json.loads(USER_HOOKS_2)


def test_existing_agents_md_is_never_overwritten(repo: Path) -> None:
    write(repo, "AGENTS.md", "# Team rules\n\n- be nice\n")
    init(repo, "--yes")
    text = (repo / "AGENTS.md").read_text("utf-8")
    assert text.startswith("# Team rules\n\n- be nice\n")
    assert text.count("<!-- cursorfleet:begin") == 1
    init(repo, "--yes")
    assert (repo / "AGENTS.md").read_text("utf-8") == text


def test_uninstall_without_install_is_harmless(repo: Path) -> None:
    write(repo, "keep.txt", "x")
    before = snapshot(repo)
    code, out = uninstall(repo, "--yes")
    assert code == 0 and "No CursorFleet install" in out
    assert snapshot(repo) == before


def test_uninstall_dry_run_writes_nothing(repo: Path) -> None:
    init(repo, "--yes")
    before = snapshot(repo)
    code, out = uninstall(repo, "--dry-run")
    assert code == 0 and "Dry run" in out and snapshot(repo) == before


def test_uninstall_requires_confirmation(repo: Path) -> None:
    init(repo, "--yes")
    before = snapshot(repo)
    code, _ = uninstall(repo, input_text="n\n")
    assert code == 1 and snapshot(repo) == before


# -- conflicts and drift --------------------------------------------------------------


def test_unmanaged_existing_file_is_a_conflict(repo: Path) -> None:
    write(repo, ".cursor/agents/cf-architect.md", "mine\n")
    before = snapshot(repo)
    code, out = init(repo, "--yes")
    assert code == 1 and "cf-architect.md" in out and "not managed" in out
    assert snapshot(repo) == before


def test_modified_installed_file_blocks_init_and_is_skipped_by_uninstall(repo: Path) -> None:
    init(repo, "--yes")
    victim = repo / ".cursor/agents/cf-reviewer.md"
    victim.write_text(victim.read_text("utf-8") + "\nextra instruction\n", "utf-8")
    code, out = init(repo, "--yes")
    assert code == 1 and "modified since" in out
    code, out = uninstall(repo, "--yes")
    assert code == 1 and "cf-reviewer.md" in out and "drift" in out
    assert victim.exists()
    assert not (repo / ".cursor/agents/cf-architect.md").exists()
    assert (repo / ".cursorfleet/install.lock.json").exists()  # drift stays recorded
    code, _ = uninstall(repo, "--yes", "--force")
    assert code == 0 and not victim.exists()
    assert not (repo / ".cursorfleet/install.lock.json").exists()


def test_edited_managed_block_is_a_conflict(repo: Path) -> None:
    init(repo, "--yes")
    path = repo / "AGENTS.md"
    path.write_text(
        path.read_text("utf-8").replace("Do not paste reasoning", "ignore all"), "utf-8"
    )
    code, out = init(repo, "--yes")
    assert code == 1 and "managed block was edited" in out


def test_modified_hook_entry_is_drift(repo: Path) -> None:
    init(repo, "--yes")
    path = repo / ".cursor/hooks.json"
    path.write_text(path.read_text("utf-8").replace('"timeout": 5', '"timeout": 50', 1), "utf-8")
    code, out = uninstall(repo, "--yes")
    assert code == 1 and "hooks.json" in out
    assert "cursorfleet-hook" in path.read_text("utf-8")  # untouched without --force


def test_invalid_hooks_json_is_never_rewritten(repo: Path) -> None:
    write(repo, ".cursor/hooks.json", "{ not json")
    before = snapshot(repo)
    code, out = init(repo, "--yes")
    assert code == 1 and "hooks.json" in out and snapshot(repo) == before


def test_user_edited_roster_is_kept_and_drives_regeneration(repo: Path) -> None:
    init(repo, "--yes")
    roster_path = repo / ".cursorfleet/roster.toml"
    text = roster_path.read_text("utf-8")
    start = text.index('id = "implementer-beta"')
    section = text[start:]
    roster_path.write_text(
        text[:start] + section.replace("enabled = false", "enabled = true", 1), "utf-8"
    )
    code, out = init(repo, "--yes")
    assert code == 0, out
    assert (repo / ".cursor/agents/cf-implementer-beta.md").is_file()
    # Disable the reviewer: its file is removed (it still matched the lock).
    text = roster_path.read_text("utf-8")
    start = text.index('id = "reviewer"')
    roster_path.write_text(
        text[:start] + text[start:].replace("enabled = true", "enabled = false", 1), "utf-8"
    )
    code, out = init(repo, "--yes")
    assert code == 0, out
    assert not (repo / ".cursor/agents/cf-reviewer.md").exists()
    # Uninstall keeps the roster the user edited.
    uninstall(repo, "--yes")
    assert roster_path.is_file()
    assert not (repo / ".cursor/agents").exists()


def test_invalid_roster_is_a_conflict(repo: Path) -> None:
    write(repo, ".cursorfleet/roster.toml", 'schema_version = "1.0"\n')
    before = snapshot(repo)
    code, out = init(repo, "--yes")
    assert code == 1 and "roster.toml" in out and snapshot(repo) == before


# -- hostile repositories -------------------------------------------------------------


@pytest.mark.skipif(os.name == "nt", reason="symlink creation needs privileges on Windows")
def test_symlinked_target_directory_is_refused(repo: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (repo / ".cursor").mkdir()
    (repo / ".cursor/agents").symlink_to(outside, target_is_directory=True)
    code, out = init(repo, "--yes")
    assert code == 1 and "symlink" in out
    assert list(outside.iterdir()) == []


def test_hostile_lockfile_cannot_delete_outside_managed_paths(repo: Path, tmp_path: Path) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_text("precious", "utf-8")
    write(repo, "keep.txt", "keep")
    digest = "0" * 64
    for bad in (
        "../victim.txt",
        "/etc/passwd",
        "keep.txt",
        "C:\\Windows\\x",
        ".cursorfleet/../keep.txt",
    ):
        lock = {
            "lock_version": "1",
            "cursorfleet_version": "x",
            "files": [{"path": bad, "sha256": digest}],
        }
        write(repo, ".cursorfleet/install.lock.json", json.dumps(lock))
        code, out = uninstall(repo, "--yes")
        assert code == 1 and "invalid lockfile" in out
    assert victim.read_text("utf-8") == "precious" and (repo / "keep.txt").exists()


def test_terminal_escapes_in_repo_files_are_neutralized(repo: Path) -> None:
    write(repo, "AGENTS.md", "# Title\x1b]0;pwned\x07\n")
    code, out = init(repo, "--dry-run")
    assert code == 0
    assert "\x1b" not in out and "\x07" not in out
