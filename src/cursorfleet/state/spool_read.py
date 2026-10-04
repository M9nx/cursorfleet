"""Corruption-tolerant spool reader. Reports counts; never raises on bad data.

Tolerated and counted: missing/garbled CRC prefix, CRC mismatch, non-UTF-8 or non-JSON
payloads, over-long lines, events failing the Pydantic model, unknown ``schema_version``,
and a torn tail (final line without a newline). A torn fragment followed directly by a
good record (a killed writer, then a normal append) is resynchronised so the good
record is not lost.
"""

from __future__ import annotations

import json
import os
import re
import zlib
from dataclasses import dataclass, field

from pydantic import ValidationError

from cursorfleet.events.ids import fs_name_for
from cursorfleet.events.kinds import SCHEMA_VERSION
from cursorfleet.events.models import Event
from cursorfleet.state.runtime import RuntimePaths, untrusted_reason
from cursorfleet.state.spool import MAX_LINE_BYTES, SPOOL_SUFFIX, decode_line

MAX_READ_BYTES = 32 * 1024 * 1024
_RESYNC = re.compile(rb'[0-9a-f]{8} \{"schema_version"')


@dataclass
class Corruption:
    """Counters for everything the reader skipped."""

    bad_format: int = 0
    bad_crc: int = 0
    bad_json: int = 0
    invalid_event: int = 0
    unknown_version: int = 0
    oversize: int = 0
    misplaced: int = 0  # event whose session id does not match its spool directory
    torn_tail: int = 0
    resynced: int = 0  # good records recovered after a torn/garbled prefix (informational)

    @property
    def total(self) -> int:
        return (
            self.bad_format
            + self.bad_crc
            + self.bad_json
            + self.invalid_event
            + self.unknown_version
            + self.oversize
            + self.misplaced
            + self.torn_tail
        )

    def add(self, other: Corruption) -> None:
        for name in self.__dataclass_fields__:
            setattr(self, name, getattr(self, name) + getattr(other, name))

    def to_dict(self) -> dict[str, int]:
        data = {name: getattr(self, name) for name in self.__dataclass_fields__}
        data["total"] = self.total
        return data

    @classmethod
    def from_dict(cls, data: dict[str, int]) -> Corruption:
        return cls(**{n: int(data.get(n, 0)) for n in cls.__dataclass_fields__})


@dataclass
class FileRead:
    events: list[Event] = field(default_factory=list)
    new_offset: int = 0
    size: int = 0
    fingerprint: str | None = None
    torn_tail_bytes: int = 0
    corruption: Corruption = field(default_factory=Corruption)


def fingerprint_of(first_line: bytes) -> str:
    return f"{zlib.crc32(first_line) & 0xFFFFFFFF:08x}"


def _parse_event(text: str, counts: Corruption) -> Event | None:
    try:
        obj = json.loads(text)
    except (ValueError, RecursionError):
        counts.bad_json += 1
        return None
    if not isinstance(obj, dict):
        counts.bad_json += 1
        return None
    if obj.get("schema_version") != SCHEMA_VERSION:
        counts.unknown_version += 1
        return None
    try:
        return Event.model_validate(obj)
    except ValidationError:
        counts.invalid_event += 1
        return None


def _decode_with_resync(line: bytes, counts: Corruption) -> str | None:
    text = decode_line(line)
    if text is not None:
        return text
    for match in _RESYNC.finditer(line, 1):
        text = decode_line(line[match.start() :])
        if text is not None:
            counts.bad_crc += 1  # the torn/garbled prefix
            counts.resynced += 1
            return text
    if len(line) < 10 or line[8:9] != b" ":
        counts.bad_format += 1
    else:
        counts.bad_crc += 1
    return None


