# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the standard commands declared beyond python-obd's table."""

from __future__ import annotations

import obd
import pytest
from obd.protocols import ECU
from obd.protocols.protocol import Message

from obd_tui.models.dpf import DpfPressure
from obd_tui.models.exhaust import ExhaustTemperatures
from obd_tui.obd.standard import (
    DPF_PRESSURE,
    EGT_BANKS,
    EGT_PIDS,
    PIDS_D,
    STANDARD_COMMANDS,
    STANDARD_PIDS,
    decode_dpf_pressure,
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
        assert all(command.name == name for name, command in STANDARD_COMMANDS.items())

    @pytest.mark.parametrize("name", sorted(STANDARD_COMMANDS))
    def test_python_obd_does_not_already_define_them(self, name: str) -> None:
        assert not hasattr(obd.commands, name)

    def test_one_command_per_bank(self) -> None:
        assert set(EGT_BANKS) == {"EGT_BANK_1", "EGT_BANK_2"}

    def test_bank_1_asks_mode_01_pid_78(self) -> None:
        assert EGT_BANKS["EGT_BANK_1"].command == b"0178"
        assert EGT_BANKS["EGT_BANK_1"].bytes == 11

    def test_bank_2_asks_mode_01_pid_79(self) -> None:
        assert EGT_BANKS["EGT_BANK_2"].command == b"0179"
        assert EGT_BANKS["EGT_BANK_2"].bytes == 11

    def test_pids_d_asks_mode_01_pid_60(self) -> None:
        assert PIDS_D.command == b"0160"
        assert PIDS_D.bytes == 6

    def test_every_capability_is_vouched_for_by_its_own_pid(self) -> None:
        assert STANDARD_PIDS == {
            "EGT_BANK_1": 0x78,
            "EGT_BANK_2": 0x79,
            "DPF_DIFFERENTIAL_PRESSURE": 0x7A,
        }
        assert set(EGT_PIDS.values()) <= set(STANDARD_PIDS.values())

    def test_the_bitmap_is_not_a_capability(self) -> None:
        assert PIDS_D.name not in STANDARD_COMMANDS


class TestExhaustDecoder:
    def test_decodes_a_full_bank(self) -> None:
        # Sensors 1 and 2 fitted: 185.0 °C and 202.5 °C.
        message = reply(0x41, 0x78, 0b0011, 0x08, 0xCA, 0x09, 0x79, 0, 0, 0, 0)

        assert decode_exhaust_temperatures(1, [message]) == ExhaustTemperatures(
            1, (185.0, 202.5, None, None)
        )

    def test_runs_through_python_obd_as_a_command(self) -> None:
        message = reply(0x41, 0x78, 0b0001, 0x08, 0xCA, 0, 0, 0, 0, 0, 0)

        response = EGT_BANKS["EGT_BANK_1"]([message])

        assert not response.is_null()
        assert response.value == ExhaustTemperatures(1, (185.0, None, None, None))

    def test_bank_2_decodes_for_bank_2(self) -> None:
        message = reply(0x41, 0x79, 0b0001, 0x09, 0x06, 0, 0, 0, 0, 0, 0)

        assert EGT_BANKS["EGT_BANK_2"]([message]).value == ExhaustTemperatures(
            2, (191.0, None, None, None)
        )

    def test_python_obd_pads_a_short_reply_before_decoding(self) -> None:
        """The library guarantees the frame size; a truncated reply reads as zeros."""
        response = EGT_BANKS["EGT_BANK_1"]([reply(0x41, 0x78, 0b0001, 0x08)])

        assert response.value == ExhaustTemperatures(1, (0x0800 / 10.0 - 40.0, None, None, None))

    def test_a_short_frame_handed_straight_to_the_decoder_is_nothing(self) -> None:
        assert decode_exhaust_temperatures(1, [reply(0x41, 0x78, 0b0001)]) is None

    def test_a_reply_from_another_ecu_is_ignored(self) -> None:
        message = reply(0x41, 0x78, 0b0001, 0x08, 0xCA, 0, 0, 0, 0, 0, 0, ecu=ECU.TRANSMISSION)

        assert EGT_BANKS["EGT_BANK_1"]([message]).is_null()


class TestDpfPressureDecoder:
    def test_the_filter_pressure_asks_mode_01_pid_7a(self) -> None:
        assert DPF_PRESSURE.command == b"017A"
        assert DPF_PRESSURE.bytes == 9
        assert STANDARD_COMMANDS["DPF_DIFFERENTIAL_PRESSURE"] is DPF_PRESSURE

    def test_decodes_the_three_pressures(self) -> None:
        # Differential 4.8 kPa (0x81E0), inlet 105.2 (0x2918), outlet 100.4 (0x2738).
        message = reply(0x41, 0x7A, 0b111, 0x81, 0xE0, 0x29, 0x18, 0x27, 0x38)

        reading = decode_dpf_pressure([message])

        assert reading is not None
        assert reading.differential == pytest.approx(4.8, abs=0.01)
        assert reading.inlet == pytest.approx(105.2, abs=0.01)
        assert reading.outlet == pytest.approx(100.4, abs=0.01)

    def test_runs_through_python_obd_as_a_command(self) -> None:
        response = DPF_PRESSURE([reply(0x41, 0x7A, 0b001, 0x81, 0xC0, 0, 0, 0, 0)])

        assert not response.is_null()
        assert isinstance(response.value, DpfPressure)
        assert response.value.inlet is None

    def test_a_short_frame_handed_straight_to_the_decoder_is_nothing(self) -> None:
        assert decode_dpf_pressure([reply(0x41, 0x7A, 0b001)]) is None


class TestSupportedPidsDecoder:
    def test_names_the_pids_whose_bits_are_set(self) -> None:
        # Bit 31 is PID 0x61, bits 8 and 7 are PIDs 0x78 and 0x79, bit 0 is 0x80.
        message = reply(0x41, 0x60, 0x80, 0x00, 0x01, 0x81)

        assert decode_supported_pids([message]) == frozenset({0x61, 0x78, 0x79, 0x80})

    def test_a_clear_bitmap_names_nothing(self) -> None:
        assert decode_supported_pids([reply(0x41, 0x60, 0, 0, 0, 0)]) == frozenset()

    def test_a_short_bitmap_names_nothing(self) -> None:
        assert decode_supported_pids([reply(0x41, 0x60, 0xFF)]) == frozenset()

    def test_runs_through_python_obd_as_a_command(self) -> None:
        response = PIDS_D([reply(0x41, 0x60, 0x00, 0x00, 0x01, 0x00)])

        assert response.value == frozenset({0x78})
