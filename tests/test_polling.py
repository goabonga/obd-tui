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
    ALL_READINGS,
    CODE_READINGS,
    FAST_COMMANDS,
    NUMERIC_READINGS,
    RAW_READINGS,
    SLOW_COMMANDS,
    SensorPoller,
    Tier,
    is_due,
    tier_of,
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


class TestTiers:
    def test_a_driving_reading_is_fast(self) -> None:
        assert tier_of("RPM") is Tier.FAST

    def test_a_session_wide_reading_is_slow(self) -> None:
        assert tier_of("CALIBRATION_ID") is Tier.SLOW

    def test_anything_else_falls_back_to_medium(self) -> None:
        assert tier_of("COOLANT_TEMP") is Tier.MEDIUM
        assert tier_of("NOT_A_COMMAND") is Tier.MEDIUM

    def test_the_tiers_only_name_commands_the_poller_reads(self) -> None:
        assert set(ALL_READINGS) >= FAST_COMMANDS
        assert set(ALL_READINGS) >= SLOW_COMMANDS

    def test_a_command_has_a_single_tier(self) -> None:
        assert not FAST_COMMANDS & SLOW_COMMANDS

    def test_all_readings_covers_the_three_maps(self) -> None:
        assert set(ALL_READINGS) == {*NUMERIC_READINGS, *RAW_READINGS, *CODE_READINGS}

    @pytest.mark.parametrize(
        ("sweep", "fast", "medium", "slow"),
        [
            (0, True, True, True),
            (1, True, False, False),
            (5, True, True, False),
            (59, True, False, False),
            (60, True, True, True),
        ],
    )
    def test_each_tier_comes_round_on_its_own_period(
        self, sweep: int, fast: bool, medium: bool, slow: bool
    ) -> None:
        assert is_due("RPM", sweep) is fast
        assert is_due("COOLANT_TEMP", sweep) is medium
        assert is_due("GET_DTC", sweep) is slow


class TestSweepCadence:
    def test_the_first_sweep_asks_for_everything(self) -> None:
        poll, connection = poller()

        poll.poll(VehicleState())

        assert set(connection.asked) == set(ALL_READINGS)

    def test_the_next_sweep_asks_only_for_the_fast_readings(self) -> None:
        poll, connection = poller()
        poll.poll(VehicleState())
        connection.asked.clear()

        poll.poll(VehicleState())

        assert set(connection.asked) == FAST_COMMANDS

    def test_the_medium_readings_come_back_round(self) -> None:
        poll, connection = poller()
        for _ in range(5):
            poll.poll(VehicleState())
        connection.asked.clear()

        poll.poll(VehicleState())

        assert "COOLANT_TEMP" in connection.asked
        assert "GET_DTC" not in connection.asked

    def test_a_skipped_reading_keeps_its_previous_value(self) -> None:
        poll, connection = poller({"COOLANT_TEMP": 91.0})
        state = poll.poll(VehicleState())

        connection.answers.clear()
        poll.poll(state)

        assert state.coolant_temp == pytest.approx(91.0)

    def test_the_sweep_count_follows_the_polls(self) -> None:
        poll, _ = poller()

        assert poll.sweep_count == 0
        poll.poll(VehicleState())
        assert poll.sweep_count == 1


class TestCatalogFiltering:
    def test_queries_only_the_supported_commands(self) -> None:
        poll, connection = poller({"RPM": 900.0})

        poll.poll(VehicleState(), catalog_of("RPM", "SPEED"))

        assert connection.asked == ["RPM", "SPEED"]

    def test_queries_everything_without_a_catalog(self) -> None:
        poll, connection = poller()

        poll.poll(VehicleState())

        assert len(connection.asked) == len(ALL_READINGS)

    def test_queries_everything_when_discovery_came_back_empty(self) -> None:
        poll, connection = poller()

        poll.poll(VehicleState(), CommandCatalog())

        assert "RPM" in connection.asked
