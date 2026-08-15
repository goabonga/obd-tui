# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Write each sweep of readings to a file, one JSON object per line."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from obd_tui.models.vehicle import TroubleCode, VehicleState

Timestamps = Callable[[], datetime]


def utc_now() -> datetime:
    """Return the current UTC time."""
    return datetime.now(UTC)


def as_row(state: VehicleState) -> dict[str, Any]:
    """Return ``state`` as a JSON-serialisable mapping.

    Readings the vehicle did not report stay ``None`` rather than being
    dropped, so every line of a recording has the same keys and the file
    loads as a table. Derived readings are written too: recomputing
    ``net_boost`` from a recording should not be the reader's job.
    """
    row = {field.name: _plain(getattr(state, field.name)) for field in fields(state)}
    row["net_boost"] = state.net_boost
    return row


def _plain(value: Any) -> Any:
    """Reduce a reading to something ``json`` can write.

    ECU responses are library objects whose repr is the only thing worth
    keeping; trouble codes become objects of their own.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, TroubleCode):
        return {"code": value.code, "description": value.description}
    return str(value)


class SessionRecorder:
    """Append every sweep to a JSON Lines file.

    Args:
        path: File to append to. Its parent directories are created, and an
            existing file is kept: reconnecting continues the same log.
        timestamps: Source of the time stamped on each line. Injected so
            tests get a fixed one.
    """

    def __init__(self, path: Path, timestamps: Timestamps = utc_now) -> None:
        self.path = path
        self._timestamps = timestamps
        self._handle: TextIO | None = None

    def record(self, state: VehicleState) -> None:
        """Write one line for this sweep and flush it.

        Flushing every sweep costs little and means a session that ends with
        a pulled plug still has every sweep that reached the disk.
        """
        line = {"time": self._timestamps().isoformat(), **as_row(state)}
        handle = self._writer()
        handle.write(json.dumps(line, separators=(",", ":")) + "\n")
        handle.flush()

    def close(self) -> None:
        """Close the file, if it was ever opened."""
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def _writer(self) -> TextIO:
        """Return the open file, creating it on the first sweep."""
        if self._handle is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = self.path.open("a", encoding="utf-8")
        return self._handle
