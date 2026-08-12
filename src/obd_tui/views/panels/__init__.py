# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""The dashboard's panels, and the order they appear in."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from obd_tui.models.commands import CommandCatalog
from obd_tui.models.vehicle import VehicleState
from obd_tui.views.panels import air, catalog, diagnostics, egr, engine, faults

Renderer = Callable[[VehicleState, CommandCatalog], str]


@dataclass(frozen=True, slots=True)
class PanelSpec:
    """One tab of the dashboard.

    Attributes:
        key: Identifier of the tab and of its content widget.
        title: Label shown on the tab.
        shortcut: Key that jumps to the tab.
        render: Builds the tab's text from the latest readings.
    """

    key: str
    title: str
    shortcut: str
    render: Renderer


PANELS: tuple[PanelSpec, ...] = (
    PanelSpec("engine", "Engine", "1", engine.render),
    PanelSpec("air", "Air", "2", air.render),
    PanelSpec("egr", "EGR", "3", egr.render),
    PanelSpec("diagnostics", "Diag", "4", diagnostics.render),
    PanelSpec("faults", "Faults", "5", faults.render),
    PanelSpec("catalog", "PIDs", "p", catalog.render),
)

PANELS_BY_KEY: dict[str, PanelSpec] = {panel.key: panel for panel in PANELS}

__all__ = ["PANELS", "PANELS_BY_KEY", "PanelSpec", "Renderer"]
