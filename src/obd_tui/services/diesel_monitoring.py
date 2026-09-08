# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Make sense of the diesel aftertreatment readings, once they are read.

Everything here works on a snapshot the poller already filled and on the
vehicle's manufacturer profile. It never sends a command, and it never
tests a make: what a profile knows about an engine is asked of the
profile, which is the one place allowed to know it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from obd_tui.models.dpf import (
    DpfRegeneration,
    DpfRegenState,
    DpfRole,
    DpfTemperatures,
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
