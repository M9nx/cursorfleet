"""Delimited, idempotent managed blocks inside files such as ``AGENTS.md``.

CursorFleet never overwrites a user's ``AGENTS.md``: it appends one clearly
delimited block, rewrites only that block on update, and removes exactly what it
inserted on uninstall (including the separator recorded at insert time).
"""

from __future__ import annotations

BEGIN = (
    "<!-- cursorfleet:begin (managed by `cursorfleet init`; "
    "`cursorfleet uninstall` removes this block) -->"
)
END = "<!-- cursorfleet:end -->"
_BEGIN_PREFIX = "<!-- cursorfleet:begin"


class BlockError(ValueError):
    """The managed markers in a file are malformed (unpaired or duplicated)."""


def make_block(body: str) -> str:
    """Return the block text (LF newlines, no trailing newline)."""
    return f"{BEGIN}\n{body.strip(chr(10))}\n{END}"


def newline_for(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _to_style(block: str, nl: str) -> str:
    return block if nl == "\n" else block.replace("\n", nl)


def find_block(text: str) -> tuple[int, int] | None:
    """Return the ``(start, end)`` span of the managed block, or ``None``.

    Raises ``BlockError`` if markers are unpaired or appear more than once.
    """
    start = text.find(_BEGIN_PREFIX)
    if start == -1:
        if END in text:
            msg = "found a CursorFleet end marker without a begin marker"
            raise BlockError(msg)
        return None
    if text.find(_BEGIN_PREFIX, start + 1) != -1:
        msg = "found more than one CursorFleet begin marker"
        raise BlockError(msg)
    end_idx = text.find(END, start)
    if end_idx == -1:
        msg = "found a CursorFleet begin marker without an end marker"
        raise BlockError(msg)
    if text.find(END, end_idx + 1) != -1:
        msg = "found more than one CursorFleet end marker"
        raise BlockError(msg)
    return start, end_idx + len(END)


def block_text(text: str) -> str | None:
    """Return the current managed block in ``text`` with LF newlines, or ``None``."""
    span = find_block(text)
    if span is None:
        return None
    return text[span[0] : span[1]].replace("\r\n", "\n")


def insert_block(text: str, block: str) -> tuple[str, str]:
    """Append ``block`` to ``text``. Return ``(new_text, prefix)``.

    ``prefix`` is the separator inserted before the block; record it so that
    ``remove_block`` restores the original bytes.
    """
    nl = newline_for(text)
    if text == "":
        prefix = ""
    elif text.endswith("\n"):
        prefix = nl
    else:
        prefix = nl + nl
    return text + prefix + _to_style(block, nl) + nl, prefix


def replace_block(text: str, block: str) -> str:
    """Replace the existing managed block, keeping everything else byte-identical."""
    span = find_block(text)
    if span is None:
        msg = "no managed block to replace"
        raise BlockError(msg)
    return text[: span[0]] + _to_style(block, newline_for(text)) + text[span[1] :]


def remove_block(text: str, prefix: str) -> str:
    """Remove the managed block, the separator ``prefix`` and one trailing newline."""
    span = find_block(text)
    if span is None:
        return text
    start, end = span
    if prefix and text[:start].endswith(prefix):
        start -= len(prefix)
    for nl in ("\r\n", "\n"):
        if text.startswith(nl, end):
            end += len(nl)
            break
    return text[:start] + text[end:]
