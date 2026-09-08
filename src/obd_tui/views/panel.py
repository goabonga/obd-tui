# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Build the text of one dashboard panel."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from obd_tui.models.vehicle import VehicleState
from obd_tui.views.format import number
from obd_tui.views.gauges import bar
from obd_tui.views.units import Quantity, UnitSystem, quantity_of

# Shown by a panel whose every reading was missing.
NO_DATA = "  No data reported by the vehicle"

LABEL_WIDTH = 18
VALUE_WIDTH = 8
RULE_WIDTH = 60
RULE = "─"

Formatter = Callable[[Any], str]


class Panel:
    """Lines of a panel, assembled reading by reading.

    A reading the vehicle did not report is dropped rather than shown as a
    placeholder, and a section whose readings were all dropped never prints
    its heading — so a panel shows exactly what the ECU answered.

    Args:
        units: System the readings are displayed in. Values are converted
            on the way out only; what the ECU sent is what is stored.
    """

    def __init__(self, units: UnitSystem = UnitSystem.METRIC) -> None:
        self._units = units
        self._lines: list[str] = []
        self._pending_section: str | None = None

    def __bool__(self) -> bool:
        """Return whether anything has been added to the panel."""
        return bool(self._lines)

    def section(self, title: str) -> None:
        """Open a section, printed only once it gets a line."""
        self._pending_section = title

    def line(self, content: str = "") -> None:
        """Append a raw line, flushing the pending section heading first."""
        self._flush_section()
        self._lines.append(content)

    def reading(
        self,
        state: VehicleState,
        field: str,
        label: str,
        formatter: Formatter = number,
        gauge_max: float | None = None,
        note: str = "",
    ) -> None:
        """Append one of the state's readings, or nothing when it is missing.

        Args:
            state: Snapshot to read from.
            field: Name of the reading, which also decides its unit.
            label: Left-hand label, without the unit — that is appended from
                the unit system in use.
            formatter: Turns the value into its displayed text.
            gauge_max: Reading that fills the gauge drawn after the value,
                expressed in the units the vehicle reports. ``None`` draws
                no gauge.
            note: Text appended after the value, e.g. an interpretation.
        """
        self.measure(
            getattr(state, field, None),
            label,
            quantity_of(field),
            formatter=formatter,
            gauge_max=gauge_max,
            note=note,
        )

    def measure(
        self,
        value: Any,
        label: str,
        quantity: Quantity = Quantity.NONE,
        formatter: Formatter = number,
        gauge_max: float | None = None,
        note: str = "",
    ) -> None:
        """Append one value, or nothing when it is ``None``.

        The reading may come from anywhere - a state field, or one entry
        of a family the state holds indexed rather than named. What it
        measures is said outright, since there is no field to look it up
        by.

        Args:
            value: The reading, in the units the vehicle reports.
            label: Left-hand label, without the unit — that is appended from
                the unit system in use.
            quantity: What the value measures, which decides its unit.
            formatter: Turns the value into its displayed text.
            gauge_max: Reading that fills the gauge drawn after the value,
                expressed in the units the vehicle reports. ``None`` draws
                no gauge.
            note: Text appended after the value, e.g. an interpretation.
        """
        if value is None:
            return

        suffix = self._units.suffix(quantity)
        shown = self._units.convert(quantity, value) if _is_number(value) else value
        heading = f"{label} {suffix}".rstrip()

        row = f"  {heading:<{LABEL_WIDTH}} {formatter(shown):>{VALUE_WIDTH}}"
        if gauge_max is not None:
            # Gauged from what the vehicle reported, so the bar reads the
            # same whichever system the numbers are shown in.
            row += f"  {bar(_as_float(value), gauge_max)}"
        if note:
            row += f"  {note}"
        self.line(row)

    def render(self, empty: str = "") -> str:
        """Return the panel as a single string.

        Args:
            empty: Text to return when no reading made it into the panel.
        """
        return "\n".join(self._lines) if self._lines else empty

    def _flush_section(self) -> None:
        """Print the pending heading, preceded by a blank separator line."""
        if self._pending_section is None:
            return
        title, self._pending_section = self._pending_section, None
        if self._lines:
            self._lines.append("")
        self._lines.append(title)
        self._lines.append(RULE * RULE_WIDTH)


def _is_number(value: Any) -> bool:
    """Return whether a reading is a number, rather than an ECU object."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _as_float(value: Any) -> float | None:
    """Return ``value`` as a float when a gauge can be drawn from it."""
    return value if _is_number(value) else None
