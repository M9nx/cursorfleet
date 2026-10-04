"""The Textual application: one screen, six views, three responsive layouts.

The app reads through a :class:`DataSource` (SQLite projection + read-only git + artifact
scan) on a worker thread and renders pure ``Text`` produced by :mod:`cursorfleet.tui.views`.
It holds no prompts, thinking or file contents because none exist in its inputs, and it
makes no network calls.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from cursorfleet import __version__
from cursorfleet.events.models import Event
from cursorfleet.state.event_store import DEFAULT_PAGE, MAX_PAGE, EventFilter
from cursorfleet.tui import views
from cursorfleet.tui.data import DataSource, FleetData
from cursorfleet.tui.filters import parse_timeline_filter
from cursorfleet.tui.help import HelpScreen
from cursorfleet.tui.layout import SINGLE, SPLIT, TILED, layout_for
from cursorfleet.tui.theme import Theme, fmt_ts, plural, safe
from cursorfleet.tui.watch import WatchFactory, default_watch_factory

DEFAULT_REFRESH_S = 2.0
PAGE_STEP = DEFAULT_PAGE

KEYS_WIDE = (
    "q quit | ? help | / filter | j/k move | Enter detail | p pin | t tile | "
    "o overview | l timeline | w worktrees | g gates | e evidence | v violations | r refresh"
)
KEYS_NARROW = "? help  q quit  / filter  o l w g e v  p pin  r refresh"


class Source(Protocol):
    """What the app needs from a data source (``DataSource`` or a test double)."""

    def now(self) -> Any: ...

    def load(
        self, flt: EventFilter | None = None, *, limit: int = 200, force_git: bool = False
    ) -> FleetData: ...

    def recent_tools(self, session_id: str, agent_key: str, limit: int = 6) -> list[Event]: ...


class Tile(VerticalScroll, can_focus=False):
    """A read-only pane of the 2x2 grid."""


class FleetList(OptionList):
    """The primary list. Rows are ``Text``; headers are disabled options."""


CSS = """
Screen { layout: vertical; }
#titlebar { height: 1; padding: 0 1; background: $boost; }
#banner { height: auto; max-height: 3; padding: 0 1; display: none; }
#banner.has-problems { display: block; }
#filter { height: 1; border: none; padding: 0 1; display: none; }
#filter.open { display: block; }
#statusbar { height: 1; padding: 0 1; background: $boost; }
#body { height: 1fr; }
#list, #detail, .tile { border: round $primary; padding: 0 1; }
#list:focus, #detail:focus { border: heavy $accent; }
#body.single { layout: vertical; }
#body.single #detail, #body.single .tile { display: none; }
#body.single.show-detail #list { display: none; }
#body.single.show-detail #detail { display: block; height: 1fr; }
#body.split { layout: horizontal; }
#body.split #list { width: 45%; height: 1fr; }
#body.split #detail { width: 1fr; height: 1fr; }
#body.split .tile { display: none; }
#body.tiled { layout: grid; grid-size: 2 2; }
#body.tiled #list, #body.tiled #detail, #body.tiled .tile { width: 1fr; height: 1fr; }
"""


class CursorFleetApp(App[None]):
    """CursorFleet v0.1 (Observe)."""

    TITLE = "CursorFleet"
    CSS = CSS
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [  # noqa: RUF012 - Textual convention
        Binding("q", "quit", "Quit"),
        Binding("question_mark", "help", "Help"),
        Binding("slash", "filter", "Filter"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("p", "pin", "Pin"),
        Binding("t", "tile", "Tile"),
        Binding("g", "show('gates')", "Gates"),
        Binding("w", "show('worktrees')", "Worktrees"),
        Binding("v", "show('violations')", "Violations"),
        Binding("e", "show('evidence')", "Evidence"),
        Binding("o", "show('overview')", "Overview"),
        Binding("l", "show('timeline')", "Timeline"),
        Binding("r", "refresh", "Refresh"),
        Binding("m", "more", "More"),
        Binding("escape", "leave", "Back"),
    ]

    def __init__(  # noqa: PLR0913 - keyword-only wiring points, all optional
        self,
        source: Source,
        *,
        refresh_s: float = DEFAULT_REFRESH_S,
        watch: bool = True,
        watch_factory: WatchFactory | None = None,
        spool_dir: str | None = None,
        mono: bool | None = None,
    ) -> None:
        # Textual pops NO_COLOR from the environment in App.__init__: read it first.
        no_color = os.environ.get("NO_COLOR") is not None if mono is None else mono
        super().__init__()
        self.source = source
        self.refresh_s = max(0.25, refresh_s)
        self.ui = views.UiState(theme=Theme(mono=no_color))
        self.view = "overview"
        self.data = FleetData(now=source.now())
        self.tile_enabled = False
        self.detail_open = False
        self.flash_message = ""
        self._view_filters: dict[str, str] = {}
        self._rows: list[views.Row] = []
        self._signature: list[tuple[str, str, bool]] = []
        self._loading = False
        self._again = False
        self._force_git = False
        self._mode = SPLIT
        self._width = 0
        self._watch = watch
        self._watch_factory = watch_factory
        self._spool_dir = spool_dir
        self.last_refresh_error: str | None = None
        self._titlebar_plain = ""
        self._fleet_ready = False
        self._detail_plain = ""
        self._tile_plain = ""
        self.refresh_count = 0

    # ------------------------------------------------------------------ compose

    def compose(self) -> ComposeResult:
        yield Static(id="titlebar")
        yield Static(id="banner")
        yield Input(placeholder="filter (/ to open, Enter to apply, Esc to clear)", id="filter")
        with Container(id="body", classes="split"):
            yield FleetList(id="list")
            with VerticalScroll(id="detail"):
                yield Static(id="detail_text")
            with Tile(id="tile_recent", classes="tile"):
                yield Static(id="recent_text")
            with Tile(id="tile_side", classes="tile"):
                yield Static(id="side_text")
        yield Static(id="statusbar")

    async def on_mount(self) -> None:
        self._apply_layout(self.size.width)
        self.query_one("#list", FleetList).focus()
        self._fleet_ready = True
        await self.refresh_data()
        self.set_interval(self.refresh_s, self._tick)
        self._start_watcher()

    async def on_resize(self, event: events.Resize) -> None:
        self._apply_layout(event.size.width)
        self._render_all()

    # ------------------------------------------------------------------ data

    async def _tick(self) -> None:
        await self.refresh_data()

    async def refresh_data(self, *, force_git: bool = False) -> None:
        """Reload on a worker thread; overlapping requests coalesce into one more pass."""
        self._force_git = self._force_git or force_git
        if self._loading:
            self._again = True
            return
        self._loading = True
        try:
            while True:
                self._again = False
                force, self._force_git = self._force_git, False
                flt, errors = self._timeline_filter()
                try:
                    data = await asyncio.to_thread(
                        self.source.load, flt, limit=self.ui.timeline_limit, force_git=force
                    )
                except Exception as exc:
                    self.last_refresh_error = type(exc).__name__
                    self.data.problems = [
                        f"refresh failed ({type(exc).__name__}); showing old data"
                    ]
                else:
                    data.timeline_errors = errors
                    self.last_refresh_error = None
                    self.data = data
                    self.refresh_count += 1
                self._render_all()
                if not self._again:
                    break
        finally:
            self._loading = False

    def _timeline_filter(self) -> tuple[EventFilter | None, tuple[str, ...]]:
        text = self._view_filters.get("timeline", "").strip()
        if not text:
            return None, ()
        parsed = parse_timeline_filter(text, self.source.now())
        return parsed.event, parsed.errors

    def _start_watcher(self) -> None:
        factory = self._watch_factory
        if factory is None and self._watch:
            factory = default_watch_factory()
        directory = self._spool_dir or getattr(self.data, "runtime_dir", None)
        if factory is None or directory is None:
            return
        spool = os.path.join(directory, "spool") if self._spool_dir is None else directory
        if not os.path.isdir(spool):
            return
        self.run_worker(self._watch_loop(factory, spool), exclusive=False, name="spool-watch")

    async def _watch_loop(self, factory: WatchFactory, spool: str) -> None:
        try:
            async for _batch in factory(spool):
                await self.refresh_data()
        except Exception as exc:
            self.flash(f"file watcher stopped ({type(exc).__name__}); polling continues")

    # ------------------------------------------------------------------ layout

    def _apply_layout(self, width: int) -> None:
        self._width = width
        self._mode = layout_for(width, self.tile_enabled)
        body = self.query_one("#body", Container)
        body.remove_class(SINGLE, SPLIT, TILED)
        body.add_class(self._mode)
        body.set_class(self.detail_open and self._mode == SINGLE, "show-detail")

    @property
    def loading(self) -> bool:
        return self._loading

    @property
    def layout_mode(self) -> str:
        return self._mode

    # ------------------------------------------------------------------ rendering

    def _render_all(self) -> None:
        if not self._fleet_ready:
            return
        self._rows = views.rows_for(self.view, self.data, self.ui)
        self._render_titlebar()
        self._render_banner()
        self._render_list()
        self._render_detail()
        self._render_tiles()
        self._render_statusbar()

    def _render_titlebar(self) -> None:
        data = self.data
        narrow = self._width < 100
        blocked = data.blocked_count()
        if narrow:
            hooks = f"hooks {len(data.sessions)}" if data.telemetry == "hooks" else "no telemetry"
            git = (
                "git off"
                if not data.git_enabled
                else ("git ok" if data.git and data.git.available else "no git")
            )
            parts = ["CursorFleet observe-only", views.VIEW_TITLE[self.view]]
            if blocked:
                parts.append(f"BLOCKED {blocked}")
            parts.extend([hooks, git])
        else:
            hooks = (
                f"hooks: {plural(len(data.sessions), 'session')}"
                if data.telemetry == "hooks"
                else "hooks: no telemetry"
            )
            git = (
                "git: off"
                if not data.git_enabled
                else ("git: ok" if data.git and data.git.available else "git: n/a")
            )
            parts = [f"CursorFleet {__version__} OBSERVE-ONLY", views.VIEW_TITLE[self.view]]
            if blocked:
                parts.append(f"BLOCKED: {blocked}")
            parts.extend([hooks, git, f"UTC {fmt_ts(data.now)}"])
        text = Text(" | ".join(parts))
        self._titlebar_plain = text.plain
        text.no_wrap = True
        text.overflow = "ellipsis"
        self.query_one("#titlebar", Static).update(text)

    def _render_banner(self) -> None:
        banner = self.query_one("#banner", Static)
        problems = [safe(p, 200) for p in self.data.problems]
        if problems:
            banner.update(Text("! " + " | ".join(problems), style="bold"))
            banner.add_class("has-problems")
        else:
            banner.update(Text(""))
            banner.remove_class("has-problems")

    def _render_list(self) -> None:
        widget = self.query_one("#list", FleetList)
        widget.border_title = views.VIEW_TITLE[self.view]
        signature = [(r.key, r.label.plain, r.header) for r in self._rows]
        if signature == self._signature:
            return
        self._signature = signature
        wanted = self.ui.selected.get(self.view)
        widget.clear_options()
        widget.add_options(Option(r.label, id=r.key, disabled=r.header) for r in self._rows)
        index = next(
            (i for i, r in enumerate(self._rows) if r.key == wanted and not r.header), None
        )
        if index is None:
            index = next((i for i, r in enumerate(self._rows) if not r.header), None)
        if index is not None:
            widget.highlighted = index

    def _selected_key(self) -> str | None:
        key = self.ui.selected.get(self.view)
        if key is not None and any(r.key == key and not r.header for r in self._rows):
            return key
        return views.first_selectable(self._rows)

    def _render_detail(self) -> None:
        key = self._selected_key()
        tools: list[Event] | None = None
        if self.view == "overview" and key is not None:
            bundle = self.data.bundles.get(key)
            if bundle is not None and bundle.session is not None and bundle.view is not None:
                tools = self.source.recent_tools(bundle.session.session_id, bundle.acc.key)
        if self.view == "overview" and self.data.is_empty and key is None:
            text = Text(views.GUIDANCE_NO_TELEMETRY, style="")
            text.append(
                "\n\nWithout telemetry the state is UNKNOWN; CursorFleet never infers inactivity.",
                style="dim",
            )
        else:
            text = views.detail_for(self.view, self.data, self.ui, key, tools)
        widget = self.query_one("#detail", VerticalScroll)
        widget.border_title = "Detail"
        self.query_one("#detail_text", Static).update(text)
        self._detail_plain = text.plain

    def _render_tiles(self) -> None:
        recent = views.recent_events_text(self.data, self.ui)
        side = views.side_summary_text(self.data, self.ui)
        self.query_one("#recent_text", Static).update(recent)
        self.query_one("#side_text", Static).update(side)
        self.query_one("#tile_recent").border_title = "Recent events"
        self.query_one("#tile_side").border_title = "Gates / worktrees"
        self._tile_plain = recent.plain + "\n" + side.plain

    def _render_statusbar(self) -> None:
        keys = KEYS_WIDE if self._width >= 130 else KEYS_NARROW
        text = Text()
        flt = self._view_filters.get(self.view, "").strip()
        if self.flash_message:
            text.append(self.flash_message + " | ", style="bold")
        if flt:
            text.append(f"filter: {safe(flt, 40)} | ", style="bold")
        text.append(keys)
        text.no_wrap = True
        text.overflow = "ellipsis"
        self.query_one("#statusbar", Static).update(text)

    def flash(self, message: str) -> None:
        self.flash_message = message
        if self._fleet_ready:
            self._render_statusbar()

    # ------------------------------------------------------------------ introspection

    def rendered_text(self) -> str:
        """All text currently drawn or drawable (titlebar, rows, detail, visible tiles).

        Used by tests (privacy, snapshot-like assertions). Rows include off-screen ones.
        """
        chunks = [self._titlebar_plain]
        chunks.extend(p for p in self.data.problems)
        chunks.extend(r.label.plain for r in self._rows)
        chunks.append(self._detail_plain)
        if self._mode == TILED:
            chunks.append(self._tile_plain)
        chunks.append(self.flash_message)
        return "\n".join(chunks)

    def row_keys(self) -> list[str]:
        return [r.key for r in self._rows if not r.header]

    @property
    def selected_key(self) -> str | None:
        return self._selected_key()

    # ------------------------------------------------------------------ events

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_list.id != "list" or event.option.id is None:
            return
        self.ui.selected[self.view] = event.option.id
        self._render_detail()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "list":
            self.action_open_detail()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "filter":
            return
        self._view_filters[self.view] = event.value
        self.ui.filter_text = event.value
        if self.view == "timeline":
            self.run_worker(self.refresh_data(), exclusive=False)
        else:
            self._render_all()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "filter":
            self.query_one("#list", FleetList).focus()

    # ------------------------------------------------------------------ actions

    def action_help(self) -> None:
        if not isinstance(self.screen, HelpScreen):
            self.push_screen(HelpScreen())

    def action_filter(self) -> None:
        box = self.query_one("#filter", Input)
        box.add_class("open")
        box.value = self._view_filters.get(self.view, "")
        box.focus()
        box.cursor_position = len(box.value)

    def action_leave(self) -> None:
        box = self.query_one("#filter", Input)
        if self.focused is box:
            self._close_filter(clear=True)
            return
        if self.focused is self.query_one("#detail"):
            self.query_one("#list", FleetList).focus()
        if self.detail_open:
            self.detail_open = False
            self._apply_layout(self._width)
            self.query_one("#list", FleetList).focus()
            return
        if self._view_filters.get(self.view):
            self._close_filter(clear=True)

    def _close_filter(self, *, clear: bool) -> None:
        box = self.query_one("#filter", Input)
        if clear:
            box.value = ""
            self._view_filters[self.view] = ""
            self.ui.filter_text = ""
        box.remove_class("open")
        self.query_one("#list", FleetList).focus()
        if self.view == "timeline":
            self.run_worker(self.refresh_data(), exclusive=False)
        else:
            self._render_all()

    def action_show(self, view: str) -> None:
        if view not in views.VIEWS:
            return
        self.view = view
        self.detail_open = False
        self.ui.filter_text = self._view_filters.get(view, "")
        box = self.query_one("#filter", Input)
        box.value = self.ui.filter_text
        box.set_class(bool(self.ui.filter_text), "open")
        self._apply_layout(self._width)
        self.query_one("#list", FleetList).focus()
        self._signature = []
        self.flash("")
        if view == "timeline":
            self.run_worker(self.refresh_data(), exclusive=False)
        else:
            self._render_all()

    def action_cursor_down(self) -> None:
        self._move(1)

    def action_cursor_up(self) -> None:
        self._move(-1)

    def _move(self, step: int) -> None:
        focused = self.focused
        if isinstance(focused, VerticalScroll):
            focused.scroll_down() if step > 0 else focused.scroll_up()
            return
        if isinstance(focused, Input):
            return
        widget = self.query_one("#list", FleetList)
        widget.action_cursor_down() if step > 0 else widget.action_cursor_up()

    def action_open_detail(self) -> None:
        if self._mode == SINGLE:
            self.detail_open = True
            self._apply_layout(self._width)
        self.query_one("#detail", VerticalScroll).focus()

    def action_pin(self) -> None:
        key = self._selected_key()
        if self.view != "overview" or key is None or key not in self.data.bundles:
            self.flash("pin works on agents in the overview (o)")
            return
        if key in self.ui.pinned:
            self.ui.pinned.discard(key)
            self.flash("unpinned")
        else:
            self.ui.pinned.add(key)
            self.flash("pinned (kept in memory for this session only)")
        self._signature = []
        self._render_all()

    def action_tile(self) -> None:
        self.tile_enabled = not self.tile_enabled
        self._apply_layout(self._width)
        if self.tile_enabled and self._mode != TILED:
            self.flash("tiling applies at 160+ columns; widen the terminal")
        else:
            self.flash("tiled panes on" if self.tile_enabled else "tiled panes off")
        self._render_all()

    async def action_refresh(self) -> None:
        self.flash("re-read (no fetch)")
        await self.refresh_data(force_git=True)

    def action_more(self) -> None:
        if self.view != "timeline":
            self.flash("m loads more events in the timeline (l)")
            return
        if self.ui.timeline_limit >= MAX_PAGE:
            self.flash(f"timeline is capped at {MAX_PAGE} events; narrow the filter with /")
            return
        self.ui.timeline_limit = min(MAX_PAGE, self.ui.timeline_limit + PAGE_STEP)
        self.run_worker(self.refresh_data(), exclusive=False)


def build_app(
    repo: str | Path,
    *,
    refresh_s: float = DEFAULT_REFRESH_S,
    with_git: bool = True,
    watch: bool = True,
    clock: Callable[[], Any] | None = None,
) -> CursorFleetApp:
    """The production wiring used by ``cursorfleet tui``."""
    refresh = max(0.25, refresh_s)
    # Git is slow relative to the spool: re-collect about every 10 s however fast we poll.
    git_every = max(1, round(10 / refresh))
    source = DataSource(repo, with_git=with_git, clock=clock, git_every=git_every)
    return CursorFleetApp(source, refresh_s=refresh, watch=watch)
