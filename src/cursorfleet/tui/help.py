"""Help screen text (kept as data so tests and docs can assert on it)."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from cursorfleet.tui.gates import DISPLAY_ONLY
from cursorfleet.tui.layout import SINGLE_BELOW, TILE_FROM

KEYS: tuple[tuple[str, str], ...] = (
    ("o", "Workflow overview: lanes of agents (default)"),
    ("l", "Timeline: filterable event stream (newest first)"),
    ("w", "Worktrees: branch, HEAD, dirty, ahead/behind, owner"),
    ("g", "Gates: independent signals, display-only"),
    ("e", "Evidence: observed runs vs SELF-REPORTED declarations"),
    ("v", "Policy violations (placeholder until v0.2)"),
    ("j / k, arrows", "Move down / up (scrolls the detail when it has focus)"),
    ("Enter", "Open the detail for the selected item"),
    ("Esc", "Back: leave detail, close or clear the filter"),
    ("/", "Filter (timeline: agent: session: kind: risk: source: file: since: until: words)"),
    ("m", "Timeline: load more events"),
    ("p", "Pin the selected agent to the top of its lane (this session only)"),
    ("t", f"Toggle 2x2 tiled panes ({TILE_FROM}+ columns only)"),
    ("r", "Re-read now (index, git, artifacts); never fetches"),
    ("Tab", "Move focus between filter, list and detail"),
    ("?", "This help"),
    ("q", "Quit"),
)

HONESTY: tuple[str, ...] = (
    "CursorFleet v0.1 OBSERVES. It does not enforce, approve or block anything.",
    "obs = observed from a Cursor hook; drv = derived by CursorFleet; SELF = reported by an",
    "agent in a work artifact (a claim, not evidence; the author role can be forged).",
    "A silent agent is shown STALE / OFFLINE, never idle. No telemetry means UNKNOWN.",
    "session_id groups one Cursor chat; it is correlation only, not agent identity.",
    "Q1 and Q2 (subagent identity in hooks) are OPEN; incomplete lifecycles stay visible.",
    "Token and cost budgets are unknown: Cursor hooks do not expose them.",
    f"Gates: {DISPLAY_ONLY}. Each gate is its own signal; there is no overall score.",
    "Cloud agents are not visible. Local Cursor sessions only.",
    "Status is always written as text; colour is only a hint and NO_COLOR is honoured.",
)

LAYOUTS: tuple[str, ...] = (
    f"Under {SINGLE_BELOW} columns: one pane (Enter opens the detail, Esc returns).",
    f"{SINGLE_BELOW}-{TILE_FROM - 1} columns: list on the left, detail on the right.",
    f"{TILE_FROM}+ columns: same, or press t for a 2x2 grid of list, detail, recent events "
    "and gates/worktrees.",
)

SETUP: tuple[str, ...] = (
    "No data? Run `cursorfleet init --cursor` to install the hooks, then use Cursor.",
    "`cursorfleet doctor` explains what is missing.",
)


def help_text() -> Text:
    text = Text("CursorFleet help\n\n", style="bold")
    text.append("KEYS\n", style="bold")
    for key, meaning in KEYS:
        text.append(f"  {key:<14}", style="bold")
        text.append(f"{meaning}\n")
    text.append("\nLAYOUT\n", style="bold")
    for line in LAYOUTS:
        text.append(f"  {line}\n")
    text.append("\nHONESTY\n", style="bold")
    for line in HONESTY:
        text.append(f"  {line}\n")
    text.append("\nSETUP\n", style="bold")
    for line in SETUP:
        text.append(f"  {line}\n")
    text.append("\nPress Esc, ? or q to close.\n", style="dim")
    return text


class HelpScreen(ModalScreen[None]):
    """Modal help. Closing it never quits the app."""

    BINDINGS = [  # noqa: RUF012 - Textual convention
        Binding("escape", "close", "Close", show=False),
        Binding("question_mark", "close", "Close", show=False),
        Binding("q", "close", "Close", show=False),
    ]
    DEFAULT_CSS = """
    HelpScreen { align: center middle; }
    HelpScreen > VerticalScroll {
        width: 90%; max-width: 100; height: 90%; border: round $primary; padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield Static(help_text(), id="help_text")

    def action_close(self) -> None:
        self.dismiss(None)
