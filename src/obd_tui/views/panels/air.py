# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Air path panel: manifold pressure, boost, throttle and pedal."""

from __future__ import annotations

from obd_tui.models.commands import CommandCatalog
from obd_tui.models.vehicle import VehicleState
from obd_tui.views.panel import NO_DATA, Panel
from obd_tui.views.units import UnitSystem

MAX_INTAKE_PRESSURE = 300.0
MAX_BOOST = 200.0
PERCENT = 100.0


def render(state: VehicleState, catalog: CommandCatalog, units: UnitSystem) -> str:
    """Render the air path panel."""
    panel = Panel(units)

    panel.reading(state, "intake_pressure", "INTAKE", gauge_max=MAX_INTAKE_PRESSURE)
    panel.reading(state, "barometric_pressure", "BARO")
    # A manifold below ambient is vacuum, not boost: gauge only the positive
    # side so a naturally aspirated engine does not read as a full bar.
    boost = state.net_boost
    panel.reading(
        state,
        "net_boost",
        "NET BOOST",
        gauge_max=MAX_BOOST if boost is not None and boost > 0 else None,
        note="" if boost is None or boost > 0 else "(vacuum)",
    )

    panel.section("THROTTLE")
    panel.reading(state, "throttle", "POSITION %", gauge_max=PERCENT)
    panel.reading(state, "throttle_b", "POSITION B %", gauge_max=PERCENT)
    panel.reading(state, "throttle_actuator", "ACTUATOR %", gauge_max=PERCENT)

    panel.section("ACCELERATOR")
    panel.reading(state, "accel_pedal_d", "PEDAL D %", gauge_max=PERCENT)
    panel.reading(state, "accel_pedal_e", "PEDAL E %", gauge_max=PERCENT)
    panel.reading(state, "relative_accel", "RELATIVE %", gauge_max=PERCENT)

    return panel.render(NO_DATA)
