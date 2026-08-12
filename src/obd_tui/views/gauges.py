# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Text gauges drawn with block characters."""

from __future__ import annotations

FILLED = "█"
EMPTY = "░"
DEFAULT_WIDTH = 28


def bar(value: float | None, maximum: float, width: int = DEFAULT_WIDTH) -> str:
    """Draw a horizontal gauge of ``width`` characters.

    Args:
        value: Reading to draw. ``None`` draws an empty gauge.
        maximum: Reading that fills the gauge. A non-positive maximum draws
            an empty gauge rather than dividing by zero.
        width: Total width in characters.

    Returns:
        A ``width``-character string; readings outside ``0..maximum`` clamp
        to an empty or a full gauge.
    """
    if value is None or maximum <= 0:
        return EMPTY * width
    ratio = min(1.0, max(0.0, value / maximum))
    filled = int(ratio * width)
    return FILLED * filled + EMPTY * (width - filled)
