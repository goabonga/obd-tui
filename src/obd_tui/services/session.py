# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Drive the connection lifecycle the dashboard sits on top of."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Collection
from dataclasses import replace

from obd_tui.models.adapter import UNKNOWN, AdapterInfo, ConnectionState
from obd_tui.models.commands import CommandCatalog
from obd_tui.models.history import ReadingHistory
from obd_tui.models.vehicle import VehicleState
from obd_tui.obd.manufacturers import GenericProfile, ManufacturerProfile
from obd_tui.services.connection import ObdConnection
from obd_tui.services.detection import detect_adapter
from obd_tui.services.diesel_monitoring import Clock, DieselMonitor
from obd_tui.services.polling import CODE_FIELDS, LinkLost, SensorPoller
from obd_tui.services.recording import SessionRecorder

logger = logging.getLogger(__name__)

Detector = Callable[[], AdapterInfo | None]


class Session:
    """The application's view of one connection to a vehicle.

    Holds the connection state, the adapter it is bound to, the discovered
    capabilities and the latest readings — everything the UI renders, and
    nothing that knows about the UI.

    Attributes:
        held: ``True`` once the user hung up on purpose. It answers whether
            a down link should be brought back, which the state alone
            cannot: ``DISCONNECTED`` is also where a session starts.

    Args:
        port: Serial port to use, skipping detection. ``None`` scans for an
            adapter on every connect.
        connection: Link to the vehicle. Injected by tests.
        detector: Adapter scan. Injected by tests.
        recorder: Where to log each sweep, or ``None`` to log nothing.
        clock: Source of the time the aftertreatment is watched by.
            Injected by tests and the demo.
        engine: The engine code the user declared, handed to discovery so
            the manufacturer profile knows which readings it may answer.
    """

    def __init__(
        self,
        port: str | None = None,
        connection: ObdConnection | None = None,
        detector: Detector = detect_adapter,
        recorder: SessionRecorder | None = None,
        clock: Clock = time.monotonic,
        engine: str | None = None,
    ) -> None:
        self._connection = connection if connection is not None else ObdConnection()
        self._poller = SensorPoller(self._connection)
        self._detector = detector
        self._recorder = recorder
        self._monitor = DieselMonitor(clock)
        self._requested_port = port
        self._engine = engine
        self.state = ConnectionState.DISCONNECTED
        self.held = False
        self.adapter: AdapterInfo | None = None
        self.catalog = CommandCatalog()
        self.vehicle = VehicleState()
        self.history = ReadingHistory()
        # What discovery recognised the vehicle as, for the readings only
        # its manufacturer can make sense of.
        self.profile: ManufacturerProfile = GenericProfile()
        self.vin: str | None = None

    @property
    def is_connected(self) -> bool:
        """Return whether the session is reading from a vehicle."""
        return self.state.is_live

    @property
    def wants_link(self) -> bool:
        """Return whether the link is down and nobody asked for that.

        This is the question a reconnect policy has to ask: a lost link, a
        failed open or an adapter that was never found are all worth
        another try, while a link the user hung up on is not.
        """
        return not self.is_connected and not self.held

    @property
    def engine(self) -> str | None:
        """Return the engine code declared for this vehicle, if any."""
        return self._engine

    @property
    def vehicle_label(self) -> str:
        """Return the make and engine as known, or nothing for a generic vehicle."""
        parts = [] if isinstance(self.profile, GenericProfile) else [self.profile.name]
        if self._engine is not None:
            parts.append(self._engine)
        return " ".join(parts)

    @property
    def summary(self) -> str:
        """Return the one-line status shown in the footer."""
        port = self.adapter.port if self.adapter is not None else UNKNOWN
        usb_id = self.adapter.usb_id if self.adapter is not None else f"{UNKNOWN}:{UNKNOWN}"
        summary = f"{self.state}  |  {port}  |  {usb_id}"
        label = self.vehicle_label
        return f"{summary}  |  {label}" if label else summary

    def set_engine(self, engine: str | None) -> None:
        """Declare the engine, or ``None`` for the standard readings alone.

        Takes effect at once on a live link: the capabilities are settled
        again with the profile bound to the new engine, so a manufacturer
        table applies, or stops applying, without reconnecting. Off the
        link it waits for the next connect.
        """
        self._engine = engine
        if self.is_connected:
            self.catalog = self._connection.discover(engine=engine)
            self.profile = self._connection.profile

    def connect(self, *, retry: bool = False) -> ConnectionState:
        """Find an adapter, open the link and discover its capabilities.

        Asking to connect lifts the hold a ``disconnect`` put on the session,
        whether or not the attempt succeeds: the user wants a link again.
        A retry is different: it never lifts the hold, and does nothing
        while one is on. One can be in flight on a worker when the user
        hangs up, and must not undo that on landing.

        Args:
            retry: Whether this attempt comes from the reconnect timer
                rather than from the user.

        Returns:
            The resulting state: ``CONNECTED``, ``NO_DEVICE`` when no adapter
            was found, or ``FAILED`` when the port refused to open.
        """
        if retry and self.held:
            return self.state
        self.held = False
        self.state = ConnectionState.CONNECTING
        adapter = self._resolve_adapter()
        if adapter is None:
            self.state = ConnectionState.NO_DEVICE
            return self.state

        self.adapter = adapter
        if not self._connection.open(adapter.port):
            self.state = ConnectionState.FAILED
            return self.state

        self.catalog = self._connection.discover(engine=self._engine)
        self.profile = self._connection.profile
        self.vin = self._connection.vin
        self.state = ConnectionState.CONNECTED
        return self.state

    def disconnect(self) -> None:
        """Close the link and forget everything read through it.

        The session is then held: the link stays down until ``connect`` is
        called again, however it went down before. A link that drops on
        its own (see ``_drop_link``) is not held.
        """
        self._connection.close()
        self.state = ConnectionState.DISCONNECTED
        self.held = True
        self.adapter = None
        self.catalog = CommandCatalog()
        self.vehicle = VehicleState()
        self.history.clear()
        self.profile = GenericProfile()
        self.vin = None
        self._monitor.reset()
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
        state = self._monitor.observe(state, self.profile)
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
