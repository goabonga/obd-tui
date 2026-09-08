# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the exhaust gas temperature model."""

from __future__ import annotations

import pytest

from obd_tui.models.exhaust import FRAME_LENGTH, SENSORS_PER_BANK, ExhaustTemperatures


def frame(present: int, *temperatures: float) -> bytes:
    """Encode a bank's payload the way an ECU does.

    Args:
        present: The sensor bitmap, bit 0 for sensor 1.
        temperatures: Values in °C for each of the four slots; a slot left
            out is sent as the floor of the encoding, which is what an ECU
            pads with.
    """
    payload = bytes([present])
    padding = [-40.0] * (SENSORS_PER_BANK - len(temperatures))
    for temperature in (*temperatures, *padding):
        raw = round((temperature + 40.0) * 10.0)
        payload += bytes([raw >> 8, raw & 0xFF])
    return payload


class TestFromFrame:
    def test_decodes_every_sensor_when_all_are_present(self) -> None:
        reading = ExhaustTemperatures.from_frame(1, frame(0b1111, 184.0, 202.5, 176.0, 150.0))

        assert reading == ExhaustTemperatures(1, (184.0, 202.5, 176.0, 150.0))

    def test_carries_the_bank_it_was_decoded_for(self) -> None:
        reading = ExhaustTemperatures.from_frame(2, frame(0b0001, 191.0))

        assert reading is not None
        assert reading.bank == 2

    def test_leaves_out_the_sensors_the_bitmap_does_not_name(self) -> None:
        reading = ExhaustTemperatures.from_frame(1, frame(0b0010, 999.0, 202.5, 999.0, 999.0))

        assert reading == ExhaustTemperatures(1, (None, 202.5, None, None))

    def test_a_missing_sensor_does_not_shift_the_others(self) -> None:
        reading = ExhaustTemperatures.from_frame(1, frame(0b1010, 0.0, 202.5, 0.0, 150.0))

        assert reading == ExhaustTemperatures(1, (None, 202.5, None, 150.0))

    def test_a_bitmap_of_zero_names_no_sensor(self) -> None:
        reading = ExhaustTemperatures.from_frame(1, frame(0b0000, 184.0, 202.5, 176.0, 150.0))

        assert reading == ExhaustTemperatures(1)

    def test_a_short_frame_decodes_to_nothing(self) -> None:
        assert ExhaustTemperatures.from_frame(1, frame(0b1111, 184.0)[:-1]) is None

    def test_an_empty_frame_decodes_to_nothing(self) -> None:
        assert ExhaustTemperatures.from_frame(1, b"") is None

    def test_bytes_past_the_frame_are_ignored(self) -> None:
        reading = ExhaustTemperatures.from_frame(1, frame(0b0001, 184.0) + b"\xff\xff")

        assert reading is not None
        assert reading.sensors[0] == pytest.approx(184.0)

    def test_the_frame_is_nine_bytes(self) -> None:
        assert FRAME_LENGTH == 9
        assert len(frame(0b1111)) == FRAME_LENGTH

    def test_raw_zero_is_the_floor_of_the_encoding(self) -> None:
        reading = ExhaustTemperatures.from_frame(1, bytes([0b0001, 0, 0, 0, 0, 0, 0, 0, 0]))

        assert reading is not None
        assert reading.sensors[0] == pytest.approx(-40.0)

    def test_a_known_encoding_decodes_to_the_documented_value(self) -> None:
        # 0x08CA = 2250 tenths above -40 °C, i.e. 185 °C.
        reading = ExhaustTemperatures.from_frame(1, bytes([0b0001, 0x08, 0xCA, 0, 0, 0, 0, 0, 0]))

        assert reading is not None
        assert reading.sensors[0] == pytest.approx(185.0)

    def test_raw_maximum_is_the_ceiling_of_the_encoding(self) -> None:
        reading = ExhaustTemperatures.from_frame(1, bytes([0b0001, 0xFF, 0xFF, 0, 0, 0, 0, 0, 0]))

        assert reading is not None
        assert reading.sensors[0] == pytest.approx(6513.5)


class TestFitted:
    def test_numbers_the_sensors_present_from_one(self) -> None:
        reading = ExhaustTemperatures(1, (184.0, None, 176.0, None))

        assert reading.fitted == ((1, 184.0), (3, 176.0))

    def test_an_empty_bank_has_no_sensor_fitted(self) -> None:
        assert ExhaustTemperatures(1).fitted == ()

    def test_a_bank_defaults_to_four_empty_slots(self) -> None:
        assert ExhaustTemperatures(2).sensors == (None, None, None, None)
