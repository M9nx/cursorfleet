"""Stdlib-only validation for workspace-relative POSIX paths."""

from __future__ import annotations

import re

from cursorfleet.events.kinds import EXTERNAL_PATH

_DRIVE = re.compile(r"^[A-Za-z]:")
MAX_PATH_CHARS = 1024


def check_relative_posix(value: str, *, allow_external: bool = False) -> str:
    """Return ``value`` if it is a safe workspace-relative POSIX path, else raise ValueError.

    Rejects absolute paths, drive letters, backslashes, empty/``.``/``..`` segments
    and non-printable characters (control, bidi override, line separators).
    """
    if allow_external and value == EXTERNAL_PATH:
        return value
    if not value or len(value) > MAX_PATH_CHARS:
        msg = "path must be 1..1024 characters"
        raise ValueError(msg)
    if not value.isprintable():
        msg = "path contains non-printable characters"
        raise ValueError(msg)
    if "\\" in value or value.startswith("/") or _DRIVE.match(value):
        msg = "path must be workspace-relative with '/' separators"
        raise ValueError(msg)
    if any(part in {"", ".", ".."} for part in value.split("/")):
        msg = "path must not contain empty, '.' or '..' segments"
        raise ValueError(msg)
    return value


def check_not_in_git_dir(value: str) -> str:
    """Raise ``ValueError`` if ``value`` has a ``.git`` segment (any case); else return it.

    For locations CursorFleet *writes or deletes* (work dir, lockfile paths): a hostile
    config or lockfile must not be able to aim those operations at repository internals.
    """
    if any(part.lower() == ".git" for part in value.split("/")):
        msg = "path must not be inside .git"
        raise ValueError(msg)
    return value
