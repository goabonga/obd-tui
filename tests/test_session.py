# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the connection lifecycle."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from obd_tui.models.adapter import AdapterInfo, ConnectionState
from obd_tui.models.commands import CommandCatalog, CommandInfo
from obd_tui.models.vehicle import TroubleCode
from obd_tui.services.connection import AdapterError
from obd_tui.services.recording import SessionRecorder
from obd_tui.services.session import Session

ADAPTER = AdapterInfo(port="/dev/ttyUSB0", vid="0403", pid="6015", label="vLinker MC+")
CATALOG = CommandCatalog(modes={"Mode 01": [CommandInfo("RPM", "0x0C", "Engine RPM", True)]})

# A vehicle supporting enough commands for a run of unanswered ones to read
# as a lost link rather than a few dropped frames.
CHATTY = ("RPM", "SPEED", "ENGINE_LOAD", "MAF", "THROTTLE_POS", "OIL_TEMP")
CHATTY_CATALOG = CommandCatalog(
    modes={"Mode 01": [CommandInfo(command, supported=True) for command in CHATTY]}
)


class FakeConnection:
    """Connection double with scripted open/query behaviour."""

    def __init__(
        self,
        opens: bool = True,
        answers: dict[str, Any] | None = None,
        catalog: CommandCatalog = CATALOG,
    ) -> None:
        self.opens = opens
        self.answers = answers or {}
        self.catalog = catalog
        self.clears = True
        self.cleared = 0
        # Flipped when the adapter itself stops carrying questions, which
        # is the only thing that means the link is gone.
        self.unreachable = False
        self.opened: list[str] = []
        self.asked: list[str] = []
        self.sweeps = 0
        self.closed = 0

    def open(self, port: str) -> bool:
        self.opened.append(port)
        return self.opens

    def close(self) -> None:
        self.closed += 1

    def discover(self) -> CommandCatalog:
        return self.catalog

    def clear_codes(self) -> bool:
        self.cleared += 1
        return self.clears

    @contextmanager
    def sweep(self) -> Iterator[None]:
        self.sweeps += 1
        yield

    def query(self, name: str) -> Any | None:
        self.asked.append(name)
        if self.unreachable:
            raise AdapterError(f"cannot reach the vehicle for {name}")
        return self.answers.get(name)


def session(
    connection: FakeConnection | None = None,
    adapter: AdapterInfo | None = ADAPTER,
    port: str | None = None,
) -> tuple[Session, FakeConnection]:
    link = connection or FakeConnection()
    return Session(port=port, connection=link, detector=lambda: adapter), link  # type: ignore[arg-type]


class TestConnect:
    def test_opens_the_detected_adapter(self) -> None:
        sess, link = session()

        assert sess.connect() is ConnectionState.CONNECTED
        assert link.opened == ["/dev/ttyUSB0"]
        assert sess.adapter == ADAPTER
        assert sess.is_connected

    def test_stores_the_discovered_catalog(self) -> None:
        sess, _ = session()

        sess.connect()

        assert sess.catalog is CATALOG

    def test_reports_no_device_when_nothing_is_plugged_in(self) -> None:
        sess, link = session(adapter=None)

        assert sess.connect() is ConnectionState.NO_DEVICE
        assert link.opened == []
        assert not sess.is_connected

    def test_reports_failure_when_the_port_refuses_to_open(self) -> None:
        sess, _ = session(FakeConnection(opens=False))

        assert sess.connect() is ConnectionState.FAILED
        assert not sess.is_connected

    def test_remembers_the_adapter_that_failed_to_open(self) -> None:
        sess, _ = session(FakeConnection(opens=False))

        sess.connect()

        assert sess.adapter == ADAPTER


class TestRequestedPort:
    def test_uses_the_requested_port_instead_of_scanning(self) -> None:
        sess, link = session(adapter=None, port="/dev/rfcomm0")

        assert sess.connect() is ConnectionState.CONNECTED
        assert link.opened == ["/dev/rfcomm0"]

    def test_keeps_the_usb_ids_when_the_scan_found_that_same_port(self) -> None:
        sess, _ = session(port="/dev/ttyUSB0")

        sess.connect()

        assert sess.adapter == ADAPTER

    def test_overrides_a_detected_adapter_on_another_port(self) -> None:
        sess, link = session(port="/dev/ttyUSB9")

        sess.connect()

        assert link.opened == ["/dev/ttyUSB9"]
        assert sess.adapter == AdapterInfo(port="/dev/ttyUSB9")


