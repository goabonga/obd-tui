# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the diesel aftertreatment monitoring service."""

from __future__ import annotations

from obd_tui.models.dpf import DpfRole, DpfTemperatures, TemperatureSource
from obd_tui.models.exhaust import ExhaustTemperatures
from obd_tui.models.vehicle import VehicleState
from obd_tui.obd.manufacturers.base import GenericProfile, ManufacturerProfile
from obd_tui.services.diesel_monitoring import complete, map_dpf_temperatures


class PlacingProfile(ManufacturerProfile):
    """A manufacturer that knows where bank 1's sensors sit on its engine."""

    name = "Placing Motors"

    def supports(self, vin: str) -> bool:
        return True

    def exhaust_sensor_role(self, bank: int, sensor: int) -> DpfRole | None:
        if bank != 1:
            return None
        return {2: DpfRole.INLET, 3: DpfRole.OUTLET}.get(sensor)


def banks(*slots: float | None) -> dict[int, ExhaustTemperatures]:
    return {1: ExhaustTemperatures(1, tuple(slots))}


class TestMapDpfTemperatures:
    def test_places_the_sensors_the_profile_knows(self) -> None:
        reading = map_dpf_temperatures(banks(500.0, 412.0, 365.0, None), PlacingProfile())

        assert reading == DpfTemperatures(
            inlet=412.0, outlet=365.0, source=TemperatureSource.EXHAUST
        )

    def test_a_sensor_the_profile_cannot_place_is_left_out(self) -> None:
        reading = map_dpf_temperatures(banks(500.0, 412.0, None, None), PlacingProfile())

        assert reading == DpfTemperatures(inlet=412.0, source=TemperatureSource.EXHAUST)

    def test_a_generic_profile_never_guesses(self) -> None:
        assert map_dpf_temperatures(banks(500.0, 412.0, 365.0, None), GenericProfile()) is None

    def test_a_bank_the_profile_does_not_know_yields_nothing(self) -> None:
        other = {2: ExhaustTemperatures(2, (412.0, 365.0, None, None))}

        assert map_dpf_temperatures(other, PlacingProfile()) is None

    def test_no_bank_yields_nothing(self) -> None:
        assert map_dpf_temperatures({}, PlacingProfile()) is None

    def test_the_first_sensor_placed_at_a_role_keeps_it(self) -> None:
        two_banks = {
            1: ExhaustTemperatures(1, (None, 412.0, None, None)),
            2: ExhaustTemperatures(2, (None, None, None, None)),
        }

        reading = map_dpf_temperatures(two_banks, PlacingProfile())

        assert reading is not None
        assert reading.inlet == 412.0


class TestComplete:
    def test_keeps_what_the_ecu_reported(self) -> None:
        ecu = DpfTemperatures(inlet=430.0, outlet=380.0)
        state = VehicleState(dpf_temperatures=ecu, egt_banks=banks(500.0, 412.0, 365.0, None))

        assert complete(state, PlacingProfile()).dpf_temperatures is ecu

    def test_fills_in_from_the_exhaust_when_the_ecu_reported_nothing(self) -> None:
        state = VehicleState(egt_banks=banks(500.0, 412.0, 365.0, None))

        completed = complete(state, PlacingProfile())

        assert completed.dpf_temperatures == DpfTemperatures(
            inlet=412.0, outlet=365.0, source=TemperatureSource.EXHAUST
        )

    def test_refreshes_a_mapped_reading_from_the_current_sensors(self) -> None:
        stale = DpfTemperatures(inlet=100.0, source=TemperatureSource.EXHAUST)
        state = VehicleState(dpf_temperatures=stale, egt_banks=banks(500.0, 412.0, 365.0, None))

        assert complete(state, PlacingProfile()).dpf_temperatures.inlet == 412.0  # type: ignore[union-attr]

    def test_a_mapped_reading_goes_when_the_sensors_do(self) -> None:
        stale = DpfTemperatures(inlet=100.0, source=TemperatureSource.EXHAUST)

        assert (
            complete(VehicleState(dpf_temperatures=stale), PlacingProfile()).dpf_temperatures
            is None
        )

    def test_a_generic_vehicle_is_left_alone(self) -> None:
        state = VehicleState(egt_banks=banks(500.0, 412.0, 365.0, None))

        assert complete(state, GenericProfile()) == state
