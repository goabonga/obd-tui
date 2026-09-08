# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""OBD-II commands python-obd does not define.

python-obd's mode 01 table stops at PID 0x5F. The exhaust gas temperature
PIDs live past it, so they are declared here in the library's own terms:
an :class:`obd.OBDCommand` with a decoder that turns the reply frames
into what the dashboard stores.

The library also has no idea which of these PIDs the vehicle supports,
since its capability scan stops with the table. PID 0x60 is the bitmap
that says, and is declared here for the same reason.
"""

from __future__ import annotations

from typing import Any

import obd
from obd.protocols import ECU

from obd_tui.models.exhaust import ExhaustTemperatures

# The supported-PID bitmaps come every 0x20 PIDs; this one covers 0x61 to
# 0x80. Bit 31 of the 32 answers for the first PID after it, bit 0 for the
# last.
PIDS_D_BASE = 0x60
BITMAP_BITS = 32

# Mode 01, PID 0x78: exhaust gas temperature bank 1.
BANK = 1
EGT_BANK_1_PID = 0x78

# Mode and PID bytes lead every mode 01 reply; the decoders skip them.
HEADER_LENGTH = 2


def _payload(messages: list[Any]) -> bytes:
    """Return the data bytes of the first reply, after the mode and PID."""
    return bytes(messages[0].data[HEADER_LENGTH:])


def decode_exhaust_temperatures(messages: list[Any]) -> ExhaustTemperatures | None:
    """Decode PID 0x78 into the temperatures of one bank."""
    return ExhaustTemperatures.from_frame(BANK, _payload(messages))


def decode_supported_pids(messages: list[Any]) -> frozenset[int]:
    """Decode a supported-PID bitmap into the PID numbers it names.

    A reply shorter than the four bytes of the bitmap names nothing: the
    missing bits cannot be told from cleared ones.
    """
    data = _payload(messages)
    if len(data) < BITMAP_BITS // 8:
        return frozenset()
    bits = int.from_bytes(data[: BITMAP_BITS // 8], "big")
    return frozenset(
        PIDS_D_BASE + offset
        for offset in range(1, BITMAP_BITS + 1)
        if bits & (1 << (BITMAP_BITS - offset))
    )


PIDS_D = obd.OBDCommand(
    "PIDS_D",
    "Supported PIDs [61-80]",
    b"0160",
    HEADER_LENGTH + BITMAP_BITS // 8,
    decode_supported_pids,
    ECU.ENGINE,
    True,
)

EGT_BANK_1 = obd.OBDCommand(
    "EGT_BANK_1",
    "Exhaust gas temperature bank 1",
    b"0178",
    HEADER_LENGTH + 9,
    decode_exhaust_temperatures,
    ECU.ENGINE,
    True,
)

# Every command declared here, by the name the rest of the dashboard uses.
# The bitmap is not a reading: it is what discovery asks to learn which of
# the others the vehicle answers.
CUSTOM_COMMANDS: dict[str, obd.OBDCommand] = {
    PIDS_D.name: PIDS_D,
    EGT_BANK_1.name: EGT_BANK_1,
}

# The commands discovery can vouch for, with the PID whose bit says so.
CUSTOM_PIDS: dict[str, int] = {EGT_BANK_1.name: EGT_BANK_1_PID}
