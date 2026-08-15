# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Diagnostics panel: MIL, compliance, counters and calibration."""

from __future__ import annotations

from obd_tui.models.commands import CommandCatalog
from obd_tui.models.vehicle import VehicleState
from obd_tui.views.format import duration, integer, onoff, text
from obd_tui.views.panel import NO_DATA, Panel
from obd_tui.views.units import UnitSystem


def render(state: VehicleState, catalog: CommandCatalog, units: UnitSystem) -> str:
    """Render the diagnostics panel."""
    panel = Panel(units)

    panel.reading(state, "mil_on", "MIL", onoff)
    panel.reading(state, "code_count", "CODE COUNT", integer)
    panel.reading(state, "ignition_type", "IGNITION", text)
    panel.reading(state, "obd_compliance", "OBD STANDARD", text)
    panel.reading(state, "fuel_type", "FUEL TYPE", text)
    panel.reading(state, "fuel_status", "FUEL STATUS", text)

    panel.section("COUNTERS")
    panel.reading(state, "distance_with_mil", "DIST MIL", integer)
    panel.reading(state, "run_time_with_mil", "TIME MIL", duration)
    panel.reading(state, "warmups_since_clear", "WARMUPS", integer)
    panel.reading(state, "distance_since_clear", "DIST CLEAR", integer)
    panel.reading(state, "time_since_clear", "TIME CLEAR min")

    panel.section("CALIBRATION")
    panel.reading(state, "calibration_id", "CAL ID", text)
    panel.reading(state, "cvn", "CVN", text)

    return panel.render(NO_DATA)
