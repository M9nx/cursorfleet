"""``cursorfleet-hook``: the Cursor hook hot-path entrypoint. Stdlib only, fails open.

Contract (ADR 0004, docs/architecture.md):

- Reads one hook JSON payload from stdin; the hook name comes from ``hook_event_name``.
- ALWAYS exits 0 and ALWAYS prints the fail-open reply for that hook
  (``{"permission":"allow"}`` for permission hooks, else ``{}``), whatever goes wrong.
- Imports only the stdlib and small stdlib-only CursorFleet modules (no pydantic,
  typer, textual, sqlite3 or any network module). A test enforces this.
- Appends sanitized events to ``<git-common-dir>/cursorfleet/spool/...``. It never opens
  SQLite. It records nothing unless the nearest Git root already has the install marker
  ``.cursorfleet/config.toml`` (ADR 0002). Missing marker, an inner uninitialized
  repository, an external symlink or an ambiguous multi-root workspace fail open.

PROVISIONAL: if the hook name cannot be determined (garbage stdin and no argv hint) the
reply is ``{"permission":"allow"}``, because Cursor treats an invalid reply from a
permission hook as a block while an unknown extra field on a non-permission reply is
assumed harmless (unverified).
"""

from __future__ import annotations

import json
import os
import sys
import time

from cursorfleet import __version__
from cursorfleet.adapters.cursor.hook_policy import (
    PERMISSION_HOOKS,
    fail_open_response,
    is_registrable,
)
from cursorfleet.events.ids import worktree_id_for
from cursorfleet.state.runtime import (
    GitLocation,
    RuntimePaths,
    ensure_runtime_root,
    has_install_marker,
    is_ambiguous_workspace_roots,
    is_external_symlink_anchor,
    resolve_inherited_location,
    runtime_paths,
    safe_realpath,
    untrusted_reason,
    write_private_file,
)
from cursorfleet.state.spool import DEFAULT_MAX_SESSION_BYTES, append_event

TYPE_CHECKING = False  # avoids importing ``typing`` (~4 ms) on the hook hot path
if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from typing import BinaryIO, TextIO

MAX_STDIN_BYTES = 8 * 1024 * 1024
_NO_COMMAND_HOOKS = frozenset({"sessionStart", "sessionEnd", "stop", "afterFileEdit", "preCompact"})
_MAX_CONFIG_BYTES = 256 * 1024
_SAFE_HINT_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
_ALLOW = '{"permission":"allow"}'
# Cursor permission hooks we never register but would still answer correctly if someone
# else (or a mistake) wires them to this command: an invalid reply there blocks the action.
_EXTRA_PERMISSION_HOOKS = frozenset({"beforeMCPExecution", "beforeReadFile", "beforeTabFileRead"})


def reply_for(hook: str | None) -> str:
    """The fail-open reply for ``hook``; allow-shaped when the hook is unknown."""
    if hook is None or hook in _EXTRA_PERMISSION_HOOKS or hook in PERMISSION_HOOKS:
        return _ALLOW
    return fail_open_response(hook)


# ---------------------------------------------------------------- inputs


def read_stdin_bytes(stream: BinaryIO | None, limit: int = MAX_STDIN_BYTES) -> bytes | None:
    """Read (and drain) stdin; ``None`` if over ``limit`` or unavailable. Never raises."""
    if stream is None:
        return None
    try:
        if stream.isatty():  # never block on an interactive terminal
            return None
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = stream.read(65536)
            if not chunk:
                break
            total += len(chunk)
            if total <= limit:
                chunks.append(chunk)
        return b"".join(chunks) if total <= limit else None
    except (OSError, ValueError):
        return None


