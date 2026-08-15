# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the Textual dashboard."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager, suppress
from typing import Any

import pytest
from textual.widgets import Sparkline, Static, TabbedContent, TabPane
from textual.worker import WorkerCancelled

from obd_tui.app import ConfirmClear, ObdApp, PanelScroll, StatusBar, scroll_id, trend_id
from obd_tui.models.adapter import AdapterInfo
from obd_tui.models.commands import CommandCatalog, CommandInfo
from obd_tui.services.session import Session
from obd_tui.views.panels import PANELS, PANELS_BY_KEY

ADAPTER = AdapterInfo(port="/dev/ttyUSB0", vid="0403", pid="6015")
CATALOG = CommandCatalog(modes={"Mode 01": [CommandInfo("RPM", "0x0C", "Engine RPM", True)]})

# A vehicle supporting enough commands for a run of unanswered ones to read
# as a lost link rather than a few dropped frames.
CHATTY = ("RPM", "SPEED", "ENGINE_LOAD", "MAF", "THROTTLE_POS", "OIL_TEMP")
CHATTY_CATALOG = CommandCatalog(
    modes={"Mode 01": [CommandInfo(command, supported=True) for command in CHATTY]}
)


class FakeConnection:
    """Connection double answering a scripted set of commands."""

    def __init__(
        self,
        opens: bool = True,
        rpm: float = 1450.0,
        catalog: CommandCatalog = CATALOG,
    ) -> None:
        self.opens = opens
        self.catalog = catalog
        self.answers: dict[str, float] = {command: rpm for command in CHATTY}
        self.opened: list[str] = []
        self.asked: list[str] = []
        self.sweeps = 0
        self.closed = 0
        self.cleared = 0

    def open(self, port: str) -> bool:
        self.opened.append(port)
        return self.opens

    def close(self) -> None:
        self.closed += 1

    def discover(self) -> CommandCatalog:
        return self.catalog

    def clear_codes(self) -> bool:
        self.cleared += 1
        return True

    @contextmanager
    def sweep(self) -> Iterator[None]:
        self.sweeps += 1
        yield

    def query(self, name: str) -> Any | None:
        self.asked.append(name)
        return self.answers.get(name)


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


class TestLinkLoss:
    async def test_stops_polling_and_says_so_when_the_vehicle_goes_quiet(self) -> None:
        link = FakeConnection(catalog=CHATTY_CATALOG)
        app, _ = build_app(link, poll_interval=POLLING_INTERVAL)

        async with app.run_test() as pilot:
            await pilot.press("c")
            await settle(app, pilot)
            await pilot.pause(POLLING_INTERVAL * 2)
            await settle(app, pilot)
            link.answers.clear()
            await pilot.pause(POLLING_INTERVAL * 3)
            await settle(app, pilot)
            asked = len(link.asked)
            await pilot.pause(POLLING_INTERVAL * 3)
            await settle(app, pilot)

            assert status_of(app).startswith("LINK LOST")
            assert len(link.asked) == asked

    async def test_the_last_readings_stay_on_screen(self) -> None:
        link = FakeConnection(catalog=CHATTY_CATALOG)
        app, _ = build_app(link, poll_interval=POLLING_INTERVAL)

        async with app.run_test() as pilot:
            await pilot.press("c")
            await settle(app, pilot)
            await pilot.pause(POLLING_INTERVAL * 2)
            await settle(app, pilot)
            link.answers.clear()
            await pilot.pause(POLLING_INTERVAL * 3)
            await settle(app, pilot)

            assert "1450" in panel_of(app, "engine")


class TestClearCodes:
    @staticmethod
    async def _open_faults(app: ObdApp, pilot: Any) -> None:
        """Connect and switch to the faults panel."""
        await pilot.press("c")
        await settle(app, pilot)
        await pilot.press("5")
        await pilot.pause()

    async def test_asks_before_clearing(self) -> None:
        app, link = build_app()

        async with app.run_test() as pilot:
            await self._open_faults(app, pilot)
            await pilot.press("x")
            await pilot.pause()

            assert isinstance(app.screen, ConfirmClear)
            assert link.cleared == 0

    async def test_clears_once_confirmed(self) -> None:
        app, link = build_app()

        async with app.run_test() as pilot:
            await self._open_faults(app, pilot)
            await pilot.press("x")
            await pilot.pause()
            await pilot.press("y")
            await settle(app, pilot)

            assert link.cleared == 1

    async def test_cancelling_clears_nothing(self) -> None:
        app, link = build_app()

        async with app.run_test() as pilot:
            await self._open_faults(app, pilot)
            await pilot.press("x")
            await pilot.pause()
            await pilot.press("escape")
            await settle(app, pilot)

            assert link.cleared == 0
            assert not isinstance(app.screen, ConfirmClear)

    async def test_does_nothing_on_another_panel(self) -> None:
        app, link = build_app()

        async with app.run_test() as pilot:
            await pilot.press("c")
            await settle(app, pilot)
            await pilot.press("x")
            await pilot.pause()

            assert not isinstance(app.screen, ConfirmClear)
            assert link.cleared == 0

    async def test_does_nothing_while_disconnected(self) -> None:
        app, link = build_app()

        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("x")
            await pilot.pause()

            assert not isinstance(app.screen, ConfirmClear)
            assert link.cleared == 0

    async def test_the_clear_button_answers_the_dialog(self) -> None:
        app, link = build_app()

        async with app.run_test() as pilot:
            await self._open_faults(app, pilot)
            await pilot.press("x")
            await pilot.pause()
            await pilot.click("#clear")
            await settle(app, pilot)

            assert link.cleared == 1

    async def test_the_cancel_button_answers_the_dialog(self) -> None:
        app, link = build_app()

        async with app.run_test() as pilot:
            await self._open_faults(app, pilot)
            await pilot.press("x")
            await pilot.pause()
            await pilot.click("#cancel")
            await settle(app, pilot)

            assert link.cleared == 0
            assert not isinstance(app.screen, ConfirmClear)

    async def test_the_action_refuses_where_it_would_mean_nothing(self) -> None:
        """The action guards itself: bindings are not its only caller."""
        app, link = build_app()

        async with app.run_test() as pilot:
            await pilot.pause()

            app.action_clear_codes()
            await pilot.pause()

            assert not isinstance(app.screen, ConfirmClear)
            assert link.cleared == 0

    async def test_the_binding_is_offered_only_on_the_faults_panel(self) -> None:
        app, _ = build_app()

        async with app.run_test() as pilot:
            await pilot.press("c")
            await settle(app, pilot)

            assert app.check_action("clear_codes", ()) is False

            await pilot.press("5")
            await pilot.pause()

            assert app.check_action("clear_codes", ()) is True

    async def test_other_bindings_stay_available(self) -> None:
        app, _ = build_app()

        async with app.run_test() as pilot:
            await pilot.pause()

            assert app.check_action("connect", ()) is True


