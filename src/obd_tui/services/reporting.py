# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Gather everything a session knows into one dated report.

The report is the whole picture at one moment: the vehicle as recognised,
every command it was found to support, the latest readings, the recent
history of the charted ones, and the trouble codes. Built here as plain
data; the text the reader sees is the views' job, and the file is written
last, next to whatever the user asked for.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from obd_tui import __version__
from obd_tui.models.vehicle import TroubleCode
from obd_tui.services.recording import as_row
from obd_tui.services.session import Session

# The file names start with this and end with the moment of the report.
REPORT_PREFIX = "obd-tui-report"


def report_stem(now: datetime) -> str:
    """Return the file name, without extension, of a report taken at ``now``."""
    return f"{REPORT_PREFIX}-{now:%Y%m%d-%H%M%S}"


@dataclass(frozen=True, slots=True)
class Report:
    """One report: when it was taken, and everything it holds.

    Attributes:
        generated_at: The moment of the report.
        data: The whole picture, JSON-serialisable.
    """

    generated_at: datetime
    data: dict[str, Any]

    @property
    def stem(self) -> str:
        """Return the file name, without extension, this report goes by."""
        return report_stem(self.generated_at)


def build_report(session: Session, now: datetime) -> Report:
    """Return the whole picture of ``session`` at ``now``, as data."""
    adapter = session.adapter
    return Report(
        generated_at=now,
        data={
            "generated_at": now.isoformat(),
            "version": __version__,
            "vehicle": {
                "state": str(session.state),
                "port": adapter.port if adapter is not None else None,
                "usb_id": adapter.usb_id if adapter is not None else None,
                "adapter": adapter.label if adapter is not None else None,
                "vin": session.vin,
                "manufacturer": session.profile.name,
                "engine": session.engine,
            },
            "catalog": {
                mode: [asdict(command) for command in commands]
                for mode, commands in session.catalog.modes.items()
            },
            "supported": sorted(session.catalog.supported_names),
            "readings": as_row(session.vehicle),
            "history": {field: session.history.series(field) for field in session.history.fields},
            "faults": {
                "stored": [_code(code) for code in session.vehicle.stored_codes],
                "pending": [_code(code) for code in session.vehicle.pending_codes],
            },
        },
    )


def write_report(report: Report, markdown: str, directory: Path) -> tuple[Path, Path]:
    """Write the report as JSON and as Markdown under ``directory``.

    Returns:
        The two paths, JSON first. The directory is created if need be.
    """
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / f"{report.stem}.json"
    markdown_path = directory / f"{report.stem}.md"
    json_path.write_text(json.dumps(report.data, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(markdown, encoding="utf-8")
    return json_path, markdown_path


def _code(code: TroubleCode) -> dict[str, str]:
    """Return a trouble code as the report writes it."""
    return {"code": code.code, "description": code.description}
