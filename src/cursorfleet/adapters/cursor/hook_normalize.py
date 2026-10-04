"""Allowlist normalizer: Cursor hook payload -> CursorFleet event dicts. Stdlib only.

Every handler reads an explicit list of payload fields; nothing is copied through
(no ``**payload``). Never read, so never persisted: ``user_email``, ``transcript_path``,
``agent_transcript_path``, ``cwd``, ``workspace_roots`` (only used to relativize paths in
``hook_main``), ``tool_input`` (except ``tool_input.command`` of Shell), ``tool_output``
(except the integer ``exitCode`` of a Shell result), ``edits``, ``task``, ``summary``,
``description``, ``error_message``, ``modified_files``, ``output``, ``agent_message``.

The output dicts are contract-tested against ``cursorfleet.events.models.Event``
(tests/unit/test_hook_normalize.py); the strings below mirror ``EventKind`` and friends
so this module need not import ``enum`` on the hot path.

PROVISIONAL (ADR 0001 section B, none of it observed live):
- Q1: whether tool hooks inside a subagent carry ``subagent_id``/``subagent_type``. If
  they do, events are attributed ``exact`` (id present) or ``inferred`` (type only); if
  not, they stay unattributed (``attribution: unknown``). We never guess from timing.
- Q2: how custom subagent names appear in ``subagent_type`` (the raw value is kept).
- ``subagentStop`` has no documented ``subagent_id``: it is attributed ``inferred`` and
  the reducer pairs it with a start by type, then ordering/duration.
- Whether ``postToolUse.tool_output`` for Shell is JSON with ``exitCode`` (the docs
  show this shape in an example only).
- ``session_id`` equals ``conversation_id`` for subagents (``parent_conversation_id`` is
  not modelled).
"""

from __future__ import annotations

import json
import math
import time

from cursorfleet.adapters.cursor.hook_sanitize import (
    PathResolver,
    is_verify_command,
    sanitize_command,
)
from cursorfleet.events.ids import derive_agent_id, new_event_id, safe_id

TYPE_CHECKING = False  # avoids importing ``typing`` (~4 ms) on the hook hot path
if TYPE_CHECKING:
    from collections.abc import Callable

SCHEMA_VERSION = "1.0"
PRODUCER = "cursor_hook"
_MAX_TOOL_OUTPUT_PARSE = 256 * 1024
_MAX_INT = 10**12

# Shared with the status/reducer layer: tool-name classes (lower-case).
SHELL_TOOLS = frozenset({"shell", "bash", "terminal"})


class HookContext:
    """Everything the normalizer needs besides the payload. Injectable for tests."""

    __slots__ = (
        "branch",
        "commit",
        "display_max",
        "entropy",
        "hash_commands",
        "key",
        "now_ns",
        "producer_version",
        "resolver",
        "store_display",
        "worktree_id",
    )

    def __init__(
        self,
        *,
        now_ns: int,
        producer_version: str,
        resolver: PathResolver,
        worktree_id: str | None = None,
        branch: str | None = None,
        commit: str | None = None,
        key: bytes | None = None,
        store_display: bool = True,
        display_max: int = 200,
        hash_commands: bool = True,
        entropy: Callable[[], bytes] | None = None,
    ) -> None:
        self.now_ns = now_ns
        self.producer_version = producer_version
        self.resolver = resolver
        self.worktree_id = worktree_id
        self.branch = branch
        self.commit = commit
        self.key = key
        self.store_display = store_display
        self.display_max = display_max
        self.hash_commands = hash_commands
        self.entropy = entropy  # returns 10 bytes; None means os.urandom


# ---------------------------------------------------------------- scalar helpers


def iso_utc(now_ns: int) -> str:
    seconds, rem = divmod(now_ns // 1_000_000, 1000)
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(seconds)) + f".{rem:03d}Z"


def _nonneg_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 0 <= value <= _MAX_INT else None
    if isinstance(value, float) and math.isfinite(value) and 0 <= value <= _MAX_INT:
        return round(value)
    return None


