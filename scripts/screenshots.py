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


class ScriptedClock:
    """A clock the script moves, one simulated second per sweep."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _tidy(svg: str) -> str:
    """Return the SVG as the repository's whitespace hooks want it.

    Textual pads its output with trailing spaces; leaving them in means a
    regenerated asset is always reformatted by pre-commit and shows up as a
    diff even when the screen is unchanged.
    """
    return "\n".join(line.rstrip() for line in svg.splitlines()) + "\n"


async def capture() -> None:
    """Render each panel of the demo session and write it out as SVG."""
    clock = ScriptedClock()
    session = simulated_session(clock=clock)
    session.connect()
    # Sweep a simulated second at a time so the trends have a history to
    # draw, ending on the moment the panels are captured.
    for second in range(int(ELAPSED) + 1):
        clock.now = float(second)
        session.refresh()

    app = ObdApp(session)
    async with app.run_test(size=SIZE) as pilot:
        for key, filename, title in SHOTS:
            app.query_one("#panels", TabbedContent).active = key
            await pilot.pause()
            (OUTPUT / filename).write_text(_tidy(app.export_screenshot(title=title)))
            print(f"wrote {OUTPUT / filename}")


if __name__ == "__main__":
    OUTPUT.mkdir(parents=True, exist_ok=True)
    asyncio.run(capture())
