"""Spool line codec and the hot-path appender. Stdlib only, no pathlib/dataclasses/typing.

Line format (ADR 0002): ``<crc32 hex8> <space> <event json> "\\n"``, at most 8 KiB,
written with a single ``O_APPEND`` ``write``. One file per writer:
``spool/<session>/<writer>.jsonl``. When a writer file reaches ``ROTATE_BYTES`` it is
renamed to ``<writer>.<ms>-<pid>.jsonl`` and a fresh file is started.

Retention on the hot path (docs/privacy.md): when a session directory reaches its byte
cap the appender writes a ``.capped`` marker and stops appending for that session
instead of rotating forever; the indexer / ``events purge`` prune and clear the marker.
"""

from __future__ import annotations

import os
import zlib

from cursorfleet.events.ids import fs_name_for
from cursorfleet.state.runtime import (
    FILE_MODE,
    RuntimePaths,
    ensure_runtime_root,
    mkdir_private,
    untrusted_reason,
    write_private_file,
)

MAX_LINE_BYTES = 8192
ROTATE_BYTES = 4 * 1024 * 1024
DEFAULT_MAX_SESSION_BYTES = 50 * 1024 * 1024
CAPPED_MARKER = ".capped"
SPOOL_SUFFIX = ".jsonl"

_O_FLAGS = (
    os.O_WRONLY
    | os.O_APPEND
    | os.O_CREAT
    | getattr(os, "O_BINARY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_NONBLOCK", 0)  # a FIFO planted at the path fails (ENXIO) instead of hanging
)


def encode_line(event_json: str) -> bytes:
    """Return the on-disk bytes for one event. Raises ``ValueError`` if over the line cap."""
    body = event_json.encode("utf-8")
    line = b"%08x %s\n" % (zlib.crc32(body) & 0xFFFFFFFF, body)
    if len(line) > MAX_LINE_BYTES:
        msg = "spool line exceeds the 8 KiB cap"
        raise ValueError(msg)
    return line


def decode_line(line: bytes) -> str | None:
    """Return the event JSON text of one complete line (without ``\\n``), or ``None`` if bad.

    "Bad" = wrong shape, non-hex CRC, CRC mismatch or non-UTF-8 payload.
    """
    if len(line) < 10 or line[8:9] != b" ":
        return None
    try:
        expected = int(line[:8], 16)
    except ValueError:
        return None
    body = line[9:]
    if (zlib.crc32(body) & 0xFFFFFFFF) != expected:
        return None
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        return None


def session_dir(paths: RuntimePaths, session_id: str) -> str:
    return os.path.join(paths.spool, fs_name_for(session_id))


def writer_file(paths: RuntimePaths, session_id: str, writer: str) -> str:
    return os.path.join(session_dir(paths, session_id), fs_name_for(writer) + SPOOL_SUFFIX)


def session_bytes(directory: str) -> int:
    """Total size of the ``.jsonl`` files in a session directory (0 if missing)."""
    total = 0
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.name.endswith(SPOOL_SUFFIX):
                    try:
                        total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
    except OSError:
        return 0
    return total


def _open_append(path: str) -> int:
    return os.open(path, _O_FLAGS, FILE_MODE)


def _cap_reached(directory: str, max_session_bytes: int) -> bool:
    if session_bytes(directory) < max_session_bytes:
        return False
    try:
        write_private_file(os.path.join(directory, CAPPED_MARKER), b"", exclusive=True)
    except OSError:
        pass
    return True


def append_event(  # noqa: PLR0911, PLR0912
    paths: RuntimePaths,
    session_id: str,
    writer: str,
    event_json: str,
    *,
    now_ms: int,
    rotate_bytes: int = ROTATE_BYTES,
    max_session_bytes: int = DEFAULT_MAX_SESSION_BYTES,
) -> bool:
    """Append one event line. Returns False (never raises for I/O) if nothing was written.

    Concurrency: the write is a single ``os.write`` on an ``O_APPEND`` descriptor, so
    parallel hook processes sharing a writer file do not interleave within a line on
    POSIX local filesystems (PROVISIONAL, ADR 0001 Q5). Readers tolerate tears anyway.
    """
    try:
        data = encode_line(event_json)
    except ValueError:
        return False
    directory = session_dir(paths, session_id)
    path = os.path.join(directory, fs_name_for(writer) + SPOOL_SUFFIX)
    try:
        if untrusted_reason(paths.root) is not None:
            return False  # never write into a directory another user could have prepared
        if os.path.lexists(os.path.join(directory, CAPPED_MARKER)):
            return False
        try:
            fd = _open_append(path)
        except FileNotFoundError:
            ensure_runtime_root(paths)
            mkdir_private(directory)
            fd = _open_append(path)
        try:
            size = os.fstat(fd).st_size
            if size == 0 and os.name == "posix":
                os.fchmod(fd, FILE_MODE)  # explicit, not umask-dependent
            if size == 0 or size >= rotate_bytes:
                if size >= rotate_bytes:
                    os.close(fd)
                    fd = -1
                    _rotate(path, now_ms)
                    fd = _open_append(path)
                    if os.name == "posix":
                        os.fchmod(fd, FILE_MODE)
                if _cap_reached(directory, max_session_bytes):
                    return False
            written = os.write(fd, data)
            if written != len(data):  # torn by ENOSPC/EINTR: terminate the fragment
                os.write(fd, b"\n")
                return False
            return True
        finally:
            if fd >= 0:
                os.close(fd)
    except OSError:
        return False


def _rotate(path: str, now_ms: int) -> None:
    base = path[: -len(SPOOL_SUFFIX)]
    target = f"{base}.{now_ms}-{os.getpid()}"
    suffix = 0
    while os.path.lexists(target + SPOOL_SUFFIX) and suffix < 1000:  # never clobber a rotation
        suffix += 1
        target = f"{base}.{now_ms}-{os.getpid()}-{suffix}"
    try:
        os.rename(path, target + SPOOL_SUFFIX)
    except OSError:
        pass  # another process rotated it first; reopening creates/uses the new file
