# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Write a report the way a person reads it: Markdown, panels included.

The data of the report is the services' business; this turns it into a
page, with every panel rendered as it stood on screen, so the file says
what the dashboard said without a terminal to say it in.
"""

from __future__ import annotations

from typing import Any

from obd_tui.models.commands import CommandCatalog
from obd_tui.models.vehicle import VehicleState
from obd_tui.views.panels import PANELS
from obd_tui.views.units import UnitSystem


def render_report(
    data: dict[str, Any], state: VehicleState, catalog: CommandCatalog, units: UnitSystem
) -> str:
    """Return the report as Markdown.

    Args:
        data: The report's data, as the reporting service built it.
        state: The readings the panels are drawn from.
        catalog: The commands the vehicle was found to support.
        units: The system the panels show their readings in.
    """
    vehicle = data["vehicle"]
    lines = [
        "# obd-tui report",
        "",
        f"Generated {data['generated_at']} by obd-tui {data['version']}.",
        "",
        "## Vehicle",
        "",
        f"- State: {vehicle['state']}",
        f"- Adapter: {_or_dash(vehicle['port'])} ({_or_dash(vehicle['usb_id'])})"
        + (f", {vehicle['adapter']}" if vehicle["adapter"] else ""),
        f"- VIN: {_or_dash(vehicle['vin'])}",
        f"- Manufacturer profile: {vehicle['manufacturer']}",
        f"- Engine: {_or_dash(vehicle['engine'])}",
        "",
        "## Trouble codes",
        "",
    ]
    lines.extend(_codes("Stored", data["faults"]["stored"]))
    lines.extend(_codes("Pending", data["faults"]["pending"]))
    lines.append("")
    lines.append("## Panels")
    for panel in PANELS:
        lines.extend(["", f"### {panel.title}", "", "```text"])
        lines.append(panel.render(state, catalog, units))
        lines.append("```")
    supported = data["supported"]
    lines.extend(["", f"## Supported commands ({len(supported)} / {len(catalog)})", ""])
    lines.extend(f"- {name}" for name in supported)
    return "\n".join(lines) + "\n"


def _codes(title: str, codes: list[dict[str, str]]) -> list[str]:
    """Return one heading line and one line per code, or none."""
    if not codes:
        return [f"- {title}: none"]
    lines = [f"- {title}:"]
    for code in codes:
        description = f" - {code['description']}" if code["description"] else ""
        lines.append(f"    - `{code['code']}`{description}")
    return lines


def _or_dash(value: str | None) -> str:
    """Return ``value``, or a dash for what the vehicle did not give."""
    return value if value else "-"
