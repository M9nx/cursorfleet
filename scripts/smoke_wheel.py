"""Smoke-test an installed CursorFleet wheel from outside the source tree.

Usage: ``python scripts/smoke_wheel.py <venv-dir>`` where the venv has the wheel installed
(and nothing else from this repository on its path). Creates a throwaway git repository,
then runs the console scripts exactly as a user would:

* ``cursorfleet --version``
* ``cursorfleet-hook`` with a synthetic sessionStart payload (reply ``{}``, event spooled)
* ``cursorfleet-hook`` with a synthetic preToolUse payload (reply ``{"permission":"allow"}``)
* ``cursorfleet init --cursor --dry-run`` (must write nothing)
* ``cursorfleet doctor --no-probe-cursor --json`` and ``cursorfleet status --json``

Everything is synthetic; Cursor is never started. Standard library only.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

TIMEOUT = 120


def scripts_dir(venv: Path) -> Path:
    return venv / ("Scripts" if os.name == "nt" else "bin")


def exe(venv: Path, name: str) -> str:
    base = scripts_dir(venv) / name
    return str(base.with_suffix(".exe")) if os.name == "nt" else str(base)


def clean_env() -> dict[str, str]:
    env = {
        k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "PYTHON", "VIRTUAL_ENV"))
    }
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    return env


def run(
    argv: list[str], cwd: Path, *, stdin: str | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - argv list, explicit timeout, local scripts only
        argv,
        cwd=cwd,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        check=False,
        env=clean_env(),
    )


def expect(condition: bool, message: str, done: subprocess.CompletedProcess[str] | None) -> None:
    if not condition:
        detail = f"\nstdout={done.stdout!r}\nstderr={done.stderr!r}" if done else ""
        print(f"FAIL: {message}{detail}", file=sys.stderr)
        raise SystemExit(1)
    print(f"ok: {message}")


def payload(hook: str, repo: Path) -> str:
    base: dict[str, object] = {
        "hook_event_name": hook,
        "conversation_id": "smoke-conversation",
        "generation_id": "smoke-generation",
        "cursor_version": "0.0.0-smoke",
        "workspace_roots": [str(repo)],
        "user_email": None,
        "transcript_path": None,
        "_synthetic": True,
    }
    if hook == "sessionStart":
        base.update({"session_id": "smoke-conversation", "composer_mode": "agent"})
    else:
        base.update(
            {
                "tool_name": "Shell",
                "tool_input": {"command": "echo hello"},
                "tool_use_id": "smoke-1",
                "cwd": str(repo),
            }
        )
    return json.dumps(base)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    venv = Path(argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="cursorfleet-smoke-") as tmp:
        repo = Path(tmp).resolve() / "repo"
        repo.mkdir()
        init = run(["git", "init", "-q", str(repo)], repo)
        expect(init.returncode == 0, "git init in a temp repository", init)

        version = run([exe(venv, "cursorfleet"), "--version"], repo)
        expect(
            version.returncode == 0 and "cursorfleet" in version.stdout,
            "cursorfleet --version",
            version,
        )
        print(f"    {version.stdout.strip()}")

        start = run([exe(venv, "cursorfleet-hook")], repo, stdin=payload("sessionStart", repo))
        expect(
            start.returncode == 0 and json.loads(start.stdout) == {},
            "hook reply for sessionStart is {}",
            start,
        )
        pre = run([exe(venv, "cursorfleet-hook")], repo, stdin=payload("preToolUse", repo))
        expect(
            pre.returncode == 0 and json.loads(pre.stdout) == {"permission": "allow"},
            'hook reply for preToolUse is {"permission":"allow"}',
            pre,
        )
        spooled = list((repo / ".git" / "cursorfleet" / "spool").rglob("*.jsonl"))
        expect(len(spooled) >= 1, "the hook wrote an event to the spool", None)
        raw = "".join(p.read_text(encoding="utf-8") for p in spooled)
        expect(
            '"kind":"session.started"' in raw and '"kind":"tool.started"' in raw,
            "spooled events are session.started and tool.started",
            None,
        )

        dry = run(
            [exe(venv, "cursorfleet"), "init", "--cursor", "--dry-run", "--path", str(repo)], repo
        )
        expect(dry.returncode == 0, "init --cursor --dry-run succeeds", dry)
        expect("hooks.json" in dry.stdout, "the dry run shows the hooks.json change", dry)
        expect(
            not (repo / ".cursor").exists() and not (repo / ".cursorfleet").exists(),
            "the dry run wrote nothing",
            dry,
        )

        doctor = run(
            [
                exe(venv, "cursorfleet"),
                "doctor",
                "--no-probe-cursor",
                "--json",
                "--path",
                str(repo),
            ],
            repo,
        )
        expect(doctor.returncode in {0, 1}, "doctor --json runs (exit 0 or 1)", doctor)
        json.loads(doctor.stdout)
        status = run([exe(venv, "cursorfleet"), "status", "--json", "--repo", str(repo)], repo)
        expect(status.returncode == 0, "status --json runs", status)
        document = json.loads(status.stdout)
        expect(isinstance(document, dict), "status --json emits a JSON object", status)
    print("smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