def parse_payload(data: bytes | None) -> dict[str, object] | None:
    if not data:
        return None
    try:
        parsed = json.loads(data)
    except (ValueError, RecursionError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _hint(argv: Sequence[str]) -> str | None:
    if len(argv) > 1 and argv[1] and all(c in _SAFE_HINT_CHARS for c in argv[1]):
        return argv[1]
    return None


# ---------------------------------------------------------------- git context


def _read_text(path: str, limit: int = 4096) -> str | None:
    try:
        with open(path, "rb") as handle:
            return handle.read(limit).decode("utf-8", "replace")
    except OSError:
        return None


def _is_commit(value: str) -> bool:
    return 7 <= len(value) <= 64 and all(c in "0123456789abcdef" for c in value)


def read_head(location: GitLocation) -> tuple[str | None, str | None]:
    """Return ``(branch, commit)`` from ``HEAD`` by reading files; either may be ``None``."""
    head = _read_text(os.path.join(location.git_dir, "HEAD"))
    if head is None:
        return None, None
    line = head.strip().splitlines()[0] if head.strip() else ""
    if not line.startswith("ref:"):
        return None, line if _is_commit(line) else None
    ref = line[4:].strip()
    if not ref.startswith("refs/") or ".." in ref or "\\" in ref or ":" in ref:
        return None, None  # ":" would let a Windows drive component escape the git dir
    branch = ref[len("refs/heads/") :] if ref.startswith("refs/heads/") else None
    if branch is not None and not (1 <= len(branch) <= 255 and branch.isprintable()):
        branch = None
    text = _read_text(os.path.join(location.common_dir, *ref.split("/")))
    if text is not None:
        sha = text.strip().splitlines()[0] if text.strip() else ""
        if _is_commit(sha):
            return branch, sha
    packed = _read_text(os.path.join(location.common_dir, "packed-refs"), 1024 * 1024)
    if packed is not None:
        for entry in packed.splitlines():
            sha, _, name = entry.partition(" ")
            if name == ref and _is_commit(sha):
                return branch, sha
    return branch, None


# ---------------------------------------------------------------- local config and key


class Settings:
    """Hot-path view of ``.cursorfleet/config.toml`` (only privacy and retention knobs)."""

    __slots__ = ("display_max", "hash_commands", "max_session_bytes", "store_display")

    def __init__(self) -> None:
        self.store_display = True
        self.display_max = 200
        self.hash_commands = True
        self.max_session_bytes = DEFAULT_MAX_SESSION_BYTES


def load_settings(top_level: str, environ: Mapping[str, str]) -> Settings:
    """Read privacy/retention settings; fail toward LESS storage on any parse problem."""
    settings = Settings()
    override = environ.get("CURSORFLEET_MAX_SESSION_MB")
    if override and override.isdigit() and 1 <= int(override) <= 1024:
        settings.max_session_bytes = int(override) * 1024 * 1024
    path = os.path.join(top_level, ".cursorfleet", "config.toml")
    try:
        with open(path, "rb") as handle:
            data = handle.read(_MAX_CONFIG_BYTES + 1)
    except OSError:
        return settings
    if len(data) > _MAX_CONFIG_BYTES:
        settings.store_display = False
        return settings
    if b"privacy" not in data and b"retention" not in data:
        return settings
    try:
        import tomllib  # lazy: only when the user customized these sections

        parsed = tomllib.loads(data.decode("utf-8"))
        privacy = parsed.get("privacy", {})
        retention = parsed.get("retention", {})
        if isinstance(privacy, dict):
            if privacy.get("store_command_display") is False:
                settings.store_display = False
            if privacy.get("hash_commands") is False:
                settings.hash_commands = False
            max_chars = privacy.get("command_display_max_chars")
            if isinstance(max_chars, int) and not isinstance(max_chars, bool):
                settings.display_max = max(20, min(max_chars, 200))
        if isinstance(retention, dict) and "CURSORFLEET_MAX_SESSION_MB" not in environ:
            mb = retention.get("max_session_mb")
            if isinstance(mb, int) and not isinstance(mb, bool) and 1 <= mb <= 1024:
                settings.max_session_bytes = mb * 1024 * 1024
    except (ValueError, UnicodeDecodeError, OSError):
        settings.store_display = False
    return settings


def load_hmac_key(paths: RuntimePaths) -> bytes | None:
    """Return the per-install HMAC key, creating it (0600) on first use."""
    if untrusted_reason(paths.root) is not None:
        return None
    try:
        with open(paths.hmac_key, "rb") as handle:
            key = handle.read(256)
        if len(key) >= 16:
            return key
    except OSError:
        pass
    try:
        ensure_runtime_root(paths)
        write_private_file(paths.hmac_key, os.urandom(32), exclusive=True)
        with open(paths.hmac_key, "rb") as handle:
            key = handle.read(256)
        return key if len(key) >= 16 else None
    except OSError:
        return None


# ---------------------------------------------------------------- core


def _tool_cwd(payload: dict[str, object]) -> str | None:
    """Cursor tool cwd when the payload names a path that still exists (including a symlink)."""
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return None
    try:
        return cwd if os.path.lexists(cwd) else None
    except OSError:
        return None


def _anchor(payload: dict[str, object], environ: Mapping[str, str]) -> str | None:
    """Single resolution start: tool cwd when available, otherwise ``CURSOR_PROJECT_DIR``.

    Tool cwd is ``payload.cwd`` when that path lexists, else the hook process cwd.
    ``workspace_roots`` is never a start (ADR 0002 runtime inheritance).
    """
    cwd = _tool_cwd(payload)
    if cwd is not None:
        return cwd
    try:
        return os.getcwd()
    except OSError:
        pass
    project = environ.get("CURSOR_PROJECT_DIR")
    return project if project else None


def _resolve_runtime_location(
    payload: dict[str, object], environ: Mapping[str, str]
) -> GitLocation | None:
    """Inherited Git root for this hook, or ``None`` (record nothing, fail open).

    Validates the install marker before the caller may create a runtime directory.
    Never continues past an inner ``.git`` / gitfile / submodule boundary.
    """
    if is_ambiguous_workspace_roots(payload.get("workspace_roots")):
        return None
    anchor = _anchor(payload, environ)
    if anchor is None or is_external_symlink_anchor(anchor):
        return None
    try:
        real = safe_realpath(anchor)
    except (OSError, ValueError):
        return None
    location = resolve_inherited_location(real)
    if location is None or not has_install_marker(location.top_level):
        return None
    return location


def _dump(event: dict[str, object]) -> str:
    return json.dumps(event, separators=(",", ":"), ensure_ascii=True)


def _fit(event: dict[str, object], limit: int = 7800) -> str | None:
    """Serialize ``event`` under the line cap by dropping optional detail; else ``None``."""
    text = _dump(event)
    if len(text) <= limit:
        return text
    command = event.get("command")
    if isinstance(command, dict):
        command.pop("display", None)
        command.pop("display_truncated", None)
        text = _dump(event)
    paths = event.get("paths")
    while len(text) > limit and isinstance(paths, list) and len(paths) > 1:
        del paths[len(paths) // 2 :]
        text = _dump(event)
    return text if len(text) <= limit else None


def record(
    hook: str,
    payload: dict[str, object],
    *,
    environ: Mapping[str, str],
    now_ns: int,
    entropy: Callable[[], bytes] | None = None,
) -> int:
    """Normalize and append events for one hook payload. Returns the number written."""
    from cursorfleet.adapters.cursor import hook_normalize
    from cursorfleet.adapters.cursor.hook_sanitize import PathResolver

    location = _resolve_runtime_location(payload, environ)
    if location is None:
        return 0  # missing marker, rejected root, or not a git repo: record nothing
    paths = runtime_paths(location.common_dir)
    settings = load_settings(location.top_level, environ)
    branch = commit = None
    if hook in {"sessionStart", "subagentStart"}:
        branch, commit = read_head(location)
    uses_commands = hook not in _NO_COMMAND_HOOKS
    ctx = hook_normalize.HookContext(
        now_ns=now_ns,
        producer_version=__version__,
        resolver=PathResolver([location.top_level]),
        worktree_id=worktree_id_for(location.top_level),
        branch=branch,
        commit=commit,
        key=load_hmac_key(paths) if uses_commands and settings.hash_commands else None,
        store_display=settings.store_display,
        display_max=settings.display_max,
        hash_commands=settings.hash_commands,
        entropy=entropy,
    )
    events = hook_normalize.normalize(hook, payload, ctx)
    if not events:
        return 0
    writer = hook_normalize.writer_of(hook, payload)
    written = 0
    attached_session: str | None = None
    for event in events:
        text = _fit(event)
        session_id = event.get("session_id")
        if text is None or not isinstance(session_id, str):
            continue
        if append_event(
            paths,
            session_id,
            writer,
            text,
            now_ms=now_ns // 1_000_000,
            max_session_bytes=settings.max_session_bytes,
        ):
            written += 1
            attached_session = session_id
    if written and attached_session:
        active = environ.get("CURSORFLEET_ACTIVE_RUN", "").strip()
        if active:
            try:
                from cursorfleet.state.run_store import attach_session

                attach_session(paths.root, active, attached_session)
            except OSError:
                pass  # fail-open: run attach must never block hooks
    return written


def run(
    argv: Sequence[str],
    stdin: BinaryIO | None,
    *,
    environ: Mapping[str, str],
    now_ns: int,
    entropy: Callable[[], bytes] | None = None,
) -> str:
    """Process one hook invocation and return the reply text. Never raises."""
    hook = _hint(argv)
    try:
        payload = parse_payload(read_stdin_bytes(stdin))
        if payload is not None:
            name = payload.get("hook_event_name")
            if isinstance(name, str):
                hook = name
        if payload is not None and hook is not None and is_registrable(hook):
            record(hook, payload, environ=environ, now_ns=now_ns, entropy=entropy)
    except Exception:  # noqa: S110 - the hot path must fail open on anything
        pass
    return reply_for(hook)


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: BinaryIO | None = None,
    stdout: TextIO | None = None,
    environ: Mapping[str, str] | None = None,
    clock_ns: Callable[[], int] | None = None,
    entropy: Callable[[], bytes] | None = None,
) -> int:
    """Console-script entry point. Always returns 0."""
    try:
        reply = run(
            sys.argv if argv is None else argv,
            stdin if stdin is not None else getattr(sys.stdin, "buffer", None),
            environ=os.environ if environ is None else environ,
            now_ns=(clock_ns or time.time_ns)(),
            entropy=entropy,
        )
    except BaseException:  # last resort; even KeyboardInterrupt exits open
        reply = _ALLOW
    try:
        out = sys.stdout if stdout is None else stdout
        out.write(reply + "\n")
        out.flush()
    except Exception:  # noqa: S110
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
