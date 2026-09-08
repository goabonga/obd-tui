# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the diesel aftertreatment monitoring service."""

from __future__ import annotations

from obd_tui.models.dpf import (
    DpfLoad,
    DpfPressure,
    DpfRegeneration,
    DpfRegenState,
    DpfRole,
    DpfTemperatures,
    PressureAssessment,
    TemperatureSource,
)
from obd_tui.models.exhaust import ExhaustTemperatures
from obd_tui.models.vehicle import VehicleState
from obd_tui.obd.manufacturers.base import GenericProfile, ManufacturerProfile
from obd_tui.services.diesel_monitoring import (
    DieselMonitor,
    assess_pressure,
    complete,
    estimate_regeneration,
    map_dpf_temperatures,
    pressure_per_flow,
    temperature_delta,
)


class FakeClock:
    """A clock the test moves by hand."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


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


class TestAssessPressure:
    def test_unavailable_without_a_differential(self) -> None:
        assert assess_pressure(VehicleState()) is PressureAssessment.UNAVAILABLE
        state = VehicleState(dpf_pressure=DpfPressure(inlet=105.0, outlet=100.0))
        assert assess_pressure(state) is PressureAssessment.UNAVAILABLE

    def test_normal_at_a_few_kpa(self) -> None:
        state = VehicleState(dpf_pressure=DpfPressure(differential=4.8))

        assert assess_pressure(state) is PressureAssessment.NORMAL

    def test_elevated_past_the_bound(self) -> None:
        state = VehicleState(dpf_pressure=DpfPressure(differential=24.0))

        assert assess_pressure(state) is PressureAssessment.ELEVATED

    def test_inconsistent_when_more_pressure_after_the_filter_than_before(self) -> None:
        state = VehicleState(dpf_pressure=DpfPressure(differential=4.8, inlet=100.0, outlet=105.0))

        assert assess_pressure(state) is PressureAssessment.INCONSISTENT

    def test_never_a_verdict(self) -> None:
        assert "clogged" not in {state.value for state in PressureAssessment}


class TestDerived:
    def test_pressure_per_flow_takes_the_flow_out(self) -> None:
        state = VehicleState(dpf_pressure=DpfPressure(differential=8.0), mass_air_flow=40.0)

        assert pressure_per_flow(state) == 0.2

    def test_pressure_per_flow_needs_both_and_a_moving_flow(self) -> None:
        assert pressure_per_flow(VehicleState(mass_air_flow=40.0)) is None
        assert pressure_per_flow(VehicleState(dpf_pressure=DpfPressure(differential=8.0))) is None
        still = VehicleState(dpf_pressure=DpfPressure(differential=8.0), mass_air_flow=0.0)
        assert pressure_per_flow(still) is None

    def test_temperature_delta_is_inlet_minus_outlet(self) -> None:
        state = VehicleState(dpf_temperatures=DpfTemperatures(inlet=512.0, outlet=438.0))

        assert temperature_delta(state) == 74.0

    def test_temperature_delta_needs_both_ends(self) -> None:
        assert temperature_delta(VehicleState()) is None
        assert (
            temperature_delta(VehicleState(dpf_temperatures=DpfTemperatures(inlet=512.0))) is None
        )


class TestDieselMonitor:
    @staticmethod
    def _monitor() -> tuple[DieselMonitor, FakeClock]:
        clock = FakeClock()
        return DieselMonitor(clock), clock

    def test_sums_the_readings_up_in_one_view(self) -> None:
        monitor, _ = self._monitor()
        state = VehicleState(
            dpf_pressure=DpfPressure(differential=8.2),
            dpf_load=DpfLoad(percent=42.0, soot_mass_g=18.4),
            dpf_temperatures=DpfTemperatures(inlet=512.0, outlet=438.0),
            dpf_regeneration=DpfRegeneration(DpfRegenState.ACTIVE),
            mass_air_flow=41.0,
        )

        view = monitor.observe(state, GenericProfile()).diesel

        assert view is not None
        assert view.differential_pressure_kpa == 8.2
        assert view.pressure_per_flow == 8.2 / 41.0
        assert view.pressure_state is PressureAssessment.NORMAL
        assert view.soot_load_percent == 42.0
        assert view.soot_mass_g == 18.4
        assert view.temperatures == state.dpf_temperatures
        assert view.temperature_delta == 74.0
        assert view.regeneration == state.dpf_regeneration

    def test_a_petrol_vehicle_gets_an_empty_view(self) -> None:
        monitor, _ = self._monitor()

        view = monitor.observe(VehicleState(rpm=900.0), GenericProfile()).diesel

        assert view is not None
        assert view.pressure_state is PressureAssessment.UNAVAILABLE
        assert view.regeneration is None
        assert view.soot_load_percent is None
        assert view.since_regeneration_s is None

    def test_completes_the_readings_before_summing_them_up(self) -> None:
        monitor, _ = self._monitor()
        state = VehicleState(egt_banks=banks(300.0, 610.0, None, None), engine_load=35.0)

        view = monitor.observe(state, PlacingProfile()).diesel

        assert view is not None
        assert view.temperatures is not None
        assert view.temperatures.source is TemperatureSource.EXHAUST
        assert view.regeneration is not None
        assert view.regeneration.estimated

    def test_counts_the_time_since_a_regeneration_it_saw_end(self) -> None:
        monitor, clock = self._monitor()
        active = VehicleState(dpf_regeneration=DpfRegeneration(DpfRegenState.ACTIVE))
        inactive = VehicleState(dpf_regeneration=DpfRegeneration(DpfRegenState.INACTIVE))

        assert monitor.observe(active, GenericProfile()).diesel.since_regeneration_s is None  # type: ignore[union-attr]
        clock.now = 100.0
        assert monitor.observe(inactive, GenericProfile()).diesel.since_regeneration_s == 0.0  # type: ignore[union-attr]
        clock.now = 160.0
        assert monitor.observe(inactive, GenericProfile()).diesel.since_regeneration_s == 60.0  # type: ignore[union-attr]

    def test_counts_nothing_before_a_regeneration_was_seen_to_end(self) -> None:
        monitor, clock = self._monitor()
        inactive = VehicleState(dpf_regeneration=DpfRegeneration(DpfRegenState.INACTIVE))

        clock.now = 500.0

        assert monitor.observe(inactive, GenericProfile()).diesel.since_regeneration_s is None  # type: ignore[union-attr]

    def test_a_new_regeneration_stops_the_count(self) -> None:
        monitor, clock = self._monitor()
        active = VehicleState(dpf_regeneration=DpfRegeneration(DpfRegenState.ACTIVE))
        inactive = VehicleState(dpf_regeneration=DpfRegeneration(DpfRegenState.INACTIVE))
        monitor.observe(active, GenericProfile())
        clock.now = 100.0
        monitor.observe(inactive, GenericProfile())
        clock.now = 200.0

        assert monitor.observe(active, GenericProfile()).diesel.since_regeneration_s is None  # type: ignore[union-attr]

    def test_an_estimated_regeneration_is_watched_too(self) -> None:
        monitor, clock = self._monitor()
        hot = VehicleState(dpf_temperatures=DpfTemperatures(inlet=610.0), engine_load=30.0)
        cool = VehicleState(dpf_temperatures=DpfTemperatures(inlet=300.0), engine_load=30.0)
        monitor.observe(hot, GenericProfile())
        clock.now = 50.0

        assert monitor.observe(cool, GenericProfile()).diesel.since_regeneration_s == 0.0  # type: ignore[union-attr]

    def test_reset_forgets_the_watch(self) -> None:
        monitor, clock = self._monitor()
        active = VehicleState(dpf_regeneration=DpfRegeneration(DpfRegenState.ACTIVE))
        inactive = VehicleState(dpf_regeneration=DpfRegeneration(DpfRegenState.INACTIVE))
        monitor.observe(active, GenericProfile())
        clock.now = 100.0
        monitor.observe(inactive, GenericProfile())

        monitor.reset()

        assert monitor.observe(inactive, GenericProfile()).diesel.since_regeneration_s is None  # type: ignore[union-attr]

    def test_the_default_clock_is_the_monotonic_one(self) -> None:
        monitor = DieselMonitor()

        assert monitor.observe(VehicleState(), GenericProfile()).diesel is not None
