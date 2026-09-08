# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Exhaust panel: the gas temperatures along every bank the vehicle has."""

from __future__ import annotations

from statistics import median

from obd_tui.models.commands import CommandCatalog
from obd_tui.models.vehicle import VehicleState
from obd_tui.views.panel import NO_DATA, Panel
from obd_tui.views.units import Quantity, UnitSystem

# A particulate filter regenerates around 600 °C; the gauge leaves room
# above it so a regeneration reads as hot rather than pegged.
MAX_EGT = 900.0

# How far a sensor may sit from the median of the others before it is
# pointed out, in °C. Wide on purpose: along a diesel exhaust the sensors
# read a couple of hundred degrees apart under load, and a sensor whose
# circuit has failed reads either end of the scale - a thousand degrees
# from the others on a cold engine. The note is a hint for the eye, not a
# verdict.
SUSPECT_SPREAD = 300.0
SUSPECT = "⚠ far from the other sensors"

# A sensor's place: bank number, sensor number.
Slot = tuple[int, int]


def render(state: VehicleState, catalog: CommandCatalog, units: UnitSystem) -> str:
    """Render the exhaust gas temperature panel.

    One row per sensor fitted, bank by bank and upstream first, named the
    way a trouble code names them: ``B1S2`` is bank 1 sensor 2. A bank
    the vehicle does not answer, or a sensor it reports as not fitted,
    never appears.
    """
    panel = Panel(units)
    readings: dict[Slot, float] = {
        (bank.bank, number): temperature
        for bank in sorted(state.egt_banks.values(), key=lambda bank: bank.bank)
        for number, temperature in bank.fitted
    }
    suspects = _suspects(readings)

    for (bank, number), temperature in readings.items():
        note = SUSPECT if (bank, number) in suspects else ""
        panel.measure(
            temperature, f"B{bank}S{number}", Quantity.TEMPERATURE, gauge_max=MAX_EGT, note=note
        )

    return panel.render(NO_DATA)


def _suspects(readings: dict[Slot, float]) -> frozenset[Slot]:
    """Return the sensors sitting far from the median of all the others.

    One sensor has nothing to disagree with. Two disagree symmetrically,
    and both are pointed out: which one is wrong is for the reader, who
    can see the ambient temperature on the engine panel, to say.
    """
    if len(readings) < 2:
        return frozenset()
    centre = median(readings.values())
    return frozenset(
        slot for slot, temperature in readings.items() if abs(temperature - centre) > SUSPECT_SPREAD
    )
