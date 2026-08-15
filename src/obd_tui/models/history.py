# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Recent history of the readings, for trend rendering.

The series live beside :class:`VehicleState` rather than inside it: a state
is the snapshot of one sweep, while a history spans many, and keeping them
apart leaves the snapshot free to become immutable.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field

from obd_tui.models.vehicle import VehicleState

# Points kept per reading: five minutes at the default one-second sweep.
HISTORY_LENGTH = 300

# Readings worth a trend. Every name must be a numeric VehicleState field.
TRACKED_FIELDS: tuple[str, ...] = (
    "rpm",
    "coolant_temp",
    "mass_air_flow",
    "speed",
    "engine_load",
    "intake_pressure",
)


@dataclass(slots=True)
class History:
    """The most recent values of one reading, oldest first.

    Args:
        length: How many points to keep before dropping the oldest.
    """

    length: int = HISTORY_LENGTH
    _values: deque[float] = field(init=False, repr=False, default_factory=deque)

    def __post_init__(self) -> None:
        """Size the underlying buffer from ``length``."""
        self._values = deque(maxlen=self.length)

    def __len__(self) -> int:
        """Return how many points are held."""
        return len(self._values)

    def __iter__(self) -> Iterator[float]:
        """Iterate over the points, oldest first."""
        return iter(self._values)

    def __bool__(self) -> bool:
        """Return whether any point has been recorded."""
        return bool(self._values)

    @property
    def values(self) -> list[float]:
        """Return the points as a list, oldest first."""
        return list(self._values)

    @property
    def latest(self) -> float | None:
        """Return the most recent point, or ``None`` when empty."""
        return self._values[-1] if self._values else None

    def push(self, value: float | None) -> None:
        """Append a reading, ignoring the ones the vehicle did not report."""
        if value is not None:
            self._values.append(value)

    def clear(self) -> None:
        """Drop every point."""
        self._values.clear()


class ReadingHistory:
    """The series of every tracked reading.

    Args:
        fields: Names of the :class:`VehicleState` fields to follow.
        length: Points kept per reading.
    """

    def __init__(
        self, fields: Sequence[str] = TRACKED_FIELDS, length: int = HISTORY_LENGTH
    ) -> None:
        self._series = {name: History(length=length) for name in fields}

    def __contains__(self, name: str) -> bool:
        """Return whether ``name`` is followed."""
        return name in self._series

    @property
    def fields(self) -> tuple[str, ...]:
        """Return the followed field names."""
        return tuple(self._series)

    def record(self, state: VehicleState) -> None:
        """Append this sweep's value of every tracked reading."""
        for name, series in self._series.items():
            series.push(getattr(state, name, None))

    def series(self, name: str) -> list[float]:
        """Return the points of one reading, empty when it is not followed."""
        history = self._series.get(name)
        return history.values if history is not None else []

    def clear(self) -> None:
        """Drop every point of every reading."""
        for series in self._series.values():
            series.clear()
