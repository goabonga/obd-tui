# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the Textual dashboard."""

from __future__ import annotations

from contextlib import suppress
from typing import Any

from textual.widgets import Sparkline, Static, TabbedContent, TabPane
from textual.worker import WorkerCancelled

from obd_tui.app import ObdApp, StatusBar, trend_id
from obd_tui.models.adapter import AdapterInfo
from obd_tui.models.commands import CommandCatalog, CommandInfo
from obd_tui.services.session import Session
from obd_tui.views.panels import PANELS, PANELS_BY_KEY

ADAPTER = AdapterInfo(port="/dev/ttyUSB0", vid="0403", pid="6015")
CATALOG = CommandCatalog(
    modes={"Mode 01": [CommandInfo("RPM", "0x0C", "Engine RPM", supported=True)]}
)


class FakeConnection:
    """Connection double answering a single command."""

    def __init__(self, opens: bool = True, rpm: float = 1450.0) -> None:
        self.opens = opens
        self.rpm = rpm
        self.opened: list[str] = []
        self.closed = 0

    def open(self, port: str) -> bool:
        self.opened.append(port)
        return self.opens

    def close(self) -> None:
        self.closed += 1

    def discover(self) -> CommandCatalog:
        return CATALOG

    def query(self, name: str) -> Any | None:
        return self.rpm if name == "RPM" else None


# Long enough that the timer never fires on its own: a poll every few
# milliseconds floods the message loop and makes every `pilot` wait time out.
IDLE_INTERVAL = 30.0
POLLING_INTERVAL = 0.1


def build_app(
    connection: FakeConnection | None = None,
    adapter: AdapterInfo | None = ADAPTER,
    poll_interval: float = IDLE_INTERVAL,
) -> tuple[ObdApp, FakeConnection]:
    """Return an app driving a session with no real hardware behind it."""
    link = connection or FakeConnection()
    session = Session(connection=link, detector=lambda: adapter)  # type: ignore[arg-type]
    return ObdApp(session, poll_interval=poll_interval), link


def status_of(app: ObdApp) -> str:
    """Return the text currently shown in the status bar."""
    return str(app.query_one("#status", StatusBar).visual)


def panel_of(app: ObdApp, key: str) -> str:
    """Return the text currently shown in one panel."""
    return str(app.query_one(f"#content-{key}", Static).visual)


async def settle(app: ObdApp, pilot: Any) -> None:
    """Let the adapter worker finish and the UI redraw.

    Adapter workers are exclusive, so a poll started while another is
    running is cancelled by design; that is not a failure to wait on.
    """
    with suppress(WorkerCancelled):
        await app.workers.wait_for_complete()
    await pilot.pause()


class TestStartup:
    async def test_starts_disconnected(self) -> None:
        app, link = build_app()

        async with app.run_test() as pilot:
            await pilot.pause()

            assert status_of(app) == "DISCONNECTED  |  -  |  -:-"
            assert link.opened == []

    async def test_starts_with_every_tab_disabled(self) -> None:
        app, _ = build_app()

        async with app.run_test() as pilot:
            await pilot.pause()
            tabs = app.query_one("#panels", TabbedContent)

            assert all(tabs.get_tab(panel.key).disabled for panel in PANELS)

    async def test_shows_the_engine_panel_first(self) -> None:
        app, _ = build_app()

        async with app.run_test() as pilot:
            await pilot.pause()

            assert app.query_one("#panels", TabbedContent).active == "engine"
            assert panel_of(app, "engine")


class TestConnect:
    async def test_connects_and_enables_the_tabs(self) -> None:
        app, link = build_app()

        async with app.run_test() as pilot:
            await pilot.press("c")
            await settle(app, pilot)
            tabs = app.query_one("#panels", TabbedContent)

            assert link.opened == ["/dev/ttyUSB0"]
            assert status_of(app) == "CONNECTED  |  /dev/ttyUSB0  |  0403:6015"
            assert not any(tabs.get_tab(panel.key).disabled for panel in PANELS)

    async def test_shows_the_readings_once_polling_starts(self) -> None:
        app, _ = build_app(poll_interval=POLLING_INTERVAL)

        async with app.run_test() as pilot:
            await pilot.press("c")
            await settle(app, pilot)
            await pilot.pause(POLLING_INTERVAL * 2)
            await settle(app, pilot)

            assert "1450" in panel_of(app, "engine")

    async def test_reports_a_missing_adapter(self) -> None:
        app, link = build_app(adapter=None)

        async with app.run_test() as pilot:
            await pilot.press("c")
            await settle(app, pilot)

            assert status_of(app).startswith("NO DEVICE")
            assert link.opened == []

    async def test_reports_a_port_that_refuses_to_open(self) -> None:
        app, _ = build_app(FakeConnection(opens=False))

        async with app.run_test() as pilot:
            await pilot.press("c")
            await settle(app, pilot)
            tabs = app.query_one("#panels", TabbedContent)

            assert status_of(app).startswith("FAILED")
            assert all(tabs.get_tab(panel.key).disabled for panel in PANELS)

    async def test_connecting_twice_does_not_reopen_the_port(self) -> None:
        app, link = build_app()

        async with app.run_test() as pilot:
            await pilot.press("c")
            await settle(app, pilot)
            await pilot.press("c")
            await settle(app, pilot)

            assert link.opened == ["/dev/ttyUSB0"]


