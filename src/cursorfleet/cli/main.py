"""CursorFleet CLI entry point.

Command registration pattern
----------------------------
Each command group lives in its own module under ``cursorfleet.cli.commands``
and exposes ``register(app: typer.Typer) -> None``. Modules are discovered and
imported by :func:`register_commands` below, so adding a command group means
adding one new file and never editing this one (no merge conflicts between
phases). Modules are loaded in alphabetical order for deterministic help
output.

Example (``cursorfleet/cli/commands/doctor.py``)::

    import typer

    def register(app: typer.Typer) -> None:
        @app.command()
        def doctor() -> None:
            ...
"""

from __future__ import annotations

import importlib
import pkgutil

import typer

from cursorfleet import __version__
from cursorfleet.cli import commands as _commands_pkg

app = typer.Typer(
    name="cursorfleet",
    help="A local TUI and workflow harness for Cursor agent teams.",
    no_args_is_help=True,
    add_completion=False,
    # An unexpected error must not dump local variables (paths, config text, spool data)
    # into a pasted traceback (security review SR-08).
    pretty_exceptions_show_locals=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"cursorfleet {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """A local TUI and workflow harness for Cursor agent teams."""


def register_commands(target: typer.Typer) -> None:
    """Import every module in ``cursorfleet.cli.commands`` and call its ``register``."""
    for info in sorted(pkgutil.iter_modules(_commands_pkg.__path__), key=lambda m: m.name):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{_commands_pkg.__name__}.{info.name}")
        register = getattr(module, "register", None)
        if callable(register):
            register(target)


register_commands(app)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
