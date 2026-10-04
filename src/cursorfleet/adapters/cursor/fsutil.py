"""Small filesystem helpers for the installer: hashing, safe printing, atomic writes.

Everything here is install-time only (never on the hook hot path).
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import stat
import tempfile
from pathlib import Path

DEFAULT_FILE_MODE = 0o644
MAX_FILE_BYTES = 1024 * 1024


class UnsafePathError(ValueError):
    """A managed path would leave the workspace or goes through a symlink."""


_REPARSE_POINT = 0x400  # FILE_ATTRIBUTE_REPARSE_POINT: symlinks and junctions on Windows


def is_link_like(path: Path) -> bool:
    """True for a symlink or, on Windows, any reparse point (junctions included).

    ``Path.is_symlink`` misses NTFS junctions, which redirect a directory just as well.
    """
    try:
        info = path.lstat()
    except OSError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & _REPARSE_POINT
    )


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n")


def sha256_text(text: str) -> str:
    """SHA-256 hex of ``text`` with CRLF normalized to LF.

    Normalizing keeps drift detection stable when git converts line endings.
    """
    return hashlib.sha256(normalize_newlines(text).encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_text(text: str) -> str:
    """Escape control and bidi characters so repo content cannot drive the terminal.

    Newlines and tabs pass through; everything else non-printable becomes ``\\uXXXX``.
    """
    out: list[str] = []
    for ch in text:
        if ch in "\n\t" or ch.isprintable():
            out.append(ch)
        elif ch == "\r":
            out.append("\\r")
        else:
            out.append(f"\\u{ord(ch):04x}")
    return "".join(out)


def read_text(path: Path) -> str | None:
    """Return file text, ``None`` if absent. Raises ``ValueError`` if unreadable as UTF-8.

    Reads at most ``MAX_FILE_BYTES``; larger files are refused rather than truncated.
    """
    try:
        if is_link_like(path):
            msg = f"{path.name} is a symlink"
            raise UnsafePathError(msg)
        if not path.exists():
            return None
        if not path.is_file():
            msg = f"{path.name} is not a regular file"
            raise ValueError(msg)
        if path.stat().st_size > MAX_FILE_BYTES:
            msg = f"{path.name} is larger than {MAX_FILE_BYTES} bytes"
            raise ValueError(msg)
        return path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        msg = f"{path.name} is not valid UTF-8"
        raise ValueError(msg) from exc
    except OSError as exc:
        msg = f"cannot read {path.name}: {exc.strerror or exc}"
        raise ValueError(msg) from exc


def ensure_inside(root: Path, rel: str) -> Path:
    """Resolve workspace-relative ``rel`` under ``root``; refuse escapes and symlinks.

    Every existing component (including the target) must not be a symlink, so a
    malicious repository cannot redirect a managed write elsewhere.
    """
    base = root.resolve()
    current = base
    for part in rel.split("/"):
        current = current / part
        if is_link_like(current):
            msg = f"refusing to follow symlink at {rel!r}"
            raise UnsafePathError(msg)
    target = base.joinpath(*rel.split("/"))
    try:
        target.resolve().relative_to(base)
    except ValueError as exc:
        msg = f"path {rel!r} escapes the workspace"
        raise UnsafePathError(msg) from exc
    return target


def atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` (UTF-8, no newline translation) to ``path`` atomically.

    Preserves the permission bits of an existing file; new files get 0644.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = DEFAULT_FILE_MODE
    with contextlib.suppress(OSError):
        mode = path.stat().st_mode & 0o777
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(text.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        with contextlib.suppress(OSError):
            os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


def remove_empty_dirs(root: Path, rel_dirs: list[str]) -> list[str]:
    """Remove each directory in ``rel_dirs`` (deepest first) when empty. Return removed ones."""
    removed: list[str] = []
    for rel in sorted(set(rel_dirs), key=lambda d: (-d.count("/"), d)):
        target = root.joinpath(*rel.split("/"))
        if is_link_like(target) or not target.is_dir():
            continue
        try:
            target.rmdir()
        except OSError:
            continue
        removed.append(rel)
    return removed
