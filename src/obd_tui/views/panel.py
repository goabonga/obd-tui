# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Build the text of one dashboard panel."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from obd_tui.views.format import number
from obd_tui.views.gauges import bar

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
    """

    def __init__(self) -> None:
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
        label: str,
        value: Any | None,
        formatter: Formatter = number,
        gauge_max: float | None = None,
        note: str = "",
    ) -> None:
        """Append one reading, or nothing at all when it is missing.

        Args:
            label: Left-hand label.
            value: Reading to show. ``None`` drops the whole row.
            formatter: Turns ``value`` into its displayed text.
            gauge_max: Reading that fills the gauge drawn after the value.
                ``None`` draws no gauge.
            note: Text appended after the value, e.g. an interpretation.
        """
        if value is None:
            return
        row = f"  {label:<{LABEL_WIDTH}} {formatter(value):>{VALUE_WIDTH}}"
        if gauge_max is not None:
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


def _as_float(value: Any) -> float | None:
    """Return ``value`` as a float when a gauge can be drawn from it."""
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None
