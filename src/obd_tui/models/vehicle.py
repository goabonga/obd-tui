# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Snapshot of the readings collected from the vehicle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TroubleCode:
    """A diagnostic trouble code and its description."""

    code: str
    description: str = ""


@dataclass(frozen=True, slots=True)
class VehicleState:
    """Latest value of every sensor the dashboard knows how to display.

    Every field defaults to ``None``: a ``None`` means the vehicle does not
    support the command, or it has not been polled yet. Panels skip those
    rows entirely rather than printing a placeholder, so a dashboard only
    ever shows readings the ECU really produced.

    A state is an immutable snapshot of one sweep. A sweep runs on a worker
    thread while the UI renders on another, and replacing one whole value
    is atomic where filling a shared object field by field is not: without
    this, a panel could be drawn from a half-updated sweep.
    """

    # Engine
    rpm: float | None = None
    engine_load: float | None = None
    absolute_load: float | None = None
    timing_advance: float | None = None
    run_time: float | None = None
    mass_air_flow: float | None = None
    module_voltage: float | None = None
    speed: float | None = None

    # Temperatures
    coolant_temp: float | None = None
    oil_temp: float | None = None
    intake_temp: float | None = None
    ambient_temp: float | None = None

    # Fuel
    fuel_rail_pressure: float | None = None
    fuel_rate: float | None = None
    fuel_level: float | None = None
    fuel_inject_timing: float | None = None
    equivalence_ratio: float | None = None
    short_fuel_trim: float | None = None
    long_fuel_trim: float | None = None

    # Air path
    intake_pressure: float | None = None
    barometric_pressure: float | None = None
    throttle: float | None = None
    throttle_b: float | None = None
    throttle_actuator: float | None = None
    accel_pedal_d: float | None = None
    accel_pedal_e: float | None = None
    relative_accel: float | None = None

    # Oxygen sensors
    o2_sensors: Any | None = None
    o2_s1_lambda: float | None = None
    o2_s2_lambda: float | None = None

    # Exhaust gas recirculation
    egr_commanded: float | None = None
    egr_error: float | None = None

    # Diagnostics
    status: Any | None = None
    obd_compliance: Any | None = None
    fuel_type: Any | None = None
    fuel_status: Any | None = None
    distance_with_mil: float | None = None
    run_time_with_mil: float | None = None
    warmups_since_clear: float | None = None
    distance_since_clear: float | None = None
    time_since_clear: float | None = None
    calibration_id: Any | None = None
    cvn: Any | None = None

    # Trouble codes
    stored_codes: tuple[TroubleCode, ...] = ()
    pending_codes: tuple[TroubleCode, ...] = ()

    @property
    def net_boost(self) -> float | None:
        """Return manifold pressure above ambient, or ``None`` if unknown.

        Derived rather than stored: an ECU reports absolute intake pressure,
        so boost only means something once the barometric reading is known.
        """
        if self.intake_pressure is None or self.barometric_pressure is None:
            return None
        return self.intake_pressure - self.barometric_pressure

    @property
    def mil_on(self) -> bool | None:
        """Return whether the malfunction indicator lamp is lit."""
        return _attr(self.status, "MIL")

    @property
    def code_count(self) -> int | None:
        """Return the number of codes the ECU reports as stored."""
        return _attr(self.status, "DTC_count")

    @property
    def ignition_type(self) -> str | None:
        """Return the ignition type reported alongside the MIL status."""
        return _attr(self.status, "ignition_type")


def _attr(source: Any | None, name: str) -> Any | None:
    """Return ``source.name`` when available, ``None`` otherwise.

    python-obd hands back library-specific response objects whose shape
    varies with the adapter and the protocol; reading them defensively keeps
    a partial answer from breaking the whole dashboard.
    """
    if source is None:
        return None
    return getattr(source, name, None)
