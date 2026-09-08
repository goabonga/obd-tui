# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Plain data models shared by the services and the views."""

from obd_tui.models.adapter import AdapterInfo, ConnectionState
from obd_tui.models.commands import CommandCatalog, CommandInfo
from obd_tui.models.dpf import DpfLoad, DpfPressure, DpfRole, DpfTemperatures, TemperatureSource
from obd_tui.models.exhaust import ExhaustTemperatures
from obd_tui.models.history import History, ReadingHistory
from obd_tui.models.vehicle import TroubleCode, VehicleState

__all__ = [
    "AdapterInfo",
    "CommandCatalog",
    "CommandInfo",
    "ConnectionState",
    "DpfLoad",
    "DpfPressure",
    "DpfRole",
    "DpfTemperatures",
    "ExhaustTemperatures",
    "History",
    "ReadingHistory",
    "TemperatureSource",
    "TroubleCode",
    "VehicleState",
]
