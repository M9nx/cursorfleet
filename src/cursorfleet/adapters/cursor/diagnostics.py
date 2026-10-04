"""``cursorfleet doctor`` checks. Read-only, tolerant of absent or unreadable files.

Every subprocess uses an argv list and a timeout. Nothing here writes to disk.
PROVISIONAL: the hooks.json locations for enterprise, user and project levels
come from the Cursor docs (ADR 0001 A4); Cursor's behavior with them is unverified.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
from typing import Any, Literal

from cursorfleet.adapters.cursor import hooksjson
from cursorfleet.adapters.cursor.fsutil import UnsafePathError, safe_text
from cursorfleet.adapters.cursor.hook_policy import FORBIDDEN_HOOKS
from cursorfleet.adapters.cursor.installer import check_drift, load_inputs, read_lock
from cursorfleet.adapters.cursor.kit import HOOKS_PATH, LOCK_PATH
from cursorfleet.adapters.cursor.workspace import (
    Workspace,
    WorkspaceError,
    resolve_workspace,
)
from cursorfleet.safeexe import find_executable
from cursorfleet.state.runtime import untrusted_reason

Status = Literal["ok", "warn", "fail", "info"]
HOOK_BINARY = "cursorfleet-hook"
MIN_PYTHON = (3, 11)
CURSOR_PROBE_TIMEOUT_S = 5.0
MAX_PERMISSION_SCAN = 2000
_VERSION_RE = re.compile(r"^[0-9]+(\.[0-9]+){1,3}([-+.][A-Za-z0-9.]{1,32})?$")
_COMMAND_DISPLAY_CHARS = 100


@dataclass
class Check:
    id: str
    status: Status
    message: str
    remediation: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "message": self.message,
            "remediation": self.remediation,
            "details": self.details,
        }


@dataclass
class HooksSource:
    level: str
    path: str | None
    exists: bool
    readable: bool
    error: str | None = None
    note: str | None = None
    events: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "path": self.path,
            "exists": self.exists,
            "readable": self.readable,
            "error": self.error,
            "note": self.note,
            "events": self.events,
        }


@dataclass
class DoctorReport:
    checks: list[Check]
    hooks: list[HooksSource]
    cursor_version: str | None
    runtime_dir: str | None

    @property
    def ok(self) -> bool:
        return not any(c.status == "fail" for c in self.checks)

    def counts(self) -> dict[str, int]:
        result = {"ok": 0, "warn": 0, "fail": 0, "info": 0}
        for check in self.checks:
            result[check.status] += 1
        return result

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "cursorfleet.doctor/1",
            "ok": self.ok,
            "summary": self.counts(),
            "cursor_version": self.cursor_version,
            "runtime_dir": self.runtime_dir,
            "checks": [c.as_dict() for c in self.checks],
            "effective_hooks": [h.as_dict() for h in self.hooks],
        }


def enterprise_hooks_path(platform: str, env: Mapping[str, str]) -> PurePath:
    """Documented enterprise (MDM) hooks.json location for ``platform`` (PROVISIONAL)."""
    if platform.startswith("win"):
        base = env.get("PROGRAMDATA") or "C:\\ProgramData"
        return PureWindowsPath(base) / "Cursor" / "hooks.json"
    if platform == "darwin":
        return PurePosixPath("/Library/Application Support/Cursor/hooks.json")
    return PurePosixPath("/etc/cursor/hooks.json")


def _summarize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    command = entry.get("command")
    shown = safe_text(command[:_COMMAND_DISPLAY_CHARS]) if isinstance(command, str) else None
    return {
        "command": shown,
        "ours": hooksjson.is_ours(entry),
        "has_matcher": "matcher" in entry,
        "fail_closed": entry.get("failClosed") is True,
    }


def read_hooks_source(level: str, path: Path | None, note: str | None = None) -> HooksSource:  # noqa: PLR0911
    """Read one hooks.json level without ever raising."""
    if path is None:
        return HooksSource(level, None, exists=False, readable=False, note=note)
    source = HooksSource(level, safe_text(str(path)), exists=False, readable=False, note=note)
    try:
        if not path.exists():
            return source
    except OSError as exc:
        source.error = f"cannot stat: {exc.strerror or exc}"
        return source
    source.exists = True
    try:
        if path.stat().st_size > 1024 * 1024:
            source.error = "file is larger than 1 MiB; not parsed"
            return source
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        source.error = f"cannot read: {getattr(exc, 'strerror', None) or type(exc).__name__}"
        return source
    source.readable = True
    try:
        parsed = hooksjson.effective_events(text)
    except hooksjson.HooksJsonError as exc:
        source.error = safe_text(str(exc))
        return source
    source.events = {
        # Event names come from a repository-controlled file: escape them for the terminal.
        safe_text(event)[:120]: [_summarize_entry(e) for e in entries[:20]]
        for event, entries in sorted(parsed.items())
    }
    return source


def probe_cursor_version(env: Mapping[str, str], *, probe: bool) -> tuple[str | None, str]:
    """Return ``(version, how)``. Never fabricates: ``None`` when not discoverable."""
    env_version = env.get("CURSOR_VERSION", "").strip()
    if _VERSION_RE.match(env_version):
        return env_version, "environment variable CURSOR_VERSION"
    if not probe:
        return None, "probe disabled"
    exe = find_executable("cursor")  # never the current directory (hostile repositories)
    if exe is None:
        return None, "the `cursor` command is not on PATH"
    try:
        proc = subprocess.run(  # noqa: S603
            [exe, "--version"],
            capture_output=True,
            text=True,
            timeout=CURSOR_PROBE_TIMEOUT_S,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None, "`cursor --version` failed or timed out"
    first = (proc.stdout.strip().splitlines() or [""])[0].strip()
    if proc.returncode == 0 and _VERSION_RE.match(first):
        return first, "`cursor --version`"
    return None, "`cursor --version` did not print a recognizable version"


def _check_runtime_permissions(runtime: Path) -> Check:
    reason = untrusted_reason(str(runtime))
    if reason is not None:
        return Check(
            "runtime.permissions",
            "fail",
            f"the runtime directory {reason}; CursorFleet refuses to read or write it",
            f"Inspect it, then remove it (`rm -rf {safe_text(str(runtime))}`) and let the next "
            "hook run recreate it as a private directory.",
        )
    if os.name == "nt":
        return Check(
            "runtime.permissions",
            "info",
            "permission bits are not checked on Windows (best effort ACLs; see ADR 0002)",
        )
    if not runtime.exists():
        return Check(
            "runtime.permissions",
            "info",
            "runtime directory does not exist yet; the first hook run creates it (0700/0600)",
        )
    loose: list[str] = []
    scanned = 0
    try:
        for dirpath, dirnames, filenames in os.walk(runtime, followlinks=False):
            for name in [".", *dirnames, *filenames]:
                full = Path(dirpath) if name == "." else Path(dirpath) / name
                scanned += 1
                if scanned > MAX_PERMISSION_SCAN:
                    break
                info = full.lstat()
                if stat.S_ISLNK(info.st_mode):
                    continue
                mode = stat.S_IMODE(info.st_mode)
                if mode & 0o077:
                    loose.append(f"{full.relative_to(runtime).as_posix() or '.'} ({mode:04o})")
    except OSError as exc:
        return Check(
            "runtime.permissions",
            "warn",
            f"could not inspect the runtime directory: {exc.strerror or exc}",
        )
    if loose:
        return Check(
            "runtime.permissions",
            "fail",
            f"{len(loose)} runtime path(s) are accessible by other users",
            f"Run: chmod -R go-rwx {safe_text(str(runtime))}",
            {"loose": [safe_text(x) for x in loose[:20]]},
        )
    return Check(
        "runtime.permissions", "ok", "runtime directory is private (no group/other access)"
    )


def _hook_shadows(root: Path) -> list[str]:
    """Top-level files of ``root`` called ``cursorfleet-hook`` or ``cursorfleet-hook.*``."""
    try:
        with os.scandir(root) as entries:
            return sorted(
                e.name
                for e in entries
                if e.name.lower() == HOOK_BINARY or e.name.lower().startswith(HOOK_BINARY + ".")
            )
    except OSError:
        return []


def _hooks_checks(sources: list[HooksSource], ws_known: bool, installed_hooks: bool) -> list[Check]:
    checks: list[Check] = []
    forbidden: list[str] = []
    for source in sources:
        for event, entries in source.events.items():
            if event in FORBIDDEN_HOOKS and entries:
                forbidden.append(f"{source.level}:{event}")
        if source.error:
            checks.append(
                Check(
                    f"hooks.{source.level}",
                    "warn",
                    f"{source.level} hooks.json could not be read: {source.error}",
                    "Fix or remove the file; Cursor may also ignore it.",
                )
            )
    if forbidden:
        checks.append(
            Check(
                "hooks.forbidden",
                "warn",
                "content-bearing hooks are registered by other sources: " + ", ".join(forbidden),
                "CursorFleet never registers these (ADR 0004) and cannot remove them. They "
                "receive prompts, thinking, responses or file contents; review who added them.",
                {"registered": forbidden},
            )
        )
    else:
        checks.append(
            Check("hooks.forbidden", "ok", "no content-bearing hooks found at readable levels")
        )
    foreign = sum(
        1 for s in sources for entries in s.events.values() for e in entries if not e["ours"]
    )
    checks.append(
        Check(
            "hooks.effective",
            "info",
            f"{foreign} non-CursorFleet hook entr{'y' if foreign == 1 else 'ies'} visible "
            "locally; team and third-party hooks cannot be listed from disk",
            None,
            {"foreign_entries": foreign},
        )
    )
    if ws_known and installed_hooks:
        project = next((s for s in sources if s.level == "project"), None)
        ours = sum(1 for e in (project.events if project else {}).values() for x in e if x["ours"])
        if ours == 0:
            checks.append(
                Check(
                    "hooks.project",
                    "fail",
                    "the install lockfile lists hooks but .cursor/hooks.json has none of ours",
                    "Run `cursorfleet init --cursor` to restore them.",
                )
            )
    return checks


def run_doctor(  # noqa: PLR0912, PLR0913, PLR0915
    path: Path,
    *,
    home: Path | None = None,
    platform: str | None = None,
    env: Mapping[str, str] | None = None,
    probe_cursor: bool = True,
    enterprise_path: Path | None = None,
) -> DoctorReport:
    """Run all checks for the workspace containing ``path``."""
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    home = Path.home() if home is None else home
    checks: list[Check] = []

    # Python
    py = sys.version_info
    if (py.major, py.minor) >= MIN_PYTHON:
        checks.append(Check("python.version", "ok", f"Python {py.major}.{py.minor}.{py.micro}"))
    else:
        checks.append(
            Check(
                "python.version",
                "fail",
                f"Python {py.major}.{py.minor} is too old (need >= 3.11)",
                "Install Python 3.11 or newer and reinstall cursorfleet.",
            )
        )

    # Hook binary
    exe = shutil.which(HOOK_BINARY)
    if exe:
        checks.append(Check("hook.binary", "ok", f"{HOOK_BINARY} found", None, {"path": exe}))
    else:
        checks.append(
            Check(
                "hook.binary",
                "fail",
                f"{HOOK_BINARY} is not on PATH, so registered hooks cannot record anything",
                "Install CursorFleet where Cursor's shell can see it, e.g. `uv tool install "
                "cursorfleet` or `pipx install cursorfleet`, then restart Cursor. Hooks fail "
                "open, so nothing is blocked meanwhile.",
            )
        )

    # Git and runtime dir
    ws: Workspace | None
    try:
        ws = resolve_workspace(path)
        checks.append(
            Check(
                "git.repo",
                "ok",
                "git repository found",
                None,
                {"root": safe_text(str(ws.root)), "common_dir": safe_text(str(ws.common_dir))},
            )
        )
        checks.append(
            Check(
                "runtime.dir",
                "ok",
                f"runtime directory resolves to {safe_text(str(ws.runtime_dir))}",
                None,
                {"path": safe_text(str(ws.runtime_dir)), "exists": ws.runtime_dir.exists()},
            )
        )
        checks.append(_check_runtime_permissions(ws.runtime_dir))
    except WorkspaceError as exc:
        ws = None
        checks.append(
            Check(
                "git.repo",
                "fail",
                safe_text(str(exc)),
                "Run inside a git repository (v0.1 requires git; hooks record nothing "
                "outside one), or pass --path.",
            )
        )
    root = ws.root if ws else path

    # A file named like our hook inside the repo can shadow it where the shell searches the
    # current directory first (Windows cmd.exe; hooks run from the project root).
    shadows = _hook_shadows(root)
    if shadows:
        checks.append(
            Check(
                "hook.shadow",
                "warn",
                "the repository contains a file named like the hook command: "
                + ", ".join(safe_text(x) for x in shadows[:5]),
                "On Windows the shell may run it instead of the installed `cursorfleet-hook`. "
                "Remove or rename it unless you put it there on purpose.",
                {"files": [safe_text(x) for x in shadows[:5]]},
            )
        )

    # Config
    cfg_problems: list[str] = []
    config, _roster = load_inputs(root, cfg_problems)
    if cfg_problems:
        checks.append(
            Check(
                "config.valid",
                "fail",
                "; ".join(safe_text(p) for p in cfg_problems[:3]),
                "Run `cursorfleet validate` for details.",
            )
        )
    else:
        checks.append(Check("config.valid", "ok", "config and roster load (or defaults apply)"))

    # Lockfile and drift
    lock_problems: list[str] = []
    lock = read_lock(root, lock_problems)
    if lock_problems:
        checks.append(
            Check(
                "install.lock",
                "fail",
                safe_text(lock_problems[0]),
                f"Delete {LOCK_PATH} and re-run `cursorfleet init --cursor`.",
            )
        )
    elif lock is None:
        checks.append(
            Check(
                "install.lock",
                "warn",
                "the CursorFleet kit is not installed in this repository",
                "Run `cursorfleet init --cursor --dry-run` to preview, then without --dry-run.",
            )
        )
    else:
        try:
            items = check_drift(root, lock)
        except UnsafePathError as exc:  # pragma: no cover - defensive
            items = []
            checks.append(Check("install.drift", "fail", safe_text(str(exc))))
        problems = [i for i in items if i.is_problem]
        edited = [i.path for i in items if i.status == "edited"]
        if problems:
            checks.append(
                Check(
                    "install.drift",
                    "fail",
                    f"{len(problems)} installed item(s) drifted from the lockfile",
                    "Review with `git diff`. If unintended, re-run `cursorfleet init --cursor` "
                    "(it refuses on modified files; restore them first). Agents can edit these "
                    "files; v0.1 detects but does not prevent that.",
                    {
                        "drift": [
                            {"path": i.path, "kind": i.kind, "status": i.status, "detail": i.detail}
                            for i in problems
                        ]
                    },
                )
            )
        else:
            checks.append(
                Check(
                    "install.drift",
                    "ok",
                    f"{len(items)} installed item(s) match the lockfile",
                    None,
                    {"user_edited": edited},
                )
            )

    # Effective hooks across levels
    ent = (
        enterprise_path
        if enterprise_path is not None
        else Path(str(enterprise_hooks_path(platform, env)))
    )
    sources = [
        read_hooks_source("enterprise", ent),
        HooksSource(
            "team",
            None,
            exists=False,
            readable=False,
            note="cloud-distributed (Enterprise plan); not visible from disk",
        ),
        read_hooks_source("project", root / HOOKS_PATH),
        read_hooks_source("user", home / ".cursor" / "hooks.json"),
    ]
    checks.extend(_hooks_checks(sources, ws is not None, bool(lock and lock.hooks)))

    # Cursor version
    version, how = probe_cursor_version(env, probe=probe_cursor)
    validated = config.cursor.validated_versions
    if version is None:
        checks.append(
            Check(
                "cursor.version",
                "warn",
                f"Cursor version not discoverable ({how}); behavior is unverified (PROVISIONAL)",
                "Hook events record cursor_version once they run. Add versions you have "
                "verified to [cursor].validated_versions in .cursorfleet/config.toml.",
            )
        )
    elif version in validated:
        checks.append(Check("cursor.version", "ok", f"Cursor {version} is in validated_versions"))
    else:
        checks.append(
            Check(
                "cursor.version",
                "warn",
                f"Cursor {version} (from {how}) has not been verified with CursorFleet "
                "(PROVISIONAL: no live capture reviewed)",
                "Review a capture (spike/README.md), then add it to [cursor].validated_versions.",
                {"validated_versions": list(validated)},
            )
        )

    return DoctorReport(
        checks=checks,
        hooks=sources,
        cursor_version=version,
        runtime_dir=safe_text(str(ws.runtime_dir)) if ws else None,
    )
