# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""DPF panel: the particulate filter, and the context it is read in.

The panel consumes capabilities the vehicle answered and nothing else:
which command answered them, standard or a manufacturer's, is settled
long before a reading gets here.
"""

from __future__ import annotations

from obd_tui.models.commands import CommandCatalog
from obd_tui.models.vehicle import VehicleState
from obd_tui.views.format import integer
from obd_tui.views.panel import NO_DATA, Panel
from obd_tui.views.units import Quantity, UnitSystem


def render(state: VehicleState, catalog: CommandCatalog, units: UnitSystem) -> str:
    """Render the particulate filter panel.

    A restriction reading means little on its own - it rises with the
    flow through the filter - so the engine speed and the air flow it was
    read at come after it, and no verdict does.
    """
    panel = Panel(units)

    panel.section("PARTICULATE FILTER")
    pressure = state.dpf_pressure
    if pressure is not None:
        panel.measure(pressure.differential, "DIFF PRESSURE", Quantity.PRESSURE)
        panel.measure(pressure.inlet, "INLET", Quantity.PRESSURE)
        panel.measure(pressure.outlet, "OUTLET", Quantity.PRESSURE)

    if not panel:
        # Context without a filter to put it in is the engine panel's job.
        return NO_DATA

    panel.section("CONTEXT")
    panel.reading(state, "rpm", "RPM", integer)
    panel.reading(state, "mass_air_flow", "MAF g/s")

    return panel.render(NO_DATA)
