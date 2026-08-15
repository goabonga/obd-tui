# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Faults panel: the trouble codes the ECU is holding."""

from __future__ import annotations

from collections.abc import Sequence

from obd_tui.models.commands import CommandCatalog
from obd_tui.models.vehicle import TroubleCode, VehicleState
from obd_tui.views.panel import Panel
from obd_tui.views.units import UnitSystem

NO_FAULTS = "  No trouble code stored"


def render(state: VehicleState, catalog: CommandCatalog, units: UnitSystem) -> str:
    """Render the trouble code panel."""
    panel = Panel(units)

    if state.stored_codes:
        panel.section(f"STORED ({len(state.stored_codes)})")
        _list_codes(panel, state.stored_codes)

    if state.pending_codes:
        panel.section(f"PENDING ({len(state.pending_codes)})")
        _list_codes(panel, state.pending_codes)

    return panel.render(NO_FAULTS)


def _list_codes(panel: Panel, codes: Sequence[TroubleCode]) -> None:
    """Print one code per block, description below it when there is one."""
    for code in codes:
        panel.line(f"  {code.code}")
        if code.description:
            panel.line(f"      {code.description}")
