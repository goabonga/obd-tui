# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Diagnostics panel: MIL, compliance, counters and calibration."""

from __future__ import annotations

from obd_tui.models.commands import CommandCatalog
from obd_tui.models.vehicle import VehicleState
from obd_tui.views.format import duration, integer, onoff, text
from obd_tui.views.panel import NO_DATA, Panel


def render(state: VehicleState, catalog: CommandCatalog) -> str:
    """Render the diagnostics panel."""
    panel = Panel()

    panel.reading("MIL", state.mil_on, onoff)
    panel.reading("CODE COUNT", state.code_count, integer)
    panel.reading("IGNITION", state.ignition_type, text)
    panel.reading("OBD STANDARD", state.obd_compliance, text)
    panel.reading("FUEL TYPE", state.fuel_type, text)
    panel.reading("FUEL STATUS", state.fuel_status, text)

    panel.section("COUNTERS")
    panel.reading("DIST MIL km", state.distance_with_mil, integer)
    panel.reading("TIME MIL", state.run_time_with_mil, duration)
    panel.reading("WARMUPS", state.warmups_since_clear, integer)
    panel.reading("DIST CLEAR km", state.distance_since_clear, integer)
    panel.reading("TIME CLEAR min", state.time_since_clear)

    panel.section("CALIBRATION")
    panel.reading("CAL ID", state.calibration_id, text)
    panel.reading("CVN", state.cvn, text)

    return panel.render(NO_DATA)
