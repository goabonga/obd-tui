# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""EGR panel: commanded rate and how far the valve is from it."""

from __future__ import annotations

from obd_tui.models.commands import CommandCatalog
from obd_tui.models.vehicle import VehicleState
from obd_tui.views.panel import NO_DATA, Panel
from obd_tui.views.units import UnitSystem

PERCENT = 100.0


def render(state: VehicleState, catalog: CommandCatalog, units: UnitSystem) -> str:
    """Render the exhaust gas recirculation panel."""
    panel = Panel(units)

    panel.reading(state, "egr_commanded", "COMMANDED %", gauge_max=PERCENT)
    panel.reading(state, "egr_error", "ERROR %", note=_interpret(state.egr_error))

    return panel.render(NO_DATA)


def _interpret(error: float | None) -> str:
    """Explain the sign of the EGR error, which is easy to read backwards."""
    if error is None:
        return ""
    if error < 0:
        return f"({abs(error):.1f}% below commanded)"
    if error > 0:
        return f"({error:.1f}% above commanded)"
    return "(on target)"
