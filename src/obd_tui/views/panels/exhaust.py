# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Exhaust panel: the gas temperatures along bank 1."""

from __future__ import annotations

from statistics import median

from obd_tui.models.commands import CommandCatalog
from obd_tui.models.vehicle import VehicleState
from obd_tui.views.panel import NO_DATA, Panel
from obd_tui.views.units import UnitSystem

# A particulate filter regenerates around 600 °C; the gauge leaves room
# above it so a regeneration reads as hot rather than pegged.
MAX_EGT = 900.0

# The sensors of bank 1 in the order the ECU lists them, upstream first.
SENSORS: tuple[tuple[str, str], ...] = (
    ("egt_bank_1_sensor_1", "EGT B1 S1"),
    ("egt_bank_1_sensor_2", "EGT B1 S2"),
    ("egt_bank_1_sensor_3", "EGT B1 S3"),
    ("egt_bank_1_sensor_4", "EGT B1 S4"),
)

# How far a sensor may sit from the median of the bank before it is
# pointed out, in °C. Wide on purpose: along a diesel exhaust the sensors
# read a couple of hundred degrees apart under load, and a sensor whose
# circuit has failed reads either end of the scale — a thousand degrees
# from the others on a cold engine. The note is a hint for the eye, not a
# verdict.
SUSPECT_SPREAD = 300.0
SUSPECT = "⚠ far from the other sensors"


def render(state: VehicleState, catalog: CommandCatalog, units: UnitSystem) -> str:
    """Render the exhaust gas temperature panel."""
    panel = Panel(units)
    suspects = _suspects(
        {field: value for field, _ in SENSORS if (value := getattr(state, field)) is not None}
    )

    for field, label in SENSORS:
        note = SUSPECT if field in suspects else ""
        panel.reading(state, field, label, gauge_max=MAX_EGT, note=note)

    return panel.render(NO_DATA)


def _suspects(readings: dict[str, float]) -> frozenset[str]:
    """Return the sensors sitting far from the median of the bank.

    One sensor has nothing to disagree with. Two disagree symmetrically,
    and both are pointed out: which one is wrong is for the reader, who
    can see the ambient temperature on the engine panel, to say.
    """
    if len(readings) < 2:
        return frozenset()
    centre = median(readings.values())
    return frozenset(
        field for field, value in readings.items() if abs(value - centre) > SUSPECT_SPREAD
    )
