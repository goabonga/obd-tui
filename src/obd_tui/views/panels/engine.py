# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Engine panel: load, temperatures, fuel and oxygen sensors."""

from __future__ import annotations

from obd_tui.models.commands import CommandCatalog
from obd_tui.models.vehicle import VehicleState
from obd_tui.views.format import duration, integer, precise, text
from obd_tui.views.panel import NO_DATA, Panel

MAX_RPM = 7000.0
MAX_COOLANT = 130.0
MAX_OIL = 150.0
MAX_INTAKE = 80.0
PERCENT = 100.0


def render(state: VehicleState, catalog: CommandCatalog) -> str:
    """Render the engine panel."""
    panel = Panel()

    panel.reading("RPM", state.rpm, integer, gauge_max=MAX_RPM)
    panel.reading("LOAD %", state.engine_load, gauge_max=PERCENT)
    panel.reading("ABS LOAD %", state.absolute_load, gauge_max=PERCENT)
    panel.reading("TIMING °", state.timing_advance)
    panel.reading("RUN TIME", state.run_time, duration)
    panel.reading("SPEED km/h", state.speed, integer)
    panel.reading("MAF g/s", state.mass_air_flow)
    panel.reading("VOLTAGE V", state.module_voltage)

    panel.section("TEMPERATURES")
    panel.reading("COOLANT °C", state.coolant_temp, gauge_max=MAX_COOLANT)
    panel.reading("OIL °C", state.oil_temp, gauge_max=MAX_OIL)
    panel.reading("INTAKE °C", state.intake_temp, gauge_max=MAX_INTAKE)
    panel.reading("AMBIENT °C", state.ambient_temp)

    panel.section("FUEL")
    panel.reading("RAIL kPa", state.fuel_rail_pressure)
    panel.reading("RATE L/h", state.fuel_rate)
    panel.reading("LEVEL %", state.fuel_level, gauge_max=PERCENT)
    panel.reading("INJECT °", state.fuel_inject_timing)
    panel.reading("EQUIV RATIO", state.equivalence_ratio, precise)
    panel.reading("SHORT TRIM %", state.short_fuel_trim)
    panel.reading("LONG TRIM %", state.long_fuel_trim)

    panel.section("O2 SENSORS")
    panel.reading("SENSORS", state.o2_sensors, text)
    panel.reading("S1 LAMBDA", state.o2_s1_lambda, precise)
    panel.reading("S2 LAMBDA", state.o2_s2_lambda, precise)

    return panel.render(NO_DATA)
