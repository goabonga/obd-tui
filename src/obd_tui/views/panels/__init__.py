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
class TrendSpec:
    """One reading charted above a panel.

    Attributes:
        field: Name of the :class:`VehicleState` field, which is also the
            key of its series in the reading history.
        label: Label shown beside the chart.
    """

    field: str
    label: str


@dataclass(frozen=True, slots=True)
class PanelSpec:
    """One tab of the dashboard.

    Attributes:
        key: Identifier of the tab and of its content widget.
        title: Label shown on the tab.
        shortcut: Key that jumps to the tab.
        render: Builds the tab's text from the latest readings.
        trends: Readings charted above the text, if any.
    """

    key: str
    title: str
    shortcut: str
    render: Renderer
    trends: tuple[TrendSpec, ...] = ()


PANELS: tuple[PanelSpec, ...] = (
    PanelSpec(
        "engine",
        "Engine",
        "1",
        engine.render,
        trends=(
            TrendSpec("rpm", "RPM"),
            TrendSpec("coolant_temp", "COOLANT °C"),
            TrendSpec("mass_air_flow", "MAF g/s"),
        ),
    ),
    PanelSpec("air", "Air", "2", air.render),
    PanelSpec("egr", "EGR", "3", egr.render),
    PanelSpec("diagnostics", "Diag", "4", diagnostics.render),
    PanelSpec("faults", "Faults", "5", faults.render),
    PanelSpec("catalog", "PIDs", "p", catalog.render),
)

PANELS_BY_KEY: dict[str, PanelSpec] = {panel.key: panel for panel in PANELS}

__all__ = ["PANELS", "PANELS_BY_KEY", "PanelSpec", "Renderer", "TrendSpec"]
