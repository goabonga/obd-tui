# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Talk to the vehicle through python-obd."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from threading import RLock
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

# Mode 04: erase stored codes, freeze frame data and readiness monitors.
CLEAR_COMMAND = "CLEAR_DTC"

ConnectionFactory = Callable[[str], Any]


def _open_serial(port: str) -> Any:  # pragma: no cover - needs real hardware
    """Open a python-obd connection on ``port`` with PID probing enabled."""
    return obd.OBD(port, fast=False)


class AdapterError(RuntimeError):
    """The adapter could not be talked to.

    Distinct from a vehicle that answers "no data": that is an answer, and
    a routine one. This means the question never got through.
    """


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
        self._liveness: bool | None = None
        # One conversation at a time. The UI runs adapter work on threads
        # and cancelling one only marks its task cancelled — the thread
        # keeps its blocking read to the end. Without this, clearing the
        # codes could write mode 04 into the middle of a sweep's exchange
        # and leave both talking over each other on one serial line.
        # Re-entrant because a sweep holds it while its queries take it.
        self._talking = RLock()

    @property
    def is_open(self) -> bool:
        """Return whether the vehicle link is up.

        Inside a :meth:`sweep` the answer is the one taken when the sweep
        started: a sweep asks the adapter dozens of questions, and the state
        of the link is not worth re-establishing before every one of them.
        """
        if self._liveness is not None:
            return self._liveness
        if self._connection is None:
            return False
        try:
            return bool(self._connection.is_connected())
        except Exception:
            logger.debug("adapter failed to report its connection state", exc_info=True)
            return False

    @contextmanager
    def sweep(self) -> Iterator[None]:
        """Hold the adapter, and its liveness, for the duration of a sweep."""
        with self._talking:
            self._liveness = self.is_open
            try:
                yield
            finally:
                self._liveness = None

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
        # Drop the memo too: a sweep that closes the link must not keep
        # reading through the answer it cached before doing so.
        self._liveness = None

    def query(self, name: str) -> Any | None:
        """Read one command by python-obd name.

        Returns:
            The decoded value, or ``None`` when the vehicle had nothing to
            say — an empty response is an answer, not a failure. A command
            python-obd does not define reads the same way.

        Raises:
            AdapterError: The question never reached the vehicle: the link
                is down, or the adapter raised. Only this means something
                is wrong with the connection itself.
        """
        with self._talking:
            if self._connection is None or not self.is_open:
                raise AdapterError(f"the link is down, cannot read {name}")
            command = getattr(obd.commands, name, None)
            if command is None:
                return None
            try:
                response = self._connection.query(command)
            except Exception as error:
                logger.debug("query %s failed", name, exc_info=True)
                raise AdapterError(f"the adapter failed on {name}") from error
            if response is None or response.is_null():
                return None
            return response.value

    def clear_codes(self) -> bool:
        """Send mode 04, erasing the ECU's stored diagnostics.

        Returns:
            ``True`` when the ECU acknowledged. Mode 04 carries no data
            back, so python-obd decodes it to an empty value and
            ``is_null()`` is true even on success — the acknowledgement is
            the presence of a reply message, not its content.
        """
        with self._talking:
            if self._connection is None or not self.is_open:
                return False
            command = getattr(obd.commands, CLEAR_COMMAND, None)
            if command is None:  # pragma: no cover - python-obd always defines it
                return False
            try:
                response = self._connection.query(command)
            except Exception:
                logger.warning("clearing the trouble codes failed", exc_info=True)
                return False
            return response is not None and bool(getattr(response, "messages", None))

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
