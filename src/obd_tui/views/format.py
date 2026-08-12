# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Turn a single reading into the string a panel shows."""

from __future__ import annotations

from typing import Any

# Shown instead of a value the vehicle did not report.
MISSING = "--"


def number(value: float | None, decimals: int = 1) -> str:
    """Format a reading with ``decimals`` digits after the point."""
    return MISSING if value is None else f"{value:.{decimals}f}"


def precise(value: float | None) -> str:
    """Format a reading that needs two decimals, such as a lambda ratio."""
    return number(value, decimals=2)


def integer(value: float | None) -> str:
    """Format a reading that has no meaningful fractional part."""
    return MISSING if value is None else f"{int(value)}"


def duration(seconds: float | None) -> str:
    """Format a number of seconds as ``HH:MM:SS``."""
    if seconds is None:
        return MISSING
    total = int(seconds)
    sign = "-" if total < 0 else ""
    total = abs(total)
    return f"{sign}{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def text(value: Any | None) -> str:
    """Format a value the ECU reports as an object or an enumeration."""
    return MISSING if value is None else str(value)


def onoff(value: bool | None) -> str:
    """Format a lamp or flag reading."""
    return MISSING if value is None else ("ON" if value else "OFF")
