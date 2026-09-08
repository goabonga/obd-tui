# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the diesel aftertreatment monitoring service."""

from __future__ import annotations

from obd_tui.models.dpf import (
    DpfRegeneration,
    DpfRegenState,
    DpfRole,
    DpfTemperatures,
    TemperatureSource,
)
from obd_tui.models.exhaust import ExhaustTemperatures
from obd_tui.models.vehicle import VehicleState
from obd_tui.obd.manufacturers.base import GenericProfile, ManufacturerProfile
from obd_tui.services.diesel_monitoring import (
    complete,
    estimate_regeneration,
    map_dpf_temperatures,
)


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

    def test_a_generic_vehicle_gets_no_filter_temperature(self) -> None:
        state = VehicleState(egt_banks=banks(500.0, 412.0, 365.0, None))

        assert complete(state, GenericProfile()).dpf_temperatures is None


class TestEstimateRegeneration:
    def test_a_hot_filter_at_moderate_load_reads_as_probable(self) -> None:
        state = VehicleState(dpf_temperatures=DpfTemperatures(inlet=610.0), engine_load=35.0)

        assert estimate_regeneration(state) == DpfRegeneration(DpfRegenState.ACTIVE, estimated=True)

    def test_a_hot_exhaust_sensor_counts_too(self) -> None:
        state = VehicleState(egt_banks=banks(620.0, None, None, None), engine_load=35.0)

        assert estimate_regeneration(state).state is DpfRegenState.ACTIVE  # type: ignore[union-attr]

    def test_a_hot_exhaust_under_full_load_is_a_hill_not_a_regeneration(self) -> None:
        state = VehicleState(dpf_temperatures=DpfTemperatures(inlet=610.0), engine_load=95.0)

        assert estimate_regeneration(state).state is DpfRegenState.INACTIVE  # type: ignore[union-attr]

    def test_an_unknown_load_does_not_stop_the_guess(self) -> None:
        state = VehicleState(dpf_temperatures=DpfTemperatures(inlet=610.0))

        assert estimate_regeneration(state).state is DpfRegenState.ACTIVE  # type: ignore[union-attr]

    def test_a_warm_exhaust_reads_as_unlikely(self) -> None:
        state = VehicleState(dpf_temperatures=DpfTemperatures(inlet=380.0, outlet=340.0))

        assert estimate_regeneration(state) == DpfRegeneration(
            DpfRegenState.INACTIVE, estimated=True
        )

    def test_the_hottest_point_decides(self) -> None:
        state = VehicleState(dpf_temperatures=DpfTemperatures(inlet=380.0, internal=600.0))

        assert estimate_regeneration(state).state is DpfRegenState.ACTIVE  # type: ignore[union-attr]

    def test_nothing_to_read_is_nothing_not_inactive(self) -> None:
        assert estimate_regeneration(VehicleState(engine_load=35.0)) is None


class TestCompleteRegeneration:
    def test_keeps_what_the_ecu_reported(self) -> None:
        reported = DpfRegeneration(DpfRegenState.INACTIVE)
        state = VehicleState(
            dpf_regeneration=reported, dpf_temperatures=DpfTemperatures(inlet=610.0)
        )

        assert complete(state, GenericProfile()).dpf_regeneration is reported

    def test_guesses_when_the_ecu_reported_nothing(self) -> None:
        state = VehicleState(dpf_temperatures=DpfTemperatures(inlet=610.0), engine_load=35.0)

        completed = complete(state, GenericProfile())

        assert completed.dpf_regeneration == DpfRegeneration(DpfRegenState.ACTIVE, estimated=True)

    def test_refreshes_a_guess_from_the_current_exhaust(self) -> None:
        stale = DpfRegeneration(DpfRegenState.ACTIVE, estimated=True)
        state = VehicleState(dpf_regeneration=stale, dpf_temperatures=DpfTemperatures(inlet=300.0))

        assert complete(state, GenericProfile()).dpf_regeneration.state is DpfRegenState.INACTIVE  # type: ignore[union-attr]

    def test_a_guess_goes_when_the_exhaust_does(self) -> None:
        stale = DpfRegeneration(DpfRegenState.ACTIVE, estimated=True)

        assert (
            complete(VehicleState(dpf_regeneration=stale), GenericProfile()).dpf_regeneration
            is None
        )

    def test_guesses_from_the_sensors_the_profile_just_placed(self) -> None:
        state = VehicleState(egt_banks=banks(300.0, 610.0, None, None), engine_load=35.0)

        completed = complete(state, PlacingProfile())

        assert completed.dpf_temperatures.inlet == 610.0  # type: ignore[union-attr]
        assert completed.dpf_regeneration.state is DpfRegenState.ACTIVE  # type: ignore[union-attr]
