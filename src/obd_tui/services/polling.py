# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Read the vehicle's sensors into a :class:`VehicleState`."""

from __future__ import annotations

import logging
from typing import Any

from obd_tui.models.commands import CommandCatalog
from obd_tui.models.vehicle import TroubleCode, VehicleState
from obd_tui.services.connection import ObdConnection

logger = logging.getLogger(__name__)

# python-obd command name -> VehicleState field, for readings decoded as a
# scalar (a pint quantity or a plain number).
NUMERIC_READINGS: dict[str, str] = {
    "RPM": "rpm",
    "ENGINE_LOAD": "engine_load",
    "ABSOLUTE_LOAD": "absolute_load",
    "TIMING_ADVANCE": "timing_advance",
    "RUN_TIME": "run_time",
    "MAF": "mass_air_flow",
    "CONTROL_MODULE_VOLTAGE": "module_voltage",
    "SPEED": "speed",
    "COOLANT_TEMP": "coolant_temp",
    "OIL_TEMP": "oil_temp",
    "INTAKE_TEMP": "intake_temp",
    "AMBIANT_AIR_TEMP": "ambient_temp",
    "FUEL_RAIL_PRESSURE_DIRECT": "fuel_rail_pressure",
    "FUEL_RATE": "fuel_rate",
    "FUEL_LEVEL": "fuel_level",
    "FUEL_INJECT_TIMING": "fuel_inject_timing",
    "COMMANDED_EQUIV_RATIO": "equivalence_ratio",
    "SHORT_FUEL_TRIM_1": "short_fuel_trim",
    "LONG_FUEL_TRIM_1": "long_fuel_trim",
    "INTAKE_PRESSURE": "intake_pressure",
    "BAROMETRIC_PRESSURE": "barometric_pressure",
    "THROTTLE_POS": "throttle",
    "THROTTLE_POS_B": "throttle_b",
    "THROTTLE_ACTUATOR": "throttle_actuator",
    "ACCELERATOR_POS_D": "accel_pedal_d",
    "ACCELERATOR_POS_E": "accel_pedal_e",
    "RELATIVE_ACCEL_POS": "relative_accel",
    "O2_S1_WR_CURRENT": "o2_s1_lambda",
    "O2_S2_WR_CURRENT": "o2_s2_lambda",
    "COMMANDED_EGR": "egr_commanded",
    "EGR_ERROR": "egr_error",
    "DISTANCE_W_MIL": "distance_with_mil",
    "RUN_TIME_MIL": "run_time_with_mil",
    "WARMUPS_SINCE_DTC_CLEAR": "warmups_since_clear",
    "DISTANCE_SINCE_DTC_CLEAR": "distance_since_clear",
    "TIME_SINCE_DTC_CLEARED": "time_since_clear",
}

# Readings kept as the library object they come back as: bit-field status
# words, enumerations and vehicle-info strings that the panels render
# through ``str()``.
RAW_READINGS: dict[str, str] = {
    "STATUS": "status",
    "OBD_COMPLIANCE": "obd_compliance",
    "FUEL_TYPE": "fuel_type",
    "FUEL_STATUS": "fuel_status",
    "O2_SENSORS": "o2_sensors",
    "CALIBRATION_ID": "calibration_id",
    "CVN": "cvn",
}

# Readings that come back as a list of (code, description) pairs.
CODE_READINGS: dict[str, str] = {
    "GET_DTC": "stored_codes",
    "GET_CURRENT_DTC": "pending_codes",
}


class SensorPoller:
    """Fill a :class:`VehicleState` from one sweep of the vehicle's sensors.

    Args:
        connection: The open link to query.
    """

    def __init__(self, connection: ObdConnection) -> None:
        self._connection = connection

    def poll(self, state: VehicleState, catalog: CommandCatalog | None = None) -> VehicleState:
        """Refresh ``state`` in place and return it.

        Args:
            state: The snapshot to update. Values the vehicle did not answer
                are left untouched, so a single dropped frame does not blank
                the dashboard.
            catalog: Discovered capabilities. When given, only supported
                commands are queried — a sweep of every known PID takes
                seconds on a real adapter. An empty or missing catalog falls
                back to querying everything.
        """
        for command, field in NUMERIC_READINGS.items():
            value = self._read(command, catalog)
            if value is not None:
                number = _as_float(value)
                if number is not None:
                    setattr(state, field, number)

        for command, field in RAW_READINGS.items():
            value = self._read(command, catalog)
            if value is not None:
                setattr(state, field, value)

        for command, field in CODE_READINGS.items():
            value = self._read(command, catalog)
            if value is not None:
                setattr(state, field, _as_codes(value))

        return state

    def _read(self, command: str, catalog: CommandCatalog | None) -> Any | None:
        """Query ``command`` unless the catalog rules it out."""
        if catalog is not None and len(catalog) and not catalog.supports(command):
            return None
        return self._connection.query(command)


def _as_float(value: Any) -> float | None:
    """Convert a python-obd reading to a float, or ``None`` if it is not one.

    Numeric readings arrive as pint quantities carrying a unit; a few
    adapters answer with a bare number instead.
    """
    magnitude = getattr(value, "magnitude", value)
    try:
        return float(magnitude)
    except (TypeError, ValueError):
        logger.debug("ignoring non-numeric reading %r", value)
        return None


def _as_codes(value: Any) -> list[TroubleCode]:
    """Convert a python-obd DTC list to :class:`TroubleCode` objects."""
    codes: list[TroubleCode] = []
    try:
        entries = list(value)
    except TypeError:
        logger.debug("ignoring non-iterable trouble code reading %r", value)
        return codes
    for entry in entries:
        if isinstance(entry, str):
            codes.append(TroubleCode(entry))
            continue
        code, *rest = entry
        codes.append(TroubleCode(str(code), str(rest[0]) if rest else ""))
    return codes
