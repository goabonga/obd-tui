# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Make sense of the diesel aftertreatment readings, once they are read.

Everything here works on a snapshot the poller already filled and on the
vehicle's manufacturer profile. It never sends a command, and it never
tests a make: what a profile knows about an engine is asked of the
profile, which is the one place allowed to know it.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import replace

from obd_tui.models.dpf import (
    DieselAftertreatmentState,
    DpfRegeneration,
    DpfRegenState,
    DpfRole,
    DpfTemperatures,
    PressureAssessment,
    TemperatureSource,
)
from obd_tui.models.exhaust import ExhaustTemperatures
from obd_tui.models.vehicle import VehicleState
from obd_tui.obd.manufacturers.base import ManufacturerProfile


def map_dpf_temperatures(
    banks: Mapping[int, ExhaustTemperatures], profile: ManufacturerProfile
) -> DpfTemperatures | None:
    """Return the filter temperatures the profile can read off the exhaust.

    For a vehicle whose ECU does not report the filter's own temperatures,
    the manufacturer may know that a given exhaust sensor sits at the
    filter's inlet or outlet. Only the profile says so; a sensor it cannot
    place is left out, and a bank with no placed sensor yields nothing.
    The result is marked as taken from the exhaust, never as the ECU's.
    """
    placed: dict[DpfRole, float] = {}
    for bank in banks.values():
        for number, temperature in bank.fitted:
            role = profile.exhaust_sensor_role(bank.bank, number)
            if role is not None and role not in placed:
                placed[role] = temperature
    if not placed:
        return None
    return DpfTemperatures(
        inlet=placed.get(DpfRole.INLET),
        outlet=placed.get(DpfRole.OUTLET),
        internal=placed.get(DpfRole.INTERNAL),
        source=TemperatureSource.EXHAUST,
    )


# The exhaust of a diesel under way sits well below this; a regeneration
# burns the soot off at it or above. A sustained hard pull gets there too,
# which is what the load bound is for: post-injection heats the filter at
# moderate load, a hill at full load.
REGENERATION_TEMPERATURE = 550.0
REGENERATION_MAX_LOAD = 70.0


def estimate_regeneration(state: VehicleState) -> DpfRegeneration | None:
    """Guess whether the filter is regenerating from what the exhaust says.

    For a vehicle whose ECU does not report it. The guess is marked as
    one, and is nothing at all when there is no exhaust temperature to
    guess from: an unknown is better than a made-up "inactive".
    """
    temperatures = [temperature for _, temperature in _exhaust_temperatures(state)]
    if not temperatures:
        return None
    hot = max(temperatures) >= REGENERATION_TEMPERATURE
    moderate = state.engine_load is None or state.engine_load <= REGENERATION_MAX_LOAD
    active = hot and moderate
    return DpfRegeneration(
        DpfRegenState.ACTIVE if active else DpfRegenState.INACTIVE, estimated=True
    )


def _exhaust_temperatures(state: VehicleState) -> list[tuple[str, float]]:
    """Return every temperature known along the exhaust, filter included."""
    readings: list[tuple[str, float]] = []
    filter_temperatures = state.dpf_temperatures
    if filter_temperatures is not None:
        for name in ("inlet", "internal", "outlet"):
            temperature = getattr(filter_temperatures, name)
            if temperature is not None:
                readings.append((f"dpf {name}", temperature))
    for bank in state.egt_banks.values():
        for number, temperature in bank.fitted:
            readings.append((f"B{bank.bank}S{number}", temperature))
    return readings


def complete(state: VehicleState, profile: ManufacturerProfile) -> VehicleState:
    """Return ``state`` with what can be added to the filter's readings.

    A filter temperature the ECU reported is kept as it is; when it
    reported none, the exhaust sensors the profile places at the filter
    stand in. A regeneration state the ECU reported is kept as it is;
    when it reported none, the exhaust is read for a guess. Both stand-ins
    are marked as such and refreshed on every sweep, since the sensors
    move.
    """
    temperatures = state.dpf_temperatures
    if temperatures is None or temperatures.source is not TemperatureSource.ECU:
        state = replace(state, dpf_temperatures=map_dpf_temperatures(state.egt_banks, profile))
    regeneration = state.dpf_regeneration
    if regeneration is None or regeneration.estimated:
        state = replace(state, dpf_regeneration=estimate_regeneration(state))
    return state


