# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the particulate filter models."""

from __future__ import annotations

import pytest

from obd_tui.models.dpf import (
    PRESSURE_FRAME_LENGTH,
    TEMPERATURE_FRAME_LENGTH,
    DpfPressure,
    DpfRole,
    DpfTemperatures,
    TemperatureSource,
)


def pressure_frame(
    present: int, differential: float = 0.0, inlet: float = 0.0, outlet: float = 0.0
) -> bytes:
    """Encode a PID 0x7A payload the way an ECU does, in kPa."""
    words = [
        round((differential + 327.68) / 0.01),
        round(inlet / 0.01),
        round(outlet / 0.01),
    ]
    payload = bytes([present])
    for raw in words:
        payload += bytes([raw >> 8, raw & 0xFF])
    return payload


class TestDpfPressureFromFrame:
    def test_decodes_the_three_pressures(self) -> None:
        reading = DpfPressure.from_frame(pressure_frame(0b111, 4.8, 105.2, 100.4))

        assert reading is not None
        assert reading.differential == pytest.approx(4.8, abs=0.01)
        assert reading.inlet == pytest.approx(105.2, abs=0.01)
        assert reading.outlet == pytest.approx(100.4, abs=0.01)

    def test_leaves_out_what_the_bitmap_does_not_name(self) -> None:
        reading = DpfPressure.from_frame(pressure_frame(0b001, 4.8, 105.2, 100.4))

        assert reading is not None
        assert reading.differential == pytest.approx(4.8, abs=0.01)
        assert reading.inlet is None
        assert reading.outlet is None

    def test_a_bitmap_of_zero_names_nothing(self) -> None:
        assert DpfPressure.from_frame(pressure_frame(0b000, 4.8)) == DpfPressure()

    def test_the_differential_is_signed(self) -> None:
        reading = DpfPressure.from_frame(pressure_frame(0b001, -2.5))

        assert reading is not None
        assert reading.differential == pytest.approx(-2.5, abs=0.01)

    def test_raw_zero_is_the_floor_of_the_differential(self) -> None:
        reading = DpfPressure.from_frame(bytes([0b001, 0, 0, 0, 0, 0, 0]))

        assert reading is not None
        assert reading.differential == pytest.approx(-327.68)

    def test_a_short_frame_decodes_to_nothing(self) -> None:
        assert DpfPressure.from_frame(pressure_frame(0b111)[:-1]) is None
        assert DpfPressure.from_frame(b"") is None

    def test_bytes_past_the_frame_are_ignored(self) -> None:
        reading = DpfPressure.from_frame(pressure_frame(0b001, 4.8) + b"\xff")

        assert reading is not None
        assert reading.differential == pytest.approx(4.8, abs=0.01)

    def test_the_frame_is_seven_bytes(self) -> None:
        assert PRESSURE_FRAME_LENGTH == 7
        assert len(pressure_frame(0b111)) == PRESSURE_FRAME_LENGTH


def temperature_frame(present: int, *temperatures: float) -> bytes:
    """Encode a PID 0x7C payload the way an ECU does, in °C."""
    padding = [-40.0] * (4 - len(temperatures))
    payload = bytes([present])
    for temperature in (*temperatures, *padding):
        raw = round((temperature + 40.0) * 10.0)
        payload += bytes([raw >> 8, raw & 0xFF])
    return payload


class TestDpfTemperaturesFromFrame:
    def test_decodes_the_inlet_and_the_outlet_of_bank_1(self) -> None:
        reading = DpfTemperatures.from_frame(temperature_frame(0b0011, 412.0, 365.5))

        assert reading == DpfTemperatures(inlet=412.0, outlet=365.5)
        assert reading.source is TemperatureSource.ECU

    def test_leaves_out_what_the_bitmap_does_not_name(self) -> None:
        reading = DpfTemperatures.from_frame(temperature_frame(0b0010, 999.0, 365.5))

        assert reading == DpfTemperatures(inlet=None, outlet=365.5)

    def test_leaves_bank_2_aside(self) -> None:
        reading = DpfTemperatures.from_frame(temperature_frame(0b1100, 0.0, 0.0, 400.0, 350.0))

        assert reading == DpfTemperatures()

    def test_the_internal_temperature_has_no_standard_slot(self) -> None:
        reading = DpfTemperatures.from_frame(temperature_frame(0b1111, 412.0, 365.5, 1.0, 2.0))

        assert reading is not None
        assert reading.internal is None

    def test_a_short_frame_decodes_to_nothing(self) -> None:
        assert DpfTemperatures.from_frame(temperature_frame(0b11)[:-1]) is None

    def test_the_frame_is_nine_bytes(self) -> None:
        assert TEMPERATURE_FRAME_LENGTH == 9
        assert len(temperature_frame(0b11)) == TEMPERATURE_FRAME_LENGTH

    def test_raw_zero_is_the_floor_of_the_encoding(self) -> None:
        reading = DpfTemperatures.from_frame(bytes([0b01, 0, 0, 0, 0, 0, 0, 0, 0]))

        assert reading is not None
        assert reading.inlet == pytest.approx(-40.0)


class TestDpfRole:
    def test_names_the_three_places_a_sensor_can_sit(self) -> None:
        assert {role.value for role in DpfRole} == {"inlet", "outlet", "internal"}
