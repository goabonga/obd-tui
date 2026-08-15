# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Units of the readings, and how to show them in either system.

A vehicle always reports metric: the OBD-II standard defines its PIDs in
degrees Celsius, kilopascals and kilometres. Conversion is therefore a
display concern only — the state, the history and the recordings stay in
the units the ECU sent, and only the panels change.
"""

from __future__ import annotations

from enum import Enum


class Quantity(Enum):
    """What a reading measures, when it is worth converting."""

    NONE = "none"
    TEMPERATURE = "temperature"
    SPEED = "speed"
    DISTANCE = "distance"
    PRESSURE = "pressure"
    VOLUME_RATE = "volume_rate"


class UnitSystem(Enum):
    """The system the readings are displayed in."""

    METRIC = "metric"
    IMPERIAL = "imperial"

    def __str__(self) -> str:
        """Return the name used in the configuration file."""
        return self.value

    def suffix(self, quantity: Quantity) -> str:
        """Return the unit shown beside a reading of ``quantity``."""
        return SUFFIXES[self][quantity]

    def convert(self, quantity: Quantity, value: float) -> float:
        """Convert a metric reading into this system."""
        if self is UnitSystem.METRIC:
            return value
        return CONVERSIONS[quantity](value)


SUFFIXES: dict[UnitSystem, dict[Quantity, str]] = {
    UnitSystem.METRIC: {
        Quantity.NONE: "",
        Quantity.TEMPERATURE: "°C",
        Quantity.SPEED: "km/h",
        Quantity.DISTANCE: "km",
        Quantity.PRESSURE: "kPa",
        Quantity.VOLUME_RATE: "L/h",
    },
    UnitSystem.IMPERIAL: {
        Quantity.NONE: "",
        Quantity.TEMPERATURE: "°F",
        Quantity.SPEED: "mph",
        Quantity.DISTANCE: "mi",
        Quantity.PRESSURE: "psi",
        Quantity.VOLUME_RATE: "gal/h",
    },
}

CONVERSIONS = {
    Quantity.NONE: lambda value: value,
    Quantity.TEMPERATURE: lambda value: value * 9 / 5 + 32,
    Quantity.SPEED: lambda value: value * 0.621371,
    Quantity.DISTANCE: lambda value: value * 0.621371,
    Quantity.PRESSURE: lambda value: value * 0.145038,
    Quantity.VOLUME_RATE: lambda value: value * 0.264172,
}

# What each reading measures. A field that is absent measures something
# that does not change between systems — a percentage, an angle, a count,
# a voltage, a duration — or is not a number at all.
FIELD_QUANTITY: dict[str, Quantity] = {
    "coolant_temp": Quantity.TEMPERATURE,
    "oil_temp": Quantity.TEMPERATURE,
    "intake_temp": Quantity.TEMPERATURE,
    "ambient_temp": Quantity.TEMPERATURE,
    "speed": Quantity.SPEED,
    "distance_with_mil": Quantity.DISTANCE,
    "distance_since_clear": Quantity.DISTANCE,
    "fuel_rail_pressure": Quantity.PRESSURE,
    "intake_pressure": Quantity.PRESSURE,
    "barometric_pressure": Quantity.PRESSURE,
    "net_boost": Quantity.PRESSURE,
    "fuel_rate": Quantity.VOLUME_RATE,
}


def quantity_of(field: str) -> Quantity:
    """Return what the reading held in ``field`` measures."""
    return FIELD_QUANTITY.get(field, Quantity.NONE)
