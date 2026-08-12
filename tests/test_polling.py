# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the sensor polling service."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import obd
import pytest

from obd_tui.models.commands import CommandCatalog, CommandInfo
from obd_tui.models.vehicle import TroubleCode, VehicleState
from obd_tui.services.polling import (
    CODE_READINGS,
    NUMERIC_READINGS,
    RAW_READINGS,
    SensorPoller,
)


class FakeConnection:
    """Answers a fixed set of commands and records what was asked."""

    def __init__(self, answers: dict[str, Any] | None = None) -> None:
        self.answers = answers or {}
        self.asked: list[str] = []

    def query(self, name: str) -> Any | None:
        self.asked.append(name)
        return self.answers.get(name)


def poller(answers: dict[str, Any] | None = None) -> tuple[SensorPoller, FakeConnection]:
    connection = FakeConnection(answers)
    return SensorPoller(connection), connection  # type: ignore[arg-type]


def catalog_of(*names: str) -> CommandCatalog:
    return CommandCatalog(modes={"Mode 01": [CommandInfo(name, supported=True) for name in names]})


class TestCommandMaps:
    @pytest.mark.parametrize(
        "command",
        sorted({*NUMERIC_READINGS, *RAW_READINGS, *CODE_READINGS}),
    )
    def test_every_mapped_command_exists_in_python_obd(self, command: str) -> None:
        assert hasattr(obd.commands, command)

    @pytest.mark.parametrize(
        "field",
        sorted({*NUMERIC_READINGS.values(), *RAW_READINGS.values(), *CODE_READINGS.values()}),
    )
    def test_every_mapped_field_exists_on_the_state(self, field: str) -> None:
        assert hasattr(VehicleState(), field)

    def test_the_maps_do_not_overlap(self) -> None:
        assert not set(NUMERIC_READINGS) & set(RAW_READINGS)
        assert not set(NUMERIC_READINGS) & set(CODE_READINGS)


class TestPoll:
    def test_stores_a_pint_quantity_as_a_float(self) -> None:
        poll, _ = poller({"RPM": SimpleNamespace(magnitude=1450.0, units="rpm")})

        state = poll.poll(VehicleState())

        assert state.rpm == pytest.approx(1450.0)

    def test_stores_a_bare_number(self) -> None:
        poll, _ = poller({"COOLANT_TEMP": 91})

        assert poll.poll(VehicleState()).coolant_temp == pytest.approx(91.0)

    def test_ignores_a_reading_that_is_not_numeric(self) -> None:
        poll, _ = poller({"RPM": "garbage"})

        assert poll.poll(VehicleState()).rpm is None

    def test_keeps_the_previous_value_when_a_frame_is_dropped(self) -> None:
        poll, _ = poller({})
        state = VehicleState(rpm=1200.0)

        assert poll.poll(state).rpm == pytest.approx(1200.0)

    def test_stores_a_raw_reading_untouched(self) -> None:
        status = SimpleNamespace(MIL=True, DTC_count=1)
        poll, _ = poller({"STATUS": status})

        assert poll.poll(VehicleState()).status is status

    def test_converts_trouble_codes(self) -> None:
        poll, _ = poller({"GET_DTC": [("P0401", "EGR flow insufficient"), ("P0100", "MAF")]})

        state = poll.poll(VehicleState())

        assert state.stored_codes == [
            TroubleCode("P0401", "EGR flow insufficient"),
            TroubleCode("P0100", "MAF"),
        ]

    def test_converts_a_bare_code_without_a_description(self) -> None:
        poll, _ = poller({"GET_CURRENT_DTC": ["P0401"]})

        assert poll.poll(VehicleState()).pending_codes == [TroubleCode("P0401", "")]

    def test_ignores_a_trouble_code_reading_that_is_not_a_list(self) -> None:
        poll, _ = poller({"GET_DTC": 7})

        assert poll.poll(VehicleState()).stored_codes == []

    def test_returns_the_same_state_object(self) -> None:
        poll, _ = poller()
        state = VehicleState()

        assert poll.poll(state) is state

    def test_derives_net_boost_from_the_two_pressures(self) -> None:
        poll, _ = poller({"INTAKE_PRESSURE": 175.0, "BAROMETRIC_PRESSURE": 100.0})

        assert poll.poll(VehicleState()).net_boost == pytest.approx(75.0)


class TestCatalogFiltering:
    def test_queries_only_the_supported_commands(self) -> None:
        poll, connection = poller({"RPM": 900.0})

        poll.poll(VehicleState(), catalog_of("RPM", "SPEED"))

        assert connection.asked == ["RPM", "SPEED"]

    def test_queries_everything_without_a_catalog(self) -> None:
        poll, connection = poller()

        poll.poll(VehicleState())

        assert len(connection.asked) == len(NUMERIC_READINGS) + len(RAW_READINGS) + len(
            CODE_READINGS
        )

    def test_queries_everything_when_discovery_came_back_empty(self) -> None:
        poll, connection = poller()

        poll.poll(VehicleState(), CommandCatalog())

        assert "RPM" in connection.asked
