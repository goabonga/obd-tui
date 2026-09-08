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

from obd_tui.models.dpf import DpfRole, DpfTemperatures, TemperatureSource
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


def complete(state: VehicleState, profile: ManufacturerProfile) -> VehicleState:
    """Return ``state`` with what the profile can add to the filter's readings.

    A filter temperature the ECU reported is kept as it is. When it
    reported none, the exhaust sensors the profile places at the filter
    stand in, refreshed on every sweep since the sensors move.
    """
    current = state.dpf_temperatures
    if current is not None and current.source is TemperatureSource.ECU:
        return state
    return replace(state, dpf_temperatures=map_dpf_temperatures(state.egt_banks, profile))
