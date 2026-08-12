# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the python-obd connection wrapper."""

from __future__ import annotations

from typing import Any

from obd_tui.services.connection import ADAPTER_LABEL, ObdConnection


class FakeResponse:
    """python-obd response double."""

    def __init__(self, value: Any, null: bool = False) -> None:
        self.value = value
        self._null = null

    def is_null(self) -> bool:
        return self._null


class FakeObd:
    """python-obd connection double."""

    def __init__(
        self,
        connected: bool = True,
        supported: tuple[str, ...] = ("RPM",),
        response: Any = None,
    ) -> None:
        self._connected = connected
        self.supported_commands = [FakeCommand(name) for name in supported]
        self.response = FakeResponse(42.0) if response is None else response
        self.closed = False
        self.queried: list[str] = []

    def is_connected(self) -> bool:
        return self._connected

    def close(self) -> None:
        self.closed = True
        self._connected = False

    def query(self, command: Any) -> Any:
        self.queried.append(str(command.name))
        return self.response


class FakeCommand:
    """python-obd command double, enough for the supported-name scan."""

    def __init__(self, name: str) -> None:
        self.name = name


def connection(adapter: FakeObd | None = None, port: str = "/dev/ttyUSB0") -> ObdConnection:
    """Return an already-opened connection backed by ``adapter``."""
    conn = ObdConnection(factory=lambda _: adapter or FakeObd())
    conn.open(port)
    return conn


class TestOpen:
    def test_opens_the_port_through_the_factory(self) -> None:
        seen: list[str] = []
        conn = ObdConnection(factory=lambda port: seen.append(port) or FakeObd())

        assert conn.open("/dev/ttyUSB0") is True
        assert seen == ["/dev/ttyUSB0"]
        assert conn.is_open is True

    def test_reports_failure_when_the_port_cannot_be_opened(self) -> None:
        def explode(port: str) -> Any:
            raise OSError(f"no such device: {port}")

        conn = ObdConnection(factory=explode)

        assert conn.open("/dev/ttyUSB9") is False
        assert conn.is_open is False

    def test_reports_failure_when_the_adapter_never_connects(self) -> None:
        adapter = FakeObd(connected=False)
        conn = ObdConnection(factory=lambda _: adapter)

        assert conn.open("/dev/ttyUSB0") is False
        assert adapter.closed is True

    def test_is_open_is_false_when_the_adapter_raises(self) -> None:
        adapter = FakeObd()
        conn = connection(adapter)
        adapter.is_connected = _raise  # type: ignore[method-assign]

        assert conn.is_open is False


class TestClose:
    def test_closes_the_underlying_connection(self) -> None:
        adapter = FakeObd()
        conn = connection(adapter)

        conn.close()

        assert adapter.closed is True
        assert conn.is_open is False

    def test_survives_an_adapter_that_raises_on_close(self) -> None:
        adapter = FakeObd()
        conn = connection(adapter)
        adapter.close = _raise  # type: ignore[method-assign]

        conn.close()

        assert conn.is_open is False

    def test_closing_twice_is_harmless(self) -> None:
        conn = connection()

        conn.close()
        conn.close()

        assert conn.is_open is False


class TestQuery:
    def test_returns_the_decoded_value(self) -> None:
        adapter = FakeObd(response=FakeResponse(880.0))

        assert connection(adapter).query("RPM") == 880.0
        assert adapter.queried == ["RPM"]

    def test_returns_none_for_a_null_response(self) -> None:
        adapter = FakeObd(response=FakeResponse(None, null=True))

        assert connection(adapter).query("RPM") is None

    def test_returns_none_for_an_unknown_command(self) -> None:
        adapter = FakeObd()

        assert connection(adapter).query("NOT_A_COMMAND") is None
        assert adapter.queried == []

    def test_returns_none_when_the_link_is_down(self) -> None:
        conn = ObdConnection(factory=lambda _: FakeObd())

        assert conn.query("RPM") is None

    def test_returns_none_when_the_adapter_raises(self) -> None:
        adapter = FakeObd()
        conn = connection(adapter)
        adapter.query = _raise  # type: ignore[method-assign]

        assert conn.query("RPM") is None


class TestDiscover:
    def test_lists_the_known_modes_and_the_adapter_commands(self) -> None:
        catalog = connection(FakeObd(supported=("RPM", "SPEED"))).discover()

        assert "Mode 01 — Live data" in catalog.modes
        assert ADAPTER_LABEL in catalog.modes
        assert len(catalog) > 0

    def test_marks_the_commands_the_vehicle_reported(self) -> None:
        catalog = connection(FakeObd(supported=("RPM", "SPEED"))).discover()

        assert catalog.supported_names == frozenset({"RPM", "SPEED"})
        assert catalog.supports("RPM")
        assert not catalog.supports("OIL_TEMP")

    def test_renders_the_pid_of_a_mode_01_command(self) -> None:
        catalog = connection().discover()
        rpm = next(command for command in catalog if command.name == "RPM")

        assert rpm.pid == "0x0C"
        assert rpm.description

    def test_returns_an_empty_catalog_when_the_link_is_down(self) -> None:
        conn = ObdConnection(factory=lambda _: FakeObd())

        assert len(conn.discover()) == 0

    def test_survives_an_adapter_that_hides_its_supported_commands(self) -> None:
        adapter = FakeObd()
        conn = connection(adapter)
        del adapter.supported_commands

        catalog = conn.discover()

        assert len(catalog) > 0
        assert catalog.supported_count == 0


def _raise(*args: Any, **kwargs: Any) -> Any:
    """Fail the way a flaky adapter does: at any call, with anything."""
    raise OSError("adapter went away")