def _percent(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or not 0 <= value <= 1000:
        return None
    return float(value)


def _version(value: object) -> str | None:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        return None
    ok = value[0].isalnum() and value.isascii()
    return value if ok and all(c.isalnum() or c in "._+-" for c in value) else None


def _tool_name(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    cleaned = "".join(c if (c.isascii() and (c.isalnum() or c in "_:.-")) else "_" for c in value)
    return cleaned[:128] or None


def _branch(value: object) -> str | None:
    if not isinstance(value, str) or not 1 <= len(value) <= 255 or not value.isprintable():
        return None
    return value


def _put(target: dict[str, object], key: str, value: object) -> None:
    if value is not None:
        target[key] = value


def _metrics(**values: int | float | None) -> dict[str, object] | None:
    metrics: dict[str, object] = {k: v for k, v in values.items() if v is not None}
    return metrics or None


def _is_shell(tool_name: str | None) -> bool:
    return tool_name is not None and tool_name.lower() in SHELL_TOOLS


# ---------------------------------------------------------------- event construction


class _Builder:
    """Assembles event dicts that share one payload and context."""

    def __init__(self, hook: str, payload: dict[str, object], ctx: HookContext) -> None:
        self.hook = hook
        self.payload = payload
        self.ctx = ctx
        self.index = 0
        raw_session = payload.get("conversation_id")
        if hook in {"sessionStart", "sessionEnd"} and not isinstance(raw_session, str):
            raw_session = payload.get("session_id")
        if not isinstance(raw_session, str) or not raw_session:
            raw_session = payload.get("session_id")
        self.session_id = safe_id(raw_session)

    def event(
        self,
        kind: str,
        *,
        source: str = "observed",
        identity: bool = True,
        **fields: object,
    ) -> dict[str, object]:
        ctx = self.ctx
        now_ns = ctx.now_ns + self.index * 1_000_000
        self.index += 1
        entropy = ctx.entropy() if ctx.entropy is not None else None
        event: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "event_id": new_event_id(now_ns // 1_000_000, entropy),
            "ts": iso_utc(now_ns),
            "producer": PRODUCER,
            "producer_version": ctx.producer_version,
            "source": source,
            "kind": kind,
            "session_id": self.session_id,
            "hook": self.hook,
        }
        _put(event, "cursor_version", _version(self.payload.get("cursor_version")))
        _put(event, "generation_id", safe_id(self.payload.get("generation_id")))
        _put(event, "worktree_id", ctx.worktree_id)
        if identity:
            self._identity(event)
        for key, value in fields.items():
            _put(event, key, value)
        return event

    def _identity(self, event: dict[str, object]) -> None:
        payload = self.payload
        instance = safe_id(payload.get("subagent_id"))
        role = safe_id(payload.get("subagent_type"))
        if instance is None and role is None:
            return
        _put(event, "agent_role", role)
        _put(event, "agent_instance_id", instance)
        _put(event, "agent_id", derive_agent_id(role, instance))
        event["attribution"] = "exact" if instance is not None else "inferred"

    def command(self, raw: object, **kw: int | None) -> dict[str, object] | None:
        ctx = self.ctx
        return sanitize_command(
            raw,
            key=ctx.key,
            store_display=ctx.store_display,
            display_max=ctx.display_max,
            hash_commands=ctx.hash_commands,
            exit_code=kw.get("exit_code"),
            duration_ms=kw.get("duration_ms"),
        )


def _shell_command_text(payload: dict[str, object]) -> object:
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        return tool_input.get("command")
    return None


def _exit_code_from_output(payload: dict[str, object]) -> int | None:
    """Extract only an integer ``exitCode`` from a Shell ``tool_output``; drop the rest."""
    output = payload.get("tool_output")
    parsed: object = None
    if isinstance(output, dict):
        parsed = output
    elif isinstance(output, str) and len(output) <= _MAX_TOOL_OUTPUT_PARSE:
        stripped = output.lstrip()
        if stripped.startswith("{"):
            try:
                parsed = json.loads(stripped)
            except ValueError:
                parsed = None
    if isinstance(parsed, dict):
        code = parsed.get("exitCode", parsed.get("exit_code"))
        if isinstance(code, int) and not isinstance(code, bool) and -1024 <= code <= 1024:
            return code
    return None


_STOP_STATUS: dict[str, tuple[str, str]] = {
    "completed": ("waiting", "ok"),
    "aborted": ("idle", "interrupted"),
    "error": ("error", "failed"),
}
_END_OUTCOME: dict[str, str] = {
    "completed": "ok",
    "error": "failed",
    "aborted": "interrupted",
    "window_close": "interrupted",
    "user_close": "interrupted",
}
_FAILURE_OUTCOME: dict[str, str] = {
    "error": "failed",
    "timeout": "timeout",
    "permission_denied": "permission_denied",
}
_SUBAGENT_OUTCOME: dict[str, str] = {"completed": "ok", "aborted": "interrupted", "error": "failed"}


# ---------------------------------------------------------------- handlers


def _h_session_start(b: _Builder) -> list[dict[str, object]]:
    return [b.event("session.started", branch=b.ctx.branch, commit=b.ctx.commit)]


def _h_session_end(b: _Builder) -> list[dict[str, object]]:
    p = b.payload
    final = p.get("final_status")
    key = final if isinstance(final, str) and final in _END_OUTCOME else p.get("reason")
    outcome = _END_OUTCOME.get(key, "unknown") if isinstance(key, str) else "unknown"
    status = {"ok": "done", "failed": "error"}.get(outcome)
    return [
        b.event(
            "session.stopped",
            outcome=outcome,
            status=status,
            metrics=_metrics(duration_ms=_nonneg_int(p.get("duration_ms"))),
        )
    ]


def _h_stop(b: _Builder) -> list[dict[str, object]]:
    p = b.payload
    raw_status = p.get("status")
    status, outcome = (
        _STOP_STATUS.get(raw_status, ("unknown", "unknown"))
        if isinstance(raw_status, str)
        else ("unknown", "unknown")
    )
    return [
        b.event(
            "status.changed",
            status=status,
            outcome=outcome,
            metrics=_metrics(loop_count=_nonneg_int(p.get("loop_count"))),
        )
    ]


def _h_pre_tool(b: _Builder) -> list[dict[str, object]]:
    name = _tool_name(b.payload.get("tool_name"))
    command = b.command(_shell_command_text(b.payload)) if _is_shell(name) else None
    return [
        b.event(
            "tool.started",
            tool_name=name,
            tool_use_id=safe_id(b.payload.get("tool_use_id")),
            command=command,
        )
    ]


def _verify_event(
    b: _Builder, command: dict[str, object] | None, outcome: str, name: str | None
) -> list[dict[str, object]]:
    if command is None:
        return []
    display = command.get("display")
    argv0, sub = command.get("argv0"), command.get("subcommand")
    if not is_verify_command(
        argv0 if isinstance(argv0, str) else None,
        sub if isinstance(sub, str) else None,
        display if isinstance(display, str) else None,
    ):
        return []
    return [
        b.event(
            "verification.observed",
            source="derived",
            tool_name=name,
            tool_use_id=safe_id(b.payload.get("tool_use_id")),
            outcome=outcome,
            command=command,
        )
    ]


def _h_post_tool(b: _Builder) -> list[dict[str, object]]:
    p = b.payload
    name = _tool_name(p.get("tool_name"))
    duration = _nonneg_int(p.get("duration"))
    command = None
    exit_code = None
    if _is_shell(name):
        exit_code = _exit_code_from_output(p)
        command = b.command(_shell_command_text(p), exit_code=exit_code, duration_ms=duration)
    events = [
        b.event(
            "tool.completed",
            tool_name=name,
            tool_use_id=safe_id(p.get("tool_use_id")),
            outcome="ok",
            command=command,
            metrics=_metrics(duration_ms=duration),
        )
    ]
    test_outcome = "unknown" if exit_code is None else ("ok" if exit_code == 0 else "failed")
    return events + _verify_event(b, command, test_outcome, name)


def _h_post_tool_failure(b: _Builder) -> list[dict[str, object]]:
    p = b.payload
    name = _tool_name(p.get("tool_name"))
    duration = _nonneg_int(p.get("duration"))
    failure = p.get("failure_type")
    outcome = _FAILURE_OUTCOME.get(failure, "failed") if isinstance(failure, str) else "failed"
    if p.get("is_interrupt") is True:
        outcome = "interrupted"
    command = None
    if _is_shell(name):
        command = b.command(_shell_command_text(p), duration_ms=duration)
    events = [
        b.event(
            "tool.failed",
            tool_name=name,
            tool_use_id=safe_id(p.get("tool_use_id")),
            outcome=outcome,
            command=command,
            metrics=_metrics(duration_ms=duration),
        )
    ]
    return events + _verify_event(b, command, outcome, name)


def _h_before_shell(b: _Builder) -> list[dict[str, object]]:
    return [b.event("tool.started", tool_name="Shell", command=b.command(b.payload.get("command")))]


def _h_after_shell(b: _Builder) -> list[dict[str, object]]:
    duration = _nonneg_int(b.payload.get("duration"))
    return [
        b.event(
            "tool.completed",
            tool_name="Shell",
            command=b.command(b.payload.get("command"), duration_ms=duration),
            metrics=_metrics(duration_ms=duration),
        )
    ]


def _h_file_edit(b: _Builder) -> list[dict[str, object]]:
    path = b.ctx.resolver.relativize(b.payload.get("file_path"))
    return [b.event("file.changed", paths=[{"path": path, "op": "unknown"}])]


def _h_pre_compact(b: _Builder) -> list[dict[str, object]]:
    p = b.payload
    return [
        b.event(
            "context.compacted",
            metrics=_metrics(
                context_usage_percent=_percent(p.get("context_usage_percent")),
                context_tokens=_nonneg_int(p.get("context_tokens")),
                context_window_size=_nonneg_int(p.get("context_window_size")),
                message_count=_nonneg_int(p.get("message_count")),
            ),
        )
    ]


def _h_subagent_start(b: _Builder) -> list[dict[str, object]]:
    p = b.payload
    return [
        b.event(
            "subagent.started",
            branch=_branch(p.get("git_branch")) or b.ctx.branch,
            commit=b.ctx.commit if p.get("git_branch") is None else None,
            tool_use_id=safe_id(p.get("tool_call_id")),
        )
    ]


def _h_subagent_stop(b: _Builder) -> list[dict[str, object]]:
    p = b.payload
    raw = p.get("status")
    outcome = _SUBAGENT_OUTCOME.get(raw, "unknown") if isinstance(raw, str) else "unknown"
    return [
        b.event(
            "subagent.stopped",
            outcome=outcome,
            metrics=_metrics(
                duration_ms=_nonneg_int(p.get("duration_ms")),
                message_count=_nonneg_int(p.get("message_count")),
                tool_call_count=_nonneg_int(p.get("tool_call_count")),
                loop_count=_nonneg_int(p.get("loop_count")),
            ),
        )
    ]


_HANDLERS = {
    "sessionStart": _h_session_start,
    "sessionEnd": _h_session_end,
    "stop": _h_stop,
    "preToolUse": _h_pre_tool,
    "postToolUse": _h_post_tool,
    "postToolUseFailure": _h_post_tool_failure,
    "beforeShellExecution": _h_before_shell,
    "afterShellExecution": _h_after_shell,
    "afterFileEdit": _h_file_edit,
    "preCompact": _h_pre_compact,
    "subagentStart": _h_subagent_start,
    "subagentStop": _h_subagent_stop,
}


def handled_hooks() -> frozenset[str]:
    """Hook names this module can normalize (must equal ``ALLOWED_V01_HOOKS``; tested)."""
    return frozenset(_HANDLERS)


def session_id_of(hook: str, payload: dict[str, object]) -> str | None:
    return _Builder(hook, payload, _NULL_CTX).session_id


def writer_of(hook: str, payload: dict[str, object]) -> str:
    """Spool writer name: the subagent instance id when a tool hook carries one, else ``main``.

    ``subagentStart``/``subagentStop`` are emitted on behalf of the parent, so they go to
    ``main`` (PROVISIONAL, ADR 0002: collapses to one file per session if Q1 is refuted).
    """
    if hook in {"subagentStart", "subagentStop"}:
        return "main"
    return safe_id(payload.get("subagent_id")) or "main"


def normalize(hook: str, payload: dict[str, object], ctx: HookContext) -> list[dict[str, object]]:
    """Return zero or more event dicts for an allowed hook. Never copies unlisted fields."""
    handler = _HANDLERS.get(hook)
    if handler is None:
        return []
    builder = _Builder(hook, payload, ctx)
    if builder.session_id is None:
        return []
    return handler(builder)


_NULL_CTX = HookContext(now_ns=0, producer_version="0", resolver=PathResolver([]))

__all__ = [
    "HookContext",
    "handled_hooks",
    "iso_utc",
    "normalize",
    "session_id_of",
    "writer_of",
]
