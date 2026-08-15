# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Catalogue panel: every known command and whether the vehicle answers it."""

from __future__ import annotations

from obd_tui.models.commands import CommandCatalog
from obd_tui.models.vehicle import VehicleState
from obd_tui.views.panel import Panel
from obd_tui.views.units import UnitSystem

NOT_DISCOVERED = "  Connect to discover the commands this vehicle supports"
NAME_WIDTH = 25
PID_WIDTH = 6


def render(state: VehicleState, catalog: CommandCatalog, units: UnitSystem) -> str:
    """Render the supported command catalogue."""
    panel = Panel(units)
    if not len(catalog):
        return NOT_DISCOVERED

    panel.line(f"  Supported: {catalog.supported_count} / {len(catalog)}")

    for label, commands in catalog.modes.items():
        supported = sum(1 for command in commands if command.supported)
        panel.section(f"{label}  ({supported} / {len(commands)})")
        for command in commands:
            mark = "[x]" if command.supported else "[ ]"
            panel.line(
                f"  {mark}  {command.pid:<{PID_WIDTH}}  "
                f"{command.name:<{NAME_WIDTH}} {command.description}".rstrip()
            )

    return panel.render()
