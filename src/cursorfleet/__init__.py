"""CursorFleet: a local TUI and workflow harness for Cursor agent teams.

Keep this module import-free (stdlib only, no heavy imports): the hook hot path
imports ``cursorfleet`` on every hook invocation.
"""

__version__ = "0.0.1.dev0"

__all__ = ["__version__"]