def peek_fingerprint(path: str | os.PathLike[str]) -> str | None:
    """Fingerprint of the first complete line (stable across rotation renames), or None."""
    try:
        with open(path, "rb") as handle:
            head = handle.read(MAX_LINE_BYTES)
    except OSError:
        return None
    newline = head.find(b"\n")
    return fingerprint_of(head[:newline]) if newline >= 0 else None


def read_file(path: str | os.PathLike[str], offset: int = 0, *, final: bool = False) -> FileRead:
    """Read complete lines from ``offset``. Never raises on content or missing files.

    ``new_offset`` stops before an unterminated tail, so an incremental reader retries it
    once the writer finishes. With ``final=True`` (one-shot replay/export) the tail is
    also counted as ``torn_tail``.
    """
    result = FileRead(new_offset=offset)
    try:
        with open(path, "rb") as handle:
            result.size = os.fstat(handle.fileno()).st_size
            head = handle.read(MAX_LINE_BYTES)
            newline = head.find(b"\n")
            if newline >= 0:
                result.fingerprint = fingerprint_of(head[:newline])
            if offset > result.size:
                offset = 0  # truncated or replaced file: start over (dedupe handles repeats)
                result.new_offset = 0
            handle.seek(offset)
            data = handle.read(MAX_READ_BYTES)
    except OSError:
        return result
    consumed = 0
    while True:
        end = data.find(b"\n", consumed)
        if end < 0:
            break
        line = data[consumed:end]
        consumed = end + 1
        if not line.strip():
            continue
        if len(line) > MAX_LINE_BYTES:
            result.corruption.oversize += 1
            continue
        text = _decode_with_resync(line, result.corruption)
        if text is None:
            continue
        event = _parse_event(text, result.corruption)
        if event is not None:
            result.events.append(event)
    tail = data[consumed:]
    if consumed == 0 and len(data) >= MAX_READ_BYTES:
        # one unterminated run longer than the whole read window: skip it so we make progress
        result.corruption.oversize += 1
        consumed = len(data)
        tail = b""
    result.new_offset = offset + consumed
    result.torn_tail_bytes = len(tail)
    if tail.strip() and final:
        result.corruption.torn_tail += 1
    return result


def list_spool_files(paths: RuntimePaths, session_id: str | None = None) -> list[str]:
    """All ``*.jsonl`` files under ``spool/`` (or one session), sorted for determinism."""
    root = paths.spool
    found: list[str] = []
    if untrusted_reason(paths.root) is not None:
        return found  # spool files in a directory others could write are not trusted input
    try:
        if session_id is not None:
            directories = [os.path.join(root, fs_name_for(session_id))]
        else:
            with os.scandir(root) as entries:
                directories = sorted(e.path for e in entries if e.is_dir(follow_symlinks=False))
    except OSError:
        return []
    for directory in directories:
        try:
            with os.scandir(directory) as entries:
                found.extend(
                    sorted(
                        e.path
                        for e in entries
                        if e.name.endswith(SPOOL_SUFFIX) and e.is_file(follow_symlinks=False)
                    )
                )
        except OSError:
            continue
    return found


def accept_placement(path: str, event: Event, counts: Corruption) -> bool:
    """An event is only trusted inside the spool directory named for its own session."""
    if os.path.basename(os.path.dirname(path)) == fs_name_for(event.session_id):
        return True
    counts.misplaced += 1
    return False


def read_all(
    paths: RuntimePaths, session_id: str | None = None
) -> tuple[list[Event], Corruption, int]:
    """Read every spool file once. Returns (events, corruption, files_read).

    With ``session_id`` only that session's directory is read and events are filtered to
    the id, so a forged file cannot smuggle another session in.
    """
    events: list[Event] = []
    corruption = Corruption()
    files = list_spool_files(paths, session_id)
    for file in files:
        result = read_file(file, 0, final=True)
        corruption.add(result.corruption)
        events.extend(
            e
            for e in result.events
            if (session_id is None or e.session_id == session_id)
            and accept_placement(file, e, corruption)
        )
    return events, corruption, len(files)
