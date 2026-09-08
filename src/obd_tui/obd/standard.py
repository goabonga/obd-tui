# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""SAE/ISO mode 01 commands past the end of python-obd's table.

python-obd stops at PID 0x5F. The exhaust gas temperature and particulate
filter PIDs live past it, so they are declared here in the library's own terms: an
:class:`obd.OBDCommand` with a decoder that turns the reply frames into
what the dashboard stores.

The library also has no idea which of these PIDs the vehicle supports,
since its capability scan stops with its table. PIDs 0x60 and 0x80 are
the bitmaps that say, one per block of 32, and are declared here for the
same reason.
"""

from __future__ import annotations

from functools import partial
from typing import Any

import obd
from obd.protocols import ECU

from obd_tui.models.dpf import (
    PRESSURE_FRAME_LENGTH,
    TEMPERATURE_FRAME_LENGTH,
    DpfPressure,
    DpfTemperatures,
)
from obd_tui.models.exhaust import FRAME_LENGTH, ExhaustTemperatures

# The supported-PID bitmaps come every 0x20 PIDs, each covering the 32
# after it: bit 31 answers for the first PID past the bitmap, bit 0 for
# the last. python-obd reads the first three; these are the next two.
PIDS_D_BASE = 0x60
PIDS_E_BASE = 0x80
BITMAP_BITS = 32

# Mode and PID bytes lead every mode 01 reply; the decoders skip them.
HEADER_LENGTH = 2

# One PID per bank of exhaust gas temperature sensors.
EGT_PIDS: dict[int, int] = {1: 0x78, 2: 0x79}

# Mode 01 PID 0x7A: the pressures across the particulate filter, bank 1.
DPF_PRESSURE_PID = 0x7A

# Mode 01 PID 0x7C: the temperatures at the particulate filter, bank 1.
DPF_TEMPERATURE_PID = 0x7C


def _payload(messages: list[Any]) -> bytes:
    """Return the data bytes of the first reply, after the mode and PID."""
    return bytes(messages[0].data[HEADER_LENGTH:])


def decode_exhaust_temperatures(bank: int, messages: list[Any]) -> ExhaustTemperatures | None:
    """Decode a bank's PID into the temperatures of its sensors."""
    return ExhaustTemperatures.from_frame(bank, _payload(messages))


def decode_dpf_pressure(messages: list[Any]) -> DpfPressure | None:
    """Decode PID 0x7A into the pressures across the particulate filter."""
    return DpfPressure.from_frame(_payload(messages))


def decode_dpf_temperatures(messages: list[Any]) -> DpfTemperatures | None:
    """Decode PID 0x7C into the temperatures at the particulate filter."""
    return DpfTemperatures.from_frame(_payload(messages))


def decode_supported_pids(base: int, messages: list[Any]) -> frozenset[int]:
    """Decode a supported-PID bitmap into the PID numbers it names.

    Args:
        base: The bitmap's own PID; it answers for the 32 after it.
        messages: The reply frames.

    A reply shorter than the four bytes of the bitmap names nothing: the
    missing bits cannot be told from cleared ones.
    """
    data = _payload(messages)
    if len(data) < BITMAP_BITS // 8:
        return frozenset()
    bits = int.from_bytes(data[: BITMAP_BITS // 8], "big")
    return frozenset(
        base + offset
        for offset in range(1, BITMAP_BITS + 1)
        if bits & (1 << (BITMAP_BITS - offset))
    )


def _mode_01(name: str, description: str, pid: int, length: int, decoder: Any) -> obd.OBDCommand:
    """Declare a mode 01 command the way python-obd's own table does."""
    return obd.OBDCommand(
        name, description, b"01%02X" % pid, HEADER_LENGTH + length, decoder, ECU.ENGINE, True
    )


def _bitmap(name: str, base: int) -> obd.OBDCommand:
    """Declare the supported-PID bitmap at ``base``."""
    description = f"Supported PIDs [{base + 1:02X}-{base + BITMAP_BITS:02X}]"
    return _mode_01(name, description, base, BITMAP_BITS // 8, partial(decode_supported_pids, base))


PIDS_D = _bitmap("PIDS_D", PIDS_D_BASE)
PIDS_E = _bitmap("PIDS_E", PIDS_E_BASE)

# What discovery asks to learn which of the capabilities the vehicle
# answers, by name. Not capabilities themselves.
SUPPORT_BITMAPS: dict[str, obd.OBDCommand] = {PIDS_D.name: PIDS_D, PIDS_E.name: PIDS_E}

EGT_BANKS: dict[str, obd.OBDCommand] = {
    f"EGT_BANK_{bank}": _mode_01(
        f"EGT_BANK_{bank}",
        f"Exhaust gas temperature bank {bank}",
        pid,
        FRAME_LENGTH,
        partial(decode_exhaust_temperatures, bank),
    )
    for bank, pid in EGT_PIDS.items()
}

DPF_PRESSURE = _mode_01(
    "DPF_DIFFERENTIAL_PRESSURE",
    "Diesel particulate filter pressure bank 1",
    DPF_PRESSURE_PID,
    PRESSURE_FRAME_LENGTH,
    decode_dpf_pressure,
)

DPF_TEMPERATURES = _mode_01(
    "DPF_TEMPERATURES",
    "Diesel particulate filter temperatures bank 1",
    DPF_TEMPERATURE_PID,
    TEMPERATURE_FRAME_LENGTH,
    decode_dpf_temperatures,
)

# Every capability the standard answers, by name. The bitmap is not one of
# them: it is what discovery asks to learn which of the others the vehicle
# answers. Two capabilities may share a command: the filter's inlet and
# outlet temperatures come in one frame, and each is a capability of its
# own so that a manufacturer can answer either one alone.
STANDARD_COMMANDS: dict[str, obd.OBDCommand] = {
    **EGT_BANKS,
    DPF_PRESSURE.name: DPF_PRESSURE,
    "DPF_TEMP_INLET": DPF_TEMPERATURES,
    "DPF_TEMP_OUTLET": DPF_TEMPERATURES,
}

# The PID whose bit in the bitmap vouches for each capability.
STANDARD_PIDS: dict[str, int] = {name: command.pid for name, command in STANDARD_COMMANDS.items()}
