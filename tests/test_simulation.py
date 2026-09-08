# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the simulated vehicle backend."""

from __future__ import annotations

import obd
import pytest

from obd_tui.models.dpf import DpfPressure, DpfTemperatures
from obd_tui.models.exhaust import ExhaustTemperatures
from obd_tui.models.vehicle import VehicleState
from obd_tui.obd.standard import (
    DPF_PRESSURE,
    DPF_TEMPERATURES,
    EGT_BANKS,
    PIDS_D,
    PIDS_E,
    STANDARD_COMMANDS,
)
from obd_tui.services.polling import (
    BANK_READINGS,
    CODE_READINGS,
    NUMERIC_READINGS,
    RAW_READINGS,
)
from obd_tui.services.simulation import (
    BANKS,
    CODES,
    MODELS,
    NUMERIC,
    RAW,
    SIMULATED_ADAPTER,
    SimulatedVehicle,
    constant,
    exhaust_bank,
    ramp,
    simulated_names,
    simulated_session,
    warmup,
    wave,
)
from obd_tui.views.panels import PANELS
from obd_tui.views.units import UnitSystem


class FakeClock:
    """A clock the test moves by hand."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class TestReadingShapes:
    def test_a_constant_never_moves(self) -> None:
        reading = constant(42.0)

        assert reading(0.0) == reading(1000.0) == 42.0

    def test_a_wave_oscillates_around_its_center(self) -> None:
        reading = wave(100.0, 10.0, 8.0)

        assert reading(0.0) == pytest.approx(100.0)
        assert reading(2.0) == pytest.approx(110.0)
        assert reading(6.0) == pytest.approx(90.0)

    def test_a_warmup_climbs_towards_its_target(self) -> None:
        reading = warmup(90.0, 20.0, 30.0)

        assert reading(0.0) == pytest.approx(20.0)
        assert reading(30.0) > 60.0
        assert reading(600.0) == pytest.approx(90.0, abs=0.1)

    def test_a_ramp_sweeps_between_its_bounds(self) -> None:
        reading = ramp(0.0, 100.0, 40.0)

        assert reading(0.0) == pytest.approx(0.0)
        assert reading(20.0) == pytest.approx(100.0)
        assert reading(40.0) == pytest.approx(0.0)


class TestSimulatedVehicle:
    def test_starts_connected(self) -> None:
        assert SimulatedVehicle(clock=FakeClock()).is_connected()

    def test_closing_drops_the_link(self) -> None:
        vehicle = SimulatedVehicle(clock=FakeClock())

        vehicle.close()

        assert not vehicle.is_connected()

    def test_answers_a_known_command(self) -> None:
        response = SimulatedVehicle(clock=FakeClock()).query(obd.commands.RPM)

        assert not response.is_null()
        assert response.value == pytest.approx(880.0)

    def test_answers_nothing_for_an_unsimulated_command(self) -> None:
        assert SimulatedVehicle(clock=FakeClock()).query(obd.commands.PIDS_A).is_null()

    def test_answers_nothing_once_closed(self) -> None:
        vehicle = SimulatedVehicle(clock=FakeClock())
        vehicle.close()

        assert vehicle.query(obd.commands.RPM).is_null()

    def test_readings_move_with_the_clock(self) -> None:
        clock = FakeClock()
        vehicle = SimulatedVehicle(clock=clock)
        first = vehicle.query(obd.commands.COOLANT_TEMP).value

        clock.advance(60.0)

        assert vehicle.query(obd.commands.COOLANT_TEMP).value > first

    def test_reports_its_simulated_commands_as_supported(self) -> None:
        names = {
            str(command.name) for command in SimulatedVehicle(clock=FakeClock()).supported_commands
        }

        assert "RPM" in names
        assert "GET_DTC" in names

    @pytest.mark.parametrize("name", simulated_names())
    def test_every_simulated_command_exists_in_python_obd(self, name: str) -> None:
        assert hasattr(obd.commands, name)

    def test_the_tables_cover_what_the_poller_reads(self) -> None:
        assert set(NUMERIC) == set(NUMERIC_READINGS)
        assert set(RAW) == set(RAW_READINGS)
        assert set(CODES) == set(CODE_READINGS)
        assert set(BANKS) <= set(BANK_READINGS)
        assert set(MODELS) <= {command.name for command in STANDARD_COMMANDS.values()}

    def test_answers_the_filter_pressure(self) -> None:
        response = SimulatedVehicle(clock=FakeClock()).query(DPF_PRESSURE)

        assert isinstance(response.value, DpfPressure)
        assert response.value.differential is not None
        assert response.value.inlet is not None
        assert response.value.outlet is not None
        assert response.value.inlet > response.value.outlet

    def test_answers_the_filter_temperatures(self) -> None:
        clock = FakeClock()
        vehicle = SimulatedVehicle(clock=clock)
        clock.advance(300.0)

        response = vehicle.query(DPF_TEMPERATURES)

        assert isinstance(response.value, DpfTemperatures)
        assert response.value.inlet > response.value.outlet > 100.0  # type: ignore[operator]

    def test_answers_the_exhaust_bank(self) -> None:
        response = SimulatedVehicle(clock=FakeClock()).query(EGT_BANKS["EGT_BANK_1"])

        assert response.value == ExhaustTemperatures(1, (18.0, 18.0, 18.0, None))

    def test_the_exhaust_warms_up_upstream_first(self) -> None:
        clock = FakeClock()
        vehicle = SimulatedVehicle(clock=clock)

        clock.advance(300.0)
        bank = vehicle.query(EGT_BANKS["EGT_BANK_1"]).value

        assert bank.sensors[0] > bank.sensors[1] > bank.sensors[2] > 100.0
        assert bank.sensors[3] is None

    def test_the_fourth_sensor_is_never_fitted(self) -> None:
        assert exhaust_bank(0.0).sensors[3] is None
        assert exhaust_bank(3600.0).sensors[3] is None

    def test_vouches_for_the_bank_through_the_bitmap(self) -> None:
        response = SimulatedVehicle(clock=FakeClock()).query(PIDS_D)

        assert response.value == frozenset({0x78, 0x7A, 0x7C})

    def test_the_second_bitmap_names_nothing_yet(self) -> None:
        assert SimulatedVehicle(clock=FakeClock()).query(PIDS_E).value == frozenset()

    def test_the_bank_is_not_a_python_obd_name(self) -> None:
        assert "EGT_BANK_1" not in simulated_names()


class TestSimulatedSession:
    def test_connects_without_hardware(self) -> None:
        session = simulated_session(clock=FakeClock())

        session.connect()

        assert session.is_connected
        assert session.adapter == SIMULATED_ADAPTER
        assert session.summary == "CONNECTED  |  /dev/obd-tui-demo  |  0403:6015"

    def test_discovers_the_simulated_commands(self) -> None:
        session = simulated_session(clock=FakeClock())

        session.connect()

        assert session.catalog.supports("RPM")
        assert session.catalog.supports("EGT_BANK_1")
        assert session.catalog.supports("DPF_DIFFERENTIAL_PRESSURE")
        # The catalogue counts capabilities, and two of them share one command.
        answered = sum(
            1 for command in STANDARD_COMMANDS.values() if command.name in (*BANKS, *MODELS)
        )
        assert session.catalog.supported_count == len(simulated_names()) + answered
        assert session.catalog.supports("DPF_TEMP_INLET")
        assert session.catalog.supports("DPF_TEMP_OUTLET")
        assert STANDARD_COMMANDS["DPF_TEMP_INLET"] is STANDARD_COMMANDS["DPF_TEMP_OUTLET"]

    def test_fills_all_three_families_of_readings(self) -> None:
        session = simulated_session(clock=FakeClock())
        session.connect()

        state = session.refresh()

        assert state.rpm is not None
        assert state.status is not None
        assert state.stored_codes

    def test_fills_every_field_the_poller_knows(self) -> None:
        session = simulated_session(clock=FakeClock())
        session.connect()

        state = session.refresh()
        fields = (*NUMERIC_READINGS.values(), *RAW_READINGS.values())

        assert [field for field in fields if getattr(state, field) is None] == []

    def test_fills_the_exhaust_sensors_that_are_fitted(self) -> None:
        session = simulated_session(clock=FakeClock())
        session.connect()

        state = session.refresh()

        assert [number for number, _ in state.egt_banks[1].fitted] == [1, 2, 3]

    def test_fills_the_filter_pressure(self) -> None:
        session = simulated_session(clock=FakeClock())
        session.connect()

        state = session.refresh()

        assert state.dpf_differential_pressure_kpa is not None
        assert state.dpf_temperatures is not None

    def test_every_panel_renders_the_simulated_vehicle(self) -> None:
        session = simulated_session(clock=FakeClock())
        session.connect()
        session.refresh()

        for panel in PANELS:
            for units in UnitSystem:
                assert panel.render(session.vehicle, session.catalog, units).strip()

    def test_disconnecting_stops_the_readings(self) -> None:
        session = simulated_session(clock=FakeClock())
        session.connect()
        session.refresh()

        session.disconnect()

        assert session.refresh() == VehicleState()
