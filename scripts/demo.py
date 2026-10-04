"""A reproducible, SYNTHETIC CursorFleet demo. No live Cursor is involved.

    python scripts/demo.py [--venv DIR] [--keep] [--no-uninstall]

What it does, in a throwaway directory:

1. creates a git repository and a linked worktree;
2. runs ``cursorfleet init --cursor`` (dry run, then ``--yes``);
3. feeds hand-built payloads (derived from Cursor's documentation, see
   ``spike/doc_examples/``) through the real ``cursorfleet-hook`` executable, as two
   "sessions" (the main checkout and the linked worktree);
4. proves that planted secrets and file contents never reached the spool;
5. runs ``doctor``, ``status``, ``status --json``, ``replay`` and ``events export``;
6. runs ``uninstall --yes`` and checks the repository is byte-for-byte as before.

The payloads are NOT captured from Cursor and prove nothing about real Cursor behaviour
(docs/adr/0001-cursor-capabilities.md). Command resolution: ``--venv`` (an environment with
CursorFleet installed), else ``cursorfleet`` and ``cursorfleet-hook`` on ``PATH``, else
``uv run --project <this checkout>``. The interactive dashboard is not launched; run
``cursorfleet tui`` in the printed directory with ``--keep`` to look at it.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC_EXAMPLES = ROOT / "spike" / "doc_examples"
TIMEOUT = 120
SECRET_TOKEN = "sk-demoSECRET0123456789abcdef"  # noqa: S105 - planted on purpose, synthetic
SECRET_OUTPUT = "PLANTED-COMMAND-OUTPUT-7731"  # noqa: S105 - synthetic
SECRET_EDIT = "PLANTED-FILE-CONTENT-4242"  # noqa: S105 - synthetic
BANNER = "SYNTHETIC DEMO: payloads are hand-built from the docs; no Cursor is running."


class Tools:
    """Resolves how to run ``cursorfleet`` and ``cursorfleet-hook``."""

    def __init__(self, venv: Path | None) -> None:
        self.prefix: dict[str, list[str]] = {}
        for name in ("cursorfleet", "cursorfleet-hook"):
            self.prefix[name] = self._resolve(name, venv)

    @staticmethod
    def _resolve(name: str, venv: Path | None) -> list[str]:
        if venv is not None:
            scripts = venv / ("Scripts" if os.name == "nt" else "bin")
            for candidate in (scripts / f"{name}.exe", scripts / name):
                if candidate.is_file():
                    return [str(candidate)]
            msg = f"{name} not found in {scripts}"
            raise SystemExit(msg)
        found = shutil.which(name)
        if found:
            return [found]
        uv = shutil.which("uv")
        if uv:
            return [uv, "run", "--quiet", "--project", str(ROOT), name]
        msg = f"cannot find {name}: install CursorFleet, pass --venv, or install uv"
        raise SystemExit(msg)

    def argv(self, name: str, *args: str) -> list[str]:
        return [*self.prefix[name], *args]


EXTRA_PATH: list[str] = []  # the --venv scripts directory, so `doctor` finds cursorfleet-hook


def clean_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "VIRTUAL_ENV"))}
    if EXTRA_PATH:
        env["PATH"] = os.pathsep.join([*EXTRA_PATH, env.get("PATH", "")])
    env.update(
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_SYSTEM=os.devnull,
        GIT_AUTHOR_NAME="Demo",
        GIT_AUTHOR_EMAIL="demo@example.invalid",
        GIT_COMMITTER_NAME="Demo",
        GIT_COMMITTER_EMAIL="demo@example.invalid",
    )
    return env


def run(
    argv: list[str], cwd: Path, *, stdin: str | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - argv list, explicit timeout, no shell
        argv,
        cwd=cwd,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        check=False,
        env=clean_env(),
    )


def step(title: str) -> None:
    print(f"\n=== {title}")


def show(done: subprocess.CompletedProcess[str], *, lines: int = 18) -> None:
    text = (done.stdout + done.stderr).rstrip()
    body = text.splitlines()
    for line in body[:lines]:
        print(f"    {line}")
    if len(body) > lines:
        print(f"    ... ({len(body) - lines} more lines)")
    print(f"    [exit {done.returncode}]")


def git(cwd: Path, *args: str) -> str:
    done = run(["git", "-c", "init.defaultBranch=main", "-c", "commit.gpgsign=false", *args], cwd)
    if done.returncode != 0:
        print(done.stderr, file=sys.stderr)
        msg = f"git {' '.join(args)} failed"
        raise SystemExit(msg)
    return done.stdout


def doc_payload(hook: str, **overrides: object) -> dict[str, object]:
    path = DOC_EXAMPLES / f"{hook}.doc-derived.json"
    data: dict[str, object] = copy.deepcopy(json.loads(path.read_text(encoding="utf-8")))
    data.pop("_doc_derived_not_captured", None)
    data.update(overrides)
    return data


def feed(tools: Tools, cwd: Path, payload: dict[str, object]) -> str:
    done = run(tools.argv("cursorfleet-hook"), cwd, stdin=json.dumps(payload))
    if done.returncode != 0:
        msg = f"hook exited {done.returncode}: {done.stderr}"
        raise SystemExit(msg)
    return done.stdout.strip()


def session(
    tools: Tools, cwd: Path, conversation: str, *, subagent: bool, final: bool
) -> list[str]:
    """Replay one synthetic session; returns the hook replies seen."""
    base: dict[str, object] = {"conversation_id": conversation, "workspace_roots": [str(cwd)]}
    shell = f"curl -sS -H 'Authorization: Bearer {SECRET_TOKEN}' https://example.invalid/health"
    steps: list[dict[str, object]] = [
        doc_payload("sessionStart", session_id=conversation, **base),
        doc_payload("preToolUse", tool_use_id=f"{conversation}-1", cwd=str(cwd), **base),
        doc_payload("beforeShellExecution", command=shell, cwd=str(cwd), **base),
        doc_payload(
            "afterShellExecution", command=shell, output=SECRET_OUTPUT, duration=840, **base
        ),
        doc_payload(
            "postToolUse",
            tool_use_id=f"{conversation}-1",
            cwd=str(cwd),
            tool_output=SECRET_OUTPUT,
            **base,
        ),
        doc_payload(
            "afterFileEdit",
            file_path=str(cwd / "src" / "app.py"),
            edits=[{"old_string": "a", "new_string": SECRET_EDIT}],
            **base,
        ),
    ]
    if subagent:
        sub = {"parent_conversation_id": conversation, "git_branch": "main"}
        steps += [
            doc_payload("subagentStart", subagent_id=f"{conversation}-sub", **sub, **base),
            doc_payload("subagentStop", **base),
        ]
    steps.append(doc_payload("preCompact", **base))
    steps.append(doc_payload("stop", **base))
    if final:
        steps.append(doc_payload("sessionEnd", session_id=conversation, **base))
    return [feed(tools, cwd, payload) for payload in steps]


def spool_text(repo: Path) -> str:
    spool = repo / ".git" / "cursorfleet" / "spool"
    return "".join(p.read_text(encoding="utf-8") for p in sorted(spool.rglob("*.jsonl")))


def main() -> int:  # noqa: PLR0915 - a linear narrated script
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--venv", type=Path, help="environment with CursorFleet installed")
    parser.add_argument("--keep", action="store_true", help="keep the temp directory")
    parser.add_argument(
        "--no-uninstall",
        action="store_true",
        help="skip the final uninstall (implies --keep) so you can open `cursorfleet tui` there",
    )
    args = parser.parse_args()
    args.keep = args.keep or args.no_uninstall
    if args.venv:
        EXTRA_PATH.append(str(args.venv.resolve() / ("Scripts" if os.name == "nt" else "bin")))
    tools = Tools(args.venv.resolve() if args.venv else None)
    print(BANNER)

    tmp = Path(tempfile.mkdtemp(prefix="cursorfleet-demo-")).resolve()
    repo, worktree = tmp / "repo", tmp / "repo-qa"
    try:
        step("1. a git repository with a linked worktree")
        repo.mkdir()
        git(repo, "init", "-q", ".")
        (repo / "src").mkdir()
        (repo / "src" / "app.py").write_text("print('hello')\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-q", "-m", "initial commit")
        git(repo, "worktree", "add", "-q", "-b", "feat/qa", str(worktree))
        before = git(repo, "status", "--porcelain=v1", "--untracked-files=all")
        print(f"    {repo}\n    {worktree}")

        step("2. cursorfleet init --cursor --dry-run (writes nothing)")
        dry = run(tools.argv("cursorfleet", "init", "--cursor", "--dry-run"), repo)
        show(dry, lines=8)
        step("3. cursorfleet init --cursor --yes")
        installed = run(tools.argv("cursorfleet", "init", "--cursor", "--yes"), repo)
        show(installed, lines=6)

        step("4. feed synthetic hook payloads through the real cursorfleet-hook")
        replies = session(tools, repo, "demo-main", subagent=True, final=False)
        replies += session(tools, worktree, "demo-qa", subagent=False, final=True)
        print(f"    {len(replies)} hook calls; distinct replies: {sorted(set(replies))}")

        step("5. privacy check: planted secrets must not be in the spool")
        spooled = spool_text(repo)
        for label, needle in (
            ("bearer token", SECRET_TOKEN),
            ("command output", SECRET_OUTPUT),
            ("edited file content", SECRET_EDIT),
        ):
            count = spooled.count(needle)
            print(f"    {label}: {count} occurrence(s) in {len(spooled)} bytes of spool")
            if count:
                print("FAIL: a planted secret reached the spool", file=sys.stderr)
                return 1

        step("6. cursorfleet doctor --no-probe-cursor")
        show(run(tools.argv("cursorfleet", "doctor", "--no-probe-cursor"), repo), lines=24)
        step("7. cursorfleet status")
        status = run(tools.argv("cursorfleet", "status"), repo)
        show(status, lines=30)
        step("8. cursorfleet status --json (first lines)")
        show(run(tools.argv("cursorfleet", "status", "--json"), repo), lines=12)
        step("9. cursorfleet replay demo-main (rebuilds from the spool, twice, compares)")
        show(run(tools.argv("cursorfleet", "replay", "demo-main"), repo), lines=10)
        step("10. cursorfleet events export --sanitized (first lines)")
        show(run(tools.argv("cursorfleet", "events", "export", "--sanitized"), repo), lines=3)

        if not args.no_uninstall:
            step("11. cursorfleet uninstall --yes, then compare with the original tree")
            gone = run(tools.argv("cursorfleet", "uninstall", "--yes"), repo)
            show(gone, lines=6)
            after = git(repo, "status", "--porcelain=v1", "--untracked-files=all")
            same = before == after
            print(f"    working tree identical to before init: {same}")
            if not same:
                print(f"FAIL: leftover files after uninstall:\n{after}", file=sys.stderr)
                return 1
        print(f"\n{BANNER}\nDemo finished.")
        if args.keep:
            print(f"Kept {tmp}\nTry: cd {repo} && cursorfleet tui")
        return 0
    finally:
        if not args.keep:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
