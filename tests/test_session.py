# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the connection lifecycle."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from obd_tui.models.adapter import AdapterInfo, ConnectionState
from obd_tui.models.commands import CommandCatalog, CommandInfo
from obd_tui.services.recording import SessionRecorder
from obd_tui.services.session import Session

ADAPTER = AdapterInfo(port="/dev/ttyUSB0", vid="0403", pid="6015", label="vLinker MC+")
CATALOG = CommandCatalog(modes={"Mode 01": [CommandInfo("RPM", "0x0C", "Engine RPM", True)]})


class FakeConnection:
    """Connection double with scripted open/query behaviour."""

    def __init__(self, opens: bool = True, answers: dict[str, Any] | None = None) -> None:
        self.opens = opens
        self.answers = answers or {}
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
