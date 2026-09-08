# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Turn a capability into the command that fetches it, for one vehicle.

The order is the standard's first: a SAE/ISO PID the vehicle vouches for
in its supported-PID bitmap always wins. Only when the standard has no
answer is the vehicle's manufacturer profile asked. A capability neither
can answer is simply not available on this vehicle.
"""

from __future__ import annotations

from collections.abc import Collection

import obd

from obd_tui.obd.manufacturers.base import ManufacturerProfile
from obd_tui.obd.standard import STANDARD_COMMANDS, STANDARD_PIDS

# Capabilities the standard has no PID for. Only a manufacturer profile
# answers them, so they are listed for a vehicle only when its profile does.
MANUFACTURER_ONLY: frozenset[str] = frozenset({"DPF_TEMP_INTERNAL", "DPF_SOOT_LOAD"})

# Every capability the dashboard knows how to store and show, whether or
# not any given vehicle answers it.
KNOWN_CAPABILITIES: frozenset[str] = frozenset(STANDARD_COMMANDS) | MANUFACTURER_ONLY


def capabilities(profile: ManufacturerProfile) -> frozenset[str]:
    """Return every capability worth asking about on a vehicle of ``profile``."""
    return frozenset(STANDARD_COMMANDS) | profile.capabilities


def resolve(
    capability: str, supported_pids: Collection[int], profile: ManufacturerProfile
) -> obd.OBDCommand | None:
    """Return the command fetching ``capability``, or ``None`` if none does.

    Args:
        capability: What the dashboard wants to know, e.g. ``EGT_BANK_1``.
        supported_pids: The PIDs the vehicle named in its bitmap. A
            standard command is only used when its PID is among them.
        profile: The vehicle's manufacturer, asked when the standard has
            nothing the vehicle supports.
    """
    standard = STANDARD_COMMANDS.get(capability)
    if standard is not None and STANDARD_PIDS[capability] in supported_pids:
        return standard
    return profile.command(capability)
