# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Find the serial port an OBD-II adapter is plugged into."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

from serial.tools import list_ports

from obd_tui.models.adapter import AdapterInfo

# USB vendor/product pairs of adapters known to be OBD-II interfaces. The
# FTDI 0403:6015 pair covers the vLinker family, which advertises a generic
# FTDI descriptor and would otherwise be indistinguishable from any other
# serial bridge.
KNOWN_USB_IDS: frozenset[tuple[str, str]] = frozenset({("0403", "6015")})

# Substrings that identify an adapter by its USB descriptor strings, for the
# many clones that do not share a single vendor id.
KNOWN_KEYWORDS: tuple[str, ...] = (
    "obd",
    "elm327",
    "obdlink",
    "stn11",
    "vlinker",
    "vgate",
)


class SerialPort(Protocol):
    """The part of ``serial.tools.list_ports_common.ListPortInfo`` we read."""

    device: str
    vid: int | None
    pid: int | None
    product: str | None
    manufacturer: str | None
    description: str | None


def detect_adapter(ports: Iterable[SerialPort] | None = None) -> AdapterInfo | None:
    """Return the first serial port that looks like an OBD-II adapter.

    Args:
        ports: Ports to consider. Defaults to every port the system reports,
            which is what the application uses; tests pass their own.

    Returns:
        The matching adapter, or ``None`` when no port looks like one.
    """
    # pyserial's own ListPortInfo satisfies SerialPort structurally, but its
    # stubs declare the attributes mutably, which a Protocol cannot accept.
    candidates: Iterable[Any] = list_ports.comports() if ports is None else ports
    for port in candidates:
        if _is_adapter(port):
            return _describe(port)
    return None


def _is_adapter(port: SerialPort) -> bool:
    """Return whether ``port`` matches a known adapter id or descriptor."""
    usb_id = _usb_id(port)
    if usb_id is not None and usb_id in KNOWN_USB_IDS:
        return True
    descriptor = " ".join(
        text for text in (port.product, port.manufacturer, port.description) if text
    ).lower()
    return any(keyword in descriptor for keyword in KNOWN_KEYWORDS)


def _usb_id(port: SerialPort) -> tuple[str, str] | None:
    """Return the ``(vid, pid)`` hex pair of ``port``, if it exposes one."""
    if port.vid is None or port.pid is None:
        return None
    return f"{port.vid:04x}", f"{port.pid:04x}"


def _describe(port: SerialPort) -> AdapterInfo:
    """Build the :class:`AdapterInfo` describing ``port``."""
    usb_id = _usb_id(port)
    vid, pid = usb_id if usb_id is not None else (None, None)
    return AdapterInfo(port=port.device, vid=vid, pid=pid, label=port.product or port.description)
