#!/usr/bin/env python3

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Regenerate the dashboard screenshots under docs/assets.

Run from the repository root:

    uv run python scripts/screenshots.py

The simulated vehicle is driven by a fixed clock, so the readings are the
same on every run; only the wall clock in the header differs.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import TabbedContent

from obd_tui.app import ObdApp
from obd_tui.services.simulation import simulated_session

# Seconds of simulated driving to show: far enough in that the engine has
# warmed up and the ramps sit mid-travel.
ELAPSED = 300.0

# Wide enough for a gauge to sit beside its reading, tall enough for the
# whole engine panel down to the O2 section.
SIZE = (100, 38)

OUTPUT = Path("docs/assets")

SHOTS: tuple[tuple[str, str, str], ...] = (
    ("engine", "dashboard-engine.svg", "obd-tui — engine"),
    ("faults", "dashboard-faults.svg", "obd-tui — faults"),
    ("catalog", "dashboard-catalog.svg", "obd-tui — supported PIDs"),
)


class FixedClock:
    """A clock that jumps to a fixed elapsed time after the first reading."""

    def __init__(self, elapsed: float) -> None:
        self._elapsed = elapsed
        self._read = False

    def __call__(self) -> float:
        if self._read:
            return self._elapsed
        self._read = True
        return 0.0


async def capture() -> None:
    """Render each panel of the demo session and write it out as SVG."""
    session = simulated_session(clock=FixedClock(ELAPSED))
    session.connect()
    session.refresh()

    app = ObdApp(session)
    async with app.run_test(size=SIZE) as pilot:
        for key, filename, title in SHOTS:
            app.query_one("#panels", TabbedContent).active = key
            await pilot.pause()
            (OUTPUT / filename).write_text(app.export_screenshot(title=title))
            print(f"wrote {OUTPUT / filename}")


if __name__ == "__main__":
    OUTPUT.mkdir(parents=True, exist_ok=True)
    asyncio.run(capture())
