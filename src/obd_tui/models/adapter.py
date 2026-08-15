# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Description of an OBD-II adapter and of the link to it."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

UNKNOWN = "-"


@dataclass(frozen=True, slots=True)
class AdapterInfo:
    """A serial port that looks like an OBD-II adapter.

    Attributes:
        port: Device path of the serial port, e.g. ``/dev/ttyUSB0``.
        vid: USB vendor id as a four-digit hex string, or ``None`` for a
            non-USB port (a Bluetooth RFCOMM node has no VID/PID).
        pid: USB product id as a four-digit hex string, or ``None``.
        label: Human-readable product or manufacturer string, if the port
            exposes one.
    """

    port: str
    vid: str | None = None
    pid: str | None = None
    label: str | None = None

    @property
    def usb_id(self) -> str:
        """Return ``vid:pid`` for display, using ``-`` for missing halves."""
        return f"{self.vid or UNKNOWN}:{self.pid or UNKNOWN}"


class ConnectionState(Enum):
    """Where the session currently stands with the adapter.

    ``LOST`` is its own state rather than a plain disconnect: the readings
    on screen are still the last ones the vehicle gave, and the status bar
    should say why they stopped moving.
    """

    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    NO_DEVICE = "NO DEVICE"
    FAILED = "FAILED"
    LOST = "LINK LOST"

    def __str__(self) -> str:
        """Return the label shown in the footer."""
        return self.value

    @property
    def is_live(self) -> bool:
        """Return whether the session can currently read from the vehicle."""
        return self is ConnectionState.CONNECTED
