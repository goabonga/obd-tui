# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""The Textual dashboard."""

from __future__ import annotations

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Label,
    Sparkline,
    Static,
    TabbedContent,
    TabPane,
)

from obd_tui import __version__
from obd_tui.config import DEFAULT_POLL_INTERVAL, DEFAULT_RECONNECT_INTERVAL
from obd_tui.logs import NoticeLog, route_to
from obd_tui.services.session import Session
from obd_tui.views.panels import PANELS, PANELS_BY_KEY, TrendSpec
from obd_tui.views.units import UnitSystem

# Seconds between two sweeps of the vehicle's sensors, when the caller does
# not say. The configuration file and the command line both do.
POLL_INTERVAL = DEFAULT_POLL_INTERVAL

# Seconds between two attempts to bring a down link back up.
RECONNECT_INTERVAL = DEFAULT_RECONNECT_INTERVAL

# Workers that touch the adapter run one at a time: the serial link cannot
# serve a connect and a poll at once.
ADAPTER_GROUP = "adapter"

# The only panel where erasing the stored diagnostics means anything.
CLEARABLE_PANEL = "faults"


class StatusBar(Static):
    """One-line connection summary, sitting between panels and key hints.

    It is laid out in the flow rather than docked: the footer already docks
    to the bottom edge, and a second widget docked there would land on the
    same row and be painted over.
    """

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        padding: 0 1;
        content-align: right middle;
        color: $footer-description-foreground;
        background: $footer-background;
    }
    """


class TrendRow(Horizontal):
    """A labelled sparkline of one reading's recent history."""

    DEFAULT_CSS = """
    /* One row per trend: a sparkline taller than a line renders as a bar
       chart, because any value above half fills the row below it. */
    TrendRow {
        height: 1;
        width: 1fr;
    }
    TrendRow > Label {
        width: 20;
        padding: 0 0 0 2;
        color: green 70%;
    }
    TrendRow > Sparkline {
        width: 1fr;
        height: 1;
        margin: 0 2 0 0;
    }
    TrendRow > Sparkline > .sparkline--max-color { color: green; }
    TrendRow > Sparkline > .sparkline--min-color { color: green 55%; }
    """

    def __init__(self, panel_key: str, trend: TrendSpec) -> None:
        super().__init__()
        self._panel_key = panel_key
        self._trend = trend

    def compose(self) -> ComposeResult:
        """Lay out the label and the chart."""
        yield Label(self._trend.label)
        yield Sparkline(id=trend_id(self._panel_key, self._trend.field))


def scroll_id(panel_key: str) -> str:
    """Return the widget id of one panel's scrollable body."""
    return f"scroll-{panel_key}"


def trend_id(panel_key: str, field: str) -> str:
    """Return the widget id of one panel's chart of ``field``."""
    return f"trend-{panel_key}-{field.replace('_', '-')}"


def _window(series: list[float], chart: Sparkline) -> list[float]:
    """Return the tail of ``series`` that ``chart`` can draw point by point.

    Handing a sparkline more points than it has columns makes it bucket
    them, and a bucket of a fast oscillation is summarised by its peak - so
    a healthy idle would read as a flat, full bar.
    """
    width = chart.content_size.width
    return series[-width:] if width else series