class TestScrolling:
    # Small enough that the engine panel cannot fit; large enough that it can.
    CRAMPED = (80, 12)
    ROOMY = (110, 45)

    @staticmethod
    def _talkative() -> tuple[ObdApp, FakeConnection]:
        """An app whose engine panel has enough readings to overflow."""
        return build_app(FakeConnection(catalog=CHATTY_CATALOG))

    @staticmethod
    async def _fill(app: ObdApp, pilot: Any) -> None:
        """Connect and take one sweep, without waiting on the timer."""
        await pilot.press("c")
        await settle(app, pilot)
        app.session.refresh()
        app.refresh_view()
        await pilot.pause()

    @staticmethod
    def body(app: ObdApp, key: str = "engine") -> PanelScroll:
        """Return the scrollable body of one panel."""
        return app.query_one(f"#{scroll_id(key)}", PanelScroll)

    async def test_a_panel_taller_than_the_window_scrolls(self) -> None:
        app, _ = self._talkative()

        async with app.run_test(size=self.CRAMPED) as pilot:
            await self._fill(app, pilot)

            assert self.body(app).show_vertical_scrollbar
            assert self.body(app).max_scroll_y > 0

    async def test_a_panel_that_fits_has_no_scrollbar(self) -> None:
        app, _ = self._talkative()

        async with app.run_test(size=self.ROOMY) as pilot:
            await self._fill(app, pilot)

            assert not self.body(app).show_vertical_scrollbar
            assert self.body(app).max_scroll_y == 0

    async def test_the_panel_is_bounded_by_the_window(self) -> None:
        app, _ = self._talkative()

        async with app.run_test(size=self.CRAMPED) as pilot:
            await self._fill(app, pilot)
            body = self.body(app)

            assert body.region.height < body.virtual_size.height
            assert body.region.bottom <= self.CRAMPED[1]

    async def test_the_keys_scroll_the_open_panel(self) -> None:
        app, _ = self._talkative()

        async with app.run_test(size=self.CRAMPED) as pilot:
            await self._fill(app, pilot)
            body = self.body(app)

            await pilot.press("down")
            await pilot.pause()
            assert body.scroll_offset.y == 1

            await pilot.press("end")
            await pilot.pause()
            assert body.scroll_offset.y == body.max_scroll_y

            await pilot.press("home")
            await pilot.pause()
            assert body.scroll_offset.y == 0

    async def test_paging_moves_further_than_a_line(self) -> None:
        app, _ = self._talkative()

        async with app.run_test(size=self.CRAMPED) as pilot:
            await self._fill(app, pilot)

            await pilot.press("pagedown")
            await pilot.pause()

            assert self.body(app).scroll_offset.y > 1

    async def test_scrolling_follows_the_open_panel(self) -> None:
        app, _ = self._talkative()

        async with app.run_test(size=self.CRAMPED) as pilot:
            await self._fill(app, pilot)
            await pilot.press("p")
            await pilot.pause()

            await pilot.press("down")
            await pilot.pause()

            assert self.body(app, "catalog").scroll_offset.y == 1
            assert self.body(app).scroll_offset.y == 0


class TestRedraw:
    async def test_a_redraw_without_its_widgets_is_harmless(self) -> None:
        """A sweep can finish after the app has begun tearing down."""
        app, _ = build_app()

        async with app.run_test() as pilot:
            await pilot.pause()
            await app.query_one("#status", StatusBar).remove()

            app.refresh_view()

    async def test_an_unknown_tab_renders_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        app, _ = build_app()

        async with app.run_test() as pilot:
            await pilot.pause()
            before = panel_of(app, "engine")
            # The binding is replaced, not the registry's contents: undoing
            # a deleted key would re-insert it last and reorder the tabs for
            # every test that follows.
            monkeypatch.setattr("obd_tui.app.PANELS_BY_KEY", {})

            app._render_active_panel()

            assert panel_of(app, "engine") == before


class TestQuit:
    async def test_closes_the_link_on_the_way_out(self) -> None:
        app, link = build_app()

        async with app.run_test() as pilot:
            await pilot.press("c")
            await settle(app, pilot)
            await pilot.press("q")
            await pilot.pause()

        assert link.closed == 1


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
