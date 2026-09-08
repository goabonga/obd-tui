# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Suzuki: recognised by its VIN, served engine by engine.

Everything Suzuki-specific lives here and nowhere else. What it has to
say is kept in tables keyed by engine code, so that adding a reading is
one entry with its provenance, and an engine with no entry gets the
standard and no more.
"""

from __future__ import annotations

from collections.abc import Mapping

from obd_tui.models.dpf import DpfRole
from obd_tui.obd.manufacturers.base import ManufacturerProfile
from obd_tui.obd.uds import DataIdentifier

# World manufacturer identifiers, the first three characters of a VIN,
# under which Suzuki cars are built: Japan, Hungary and India.
WMIS: frozenset[str] = frozenset({"JS2", "JS3", "JSA", "TSM", "MA3"})

# The proprietary readings, by engine code. Each entry is a
# DataIdentifier carrying its own provenance, and is sent only to the
# engines it names. None is declared yet: the particulate filter's
# identifiers on the 1.6 DDiS (D16AA, a Bosch EDC17 ECU) have not been
# read on a vehicle or found in a source this project can cite, and a
# guessed identifier would decode to a number that looks like a reading.
# The compatibility page of the documentation tracks what is declared.
ENGINES: Mapping[str, tuple[DataIdentifier, ...]] = {}

# Where each exhaust gas sensor sits relative to the filter, by engine
# code, keyed by (bank, sensor). Again none yet: which of the D16AA's
# sensors is the filter's inlet is for a wiring diagram to say, not a
# guess from the sensor's number.
SENSOR_ROLES: Mapping[str, Mapping[tuple[int, int], DpfRole]] = {}


class SuzukiProfile(ManufacturerProfile):
    """A Suzuki, such as the diesel Vitara this dashboard was first pointed at."""

    name = "Suzuki"

    def supports(self, vin: str) -> bool:
        """Return whether the VIN carries one of Suzuki's identifiers."""
        return vin[:3].upper() in WMIS

    @property
    def identifiers(self) -> tuple[DataIdentifier, ...]:
        """Return the readings declared for this engine, and those alone.

        An identifier is sent only to an engine it names, whatever table
        it was put in: the table is a convenience, the declaration the
        rule.
        """
        if self.engine is None:
            return ()
        return tuple(
            identifier
            for identifier in ENGINES.get(self.engine, ())
            if self.engine in identifier.engines
        )

    def exhaust_sensor_role(self, bank: int, sensor: int) -> DpfRole | None:
        """Return where a sensor sits, if the wiring of this engine is known."""
        if self.engine is None:
            return None
        return SENSOR_ROLES.get(self.engine, {}).get((bank, sensor))
