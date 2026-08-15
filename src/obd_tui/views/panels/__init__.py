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
        fields: VehicleState fields this panel shows. The poller reads them
            every sweep while the panel is open, so what is on screen stays
            live even when its tier would otherwise slow it down.
    """

    key: str
    title: str
    shortcut: str
    render: Renderer
    trends: tuple[TrendSpec, ...] = ()
    fields: tuple[str, ...] = ()


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
        fields=(
            "rpm",
            "engine_load",
            "absolute_load",
            "timing_advance",
            "run_time",
            "speed",
            "mass_air_flow",
            "module_voltage",
            "coolant_temp",
            "oil_temp",
            "intake_temp",
            "ambient_temp",
            "fuel_rail_pressure",
            "fuel_rate",
            "fuel_level",
            "fuel_inject_timing",
            "equivalence_ratio",
            "short_fuel_trim",
            "long_fuel_trim",
            "o2_sensors",
            "o2_s1_lambda",
            "o2_s2_lambda",
        ),
    ),
    PanelSpec(
        "air",
        "Air",
        "2",
        air.render,
        fields=(
            "intake_pressure",
            "barometric_pressure",
            "throttle",
            "throttle_b",
            "throttle_actuator",
            "accel_pedal_d",
            "accel_pedal_e",
            "relative_accel",
        ),
    ),
    PanelSpec("egr", "EGR", "3", egr.render, fields=("egr_commanded", "egr_error")),
    PanelSpec(
        "diagnostics",
        "Diag",
        "4",
        diagnostics.render,
        fields=(
            "status",
            "obd_compliance",
            "fuel_type",
            "fuel_status",
            "distance_with_mil",
            "run_time_with_mil",
            "warmups_since_clear",
            "distance_since_clear",
            "time_since_clear",
            "calibration_id",
            "cvn",
        ),
    ),
    PanelSpec("faults", "Faults", "5", faults.render, fields=("stored_codes", "pending_codes")),
    # The catalogue shows capabilities, not readings: nothing to prioritise.
    PanelSpec("catalog", "PIDs", "p", catalog.render),
)

PANELS_BY_KEY: dict[str, PanelSpec] = {panel.key: panel for panel in PANELS}

__all__ = ["PANELS", "PANELS_BY_KEY", "PanelSpec", "Renderer", "TrendSpec"]
