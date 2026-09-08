# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""DPF panel: the diesel aftertreatment in one view.

The panel consumes capabilities the vehicle answered and the view the
monitoring service built from them, and nothing else: which command
answered a capability, standard or a manufacturer's, is settled long
before a reading gets here. What is derived says so on its row, and no
row passes a verdict on the filter.
"""

from __future__ import annotations

from obd_tui.models.commands import CommandCatalog
from obd_tui.models.dpf import (
    DieselAftertreatmentState,
    DpfRegeneration,
    DpfRegenState,
    PressureAssessment,
    TemperatureSource,
)
from obd_tui.models.vehicle import VehicleState
from obd_tui.views.format import duration, integer, text
from obd_tui.views.panel import NO_DATA, Panel
from obd_tui.views.units import Quantity, UnitSystem

# Marks a filter temperature read off an exhaust sensor, not the filter.
FROM_EXHAUST = "(exhaust sensor)"

# Marks a row the dashboard worked out rather than read.
DERIVED = "(derived)"

# A pressure reading worth a second look says so beside its value.
PRESSURE_NOTES: dict[PressureAssessment, str] = {
    PressureAssessment.ELEVATED: "(elevated)",
    PressureAssessment.INCONSISTENT: "(inconsistent)",
}

# How an estimate reads: a guess says so in its wording, not only in its
# source line, so a glance never takes it for the ECU's word.
ESTIMATED_WORDS: dict[DpfRegenState, str] = {
    DpfRegenState.ACTIVE: "probable",
    DpfRegenState.INACTIVE: "unlikely",
}

PERCENT = 100.0
MAX_EGT = 900.0


def render(state: VehicleState, catalog: CommandCatalog, units: UnitSystem) -> str:
    """Render the diesel aftertreatment panel.

    Regeneration first, since it changes how every other row reads; then
    the filter, the exhaust temperatures along the way to it, and the
    engine readings the filter's numbers only mean something against.
    """
    panel = Panel(units)
    view = state.diesel if state.diesel is not None else DieselAftertreatmentState()

    _regeneration(panel, view)
    _filter(panel, state, view)
    if not panel:
        # Context without a filter to put it in is the engine panel's job.
        return NO_DATA

    _exhaust(panel, state)
    panel.section("CONTEXT")
    panel.reading(state, "rpm", "RPM", integer)
    panel.reading(state, "engine_load", "LOAD %", gauge_max=PERCENT)
    panel.reading(state, "mass_air_flow", "MAF g/s")
    panel.reading(state, "egr_commanded", "EGR %", gauge_max=PERCENT)

    return panel.render(NO_DATA)


def _regeneration(panel: Panel, view: DieselAftertreatmentState) -> None:
    """Add the regeneration rows, reported or guessed."""
    regeneration = view.regeneration
    if regeneration is None:
        return
    panel.section("REGENERATION")
    panel.measure(_regeneration_word(regeneration), "REGEN", formatter=text)
    panel.measure("estimated" if regeneration.estimated else "ECU", "SOURCE", formatter=text)
    panel.measure(regeneration.trigger_percent, "TRIGGER %", gauge_max=PERCENT)
    panel.measure(view.since_regeneration_s, "SINCE LAST", formatter=duration, note=DERIVED)


def _filter(panel: Panel, state: VehicleState, view: DieselAftertreatmentState) -> None:
    """Add the filter's own rows: load, pressures and temperatures."""
    panel.section("PARTICULATE FILTER")
    panel.measure(view.soot_load_percent, "SOOT LOAD %", gauge_max=PERCENT)
    panel.measure(view.soot_mass_g, "SOOT MASS g")

    pressure = state.dpf_pressure
    if pressure is not None:
        note = PRESSURE_NOTES.get(view.pressure_state, "")
        panel.measure(pressure.differential, "DIFF PRESSURE", Quantity.PRESSURE, note=note)
        panel.measure(pressure.inlet, "INLET", Quantity.PRESSURE)
        panel.measure(pressure.outlet, "OUTLET", Quantity.PRESSURE)
    panel.measure(view.pressure_per_flow, "ΔP / MAF", note=DERIVED)

    temperatures = view.temperatures
    if temperatures is not None:
        # The reader must know when a row is an exhaust sensor the
        # manufacturer placed at the filter rather than the filter's own.
        note = FROM_EXHAUST if temperatures.source is TemperatureSource.EXHAUST else ""
        panel.measure(temperatures.inlet, "DPF INLET", Quantity.TEMPERATURE, note=note)
        panel.measure(temperatures.outlet, "DPF OUTLET", Quantity.TEMPERATURE, note=note)
        panel.measure(temperatures.internal, "DPF INTERNAL", Quantity.TEMPERATURE, note=note)
    panel.measure(view.temperature_delta, "DPF ΔT", Quantity.TEMPERATURE_DELTA, note=DERIVED)


def _exhaust(panel: Panel, state: VehicleState) -> None:
    """Add one row per exhaust gas sensor, bank by bank, upstream first."""
    panel.section("EXHAUST")
    for bank in sorted(state.egt_banks.values(), key=lambda bank: bank.bank):
        for number, temperature in bank.fitted:
            panel.measure(
                temperature, f"EGT B{bank.bank}S{number}", Quantity.TEMPERATURE, gauge_max=MAX_EGT
            )


def _regeneration_word(regeneration: DpfRegeneration) -> str:
    """Return the state as shown: the ECU's in capitals, a guess in words."""
    if regeneration.estimated:
        return ESTIMATED_WORDS.get(regeneration.state, regeneration.state.value)
    return regeneration.state.value.upper()
