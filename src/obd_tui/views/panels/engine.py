# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Engine panel: load, temperatures, fuel and oxygen sensors."""

from __future__ import annotations

from obd_tui.models.commands import CommandCatalog
from obd_tui.models.vehicle import VehicleState
from obd_tui.views.format import duration, integer, precise, text
from obd_tui.views.panel import NO_DATA, Panel
from obd_tui.views.units import UnitSystem

MAX_RPM = 7000.0
MAX_COOLANT = 130.0
MAX_OIL = 150.0
MAX_INTAKE = 80.0
PERCENT = 100.0


def render(state: VehicleState, catalog: CommandCatalog, units: UnitSystem) -> str:
    """Render the engine panel."""
    panel = Panel(units)

    panel.reading(state, "rpm", "RPM", integer, gauge_max=MAX_RPM)
    panel.reading(state, "engine_load", "LOAD %", gauge_max=PERCENT)
    panel.reading(state, "absolute_load", "ABS LOAD %", gauge_max=PERCENT)
    panel.reading(state, "timing_advance", "TIMING °")
    panel.reading(state, "run_time", "RUN TIME", duration)
    panel.reading(state, "speed", "SPEED", integer)
    panel.reading(state, "mass_air_flow", "MAF g/s")
    panel.reading(state, "module_voltage", "VOLTAGE V")

    panel.section("TEMPERATURES")
    panel.reading(state, "coolant_temp", "COOLANT", gauge_max=MAX_COOLANT)
    panel.reading(state, "oil_temp", "OIL", gauge_max=MAX_OIL)
    panel.reading(state, "intake_temp", "INTAKE", gauge_max=MAX_INTAKE)
    panel.reading(state, "ambient_temp", "AMBIENT")

    panel.section("FUEL")
    panel.reading(state, "fuel_rail_pressure", "RAIL")
    panel.reading(state, "fuel_rate", "RATE")
    panel.reading(state, "fuel_level", "LEVEL %", gauge_max=PERCENT)
    panel.reading(state, "fuel_inject_timing", "INJECT °")
    panel.reading(state, "equivalence_ratio", "EQUIV RATIO", precise)
    panel.reading(state, "short_fuel_trim", "SHORT TRIM %")
    panel.reading(state, "long_fuel_trim", "LONG TRIM %")

    panel.section("O2 SENSORS")
    panel.reading(state, "o2_sensors", "SENSORS", text)
    panel.reading(state, "o2_s1_lambda", "S1 LAMBDA", precise)
    panel.reading(state, "o2_s2_lambda", "S2 LAMBDA", precise)

    return panel.render(NO_DATA)
