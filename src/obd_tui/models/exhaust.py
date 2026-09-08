# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Exhaust gas temperatures, as one bank of sensors reports them.

Mode 01 answers for a whole bank in one frame - PID 0x78 for bank 1,
0x79 for bank 2: a bitmap saying which of its four sensors exist, then
four 16-bit temperatures in tenths of a degree above -40 °C. This module
holds the reading and the decoding of that frame; nothing here knows
about python-obd, nor about any one vehicle.
"""

from __future__ import annotations

from dataclasses import dataclass

# Sensors per bank the standard lays out, and the bytes each one takes.
SENSORS_PER_BANK = 4
BYTES_PER_SENSOR = 2

# One bitmap byte, then the four temperatures.
FRAME_LENGTH = 1 + SENSORS_PER_BANK * BYTES_PER_SENSOR

# The encoding: tenths of a degree, offset so that zero reads as -40 °C.
SCALE = 10.0
OFFSET = -40.0


@dataclass(frozen=True, slots=True)
class ExhaustTemperatures:
    """The temperatures of one bank of exhaust gas sensors, in °C.

    Attributes:
        bank: Which bank, numbered from 1 the way the ECU numbers them.
        sensors: One entry per sensor slot, upstream first. A sensor the
            bank leaves out is ``None``: the standard sends a value for it
            all the same, and that value means nothing. The tuple is as
            long as the frame allows, whether or not the last slots are
            fitted, so a sensor's position never depends on its neighbours.
    """

    bank: int
    sensors: tuple[float | None, ...] = (None,) * SENSORS_PER_BANK

    @property
    def fitted(self) -> tuple[tuple[int, float], ...]:
        """Return the sensors present, as (number, temperature) pairs.

        Numbered from 1, the way a trouble code names them: ``P2033`` is
        bank 1 sensor 2.
        """
        return tuple(
            (number, temperature)
            for number, temperature in enumerate(self.sensors, start=1)
            if temperature is not None
        )

    @classmethod
    def from_frame(cls, bank: int, data: bytes) -> ExhaustTemperatures | None:
        """Decode the payload of one bank's PID, or ``None`` if too short.

        Args:
            bank: The bank the frame answers for.
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
        for slot in range(SENSORS_PER_BANK):
            if not present & (1 << slot):
                temperatures.append(None)
                continue
            start = 1 + slot * BYTES_PER_SENSOR
            raw = (data[start] << 8) | data[start + 1]
            temperatures.append(raw / SCALE + OFFSET)
        return cls(bank, tuple(temperatures))
