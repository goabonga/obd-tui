# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Proprietary readings, declared with everything needed to doubt them.

A manufacturer exposes what the standard does not through UDS service
0x22, ReadDataByIdentifier: a two-byte identifier, a reply of a few bytes,
and a formula nobody published. Each one used here is declared as a
:class:`DataIdentifier` that says which ECU and engines it was seen on,
how sure anyone is of it, and where that came from - so a reader can
check it, and so an unknown engine is never sent a decoder that might be
wrong for it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

import obd
from obd.protocols import ECU

# Service 0x22 and its positive response: the reply starts with the
# service byte plus 0x40, then echoes the identifier.
READ_DATA_BY_IDENTIFIER = 0x22
POSITIVE_RESPONSE = READ_DATA_BY_IDENTIFIER + 0x40
RESPONSE_HEADER_LENGTH = 3


class Confidence(Enum):
    """How far a proprietary identifier can be trusted."""

    VALIDATED = "validated"
    """Read on a vehicle and checked against a workshop tool."""

    EXPERIMENTAL = "experimental"
    """Documented somewhere, not yet checked on a vehicle by this project."""

    REVERSE_ENGINEERED = "reverse-engineered"
    """Worked out from traffic, with the formula guessed to fit."""


Decoder = Callable[[bytes], Any | None]


@dataclass(frozen=True, slots=True)
class DataIdentifier:
    """One proprietary reading, and its provenance.

    Attributes:
        capability: What the dashboard asks for, e.g. ``DPF_SOOT_LOAD``.
        identifier: The two-byte data identifier sent after service 0x22.
        length: Data bytes expected after the three-byte response header.
            A reply of any other length is refused.
        decoder: Turns exactly ``length`` data bytes into the value the
            capability stores, or ``None`` when they cannot be believed.
        unit: The unit of the decoded value, for the reader.
        formula: The decoding, spelt out for the reader.
        ecu: Which control unit answers it.
        engines: The engine codes it was seen on. It is sent to no other.
        confidence: How far to trust it.
        source: Where the identifier and the formula come from.
        endianness: Byte order of multi-byte fields, for the reader.
    """

    capability: str
    identifier: int
    length: int
    decoder: Decoder
    unit: str
    formula: str
    ecu: str
    engines: frozenset[str]
    confidence: Confidence
    source: str
    endianness: str = "big"

    @property
    def name(self) -> str:
        """Return the name the command goes by: the capability, the identifier."""
        return f"{self.capability}@{self.identifier:04X}"

    def command(self) -> obd.OBDCommand:
        """Return the python-obd command that sends this identifier.

        The command expects no fixed size: python-obd would pad or trim
        the reply to fit, and a reply of the wrong length must be refused
        rather than made to fit.
        """
        return obd.OBDCommand(
            self.name,
            f"{self.capability} ({self.confidence.value}, {self.source})",
            b"%02X%04X" % (READ_DATA_BY_IDENTIFIER, self.identifier),
            0,
            self.decode,
            ECU.ENGINE,
            True,
        )

    def decode(self, messages: list[Any]) -> Any | None:
        """Decode the reply frames, refusing anything unexpected.

        ``None`` - which the dashboard reads as "no answer" - for a
        negative response, a reply to another identifier, or a payload of
        the wrong length. A proprietary formula applied to the wrong bytes
        gives a number that looks like a reading, and that is worse than
        nothing.
        """
        if not messages:
            return None
        data = bytes(messages[0].data)
        header = bytes([POSITIVE_RESPONSE, self.identifier >> 8, self.identifier & 0xFF])
        if data[:RESPONSE_HEADER_LENGTH] != header:
            return None
        payload = data[RESPONSE_HEADER_LENGTH:]
        if len(payload) != self.length:
            return None
        return self.decoder(payload)


def scaled(scale: float, offset: float = 0.0, signed: bool = False) -> Decoder:
    """Return a decoder reading one big-endian integer as ``raw * scale + offset``."""

    def decode(payload: bytes) -> float:
        return int.from_bytes(payload, "big", signed=signed) * scale + offset

    return decode
