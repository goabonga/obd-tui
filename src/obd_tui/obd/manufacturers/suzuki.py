# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Suzuki: recognised by its VIN, answering nothing beyond the standard yet."""

from __future__ import annotations

from obd_tui.obd.manufacturers.base import ManufacturerProfile

# World manufacturer identifiers, the first three characters of a VIN,
# under which Suzuki cars are built: Japan, Hungary and India.
WMIS: frozenset[str] = frozenset({"JS2", "JS3", "JSA", "TSM", "MA3"})


class SuzukiProfile(ManufacturerProfile):
    """A Suzuki, such as the diesel Vitara this dashboard was first pointed at.

    Recognising the make is what this profile does so far. The commands
    it will answer with - the particulate filter's own PIDs, which Suzuki
    does not expose through the standard - land with them, so that a
    manufacturer's name lives here and nowhere else.
    """

    name = "Suzuki"

    def supports(self, vin: str) -> bool:
        """Return whether the VIN carries one of Suzuki's identifiers."""
        return vin[:3].upper() in WMIS
