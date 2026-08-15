# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""A vehicle that only exists in memory, for demos and screenshots."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import obd

from obd_tui.models.adapter import AdapterInfo
from obd_tui.services.connection import ConnectionFactory, ObdConnection
from obd_tui.services.recording import SessionRecorder
from obd_tui.services.session import Session

# The demo adapter reports a port that cannot collide with a real one.
SIMULATED_PORT = "/dev/obd-tui-demo"
SIMULATED_ADAPTER = AdapterInfo(
    port=SIMULATED_PORT, vid="0403", pid="6015", label="obd-tui demo adapter"
)

Clock = Callable[[], float]
Reading = Callable[[float], float]


def constant(value: float) -> Reading:
    """Return a reading that never moves."""
    return lambda _: value


def wave(center: float, amplitude: float, period: float) -> Reading:
    """Return a reading oscillating around ``center``."""
    return lambda elapsed: center + amplitude * math.sin(2 * math.pi * elapsed / period)


def warmup(target: float, start: float, tau: float) -> Reading:
    """Return a reading climbing from ``start`` towards ``target``."""
    return lambda elapsed: target - (target - start) * math.exp(-elapsed / tau)


def ramp(low: float, high: float, period: float) -> Reading:
    """Return a reading sweeping back and forth between two bounds."""

    def read(elapsed: float) -> float:
        phase = (elapsed % period) / period
        return low + (high - low) * (2 * phase if phase < 0.5 else 2 * (1 - phase))

    return read


# Scalar readings, keyed by python-obd command name.
NUMERIC: dict[str, Reading] = {
    "RPM": wave(880.0, 70.0, 7.0),
    "SPEED": ramp(0.0, 90.0, 45.0),
    "ENGINE_LOAD": wave(28.0, 9.0, 11.0),
    "ABSOLUTE_LOAD": wave(31.0, 9.0, 11.0),
    "TIMING_ADVANCE": wave(9.5, 3.0, 13.0),
    "RUN_TIME": lambda elapsed: 312.0 + elapsed,
    "MAF": wave(4.2, 1.1, 9.0),
    "CONTROL_MODULE_VOLTAGE": wave(14.1, 0.15, 23.0),
    "COOLANT_TEMP": warmup(91.0, 21.0, 45.0),
    "OIL_TEMP": warmup(96.0, 20.0, 70.0),
    "INTAKE_TEMP": warmup(38.0, 19.0, 60.0),
    "AMBIANT_AIR_TEMP": constant(18.0),
    "FUEL_RAIL_PRESSURE_DIRECT": wave(31000.0, 900.0, 8.0),
    "FUEL_RATE": wave(1.4, 0.4, 9.0),
    "FUEL_LEVEL": constant(63.0),
    "FUEL_INJECT_TIMING": wave(-4.5, 1.5, 12.0),
    "COMMANDED_EQUIV_RATIO": wave(1.0, 0.03, 6.0),
    "SHORT_FUEL_TRIM_1": wave(1.6, 2.4, 5.0),
    "LONG_FUEL_TRIM_1": constant(3.9),
    "INTAKE_PRESSURE": wave(118.0, 34.0, 15.0),
    "BAROMETRIC_PRESSURE": constant(101.0),
    "THROTTLE_POS": ramp(13.0, 46.0, 45.0),
    "THROTTLE_POS_B": ramp(15.0, 48.0, 45.0),
    "THROTTLE_ACTUATOR": ramp(11.0, 44.0, 45.0),
    "ACCELERATOR_POS_D": ramp(12.0, 41.0, 45.0),
    "ACCELERATOR_POS_E": ramp(14.0, 43.0, 45.0),
    "RELATIVE_ACCEL_POS": ramp(0.0, 29.0, 45.0),
    "O2_S1_WR_CURRENT": wave(0.99, 0.05, 4.0),
    "O2_S2_WR_CURRENT": wave(1.01, 0.03, 6.0),
    "COMMANDED_EGR": wave(22.0, 7.0, 17.0),
    "EGR_ERROR": wave(-3.2, 1.8, 19.0),
    "DISTANCE_W_MIL": constant(148.0),
    "RUN_TIME_MIL": constant(9240.0),
    "WARMUPS_SINCE_DTC_CLEAR": constant(23.0),
    "DISTANCE_SINCE_DTC_CLEAR": constant(612.0),
    "TIME_SINCE_DTC_CLEARED": constant(1840.0),
}


