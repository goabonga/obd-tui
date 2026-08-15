# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""The Textual dashboard."""

from __future__ import annotations

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
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

from obd_tui.config import DEFAULT_POLL_INTERVAL
from obd_tui.services.session import Session
from obd_tui.views.panels import PANELS, PANELS_BY_KEY, TrendSpec
from obd_tui.views.units import UnitSystem

# Seconds between two sweeps of the vehicle's sensors, when the caller does
# not say. The configuration file and the command line both do.
POLL_INTERVAL = DEFAULT_POLL_INTERVAL

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


class ObdApp(App[None]):
    """Dashboard over one :class:`Session`.

    Every read of the adapter happens on a worker thread: a connect probes
    the protocol for seconds and a sweep queries dozens of PIDs, either of
    which would freeze the UI on the event loop.

    Args:
        session: The session to render. A default one scans for an adapter.
        poll_interval: Seconds between two sweeps while connected.
        units: System the readings are displayed in.
    """

    TITLE = "obd-tui"

    CSS = """
    Screen { background: black; color: green; }
    /* 1fr so the panels take the room left over and push the status bar
       down against the footer; overflow so a long catalogue scrolls. */
    TabbedContent { background: black; height: 1fr; }
    TabPane { background: black; color: green; overflow-y: auto; }
    Tabs { background: black; color: green; }
    Tab { background: black; color: green; }
    Tab.-active { background: green; color: black; }
    Tab.-disabled { color: $text-disabled; opacity: 0.5; }
    /* Keep the readings clear of the charts drawn above them. */
    Static.charted { margin-top: 1; }
    """

    BINDINGS = [
        Binding("c", "connect", "Connect"),
        Binding("d", "disconnect", "Disconnect"),
        *(Binding(panel.shortcut, f"show('{panel.key}')", panel.title) for panel in PANELS),
        Binding("x", "clear_codes", "Clear DTCs"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        session: Session | None = None,
        poll_interval: float = POLL_INTERVAL,
        units: UnitSystem = UnitSystem.METRIC,
    ) -> None:
        super().__init__()
        self.session = session if session is not None else Session()
        self.poll_interval = poll_interval
        self.units = units

    def compose(self) -> ComposeResult:
        """Lay out the header, the panel tabs, the status bar and the keys."""
        yield Header(show_clock=True)
        with TabbedContent(initial=PANELS[0].key, id="panels"):
            for panel in PANELS:
                with TabPane(panel.title, id=panel.key):
                    for trend in panel.trends:
                        yield TrendRow(panel.key, trend)
                    # markup=False: panel text carries bracketed marks and
                    # raw ECU strings, which Textual would read as tags.
                    yield Static(
                        id=f"content-{panel.key}",
                        markup=False,
                        classes="charted" if panel.trends else "",
                    )
        yield StatusBar(id="status")
        yield Footer()

    def on_mount(self) -> None:
        """Start paused: nothing is polled until the user connects."""
        self._timer = self.set_interval(self.poll_interval, self._tick, pause=True)
        self.refresh_view()

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
        status.update(self.session.summary)
        self._set_tabs_enabled(self.session.is_connected)
        self._render_active_panel()
        self._render_trends()
        # Connecting or losing the link changes what `x` can do.
        self.refresh_bindings()

    def action_connect(self) -> None:
        """Connect to the adapter, unless the session already is."""
        if self.session.is_connected:
            return
        self._connect()

    def action_disconnect(self) -> None:
        """Stop polling and drop the connection."""
        self._timer.pause()
        self.session.disconnect()
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

    @work(thread=True, exclusive=True, group=ADAPTER_GROUP)
    def _connect(self) -> None:
        """Open the link on a worker thread, then hand the result back."""
        self.session.connect()
        self.call_from_thread(self._connected)

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
        """Redraw after a sweep, and stop polling if the link went away.

        The readings stay on screen: they are the last thing the vehicle
        said. Pressing `c` reconnects.
        """
        if not self.session.is_connected:
            self._timer.pause()
        self.refresh_view()

    def _priority_fields(self) -> tuple[str, ...]:
        """Return the fields of the panel the user is looking at."""
        panel = PANELS_BY_KEY.get(self._active_panel_key())
        return panel.fields if panel is not None else ()

    def _active_panel_key(self) -> str:
        """Return the key of the open tab."""
        return str(self.query_one("#panels", TabbedContent).active)

    def _connected(self) -> None:
        """Redraw after a connect attempt and start polling if it worked."""
        self.refresh_view()
        if self.session.is_connected:
            self._timer.resume()

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
