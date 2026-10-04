"""Merge CursorFleet's hook entries into ``.cursor/hooks.json`` and take them out again.

Design:

* Every registered hook runs exactly ``cursorfleet-hook`` with no arguments (the
  hook name comes from ``hook_event_name`` on stdin) and a short ``timeout``.
  There is no ``failClosed``: a missing binary or a crash must never block the
  user (observe-only; fail open).
* Only hooks in ``ALLOWED_V01_HOOKS`` may be emitted. ``assert_registrable`` is
  called on every code path that builds entries, so a forbidden hook name raises
  before anything is written (ADR 0004).
* No ``matcher`` is written: every hook matches everything. Narrowing is
  PROVISIONAL territory (ADR 0001 A3: matchers target tool types, subagent types
  or command text, whose exact values for custom ``cf-*`` subagents are unverified),
  and a wrong matcher would silently lose events. Revisit after live capture.
* User entries, other events, other top-level keys and key order are preserved.
  Formatting (indent, separators, trailing newline) is detected and reproduced.
* Entries are identified as ours by ``command == "cursorfleet-hook"``.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict

from cursorfleet.adapters.cursor.hook_policy import ALLOWED_V01_HOOKS, FORBIDDEN_HOOKS
from cursorfleet.adapters.cursor.templates import read_template

HOOK_COMMAND = "cursorfleet-hook"
HOOK_TIMEOUT_S = 5
SUPPORTED_VERSION = 1
Json = Any


class HooksJsonError(ValueError):
    """``hooks.json`` cannot be merged safely (invalid JSON or unexpected structure)."""


class JsonStyle(BaseModel):
    """How a JSON file was formatted, so we can write it back the same way."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    indent: int | None = 2  # None = single line; -1 = tab
    compact: bool = False  # separators (",", ":") when indent is None
    ensure_ascii: bool = False
    trailing_newline: bool = True
    crlf: bool = False


DEFAULT_STYLE = JsonStyle()


def dumps(data: Json, style: JsonStyle) -> str:
    indent: int | str | None = "\t" if style.indent == -1 else style.indent
    separators = (",", ":") if style.indent is None and style.compact else None
    if indent is not None:
        separators = (",", ": ")
    text = json.dumps(data, indent=indent, separators=separators, ensure_ascii=style.ensure_ascii)
    text += "\n" if style.trailing_newline else ""
    return text.replace("\n", "\r\n") if style.crlf else text


def _candidate_styles(trailing: bool) -> Iterable[JsonStyle]:
    for ascii_only in (False, True):
        for indent, compact in ((2, False), (4, False), (-1, False), (None, False), (None, True)):
            yield JsonStyle(
                indent=indent,
                compact=compact,
                ensure_ascii=ascii_only,
                trailing_newline=trailing,
            )


def detect_style(text: str, data: Json) -> tuple[JsonStyle, bool]:
    """Return ``(style, reproducible)``; reproducible means ``dumps(data, style) == text``."""
    crlf = "\r\n" in text
    normalized = text.replace("\r\n", "\n")
    trailing = normalized.endswith("\n")
    for candidate in _candidate_styles(trailing):
        style = candidate.model_copy(update={"crlf": crlf})
        if dumps(data, style) == text:
            return style, True
    return JsonStyle(trailing_newline=trailing, crlf=crlf), False


def managed_entry() -> dict[str, Json]:
    """The single entry we register per hook, from ``templates/cursor/hooks/entry.json``."""
    entry = json.loads(read_template("hooks/entry.json"))
    if entry.get("command") != HOOK_COMMAND or "failClosed" in entry or "matcher" in entry:
        msg = "hooks/entry.json must be exactly the cursorfleet-hook command with a timeout"
        raise HooksJsonError(msg)
    return {str(k): v for k, v in entry.items()}


def assert_registrable(events: Iterable[str]) -> tuple[str, ...]:
    """Raise unless every event is on the v0.1 allowlist and none is forbidden."""
    ordered = tuple(events)
    for name in ordered:
        if name in FORBIDDEN_HOOKS:
            msg = f"refusing to register forbidden hook {name!r} (ADR 0004)"
            raise HooksJsonError(msg)
        if name not in ALLOWED_V01_HOOKS:
            msg = f"refusing to register hook {name!r}: not in ALLOWED_V01_HOOKS"
            raise HooksJsonError(msg)
    return ordered


def is_ours(entry: object) -> bool:
    return isinstance(entry, dict) and entry.get("command") == HOOK_COMMAND


@dataclass
class HooksState:
    """What a merge did, recorded in the lockfile so uninstall can undo exactly it."""

    added_version: bool = False
    added_hooks_key: bool = False
    added_events: list[str] = field(default_factory=list)
    entries: dict[str, dict[str, Json]] = field(default_factory=dict)


@dataclass
class MergeResult:
    text: str
    state: HooksState
    style: JsonStyle
    reproducible: bool
    conflicts: list[str]


