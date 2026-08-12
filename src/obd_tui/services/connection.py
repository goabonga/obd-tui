# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Talk to the vehicle through python-obd."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import obd

from obd_tui.models.commands import NO_PID, CommandCatalog, CommandInfo

logger = logging.getLogger(__name__)

# Mode numbers python-obd knows about, with the label used as a section
# heading in the PID catalogue panel.
MODE_LABELS: dict[int, str] = {
    1: "Mode 01 — Live data",
    2: "Mode 02 — Freeze frame",
    3: "Mode 03 — Stored DTCs",
    4: "Mode 04 — Clear DTCs",
    6: "Mode 06 — Test results",
    7: "Mode 07 — Pending DTCs",
    9: "Mode 09 — Vehicle info",
}

# Commands answered by the adapter itself rather than by the ECU.
ADAPTER_LABEL = "ELM — Adapter"
ADAPTER_COMMANDS: tuple[str, ...] = ("ELM_VERSION", "ELM_VOLTAGE")

ConnectionFactory = Callable[[str], Any]


def _open_serial(port: str) -> Any:  # pragma: no cover - needs real hardware
    """Open a python-obd connection on ``port`` with PID probing enabled."""
    return obd.OBD(port, fast=False)


class ObdConnection:
    """A single connection to the vehicle, opened on demand.

    python-obd raises freely — a missing port, a chatty clone adapter, a
    protocol it fails to negotiate — and none of that should take the
    dashboard down, so every call here degrades to "no answer" instead.

    Args:
        factory: Builds the underlying python-obd connection for a port.
            Injected so tests never touch a serial device.
    """

    def __init__(self, factory: ConnectionFactory = _open_serial) -> None:
        self._factory = factory
        self._connection: Any | None = None

    @property
    def is_open(self) -> bool:
        """Return whether the vehicle link is up."""
        if self._connection is None:
            return False
        try:
            return bool(self._connection.is_connected())
        except Exception:
            logger.debug("adapter failed to report its connection state", exc_info=True)
            return False

    def open(self, port: str) -> bool:
        """Connect to the adapter on ``port``.

        Returns:
            ``True`` once the vehicle answers, ``False`` if the port cannot
            be opened or the adapter never reaches a connected state.
        """
        try:
            self._connection = self._factory(port)
        except Exception:
            logger.warning("could not open OBD connection on %s", port, exc_info=True)
            self._connection = None
            return False
        if not self.is_open:
            self.close()
            return False
        return True

    def close(self) -> None:
        """Drop the connection, ignoring an adapter that fails to hang up."""
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception:
                logger.debug("adapter raised while closing", exc_info=True)
        self._connection = None

    def query(self, name: str) -> Any | None:
        """Read one command by python-obd name.

        Returns:
            The decoded value, or ``None`` when the link is down, the command
            is unknown, or the vehicle returned an empty response.
        """
        if self._connection is None or not self.is_open:
            return None
        command = getattr(obd.commands, name, None)
        if command is None:
            return None
        try:
            response = self._connection.query(command)
        except Exception:
            logger.debug("query %s failed", name, exc_info=True)
            return None
        if response is None or response.is_null():
            return None
        return response.value

    def discover(self) -> CommandCatalog:
        """List every known command and whether the vehicle supports it."""
        if self._connection is None or not self.is_open:
            return CommandCatalog()

        supported = _supported_names(self._connection)
        modes: dict[str, list[CommandInfo]] = {}

        for mode, label in MODE_LABELS.items():
            commands = [
                _describe(command, supported)
                for command in obd.commands.modes[mode]
                if command is not None
            ]
            if commands:
                modes[label] = commands

        adapter = [
            _describe(command, supported)
            for command in (getattr(obd.commands, name, None) for name in ADAPTER_COMMANDS)
            if command is not None
        ]
        if adapter:
            modes[ADAPTER_LABEL] = adapter

        return CommandCatalog(modes=modes)


def _supported_names(connection: Any) -> frozenset[str]:
    """Return the command names ``connection`` reported as supported."""
    try:
        return frozenset(str(command.name) for command in connection.supported_commands)
    except Exception:
        logger.debug("adapter did not report its supported commands", exc_info=True)
        return frozenset()


def _describe(command: Any, supported: frozenset[str]) -> CommandInfo:
    """Turn a python-obd command object into a :class:`CommandInfo`."""
    pid = getattr(command, "pid", None)
    name = str(command.name)
    return CommandInfo(
        name=name,
        pid=f"0x{pid:02X}" if isinstance(pid, int) else NO_PID,
        description=str(getattr(command, "desc", "")),
        supported=name in supported,
    )
