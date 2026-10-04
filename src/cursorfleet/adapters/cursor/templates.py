"""Locate and render the ``templates/cursor`` kit templates.

Installed wheels carry the templates as package data at
``cursorfleet/_templates/cursor`` (hatch ``force-include``, see pyproject.toml).
In a source checkout they live in ``<repo>/templates/cursor``. Both are read
through :mod:`importlib.resources`-style traversables, so zip installs work too.

Rendering is plain ``{{placeholder}}`` substitution with no logic; unknown or
unfilled placeholders are errors, which keeps generated output deterministic.
"""

from __future__ import annotations

import re
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path

_PLACEHOLDER = re.compile(r"\{\{([A-Za-z0-9_.]+)\}\}")


class TemplateError(RuntimeError):
    """A template is missing or references an unknown placeholder."""


def templates_root() -> Traversable:
    """Return the root of the cursor templates (packaged copy first, repo copy second)."""
    packaged = resources.files("cursorfleet").joinpath("_templates", "cursor")
    if packaged.is_dir():
        return packaged
    # src/cursorfleet/adapters/cursor/templates.py -> repository root is parents[4]
    repo = Path(__file__).resolve().parents[4] / "templates" / "cursor"
    if repo.is_dir():
        return repo
    msg = "CursorFleet templates not found (broken install?)"
    raise TemplateError(msg)


def read_template(rel: str) -> str:
    """Read template ``rel`` (POSIX path under templates/cursor) as LF-normalized text."""
    node = templates_root()
    for part in rel.split("/"):
        node = node.joinpath(part)
    if not node.is_file():
        msg = f"missing template: {rel}"
        raise TemplateError(msg)
    return node.read_text(encoding="utf-8").replace("\r\n", "\n")


def render(template: str, values: dict[str, str]) -> str:
    """Substitute ``{{key}}`` placeholders; raise on unknown keys."""

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            msg = f"unknown template placeholder: {{{{{key}}}}}"
            raise TemplateError(msg)
        return values[key]

    return _PLACEHOLDER.sub(repl, template)