class TestDisconnect:
    def test_closes_the_link_and_clears_the_session(self) -> None:
        sess, link = session(FakeConnection(answers={"RPM": 900.0}))
        sess.connect()
        sess.refresh()

        sess.disconnect()

        assert link.closed == 1
        assert sess.state is ConnectionState.DISCONNECTED
        assert sess.adapter is None
        assert len(sess.catalog) == 0
        assert sess.vehicle.rpm is None
        assert sess.history.series("rpm") == []

    def test_disconnecting_while_offline_is_harmless(self) -> None:
        sess, link = session()

        sess.disconnect()

        assert link.closed == 1
        assert sess.state is ConnectionState.DISCONNECTED


class TestRefresh:
    def test_polls_the_vehicle_while_connected(self) -> None:
        sess, _ = session(FakeConnection(answers={"RPM": 2400.0}))
        sess.connect()

        state = sess.refresh()

        assert state is sess.vehicle
        assert state.rpm == 2400.0

    def test_polls_only_the_supported_commands(self) -> None:
        sess, _ = session(FakeConnection(answers={"RPM": 2400.0, "SPEED": 55.0}))
        sess.connect()

        state = sess.refresh()

        assert state.rpm == 2400.0
        assert state.speed is None

    def test_does_not_poll_while_offline(self) -> None:
        sess, _ = session(FakeConnection(answers={"RPM": 2400.0}))

        assert sess.refresh().rpm is None

    def test_passes_the_displayed_fields_to_the_poller(self) -> None:
        sess, link = session(FakeConnection(answers={"RPM": 2400.0, "OIL_TEMP": 90.0}))
        sess.connect()
        sess.catalog = CommandCatalog()
        sess.refresh()
        link.asked.clear()

        sess.refresh(priority=("oil_temp",))

        assert "OIL_TEMP" in link.asked

    def test_records_each_sweep_in_the_history(self) -> None:
        sess, _ = session(FakeConnection(answers={"RPM": 2400.0}))
        sess.connect()

        sess.refresh()
        sess.refresh()

        assert sess.history.series("rpm") == [2400.0, 2400.0]

    def test_does_not_record_while_offline(self) -> None:
        sess, _ = session(FakeConnection(answers={"RPM": 2400.0}))

        sess.refresh()

        assert sess.history.series("rpm") == []


class TestClearCodes:
    @staticmethod
    def _faulty_session() -> tuple[Session, FakeConnection]:
        """A connected session whose vehicle reports one stored code."""
        link = FakeConnection(
            answers={"RPM": 900.0, "GET_DTC": [("P0401", "EGR flow")]},
            catalog=CommandCatalog(
                modes={
                    "Mode 01": [
                        CommandInfo("RPM", supported=True),
                        CommandInfo("GET_DTC", supported=True),
                    ]
                }
            ),
        )
        sess = Session(connection=link, detector=lambda: ADAPTER)  # type: ignore[arg-type]
        sess.connect()
        sess.refresh()
        return sess, link

    def test_sends_mode_04_and_reads_back_what_remains(self) -> None:
        sess, link = self._faulty_session()
        link.answers.pop("GET_DTC")

        assert sess.clear_codes() is True
        assert link.cleared == 1
        assert sess.vehicle.stored_codes == ()

    def test_a_fault_still_present_comes_straight_back(self) -> None:
        sess, _ = self._faulty_session()

        sess.clear_codes()

        assert sess.vehicle.stored_codes == (TroubleCode("P0401", "EGR flow"),)

    def test_does_nothing_while_offline(self) -> None:
        link = FakeConnection()
        sess = Session(connection=link, detector=lambda: ADAPTER)  # type: ignore[arg-type]

        assert sess.clear_codes() is False
        assert link.cleared == 0

    def test_keeps_the_codes_when_the_ecu_refuses(self) -> None:
        sess, link = self._faulty_session()
        link.clears = False

        assert sess.clear_codes() is False
        assert sess.vehicle.stored_codes == (TroubleCode("P0401", "EGR flow"),)


