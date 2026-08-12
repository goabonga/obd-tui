# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Air path panel: manifold pressure, boost, throttle and pedal."""

from __future__ import annotations

from obd_tui.models.commands import CommandCatalog
from obd_tui.models.vehicle import VehicleState
from obd_tui.views.panel import NO_DATA, Panel

MAX_INTAKE_PRESSURE = 300.0
MAX_BOOST = 200.0
PERCENT = 100.0


def render(state: VehicleState, catalog: CommandCatalog) -> str:
    """Render the air path panel."""
    panel = Panel()

    panel.reading("INTAKE kPa", state.intake_pressure, gauge_max=MAX_INTAKE_PRESSURE)
    panel.reading("BARO kPa", state.barometric_pressure)
    # A manifold below ambient is vacuum, not boost: gauge only the positive
    # side so a naturally aspirated engine does not read as a full bar.
    boost = state.net_boost
    panel.reading(
        "NET BOOST kPa",
        boost,
        gauge_max=MAX_BOOST if boost is not None and boost > 0 else None,
        note="" if boost is None or boost > 0 else "(vacuum)",
    )

    panel.section("THROTTLE")
    panel.reading("POSITION %", state.throttle, gauge_max=PERCENT)
    panel.reading("POSITION B %", state.throttle_b, gauge_max=PERCENT)
    panel.reading("ACTUATOR %", state.throttle_actuator, gauge_max=PERCENT)

    panel.section("ACCELERATOR")
    panel.reading("PEDAL D %", state.accel_pedal_d, gauge_max=PERCENT)
    panel.reading("PEDAL E %", state.accel_pedal_e, gauge_max=PERCENT)
    panel.reading("RELATIVE %", state.relative_accel, gauge_max=PERCENT)

    return panel.render(NO_DATA)
