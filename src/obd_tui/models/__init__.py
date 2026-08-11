# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Plain data models shared by the services and the views."""

from obd_tui.models.adapter import AdapterInfo, ConnectionState
from obd_tui.models.commands import CommandCatalog, CommandInfo
from obd_tui.models.vehicle import TroubleCode, VehicleState

__all__ = [
    "AdapterInfo",
    "CommandCatalog",
    "CommandInfo",
    "ConnectionState",
    "TroubleCode",
    "VehicleState",
]
