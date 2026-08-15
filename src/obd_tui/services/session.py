# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Drive the connection lifecycle the dashboard sits on top of."""

from __future__ import annotations

from collections.abc import Callable

from obd_tui.models.adapter import UNKNOWN, AdapterInfo, ConnectionState
from obd_tui.models.commands import CommandCatalog
from obd_tui.models.history import ReadingHistory
from obd_tui.models.vehicle import VehicleState
from obd_tui.services.connection import ObdConnection
from obd_tui.services.detection import detect_adapter
from obd_tui.services.polling import SensorPoller

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
    """

    def __init__(
        self,
        port: str | None = None,
        connection: ObdConnection | None = None,
        detector: Detector = detect_adapter,
    ) -> None:
        self._connection = connection if connection is not None else ObdConnection()
        self._poller = SensorPoller(self._connection)
        self._detector = detector
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

    def refresh(self) -> VehicleState:
        """Poll the vehicle once, or return the last readings when offline."""
        if not self.is_connected:
            return self.vehicle
        state = self._poller.poll(self.vehicle, self.catalog)
        self.history.record(state)
        return state

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
