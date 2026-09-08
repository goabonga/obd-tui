# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""The diesel particulate filter, as the standard PIDs describe it.

Plain readings and the decoding of their frames; nothing here knows about
python-obd, nor about any one vehicle.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# Mode 01 PID 0x7A: one bitmap byte, then three 16-bit pressures.
PRESSURE_FRAME_LENGTH = 7

# Mode 01 PID 0x7C: one bitmap byte, then four 16-bit temperatures, two
# per bank - inlet and outlet - in tenths of a degree above -40 °C.
TEMPERATURE_FRAME_LENGTH = 9
TEMPERATURE_SCALE = 10.0
TEMPERATURE_OFFSET = -40.0

# The differential pressure is signed, in hundredths of a kPa around
# -327.68; the inlet and outlet are unsigned hundredths of a kPa.
PRESSURE_SCALE = 0.01
DIFFERENTIAL_OFFSET = -327.68


@dataclass(frozen=True, slots=True)
class DpfPressure:
    """Pressures across the particulate filter, in kPa.

    Attributes:
        differential: Inlet minus outlet, the restriction the filter puts
            in the way of the exhaust. What a clogging filter raises.
        inlet: Absolute pressure before the filter.
        outlet: Absolute pressure after it.

    A value the vehicle does not report is ``None``; the standard sends
    bytes for it all the same, and they mean nothing.
    """

    differential: float | None = None
    inlet: float | None = None
    outlet: float | None = None

    @classmethod
    def from_frame(cls, data: bytes) -> DpfPressure | None:
        """Decode the payload of PID 0x7A, or ``None`` if too short.

        Args:
            data: The data bytes after the mode and PID: ``A`` the bitmap,
                bit 0 for the differential, bit 1 the inlet, bit 2 the
                outlet; then ``BC``, ``DE`` and ``FG`` the three pressures.
        """
        if len(data) < PRESSURE_FRAME_LENGTH:
            return None
        present = data[0]

        def word(index: int) -> float:
            return ((data[index] << 8) | data[index + 1]) * PRESSURE_SCALE

        return cls(
            differential=word(1) + DIFFERENTIAL_OFFSET if present & 0b001 else None,
            inlet=word(3) if present & 0b010 else None,
            outlet=word(5) if present & 0b100 else None,
        )


class TemperatureSource(Enum):
    """Where a filter temperature came from."""

    ECU = "ecu"
    """The vehicle reported it as the filter's own, through PID 0x7C."""

    EXHAUST = "exhaust"
    """Taken from an exhaust gas sensor the manufacturer profile placed at
    the filter. Only a profile may say which sensor sits where."""


class DpfRole(Enum):
    """Where an exhaust gas sensor sits relative to the particulate filter."""

    INLET = "inlet"
    OUTLET = "outlet"
    INTERNAL = "internal"


@dataclass(frozen=True, slots=True)
class DpfTemperatures:
    """Temperatures at the particulate filter, in °C.

    Attributes:
        inlet: Before the filter.
        outlet: After it.
        internal: Inside it, which only some vehicles report.
        source: Whether the vehicle named these as the filter's own, or a
            manufacturer profile placed exhaust sensors there. The two
            are never confused: an exhaust sensor is the filter's inlet
            only when someone who knows the engine says so.
    """

    inlet: float | None = None
    outlet: float | None = None
    internal: float | None = None
    source: TemperatureSource = TemperatureSource.ECU

    @classmethod
    def from_frame(cls, data: bytes) -> DpfTemperatures | None:
        """Decode the payload of PID 0x7C for bank 1, or ``None`` if too short.

        Args:
            data: The data bytes after the mode and PID: ``A`` the bitmap,
                bit 0 for the bank 1 inlet and bit 1 for its outlet - bits 2
                and 3 answer for bank 2 and are left aside - then ``BC``
                and ``DE`` the two temperatures.
        """
        if len(data) < TEMPERATURE_FRAME_LENGTH:
            return None
        present = data[0]

        def word(index: int) -> float:
            return ((data[index] << 8) | data[index + 1]) / TEMPERATURE_SCALE + TEMPERATURE_OFFSET

        return cls(
            inlet=word(1) if present & 0b01 else None,
            outlet=word(3) if present & 0b10 else None,
        )


# The bounds a soot load can be believed within. A percentage past its
# scale, or a negative mass, is an ECU or a decoder talking nonsense.
MAX_SOOT_PERCENT = 100.0


@dataclass(frozen=True, slots=True)
class DpfLoad:
    """How much soot the particulate filter holds.

    The standard has no PID for this; what a vehicle exposes is its
    manufacturer's, and comes in one of two shapes - a percentage of the
    filter's capacity, or a mass of soot. Both are kept when both are
    given, and neither is ever derived from the other: turning a mass
    into a percentage takes a nominal capacity that is not known here.

    Attributes:
        percent: Fill level, 0 to 100 % of the filter's capacity.
        soot_mass_g: Soot held, in grams.
    """

    percent: float | None = None
    soot_mass_g: float | None = None

    def validated(self) -> DpfLoad | None:
        """Return the load with impossible values dropped, or ``None`` if none is left."""
        percent = self.percent if _within(self.percent, 0.0, MAX_SOOT_PERCENT) else None
        mass = self.soot_mass_g if _within(self.soot_mass_g, 0.0, None) else None
        if percent is None and mass is None:
            return None
        return DpfLoad(percent=percent, soot_mass_g=mass)


def _within(value: float | None, lowest: float, highest: float | None) -> bool:
    """Return whether ``value`` is known and inside the bounds."""
    if value is None or value < lowest:
        return False
    return highest is None or value <= highest