# A clean filter puts a few kPa in the way; a restriction past this is
# worth a look whatever the flow. Wide on purpose - a verdict would take
# the engine's own figures - and said as "elevated", never "clogged".
ELEVATED_PRESSURE = 20.0

Clock = Callable[[], float]


def assess_pressure(state: VehicleState) -> PressureAssessment:
    """Describe the filter's restriction, without judging the filter.

    Inconsistent when the pressures contradict each other - more after
    the filter than before - elevated past a wide bound, unavailable
    when the vehicle did not report it, normal otherwise.
    """
    pressure = state.dpf_pressure
    if pressure is None or pressure.differential is None:
        return PressureAssessment.UNAVAILABLE
    if (
        pressure.inlet is not None
        and pressure.outlet is not None
        and pressure.inlet < pressure.outlet
    ):
        return PressureAssessment.INCONSISTENT
    if pressure.differential >= ELEVATED_PRESSURE:
        return PressureAssessment.ELEVATED
    return PressureAssessment.NORMAL


def pressure_per_flow(state: VehicleState) -> float | None:
    """Return the restriction per gram per second of air, or ``None``.

    Takes the flow out of the reading: a filter reads a few kPa at idle
    and many more at speed, and only the ratio compares one moment with
    another. Nothing at zero flow, where the ratio means nothing.
    """
    differential = state.dpf_differential_pressure_kpa
    flow = state.mass_air_flow
    if differential is None or flow is None or flow <= 0:
        return None
    return differential / flow


def temperature_delta(state: VehicleState) -> float | None:
    """Return inlet minus outlet at the filter, or ``None`` without both."""
    temperatures = state.dpf_temperatures
    if temperatures is None or temperatures.inlet is None or temperatures.outlet is None:
        return None
    return temperatures.inlet - temperatures.outlet


class DieselMonitor:
    """Keep the aftertreatment in one view across sweeps.

    Stateless readings are derived on the spot; the time since the last
    regeneration needs watching across sweeps, which is why this is an
    object. It never sends a command and never tests a make.

    Args:
        clock: Source of the time regenerations are dated by. Injected so
            tests, and the demo, can move it by hand.
    """

    def __init__(self, clock: Clock = time.monotonic) -> None:
        self._clock = clock
        self._regenerating = False
        self._last_end: float | None = None

    def observe(self, state: VehicleState, profile: ManufacturerProfile) -> VehicleState:
        """Return ``state`` completed and summed up.

        First what the profile and the exhaust add to the readings, then
        the one view built from them.
        """
        state = complete(state, profile)
        return replace(state, diesel=self._summarise(state))

    def reset(self) -> None:
        """Forget what was watched: the next link may be another vehicle."""
        self._regenerating = False
        self._last_end = None

    def _summarise(self, state: VehicleState) -> DieselAftertreatmentState:
        """Build the one view from a completed snapshot."""
        load = state.dpf_load
        return DieselAftertreatmentState(
            differential_pressure_kpa=state.dpf_differential_pressure_kpa,
            pressure_per_flow=pressure_per_flow(state),
            pressure_state=assess_pressure(state),
            soot_load_percent=load.percent if load is not None else None,
            soot_mass_g=load.soot_mass_g if load is not None else None,
            temperatures=state.dpf_temperatures,
            temperature_delta=temperature_delta(state),
            regeneration=state.dpf_regeneration,
            since_regeneration_s=self._since_regeneration(state.dpf_regeneration),
        )

    def _since_regeneration(self, regeneration: DpfRegeneration | None) -> float | None:
        """Return seconds since a regeneration last ended, watching for the end.

        Counted from what this dashboard saw: nothing until a regeneration
        has been seen to end, and nothing while one runs.
        """
        now = self._clock()
        active = regeneration is not None and regeneration.state is DpfRegenState.ACTIVE
        if active:
            self._regenerating = True
            return None
        if self._regenerating:
            self._regenerating = False
            self._last_end = now
        if self._last_end is None:
            return None
        return now - self._last_end