@dataclass(frozen=True, slots=True)
class SimulatedStatus:
    """Stand-in for the mode 01 PID 01 status word."""

    MIL: bool = True
    DTC_count: int = 2
    ignition_type: str = "spark"


# Readings handed back as the object the ECU would report.
RAW: dict[str, Any] = {
    "STATUS": SimulatedStatus(),
    "OBD_COMPLIANCE": "EOBD (Europe)",
    "FUEL_TYPE": "Diesel",
    "FUEL_STATUS": "Closed loop, using oxygen sensor feedback",
    "O2_SENSORS": "Bank 1: sensors 1, 2",
    "CALIBRATION_ID": "03L906022QT 4589",
    "CVN": "8A17C3D2",
}

# Trouble codes, as python-obd reports them: (code, description) pairs.
CODES: dict[str, list[tuple[str, str]]] = {
    "GET_DTC": [
        ("P0401", "Exhaust Gas Recirculation Flow Insufficient Detected"),
        ("P0133", "O2 Sensor Circuit Slow Response (Bank 1, Sensor 1)"),
    ],
    "GET_CURRENT_DTC": [("P0299", "Turbocharger/Supercharger Underboost")],
}


@dataclass(frozen=True, slots=True)
class SimulatedResponse:
    """Stand-in for a python-obd response."""

    value: Any

    def is_null(self) -> bool:
        """Return whether the vehicle had nothing to answer."""
        return self.value is None


class SimulatedVehicle:
    """Answers OBD queries with plausible readings that move over time.

    Args:
        clock: Source of the elapsed time the readings are derived from.
            Injected so tests can drive the animation instead of waiting.
    """

    def __init__(self, clock: Clock = time.monotonic) -> None:
        self._clock = clock
        self._started = clock()
        self._open = True

    @property
    def supported_commands(self) -> list[Any]:
        """Return the python-obd commands this vehicle answers."""
        return [
            command
            for command in (getattr(obd.commands, name, None) for name in simulated_names())
            if command is not None
        ]

    def is_connected(self) -> bool:
        """Return whether the link is still up."""
        return self._open

    def close(self) -> None:
        """Hang up."""
        self._open = False

    def query(self, command: Any) -> SimulatedResponse:
        """Answer one command, or return a null response for the rest."""
        if not self._open:
            return SimulatedResponse(None)
        name = str(getattr(command, "name", command))
        elapsed = self._clock() - self._started
        if name in NUMERIC:
            return SimulatedResponse(NUMERIC[name](elapsed))
        if name in RAW:
            return SimulatedResponse(RAW[name])
        if name in CODES:
            return SimulatedResponse(list(CODES[name]))
        return SimulatedResponse(None)


def simulated_names() -> tuple[str, ...]:
    """Return every command name the simulated vehicle answers."""
    return (*NUMERIC, *RAW, *CODES)


def simulated_factory(clock: Clock = time.monotonic) -> ConnectionFactory:
    """Return a connection factory that opens a simulated vehicle."""
    return lambda _port: SimulatedVehicle(clock=clock)


def simulated_session(
    clock: Clock = time.monotonic, recorder: SessionRecorder | None = None
) -> Session:
    """Return a session bound to the simulated vehicle instead of hardware."""
    return Session(
        connection=ObdConnection(factory=simulated_factory(clock)),
        detector=lambda: SIMULATED_ADAPTER,
        recorder=recorder,
    )