def _parse(text: str) -> dict[str, Json]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        msg = f"invalid JSON ({exc.msg} at line {exc.lineno})"
        raise HooksJsonError(msg) from exc
    if not isinstance(data, dict):
        msg = "top level must be a JSON object"
        raise HooksJsonError(msg)
    hooks = data.get("hooks")
    if hooks is not None:
        if not isinstance(hooks, dict):
            msg = '"hooks" must be an object'
            raise HooksJsonError(msg)
        for event, entries in hooks.items():
            if not isinstance(entries, list):
                msg = f"hooks.{event} must be a list"
                raise HooksJsonError(msg)
    version = data.get("version")
    if version is not None and version != SUPPORTED_VERSION:
        msg = f'unsupported hooks.json "version": {version!r} (expected {SUPPORTED_VERSION})'
        raise HooksJsonError(msg)
    return data


def merge(  # noqa: PLR0912
    existing: str | None,
    events: Iterable[str],
    previous: Mapping[str, Mapping[str, Json]] | None = None,
    previous_state: HooksState | None = None,
) -> MergeResult:
    """Return hooks.json text containing our entries for ``events``.

    ``previous`` are the entries recorded by an earlier install (event -> entry).
    Our entries not in ``events`` are removed if they are unmodified; an entry of
    ours that was modified by the user is a conflict, not silently overwritten.
    """
    wanted = assert_registrable(events)
    entry = managed_entry()
    previous = previous or {}
    state = HooksState(
        added_version=previous_state.added_version if previous_state else False,
        added_hooks_key=previous_state.added_hooks_key if previous_state else False,
        added_events=list(previous_state.added_events) if previous_state else [],
    )
    conflicts: list[str] = []

    if existing is None:
        data: dict[str, Json] = {"version": SUPPORTED_VERSION, "hooks": {}}
        style, reproducible = DEFAULT_STYLE, True
        state.added_version = state.added_hooks_key = True
    else:
        data = _parse(existing)
        style, reproducible = detect_style(existing, data)
        if "version" not in data:
            data = {"version": SUPPORTED_VERSION, **data}
            state.added_version = True
        if "hooks" not in data:
            data["hooks"] = {}
            state.added_hooks_key = True

    hooks: dict[str, list[Json]] = data["hooks"]
    for event in list(hooks):
        ours_idx = [i for i, e in enumerate(hooks[event]) if is_ours(e)]
        if len(ours_idx) > 1:
            conflicts.append(f"hooks.{event} has more than one cursorfleet-hook entry")
            continue
        recorded = previous.get(event)
        if event in wanted:
            if ours_idx:
                current = hooks[event][ours_idx[0]]
                if current != entry:
                    if recorded is not None and current == recorded:
                        hooks[event][ours_idx[0]] = dict(entry)
                    else:
                        conflicts.append(
                            f"hooks.{event} has a modified cursorfleet-hook entry; "
                            "restore it or run `cursorfleet uninstall --force`"
                        )
            continue
        # Event not wanted: drop our stale entry if unmodified.
        if ours_idx:
            current = hooks[event][ours_idx[0]]
            if recorded is not None and current == recorded:
                del hooks[event][ours_idx[0]]
                if not hooks[event] and event in state.added_events:
                    del hooks[event]
                    state.added_events.remove(event)
            else:
                conflicts.append(f"hooks.{event} has a cursorfleet-hook entry we did not record")

    for event in wanted:
        if event not in hooks:
            hooks[event] = []
            state.added_events.append(event)
        if not any(is_ours(e) for e in hooks[event]):
            hooks[event].append(dict(entry))
        state.entries[event] = dict(entry)

    return MergeResult(
        text=dumps(data, style),
        state=state,
        style=style,
        reproducible=reproducible,
        conflicts=conflicts,
    )


@dataclass
class UnmergeResult:
    text: str
    drift: list[str]
    now_empty: bool  # nothing but what we created remains


def unmerge(
    text: str,
    state: HooksState,
    style: JsonStyle,
    *,
    created: bool,
    force: bool = False,
) -> UnmergeResult:
    """Remove our entries (and only what we added) from ``text``."""
    data = _parse(text)
    drift: list[str] = []
    hooks = data.get("hooks")
    if isinstance(hooks, dict):
        for event, recorded in state.entries.items():
            entries = hooks.get(event)
            if not isinstance(entries, list):
                continue
            idx = [i for i, e in enumerate(entries) if is_ours(e)]
            for i in reversed(idx):
                if entries[i] != recorded and not force:
                    drift.append(f"hooks.{event}: cursorfleet-hook entry was modified")
                    continue
                del entries[i]
            if not entries and event in state.added_events:
                del hooks[event]
        if not hooks and state.added_hooks_key:
            del data["hooks"]
    if state.added_version and data.get("version") == SUPPORTED_VERSION:
        del data["version"]
    empty = created and not drift and data == {}
    return UnmergeResult(text=dumps(data, style), drift=drift, now_empty=empty)


def effective_events(text: str) -> dict[str, list[dict[str, Json]]]:
    """Parse any hooks.json into ``event -> [entries]``; non-object entries are skipped."""
    data = _parse_lenient(text)
    hooks = data.get("hooks")
    result: dict[str, list[dict[str, Json]]] = {}
    if isinstance(hooks, dict):
        for event, entries in hooks.items():
            if isinstance(entries, list):
                result[str(event)] = [e for e in entries if isinstance(e, dict)]
    return result


def _parse_lenient(text: str) -> dict[str, Json]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        msg = f"invalid JSON ({exc.msg} at line {exc.lineno})"
        raise HooksJsonError(msg) from exc
    if not isinstance(data, dict):
        msg = "top level must be a JSON object"
        raise HooksJsonError(msg)
    return data
