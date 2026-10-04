"""Strict frontmatter parser: a flat YAML subset, stdlib only (ADR 0006).

Accepted: ``key: value`` lines where the value is a plain scalar, a
double-quoted JSON-style string or a single-quoted string, ``true``/``false``,
an integer, or a list of such scalars written as ``- item`` lines or an inline
``[a, b]``. Rejected: nesting, anchors, tags, multi-line scalars, duplicate keys,
comments after values, and anything over the size caps. No YAML library is used,
so none of YAML's unsafe features exist here.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass

MAX_FRONTMATTER_BYTES = 16 * 1024
MAX_FRONTMATTER_LINES = 200
MAX_LIST_ITEMS = 100

Scalar = str | int | bool
Value = Scalar | list[Scalar]

_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_INT = re.compile(r"^-?[0-9]{1,15}$")
_FENCE = "---"
_TOML_FENCE = "+++"
_PLAIN_FORBIDDEN_START = set("&*!|>%@`{}[]#,'\"")


class FrontmatterError(ValueError):
    """Frontmatter is missing, malformed or outside the accepted subset."""


@dataclass(frozen=True)
class Document:
    meta: dict[str, Value]
    body: str


def _scalar(raw: str) -> Scalar:
    raw = raw.strip()
    if raw == "":
        msg = "empty value"
        raise FrontmatterError(msg)
    if raw[0] == '"':
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            msg = f"invalid double-quoted string: {raw[:40]!r}"
            raise FrontmatterError(msg) from exc
        if not isinstance(value, str):
            msg = "invalid double-quoted string"
            raise FrontmatterError(msg)
        return value
    if raw[0] == "'":
        if len(raw) < 2 or raw[-1] != "'" or "'" in raw[1:-1].replace("''", ""):
            msg = f"invalid single-quoted string: {raw[:40]!r}"
            raise FrontmatterError(msg)
        return raw[1:-1].replace("''", "'")
    if raw[0] in _PLAIN_FORBIDDEN_START:
        msg = f"unsupported YAML construct starting with {raw[0]!r}"
        raise FrontmatterError(msg)
    if " #" in raw:
        msg = "inline comments are not supported"
        raise FrontmatterError(msg)
    if raw == "true":
        return True
    if raw == "false":
        return False
    if _INT.match(raw):
        return int(raw)
    if raw.startswith(("- ", "? ")) or raw.endswith(":") or ": " in raw:
        msg = f"ambiguous plain scalar {raw[:40]!r} (quote it)"
        raise FrontmatterError(msg)
    return raw


def _inline_list(raw: str) -> list[Scalar]:
    inner = raw.strip()[1:-1].strip()
    if inner == "":
        return []
    # Split on commas outside double quotes.
    items: list[str] = []
    buf: list[str] = []
    in_quote = False
    escaped = False
    for ch in inner:
        if in_quote:
            buf.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_quote = False
        elif ch == '"':
            in_quote = True
            buf.append(ch)
        elif ch == ",":
            items.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    items.append("".join(buf))
    return [_scalar(item) for item in items]


def parse_frontmatter(text: str) -> Document:
    """Parse YAML ``---`` frontmatter (legacy artifacts and Cursor kit files)."""
    if text.startswith(_TOML_FENCE):
        return parse_toml_frontmatter(text)
    return _parse_yaml_frontmatter(text)


def parse_toml_frontmatter(text: str) -> Document:  # noqa: PLR0912
    """Parse TOML ``+++`` frontmatter (cursorfleet.artifact/0.1)."""
    if not text.startswith(_TOML_FENCE):
        msg = "TOML frontmatter must start with +++"
        raise FrontmatterError(msg)
    if len(text.encode("utf-8")) > MAX_FRONTMATTER_BYTES + 64 * 1024:
        msg = "artifact too large"
        raise FrontmatterError(msg)
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    close = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == _TOML_FENCE:
            close = index
            break
    if close is None:
        msg = "unclosed TOML frontmatter"
        raise FrontmatterError(msg)
    block = "\n".join(lines[1:close])
    try:
        meta_raw = tomllib.loads(block)
    except tomllib.TOMLDecodeError as exc:
        msg = f"invalid TOML frontmatter: {exc}"
        raise FrontmatterError(msg) from exc
    if not isinstance(meta_raw, dict):
        msg = "TOML frontmatter must be a table"
        raise FrontmatterError(msg)
    meta: dict[str, Value] = {}
    for key, value in meta_raw.items():
        if not _KEY.match(key):
            msg = f"invalid key {key!r}"
            raise FrontmatterError(msg)
        if isinstance(value, bool | int | str):
            meta[key] = value
        elif isinstance(value, list):
            if len(value) > MAX_LIST_ITEMS:
                msg = "too many list items"
                raise FrontmatterError(msg)
            meta[key] = [item for item in value if isinstance(item, bool | int | str)]
        else:
            msg = f"unsupported TOML value for {key!r}"
            raise FrontmatterError(msg)
    return Document(meta=meta, body="\n".join(lines[close + 1 :]))


def _parse_yaml_frontmatter(text: str) -> Document:  # noqa: PLR0912, PLR0915
    """Split ``text`` into frontmatter and body. Raises ``FrontmatterError``."""
    text = text.replace("\r\n", "\n")
    if text.startswith("\ufeff"):
        text = text[1:]
    lines = text.split("\n")
    if not lines or lines[0].rstrip() != _FENCE:
        msg = "file must start with a '---' frontmatter fence"
        raise FrontmatterError(msg)
    try:
        close = next(i for i in range(1, len(lines)) if lines[i].rstrip() == _FENCE)
    except StopIteration:
        msg = "frontmatter is not closed with '---'"
        raise FrontmatterError(msg) from None
    raw_lines = lines[1:close]
    if close > MAX_FRONTMATTER_LINES or sum(len(x) + 1 for x in raw_lines) > MAX_FRONTMATTER_BYTES:
        msg = "frontmatter is too large"
        raise FrontmatterError(msg)

    meta: dict[str, Value] = {}
    current_list: str | None = None
    for number, line in enumerate(raw_lines, start=2):
        if line.strip() == "":
            current_list = None
            continue
        if line.lstrip().startswith("#"):
            continue
        if line.startswith(("  - ", "- ", "    - ")) or line.strip() == "-":
            if current_list is None:
                msg = f"line {number}: list item without a key"
                raise FrontmatterError(msg)
            target = meta[current_list]
            if not isinstance(target, list):
                msg = f"line {number}: unexpected list item"
                raise FrontmatterError(msg)
            if len(target) >= MAX_LIST_ITEMS:
                msg = f"line {number}: too many list items"
                raise FrontmatterError(msg)
            target.append(_scalar(line.strip()[1:]))
            continue
        if line[0] in " \t":
            msg = f"line {number}: nested or indented values are not supported"
            raise FrontmatterError(msg)
        key, sep, rest = line.partition(":")
        if not sep or not _KEY.match(key):
            msg = f"line {number}: expected 'key: value'"
            raise FrontmatterError(msg)
        if key in meta:
            msg = f"line {number}: duplicate key {key!r}"
            raise FrontmatterError(msg)
        current_list = None
        rest = rest.strip()
        if rest == "":
            meta[key] = []
            current_list = key
        elif rest.startswith("["):
            if not rest.endswith("]"):
                msg = f"line {number}: unterminated inline list"
                raise FrontmatterError(msg)
            meta[key] = _inline_list(rest)
        else:
            try:
                meta[key] = _scalar(rest)
            except FrontmatterError as exc:
                msg = f"line {number}: {exc}"
                raise FrontmatterError(msg) from exc
    return Document(meta=meta, body="\n".join(lines[close + 1 :]))


def yaml_string(value: str) -> str:
    """Render ``value`` as a double-quoted scalar this parser (and YAML) can read back."""
    return json.dumps(value, ensure_ascii=False)
