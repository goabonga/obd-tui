# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Drive the connection lifecycle the dashboard sits on top of."""

from __future__ import annotations

import logging
from collections.abc import Callable, Collection
from dataclasses import replace

from obd_tui.models.adapter import UNKNOWN, AdapterInfo, ConnectionState
from obd_tui.models.commands import CommandCatalog
from obd_tui.models.history import ReadingHistory
from obd_tui.models.vehicle import VehicleState
from obd_tui.services.connection import ObdConnection
from obd_tui.services.detection import detect_adapter
from obd_tui.services.polling import CODE_FIELDS, LinkLost, SensorPoller
from obd_tui.services.recording import SessionRecorder

logger = logging.getLogger(__name__)

Detector = Callable[[], AdapterInfo | None]


class Session:
    """The application's view of one connection to a vehicle.

    Holds the connection state, the adapter it is bound to, the discovered
    capabilities and the latest readings — everything the UI renders, and
    nothing that knows about the UI.

    Args:
        port: Serial port to use, skipping detection. ``None`` scans for an
            adapter on every connect.
        connection: Link to the vehicle. Injected by tests.
        detector: Adapter scan. Injected by tests.
        recorder: Where to log each sweep, or ``None`` to log nothing.
    """

    def __init__(
        self,
        port: str | None = None,
        connection: ObdConnection | None = None,
        detector: Detector = detect_adapter,
        recorder: SessionRecorder | None = None,
    ) -> None:
        self._connection = connection if connection is not None else ObdConnection()
        self._poller = SensorPoller(self._connection)
        self._detector = detector
        self._recorder = recorder
        self._requested_port = port
        self.state = ConnectionState.DISCONNECTED
        self.adapter: AdapterInfo | None = None
        self.catalog = CommandCatalog()
        self.vehicle = VehicleState()
        self.history = ReadingHistory()

    @property
    def is_connected(self) -> bool:
        """Return whether the session is reading from a vehicle."""
        return self.state.is_live

    @property
    def summary(self) -> str:
        """Return the one-line status shown in the footer."""
        port = self.adapter.port if self.adapter is not None else UNKNOWN
        usb_id = self.adapter.usb_id if self.adapter is not None else f"{UNKNOWN}:{UNKNOWN}"
        return f"{self.state}  |  {port}  |  {usb_id}"

    def connect(self) -> ConnectionState:
        """Find an adapter, open the link and discover its capabilities.

        Returns:
            The resulting state: ``CONNECTED``, ``NO_DEVICE`` when no adapter
            was found, or ``FAILED`` when the port refused to open.
        """
        self.state = ConnectionState.CONNECTING
        adapter = self._resolve_adapter()
        if adapter is None:
            self.state = ConnectionState.NO_DEVICE
            return self.state

        self.adapter = adapter
        if not self._connection.open(adapter.port):
            self.state = ConnectionState.FAILED
            return self.state

        self.catalog = self._connection.discover()
        self.state = ConnectionState.CONNECTED
        return self.state

    def disconnect(self) -> None:
        """Close the link and forget everything read through it."""
        self._connection.close()
        self.state = ConnectionState.DISCONNECTED
        self.adapter = None
        self.catalog = CommandCatalog()
        self.vehicle = VehicleState()
        self.history.clear()
        if self._recorder is not None:
            self._recorder.close()

    def refresh(self, priority: Collection[str] = ()) -> VehicleState:
        """Poll the vehicle once, or return the last readings when offline.

        Args:
            priority: Fields the user is looking at. They are read on every
                sweep, whatever cadence their tier would otherwise impose.
        """
        if not self.is_connected:
            return self.vehicle
        try:
            state = self._poller.poll(self.vehicle, self.catalog, priority)
        except LinkLost:
            logger.warning("vehicle stopped answering; dropping the link")
            self._drop_link()
            return self.vehicle
        # One rebind, not a field-by-field update: the UI thread reads this
        # attribute while the sweep runs, and must never see half a sweep.
        self.vehicle = state
        self.history.record(state)
        if self._recorder is not None:
            self._recorder.record(state)
        return state

    def clear_codes(self) -> bool:
        """Erase the ECU's stored diagnostics and read back what remains.

        Returns:
            ``True`` when the ECU acknowledged. The codes are re-read in the
            same call, so the panel shows what the vehicle actually kept
            rather than an assumed empty list — a fault that is still
            present comes straight back.
        """
        if not self.is_connected:
            return False
        if not self._connection.clear_codes():
            return False
        self.vehicle = replace(self.vehicle, stored_codes=(), pending_codes=())
        self.refresh(priority=CODE_FIELDS)
        return True

    def _drop_link(self) -> None:
        """Give up on a link the vehicle stopped answering.

        The last readings, their history and the discovered catalog are kept
        on purpose: they are what the vehicle was doing when it went quiet,
        which is the interesting part. Reconnecting with ``connect`` starts
        a fresh discovery.
        """
        self._connection.close()
        self.state = ConnectionState.LOST
        if self._recorder is not None:
            self._recorder.close()

    def _resolve_adapter(self) -> AdapterInfo | None:
        """Return the adapter to open: the requested port, or a scan result."""
        found = self._detector()
        if self._requested_port is None:
            return found
        if found is not None and found.port == self._requested_port:
            # The scan recognised that very port, so keep its USB ids.
            return found
        # An explicit port wins even when the scan saw nothing there: the
        # user may be pointing at a Bluetooth node the heuristics skip.
        return AdapterInfo(port=self._requested_port)
