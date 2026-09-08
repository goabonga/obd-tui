# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the commands declared beyond python-obd's table."""

from __future__ import annotations

import obd
import pytest
from obd.protocols import ECU
from obd.protocols.protocol import Message

from obd_tui.models.exhaust import ExhaustTemperatures
from obd_tui.services.custom_commands import (
    CUSTOM_COMMANDS,
    CUSTOM_PIDS,
    EGT_BANK_1,
    EGT_BANK_1_PID,
    PIDS_D,
    decode_exhaust_temperatures,
    decode_supported_pids,
)


def reply(*data: int, ecu: int = ECU.ENGINE) -> Message:
    """Return a python-obd message carrying ``data``, mode and PID included."""
    message = Message([])
    message.data = bytearray(data)
    message.ecu = ecu
    return message


class TestDeclarations:
    def test_the_names_are_the_dictionary_keys(self) -> None:
        assert all(command.name == name for name, command in CUSTOM_COMMANDS.items())

    @pytest.mark.parametrize("name", sorted(CUSTOM_COMMANDS))
    def test_python_obd_does_not_already_define_them(self, name: str) -> None:
        assert not hasattr(obd.commands, name)

    def test_egt_bank_1_asks_mode_01_pid_78(self) -> None:
        assert EGT_BANK_1.command == b"0178"
        assert EGT_BANK_1_PID == 0x78
        assert EGT_BANK_1.bytes == 11

    def test_pids_d_asks_mode_01_pid_60(self) -> None:
        assert PIDS_D.command == b"0160"
        assert PIDS_D.bytes == 6

    def test_every_vouched_command_is_declared(self) -> None:
        assert set(CUSTOM_PIDS) <= set(CUSTOM_COMMANDS)

    def test_the_bitmap_vouches_for_nobody_but_itself(self) -> None:
        assert PIDS_D.name not in CUSTOM_PIDS


class TestExhaustDecoder:
    def test_decodes_a_full_bank(self) -> None:
        # Sensors 1 and 2 fitted: 185.0 °C and 202.5 °C.
        message = reply(0x41, 0x78, 0b0011, 0x08, 0xCA, 0x09, 0x79, 0, 0, 0, 0)

        assert decode_exhaust_temperatures([message]) == ExhaustTemperatures(185.0, 202.5)

    def test_runs_through_python_obd_as_a_command(self) -> None:
        message = reply(0x41, 0x78, 0b0001, 0x08, 0xCA, 0, 0, 0, 0, 0, 0)

        response = EGT_BANK_1([message])

        assert not response.is_null()
        assert response.value == ExhaustTemperatures(sensor_1=185.0)

    def test_python_obd_pads_a_short_reply_before_decoding(self) -> None:
        """The library guarantees the frame size; a truncated reply reads as zeros."""
        response = EGT_BANK_1([reply(0x41, 0x78, 0b0001, 0x08)])

        assert response.value == ExhaustTemperatures(sensor_1=(0x0800 / 10.0) - 40.0)

    def test_a_short_frame_handed_straight_to_the_decoder_is_nothing(self) -> None:
        assert decode_exhaust_temperatures([reply(0x41, 0x78, 0b0001)]) is None

    def test_a_reply_from_another_ecu_is_ignored(self) -> None:
        message = reply(0x41, 0x78, 0b0001, 0x08, 0xCA, 0, 0, 0, 0, 0, 0, ecu=ECU.TRANSMISSION)

        assert EGT_BANK_1([message]).is_null()


class TestSupportedPidsDecoder:
    def test_names_the_pids_whose_bits_are_set(self) -> None:
        # Bit 31 is PID 0x61, bit 8 is PID 0x78, bit 0 is PID 0x80.
        message = reply(0x41, 0x60, 0x80, 0x00, 0x01, 0x01)

        assert decode_supported_pids([message]) == frozenset({0x61, 0x78, 0x80})

    def test_a_clear_bitmap_names_nothing(self) -> None:
        assert decode_supported_pids([reply(0x41, 0x60, 0, 0, 0, 0)]) == frozenset()

    def test_a_short_bitmap_names_nothing(self) -> None:
        assert decode_supported_pids([reply(0x41, 0x60, 0xFF)]) == frozenset()

    def test_runs_through_python_obd_as_a_command(self) -> None:
        response = PIDS_D([reply(0x41, 0x60, 0x00, 0x00, 0x01, 0x00)])

        assert response.value == frozenset({EGT_BANK_1_PID})
