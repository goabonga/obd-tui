# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""DPF panel: the particulate filter, and the context it is read in.

The panel consumes capabilities the vehicle answered and nothing else:
which command answered them, standard or a manufacturer's, is settled
long before a reading gets here.
"""

from __future__ import annotations

from obd_tui.models.commands import CommandCatalog
from obd_tui.models.dpf import DpfRegeneration, DpfRegenState, TemperatureSource
from obd_tui.models.vehicle import VehicleState
from obd_tui.views.format import integer, text
from obd_tui.views.panel import NO_DATA, Panel
from obd_tui.views.units import Quantity, UnitSystem

# Marks a filter temperature read off an exhaust sensor, not the filter.
FROM_EXHAUST = "(exhaust sensor)"

PERCENT = 100.0


def render(state: VehicleState, catalog: CommandCatalog, units: UnitSystem) -> str:
    """Render the particulate filter panel.

    A restriction reading means little on its own - it rises with the
    flow through the filter - so the engine speed and the air flow it was
    read at come after it, and no verdict does.
    """
    panel = Panel(units)

    regeneration = state.dpf_regeneration
    if regeneration is not None:
        panel.section("REGENERATION")
        panel.measure(_regeneration_word(regeneration), "REGEN", formatter=text)
        panel.measure("estimated" if regeneration.estimated else "ECU", "SOURCE", formatter=text)
        panel.measure(regeneration.trigger_percent, "TRIGGER %", gauge_max=PERCENT)

    panel.section("PARTICULATE FILTER")
    pressure = state.dpf_pressure
    if pressure is not None:
        panel.measure(pressure.differential, "DIFF PRESSURE", Quantity.PRESSURE)
        panel.measure(pressure.inlet, "INLET", Quantity.PRESSURE)
        panel.measure(pressure.outlet, "OUTLET", Quantity.PRESSURE)

    load = state.dpf_load
    if load is not None:
        panel.measure(load.percent, "SOOT LOAD %", gauge_max=PERCENT)
        panel.measure(load.soot_mass_g, "SOOT MASS g")

    temperatures = state.dpf_temperatures
    if temperatures is not None:
        # The reader must know when a row is an exhaust sensor the
        # manufacturer placed at the filter rather than the filter's own.
        note = FROM_EXHAUST if temperatures.source is TemperatureSource.EXHAUST else ""
        panel.measure(temperatures.inlet, "DPF INLET", Quantity.TEMPERATURE, note=note)
        panel.measure(temperatures.outlet, "DPF OUTLET", Quantity.TEMPERATURE, note=note)
        panel.measure(temperatures.internal, "DPF INTERNAL", Quantity.TEMPERATURE, note=note)

    if not panel:
        # Context without a filter to put it in is the engine panel's job.
        return NO_DATA

    panel.section("CONTEXT")
    panel.reading(state, "rpm", "RPM", integer)
    panel.reading(state, "mass_air_flow", "MAF g/s")

    return panel.render(NO_DATA)


# How an estimate reads: a guess says so in its wording, not only in its
# source line, so a glance never takes it for the ECU's word.
ESTIMATED_WORDS: dict[DpfRegenState, str] = {
    DpfRegenState.ACTIVE: "probable",
    DpfRegenState.INACTIVE: "unlikely",
}


def _regeneration_word(regeneration: DpfRegeneration) -> str:
    """Return the state as shown: the ECU's in capitals, a guess in words."""
    if regeneration.estimated:
        return ESTIMATED_WORDS.get(regeneration.state, regeneration.state.value)
    return regeneration.state.value.upper()