class TestDisconnect:
    async def test_closes_the_link_and_clears_the_dashboard(self) -> None:
        app, link = build_app()

        async with app.run_test() as pilot:
            await pilot.press("c")
            await settle(app, pilot)
            await pilot.press("d")
            await settle(app, pilot)
            tabs = app.query_one("#panels", TabbedContent)

            assert link.closed == 1
            assert status_of(app) == "DISCONNECTED  |  -  |  -:-"
            assert all(tabs.get_tab(panel.key).disabled for panel in PANELS)

    async def test_stops_polling(self) -> None:
        app, _ = build_app(poll_interval=POLLING_INTERVAL)

        async with app.run_test() as pilot:
            await pilot.press("c")
            await settle(app, pilot)
            await pilot.press("d")
            await settle(app, pilot)
            await pilot.pause(POLLING_INTERVAL * 2)
            await settle(app, pilot)

            assert "1450" not in panel_of(app, "engine")


class TestTrends:
    async def test_the_engine_panel_charts_its_readings(self) -> None:
        app, _ = build_app()

        async with app.run_test() as pilot:
            await pilot.pause()
            charts = app.query_one("#engine", TabPane).query(Sparkline)

            assert len(charts) == len(PANELS_BY_KEY["engine"].trends)

    async def test_a_chart_starts_empty(self) -> None:
        app, _ = build_app()

        async with app.run_test() as pilot:
            await pilot.pause()

            assert app.query_one(f"#{trend_id('engine', 'rpm')}", Sparkline).data == []

    async def test_a_chart_fills_as_the_vehicle_is_polled(self) -> None:
        app, _ = build_app(poll_interval=POLLING_INTERVAL)

        async with app.run_test() as pilot:
            await pilot.press("c")
            await settle(app, pilot)
            await pilot.pause(POLLING_INTERVAL * 2)
            await settle(app, pilot)

            data = app.query_one(f"#{trend_id('engine', 'rpm')}", Sparkline).data
            assert data
            assert set(data) == {1450.0}

    async def test_disconnecting_empties_the_charts(self) -> None:
        app, _ = build_app(poll_interval=POLLING_INTERVAL)

        async with app.run_test() as pilot:
            await pilot.press("c")
            await settle(app, pilot)
            await pilot.pause(POLLING_INTERVAL * 2)
            await settle(app, pilot)
            await pilot.press("d")
            await settle(app, pilot)

            assert app.query_one(f"#{trend_id('engine', 'rpm')}", Sparkline).data == []

    async def test_a_panel_without_trends_has_no_chart(self) -> None:
        app, _ = build_app()

        async with app.run_test() as pilot:
            await pilot.pause()

            assert not app.query_one("#faults", TabPane).query(Sparkline)


class TestPanelShortcuts:
    async def test_a_shortcut_opens_its_panel(self) -> None:
        app, _ = build_app()

        async with app.run_test() as pilot:
            await pilot.press("c")
            await settle(app, pilot)
            await pilot.press("p")
            await pilot.pause()

            assert app.query_one("#panels", TabbedContent).active == "catalog"
            assert "Supported: 1 / 1" in panel_of(app, "catalog")

    async def test_a_shortcut_does_nothing_while_disconnected(self) -> None:
        app, _ = build_app()

        async with app.run_test() as pilot:
            await pilot.press("p")
            await pilot.pause()

            assert app.query_one("#panels", TabbedContent).active == "engine"

    async def test_every_panel_has_a_binding(self) -> None:
        shortcuts = {
            binding.key
            for binding in ObdApp.BINDINGS
            if getattr(binding, "action", "").startswith("show(")
        }

        assert shortcuts == {panel.shortcut for panel in PANELS}


async def test_a_default_app_builds_its_own_session() -> None:
    app = ObdApp()

    assert isinstance(app.session, Session)
    assert app.poll_interval > 0
