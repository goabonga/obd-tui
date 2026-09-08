# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Exhaust panel: the gas temperatures along bank 1."""

from __future__ import annotations

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


def render(state: VehicleState, catalog: CommandCatalog, units: UnitSystem) -> str:
    """Render the exhaust gas temperature panel."""
    panel = Panel(units)

    for field, label in SENSORS:
        panel.reading(state, field, label, gauge_max=MAX_EGT)

    return panel.render(NO_DATA)
