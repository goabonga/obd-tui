# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Read the vehicle's sensors into a :class:`VehicleState`."""

from __future__ import annotations

import logging
from collections.abc import Callable, Collection
from dataclasses import replace
from enum import Enum
from typing import Any

from obd_tui.models.commands import CommandCatalog
from obd_tui.models.vehicle import TroubleCode, VehicleState
from obd_tui.services.connection import AdapterError, ObdConnection

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

# The fields the trouble-code commands fill, for a caller that wants them
# read on demand rather than on their usual cadence.
CODE_FIELDS: tuple[str, ...] = tuple(CODE_READINGS.values())

# Every command a sweep can ask for, mapped to the field it fills.
ALL_READINGS: dict[str, str] = {**NUMERIC_READINGS, **RAW_READINGS, **CODE_READINGS}

# Consecutive adapter failures before the link is taken for lost. These
# are questions that never reached the vehicle — not questions it declined
# to answer, which is routine and says nothing about the connection.
LINK_LOSS_FAILURES = 5


class LinkLost(RuntimeError):
    """The adapter stopped carrying questions to the vehicle."""


class Tier(Enum):
    """How often a reading is worth asking the vehicle for.

    The value is the sweep period: ``FAST`` on every sweep, ``MEDIUM`` every
    fifth, ``SLOW`` every sixtieth.
    """

    FAST = 1
    MEDIUM = 5
    SLOW = 60

    @property
    def period(self) -> int:
        """Return how many sweeps pass between two reads."""
        return int(self.value)


# Readings that drive the dashboard: they change several times a second and
# are what a driver watches.
FAST_COMMANDS: frozenset[str] = frozenset(
    {
        "RPM",
        "SPEED",
        "ENGINE_LOAD",
        "ABSOLUTE_LOAD",
        "THROTTLE_POS",
        "MAF",
        "INTAKE_PRESSURE",
        "ACCELERATOR_POS_D",
    }
)

# Readings that are all but fixed for a whole session, or that cost several
# frames to fetch. Asking for them every second wastes the link.
SLOW_COMMANDS: frozenset[str] = frozenset(
    {
        "STATUS",
        "GET_DTC",
        "GET_CURRENT_DTC",
        "OBD_COMPLIANCE",
        "FUEL_TYPE",
        "FUEL_STATUS",
        "CALIBRATION_ID",
        "CVN",
        "DISTANCE_W_MIL",
        "RUN_TIME_MIL",
        "WARMUPS_SINCE_DTC_CLEAR",
        "DISTANCE_SINCE_DTC_CLEAR",
        "TIME_SINCE_DTC_CLEARED",
        "BAROMETRIC_PRESSURE",
        "FUEL_LEVEL",
        "AMBIANT_AIR_TEMP",
        "O2_SENSORS",
    }
)

# Temperatures, pressures and trims: worth following, but they move slowly
# enough that a fifth of the sweeps is plenty.
DEFAULT_TIER = Tier.MEDIUM


def tier_of(command: str) -> Tier:
    """Return how often ``command`` is worth asking for."""
    if command in FAST_COMMANDS:
        return Tier.FAST
    if command in SLOW_COMMANDS:
        return Tier.SLOW
    return DEFAULT_TIER


def is_due(command: str, sweep: int, priority: Collection[str] = ()) -> bool:
    """Return whether ``command`` should be asked for on sweep ``sweep``.

    Args:
        command: python-obd command name.
        sweep: How many sweeps have already run.
        priority: Fields the user is looking at. A command that fills one of
            them is read every sweep whatever its tier — what is on screen
            should be live, even if it is a reading that rarely moves.

    Sweep zero reads everything, so the dashboard fills up at once rather
    than revealing the slow readings a minute later.
    """
    if ALL_READINGS.get(command) in priority:
        return True
    return sweep % tier_of(command).period == 0


class SensorPoller:
    """Fill a :class:`VehicleState` from one sweep of the vehicle's sensors.

    A sweep does not query everything every time. An adapter answers a few
    dozen commands a second at best, so readings that move (engine speed,
    load, throttle) are asked for on every sweep while the ones that barely
    move, or cost several frames to fetch, are asked for less often.

    Args:
        connection: The open link to query.
    """

    def __init__(self, connection: ObdConnection) -> None:
        self._connection = connection
        self._sweep = 0

    @property
    def sweep_count(self) -> int:
        """Return how many sweeps have run, which drives the cadences."""
        return self._sweep

    def poll(
        self,
        state: VehicleState,
        catalog: CommandCatalog | None = None,
        priority: Collection[str] = (),
    ) -> VehicleState:
        """Return a new snapshot built from ``state`` and this sweep.

        Args:
            state: The snapshot to carry forward. Values the vehicle did not
                answer are copied over unchanged, so a single dropped frame
                does not blank the dashboard, and neither does a reading
                whose turn in the cadence has not come round.
            catalog: Discovered capabilities. When given, only supported
                commands are queried — a sweep of every known PID takes
                seconds on a real adapter. An empty or missing catalog falls
                back to querying everything.
            priority: Fields on display, read every sweep whatever their
                tier.

        Raises:
            LinkLost: When the adapter stops carrying questions to the
                vehicle. A command the vehicle declines to answer is not
                that — an empty answer is still an answer.
        """
        sweep = self._sweep
        self._sweep += 1
        failures = 0
        readings: dict[str, Any] = {}

        with self._connection.sweep():
            for command, field in ALL_READINGS.items():
                if not self._should_query(command, catalog, sweep, priority):
                    continue

                try:
                    value = self._connection.query(command)
                except AdapterError as error:
                    failures += 1
                    if failures >= LINK_LOSS_FAILURES:
                        raise LinkLost(
                            f"{failures} commands in a row never reached the vehicle"
                        ) from error
                    continue

                failures = 0
                if value is None:
                    # The vehicle declined to answer. Routine: a PID it
                    # reports as supported but has nothing for right now, or
                    # a counter a clear reset moments ago.
                    continue

                reading = CONVERTERS[command](value)
                if reading is not None:
                    readings[field] = reading

        return replace(state, **readings)

    def _should_query(
        self,
        command: str,
        catalog: CommandCatalog | None,
        sweep: int,
        priority: Collection[str],
    ) -> bool:
        """Return whether the catalog and the cadence allow asking now."""
        if catalog is not None and len(catalog) and not catalog.supports(command):
            return False
        return is_due(command, sweep, priority)


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


def _as_codes(value: Any) -> tuple[TroubleCode, ...]:
    """Convert a python-obd DTC list to :class:`TroubleCode` objects."""
    codes: list[TroubleCode] = []
    try:
        entries = list(value)
    except TypeError:
        logger.debug("ignoring non-iterable trouble code reading %r", value)
        return ()
    for entry in entries:
        if isinstance(entry, str):
            codes.append(TroubleCode(entry))
            continue
        code, *rest = entry
        codes.append(TroubleCode(str(code), str(rest[0]) if rest else ""))
    return tuple(codes)


def _identity(value: Any) -> Any:
    """Return a reading the state keeps exactly as the ECU sent it."""
    return value


# How each command's answer is turned into what the state holds. A numeric
# reading that will not convert yields None, and the sweep skips it.
CONVERTERS: dict[str, Callable[[Any], Any]] = {
    **{command: _as_float for command in NUMERIC_READINGS},
    **{command: _identity for command in RAW_READINGS},
    **{command: _as_codes for command in CODE_READINGS},
}
