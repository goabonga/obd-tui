# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Everything that talks to the adapter and the vehicle."""

from obd_tui.services.connection import ObdConnection
from obd_tui.services.detection import detect_adapter

__all__ = ["ObdConnection", "detect_adapter"]