class ConfirmClear(ModalScreen[bool]):
    """Ask before erasing the ECU's stored diagnostics.

    Mode 04 is not undoable and clears more than the codes on screen, so
    the dialog spells out what goes with them.
    """

    BINDINGS = [
        Binding("escape", "dismiss(False)", "Cancel"),
        Binding("y", "dismiss(True)", "Clear"),
        Binding("n", "dismiss(False)", "Cancel"),
    ]

    DEFAULT_CSS = """
    ConfirmClear {
        align: center middle;
    }
    ConfirmClear > Vertical {
        width: 62;
        height: auto;
        padding: 1 2;
        background: black;
        border: round green;
    }
    ConfirmClear Label {
        width: 1fr;
        background: black;
        color: green;
    }
    /* Not named "warning": Textual's own palette classes claim that one and
       would paint an amber block behind the text. */
    ConfirmClear .consequence {
        color: green 70%;
        margin: 1 0;
    }
    ConfirmClear > Vertical > Horizontal {
        height: auto;
        align: right middle;
    }
    ConfirmClear Button {
        margin: 0 0 0 2;
        min-width: 14;
    }
    ConfirmClear #cancel {
        background: black;
        color: green;
        border: tall green 50%;
    }
    ConfirmClear #clear {
        background: green;
        color: black;
        border: tall green;
    }
    """

    def compose(self) -> ComposeResult:
        """Lay out the question, its consequences and the two answers."""
        with Vertical():
            yield Label("Clear the stored trouble codes?")
            yield Label(
                "This sends mode 04. It erases the stored and pending codes, "
                "the freeze frame data and the readiness monitors, which the "
                "vehicle then has to re-run over several drive cycles. A "
                "fault that is still present will come straight back.",
                classes="consequence",
            )
            with Horizontal():
                yield Button("Cancel  (n)", id="cancel")
                yield Button("Clear  (y)", id="clear")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Answer with the button that was pressed."""
        self.dismiss(event.button.id == "clear")


class PanelScroll(VerticalScroll):
    """The scrollable body of one panel.

    A TabPane cannot take focus and does not scroll on its own, so the
    readings live in a container that does both — a panel taller than the
    window is reachable with the wheel, the scrollbar or the keys.
    """


class ObdApp(App[None]):
    """Dashboard over one :class:`Session`.

    Every read of the adapter happens on a worker thread: a connect probes
    the protocol for seconds and a sweep queries dozens of PIDs, either of
    which would freeze the UI on the event loop.

    Two timers drive it and at most one runs at a time: the poll timer
    while the link is up, the retry timer while it is down and wanted.
    Neither runs after `d`, which is how the user says the link is to stay
    down; `c` starts it all again.

    Args:
        session: The session to render. A default one scans for an adapter.
        poll_interval: Seconds between two sweeps while connected.
        units: System the readings are displayed in.
        connect_on_start: Open the link as soon as the screen is up, rather
            than waiting for the first retry. Meant for a caller that
            already knows which port to use.
        reconnect_interval: Seconds between two attempts to bring a down
            link back up.
    """

    TITLE = "obd-tui"
    # Shown beside the title in the header: which build is on screen is the
    # first thing to establish when a reading looks wrong.
    SUB_TITLE = __version__

    CSS = """
    Screen { background: black; color: green; }
    /* Every level of the tab stack defaults to `height: auto`, which lets a
       panel grow past the window and be cut off instead of scrolled. Each
       one is pinned to the room it is given, down to the scroll container
       that actually holds the readings. */
    TabbedContent { background: black; height: 1fr; }
    TabbedContent ContentSwitcher { height: 1fr; }
    TabPane { background: black; color: green; height: 1fr; padding: 0; }
    PanelScroll {
        height: 1fr;
        scrollbar-size-vertical: 1;
        scrollbar-background: black;
        scrollbar-background-hover: black;
        scrollbar-background-active: black;
        scrollbar-color: green 40%;
        scrollbar-color-hover: green 70%;
        scrollbar-color-active: green;
    }
    Tabs { background: black; color: green; }
    Tab { background: black; color: green; }
    Tab.-active { background: green; color: black; }
    Tab.-disabled { color: $text-disabled; opacity: 0.5; }
    /* Keep the readings clear of the charts drawn above them. */
    Static.charted { margin-top: 1; }
    /* Notifications keep Textual's bottom-right corner, themed to match
       the rest rather than arriving in the default palette. */
    Toast { background: black; border-left: outer green; }
    Toast .toast--title { color: green; }
    Toast.-warning { border-left: outer yellow; }
    Toast.-warning .toast--title { color: yellow; }
    Toast.-error { border-left: outer red; }
    Toast.-error .toast--title { color: red; }
    """

    BINDINGS = [
        Binding("c", "connect", "Connect"),
        Binding("d", "disconnect", "Disconnect"),
        *(Binding(panel.shortcut, f"show('{panel.key}')", panel.title) for panel in PANELS),
        Binding("x", "clear_codes", "Clear DTCs"),
        Binding("q", "quit", "Quit"),
        # Scrolling the open panel, wherever focus happens to be. Hidden
        # from the footer: the keys are the usual ones and the hints are
        # already full.
        Binding("down", "scroll_panel('down')", show=False),
        Binding("up", "scroll_panel('up')", show=False),
        Binding("pagedown", "scroll_panel('page_down')", show=False),
        Binding("pageup", "scroll_panel('page_up')", show=False),
        Binding("end", "scroll_panel('end')", show=False),
        Binding("home", "scroll_panel('home')", show=False),
    ]

    def __init__(
        self,
        session: Session | None = None,
        poll_interval: float = POLL_INTERVAL,
        units: UnitSystem = UnitSystem.METRIC,
        connect_on_start: bool = False,
        reconnect_interval: float = RECONNECT_INTERVAL,
    ) -> None:
        super().__init__()
        self.session = session if session is not None else Session()
        self.poll_interval = poll_interval
        self.units = units
        self.connect_on_start = connect_on_start
        self.reconnect_interval = reconnect_interval

    def compose(self) -> ComposeResult:
        """Lay out the header, the panel tabs, the status bar and the keys."""
        yield Header(show_clock=True)
        with TabbedContent(initial=PANELS[0].key, id="panels"):
            for panel in PANELS:
                with TabPane(panel.title, id=panel.key), PanelScroll(id=scroll_id(panel.key)):
                    for trend in panel.trends:
                        yield TrendRow(panel.key, trend)
                    # markup=False: panel text carries bracketed marks
                    # and raw ECU strings, read as tags otherwise.
                    yield Static(
                        id=f"content-{panel.key}",
                        markup=False,
                        classes="charted" if panel.trends else "",
                    )
        yield StatusBar(id="status")
        yield Footer()

    def on_mount(self) -> None:
        """Set the timers up and start looking for a vehicle.

        Nothing is polled until a connect goes through; until then the
        retry timer keeps trying, unless a caller with a port in hand asks
        for the first attempt right away.
        """
        # Before anything can log: python-obd writes to stderr on its own,
        # which lands on top of this screen.
        self._notices = NoticeLog()
        self._restore_logging = route_to(self._notices)
        self._timer = self.set_interval(self.poll_interval, self._tick, pause=True)
        self._retry = self.set_interval(self.reconnect_interval, self._retry_link, pause=True)
        self.refresh_view()
        if self.connect_on_start:
            self._start_connect()
        else:
            self._settle_timers()

    def on_unmount(self) -> None:
        """Give the loggers back the way they were found."""
        self._restore_logging()

    def refresh_view(self) -> None:
        """Redraw the status bar, the tab availability and the open panel.

        A sweep can finish after the app has started tearing down, and the
        redraw it asks for then finds no widgets left; that is not a
        failure, there is simply nothing to draw.
        """
        try:
            status = self.query_one("#status", StatusBar)
        except NoMatches:
            return
        status.update(self._status_line())
        self._set_tabs_enabled(self.session.is_connected)
        self._render_active_panel()
        self._render_trends()
        self._show_notices()
        # Connecting or losing the link changes what `x` can do.
        self.refresh_bindings()

    def action_connect(self) -> None:
        """Connect to the adapter, unless the session already is."""
        if self.session.is_connected:
            return
        self._start_connect()

    def action_disconnect(self) -> None:
        """Drop the connection and keep it down until the next `c`."""
        self.session.disconnect()
        self._settle_timers()
        self.refresh_view()

    async def action_quit(self) -> None:
        """Close the link, and any recording, before leaving.

        Each sweep is flushed as it is written, so an abrupt exit loses
        nothing; this only releases the handle tidily.
        """
        self.session.disconnect()
        await super().action_quit()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Offer clearing the codes only where it means something."""
        if action == "clear_codes":
            return self._can_clear_codes()
        return True

    def action_clear_codes(self) -> None:
        """Ask for confirmation before erasing the stored diagnostics."""
        if not self._can_clear_codes():
            return
        self.push_screen(ConfirmClear(), self._clear_codes_answered)

    def _can_clear_codes(self) -> bool:
        """Return whether clearing makes sense right now."""
        return self.session.is_connected and self._active_panel_key() == CLEARABLE_PANEL

    def _clear_codes_answered(self, confirmed: bool | None) -> None:
        """Clear the codes if the dialog came back with a yes."""
        if confirmed:
            self._clear_codes()

    @work(thread=True, exclusive=True, group=ADAPTER_GROUP)
    def _clear_codes(self) -> None:
        """Send mode 04 on a worker thread, then redraw what came back."""
        self.session.clear_codes()
        self.call_from_thread(self._swept)

    def action_scroll_panel(self, movement: str) -> None:
        """Scroll the open panel, whichever widget holds focus.

        A panel taller than the window would otherwise only be reachable by
        first tabbing into its body.
        """
        body = self.query_one(f"#{scroll_id(self._active_panel_key())}", PanelScroll)
        scroll = {
            "up": body.scroll_up,
            "down": body.scroll_down,
            "page_up": body.scroll_page_up,
            "page_down": body.scroll_page_down,
            "home": body.scroll_home,
            "end": body.scroll_end,
        }[movement]
        scroll(animate=False)

    def action_show(self, key: str) -> None:
        """Open the panel bound to a shortcut, if the tabs are live."""
        if not self.session.is_connected:
            return
        self.query_one("#panels", TabbedContent).active = key

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Render a panel the moment it is opened, without waiting a tick."""
        self._render_active_panel()
        # Only the faults panel offers `x`.
        self.refresh_bindings()

    def _start_connect(self) -> None:
        """Open the link on a worker, with the retry timer out of the way.

        A connect probes the protocol for seconds, and a retry landing on
        the serial link in the middle of that would help nothing; the timer
        is settled again once the attempt has answered.
        """
        self._retry.pause()
        self._connect()

    @work(thread=True, exclusive=True, group=ADAPTER_GROUP)
    def _connect(self) -> None:
        """Open the link on a worker thread, then hand the result back."""
        self.session.connect()
        self.call_from_thread(self._connected)

    def _retry_link(self) -> None:
        """Try the link again, if it is still down and still wanted.

        Guarded rather than trusted: the timer is paused whenever neither
        holds, but a tick can already be queued when that happens.
        """
        if self.session.wants_link:
            self._start_connect()

    def _tick(self) -> None:
        """Start a sweep, reading the open panel from the UI thread.

        The worker must not touch the DOM, so which fields to prioritise is
        resolved here and handed over.
        """
        self._poll(self._priority_fields())

    @work(thread=True, exclusive=True, group=ADAPTER_GROUP)
    def _poll(self, priority: tuple[str, ...]) -> None:
        """Sweep the sensors on a worker thread, then redraw."""
        self.session.refresh(priority)
        self.call_from_thread(self._swept)

    def _swept(self) -> None:
        """Redraw after a sweep, and switch to retrying if the link went away.

        The readings stay on screen: they are the last thing the vehicle
        said, and they hold until the link comes back.
        """
        self._settle_timers()
        self.refresh_view()

    def _priority_fields(self) -> tuple[str, ...]:
        """Return the fields of the panel the user is looking at."""
        panel = PANELS_BY_KEY.get(self._active_panel_key())
        return panel.fields if panel is not None else ()

    def _active_panel_key(self) -> str:
        """Return the key of the open tab."""
        return str(self.query_one("#panels", TabbedContent).active)

    def _connected(self) -> None:
        """Redraw after a connect attempt: poll if it worked, retry if not."""
        self._settle_timers()
        self.refresh_view()

    def _settle_timers(self) -> None:
        """Run the one timer the session's state calls for.

        Polling while the link is up, retrying while it is down and wanted,
        neither once the user has hung up. Kept in one place so every
        transition — connect, sweep, disconnect — leaves the same pair of
        timers in a state that matches the session.
        """
        if self.session.is_connected:
            self._retry.pause()
            self._timer.resume()
        elif self.session.wants_link:
            self._timer.pause()
            self._retry.resume()
        else:
            self._timer.pause()
            self._retry.pause()

    def _status_line(self) -> str:
        """Return the status bar's text: the session, plus what comes next.

        A down link that is being retried says so, and how often; one the
        user hung up on says nothing more, since `c` is already in the
        footer.
        """
        summary = self.session.summary
        if self.session.wants_link:
            return f"{summary}  |  retrying every {self.reconnect_interval:g} s"
        return summary

    def _show_notices(self) -> None:
        """Raise anything the loggers collected since the last redraw.

        Drained here rather than on a timer of its own: warnings come from
        the adapter, and the adapter is what a redraw follows.
        """
        for notice in self._notices.drain():
            self.notify(notice.message, title=notice.source, severity=notice.severity)

    def _render_trends(self) -> None:
        """Feed each chart the recent history of its reading.

        A reading with no history yet leaves its chart empty; the text panel
        below already states what the vehicle reported.
        """
        for panel in PANELS:
            for trend in panel.trends:
                chart = self.query_one(f"#{trend_id(panel.key, trend.field)}", Sparkline)
                chart.data = _window(self.session.history.series(trend.field), chart)

    def _render_active_panel(self) -> None:
        """Redraw whichever panel is open."""
        tabs = self.query_one("#panels", TabbedContent)
        panel = PANELS_BY_KEY.get(str(tabs.active))
        if panel is None:
            return
        content = panel.render(self.session.vehicle, self.session.catalog, self.units)
        self.query_one(f"#content-{panel.key}", Static).update(content)

    def _set_tabs_enabled(self, enabled: bool) -> None:
        """Enable the tabs only while there is a vehicle to read from."""
        tabs = self.query_one("#panels", TabbedContent)
        for panel in PANELS:
            if enabled:
                tabs.enable_tab(panel.key)
            else:
                tabs.disable_tab(panel.key)
