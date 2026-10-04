"""Stdlib-only identifier helpers (hot-path safe)."""

from __future__ import annotations

import os
import time

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

# Single source for the ULID shape; the Pydantic models and tests reuse it.
ULID_PATTERN = r"^[0-7][0-9A-HJKMNP-TV-Z]{25}$"
SAFE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:\-]{0,127}$"
AGENT_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:\-]{0,127}(#[A-Za-z0-9][A-Za-z0-9._:\-]{0,127})?$"


def _encode(value: int, length: int) -> str:
    chars = []
    for _ in range(length):
        chars.append(_CROCKFORD[value & 31])
        value >>= 5
    return "".join(reversed(chars))


def new_event_id(now_ms: int | None = None, entropy: bytes | None = None) -> str:
    """Return a 26-char ULID-style id: 48-bit ms timestamp + 80 random bits.

    Lexicographic order follows time at millisecond resolution. Ids created in
    the same millisecond are not guaranteed to be ordered.
    """
    ms = time.time_ns() // 1_000_000 if now_ms is None else now_ms
    if not 0 <= ms < 1 << 48:
        msg = "timestamp out of 48-bit range"
        raise ValueError(msg)
    raw = os.urandom(10) if entropy is None else entropy
    if len(raw) != 10:
        msg = "entropy must be exactly 10 bytes"
        raise ValueError(msg)
    return _encode(ms, 10) + _encode(int.from_bytes(raw, "big"), 16)


def derive_agent_id(agent_role: str | None, agent_instance_id: str | None) -> str | None:
    """Derive ``agent_id``: ``role#instance``; ``None`` when nothing identifies the agent.

    ``#`` is outside the SafeId alphabet, so the result is unambiguous. ``None``
    means "main agent or unattributed" (ADR 0003, PROVISIONAL until Q1 is answered).
    """
    if agent_role is None and agent_instance_id is None:
        return None
    if agent_instance_id is None:
        return agent_role
    return f"{agent_role or 'unknown'}#{agent_instance_id}"


_SAFE_ID_RE_SRC = SAFE_ID_PATTERN
_FS_SAFE_RE_SRC = r"^[A-Za-z0-9][A-Za-z0-9._\-]{0,127}$"
_WINDOWS_RESERVED = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)


def _sha256_hex(data: bytes) -> str:
    import hashlib  # lazy: hashlib costs ~2 ms of import time on the hot path

    return hashlib.sha256(data).hexdigest()


def worktree_id_for(top_level_realpath: str) -> str:
    """``wt-`` + first 12 hex of SHA-256 of the (normcased) realpath of a worktree top level.

    Callers must pass ``os.path.realpath(...)`` output. ``normcase`` makes the id stable
    on case-insensitive Windows paths; it is the identity function on POSIX.
    """
    norm = os.path.normcase(top_level_realpath)
    return "wt-" + _sha256_hex(norm.encode("utf-8", "surrogateescape"))[:12]


def safe_id(value: object, *, max_len: int = 128) -> str | None:
    """Return ``value`` if it is a valid SafeId, else a stable ``h-<24 hex>`` hash, else None.

    Non-strings, empty strings and absurdly long strings yield ``None`` (never raise).
    """
    import re

    if not isinstance(value, str) or not value or len(value) > 4096:
        return None
    if len(value) <= max_len and re.match(_SAFE_ID_RE_SRC, value):
        return value
    return "h-" + _sha256_hex(value.encode("utf-8", "surrogateescape"))[:24]


def fs_name_for(identifier: str) -> str:
    """Directory/file stem for an id: Windows-, macOS- and Linux-safe, never traversing.

    Ids that are not already portable (``:`` is illegal on Windows, reserved device
    names, trailing dots, upper case, over-long) are replaced by a stable ``h-<24 hex>`` hash.
    """
    import re

    if (
        re.match(_FS_SAFE_RE_SRC, identifier)
        and not identifier.endswith(".")
        and identifier.split(".", 1)[0].lower() not in _WINDOWS_RESERVED
        and not identifier.startswith("h-")  # keep the hash namespace collision-free
        and identifier == identifier.lower()  # case-insensitive filesystems (macOS, Windows)
    ):
        return identifier
    return "h-" + _sha256_hex(identifier.encode("utf-8", "surrogateescape"))[:24]
