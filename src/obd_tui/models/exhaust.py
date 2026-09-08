# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Exhaust gas temperatures, as one bank of sensors reports them.

Mode 01 PID 0x78 answers for a whole bank in one frame: a bitmap saying
which of its four sensors exist, then four 16-bit temperatures in tenths
of a degree above -40 °C. This module holds the reading and the decoding
of that frame; nothing here knows about python-obd.
"""

from __future__ import annotations

from dataclasses import astuple, dataclass

# Sensors per bank the standard lays out, and the bytes each one takes.
SENSORS = 4
BYTES_PER_SENSOR = 2

# One bitmap byte, then the four temperatures.
FRAME_LENGTH = 1 + SENSORS * BYTES_PER_SENSOR

# The encoding: tenths of a degree, offset so that zero reads as -40 °C.
SCALE = 10.0
OFFSET = -40.0


@dataclass(frozen=True, slots=True)
class ExhaustTemperatures:
    """The temperatures of one bank of exhaust gas sensors, in °C.

    A sensor the bitmap leaves out is ``None``: the standard sends a value
    for it all the same, and that value means nothing.
    """

    sensor_1: float | None = None
    sensor_2: float | None = None
    sensor_3: float | None = None
    sensor_4: float | None = None

    @property
    def readings(self) -> tuple[float | None, ...]:
        """Return the four sensors in order, present or not."""
        return astuple(self)

    @classmethod
    def from_frame(cls, data: bytes) -> ExhaustTemperatures | None:
        """Decode the payload of PID 0x78, or ``None`` if it is too short.

        Args:
            data: The data bytes after the mode and PID: ``A`` is the
                bitmap, bit 0 for sensor 1 up to bit 3 for sensor 4, and
                ``BC`` to ``HI`` the temperatures. Bytes past the frame
                are ignored, as an adapter that pads its answers would
                add them.
        """
        if len(data) < FRAME_LENGTH:
            return None
        present = data[0]
        temperatures: list[float | None] = []
        for sensor in range(SENSORS):
            if not present & (1 << sensor):
                temperatures.append(None)
                continue
            start = 1 + sensor * BYTES_PER_SENSOR
            raw = (data[start] << 8) | data[start + 1]
            temperatures.append(raw / SCALE + OFFSET)
        return cls(*temperatures)