class TestLinkLoss:
    def test_a_vehicle_that_answers_nothing_keeps_the_session(self) -> None:
        """A quiet vehicle is not a lost link: the adapter still answers."""
        link = FakeConnection(catalog=CHATTY_CATALOG)
        sess = Session(connection=link, detector=lambda: ADAPTER)  # type: ignore[arg-type]
        sess.connect()

        for _ in range(3):
            sess.refresh()

        assert sess.is_connected

    @staticmethod
    def _silent_session(
        recorder: SessionRecorder | None = None,
    ) -> tuple[Session, FakeConnection]:
        """A session that sweeps once, then loses the adapter."""
        link = FakeConnection(
            answers={command: 900.0 for command in CHATTY}, catalog=CHATTY_CATALOG
        )
        sess = Session(
            connection=link,  # type: ignore[arg-type]
            detector=lambda: ADAPTER,
            recorder=recorder,
        )
        sess.connect()
        sess.refresh()
        link.unreachable = True
        return sess, link

    def test_drops_the_session_when_the_vehicle_goes_quiet(self) -> None:
        sess, link = self._silent_session()

        sess.refresh()

        assert sess.state is ConnectionState.LOST
        assert not sess.is_connected
        assert link.closed == 1

    def test_keeps_the_last_readings_on_screen(self) -> None:
        sess, _ = self._silent_session()

        sess.refresh()

        assert sess.vehicle.rpm == 900.0
        assert sess.history.series("rpm") == [900.0]
        assert len(sess.catalog) > 0

    def test_stops_polling_once_the_link_is_lost(self) -> None:
        sess, link = self._silent_session()
        sess.refresh()
        link.asked.clear()

        sess.refresh()

        assert link.asked == []

    def test_says_so_in_the_summary(self) -> None:
        sess, _ = self._silent_session()

        sess.refresh()

        assert sess.summary.startswith("LINK LOST")

    def test_reconnecting_after_a_loss_works(self) -> None:
        sess, link = self._silent_session()
        sess.refresh()
        link.unreachable = False
        link.answers.update({command: 1000.0 for command in CHATTY})

        assert sess.connect() is ConnectionState.CONNECTED
        assert sess.refresh().rpm == 1000.0

    def test_closes_the_recording(self, tmp_path: Path) -> None:
        log = SessionRecorder(tmp_path / "session.jsonl")
        sess, _ = self._silent_session(recorder=log)

        sess.refresh()

        assert log._handle is None


class TestRecording:
    def test_records_each_sweep(self, tmp_path: Path) -> None:
        path = tmp_path / "session.jsonl"
        sess = Session(
            connection=FakeConnection(answers={"RPM": 2400.0}),  # type: ignore[arg-type]
            detector=lambda: ADAPTER,
            recorder=SessionRecorder(path),
        )
        sess.connect()

        sess.refresh()
        sess.refresh()

        assert len(path.read_text(encoding="utf-8").splitlines()) == 2

    def test_records_nothing_while_offline(self, tmp_path: Path) -> None:
        path = tmp_path / "session.jsonl"
        sess = Session(
            connection=FakeConnection(),  # type: ignore[arg-type]
            detector=lambda: ADAPTER,
            recorder=SessionRecorder(path),
        )

        sess.refresh()

        assert not path.exists()

    def test_disconnecting_closes_the_recording(self, tmp_path: Path) -> None:
        path = tmp_path / "session.jsonl"
        log = SessionRecorder(path)
        sess = Session(
            connection=FakeConnection(answers={"RPM": 2400.0}),  # type: ignore[arg-type]
            detector=lambda: ADAPTER,
            recorder=log,
        )
        sess.connect()
        sess.refresh()

        sess.disconnect()

        assert log._handle is None
        assert json.loads(path.read_text(encoding="utf-8").splitlines()[0])["rpm"] == 2400.0


class TestSummary:
    def test_shows_the_offline_placeholders(self) -> None:
        sess, _ = session()

        assert sess.summary == "DISCONNECTED  |  -  |  -:-"

    def test_shows_the_state_port_and_usb_ids_once_connected(self) -> None:
        sess, _ = session()
        sess.connect()

        assert sess.summary == "CONNECTED  |  /dev/ttyUSB0  |  0403:6015"

    def test_shows_the_failure_state(self) -> None:
        sess, _ = session(adapter=None)
        sess.connect()

        assert sess.summary.startswith("NO DEVICE")


def test_a_default_session_builds_its_own_collaborators() -> None:
    sess = Session()

    assert sess.state is ConnectionState.DISCONNECTED
    assert not sess.is_connected
