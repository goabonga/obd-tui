# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the panel building blocks."""

from __future__ import annotations

import pytest

from obd_tui.models.vehicle import VehicleState
from obd_tui.views.format import duration, integer, number, onoff, precise, text
from obd_tui.views.gauges import DEFAULT_WIDTH, bar
from obd_tui.views.panel import Panel
from obd_tui.views.units import UnitSystem


class TestFormat:
    def test_number_keeps_one_decimal(self) -> None:
        assert number(91.25) == "91.2"

    def test_number_accepts_another_precision(self) -> None:
        assert number(91.25, decimals=0) == "91"

    def test_precise_keeps_two_decimals(self) -> None:
        assert precise(0.985) == "0.98"

    def test_integer_truncates(self) -> None:
        assert integer(2499.9) == "2499"

    @pytest.mark.parametrize(
        ("seconds", "expected"),
        [(0, "00:00:00"), (59, "00:00:59"), (3661, "01:01:01"), (86400, "24:00:00")],
    )
    def test_duration_is_hours_minutes_seconds(self, seconds: int, expected: str) -> None:
        assert duration(seconds) == expected

    def test_duration_marks_a_negative_reading(self) -> None:
        assert duration(-61) == "-00:01:01"

    def test_text_stringifies_an_ecu_object(self) -> None:
        assert text(object.__str__) != "--"

    @pytest.mark.parametrize(("value", "expected"), [(True, "ON"), (False, "OFF")])
    def test_onoff_reads_a_lamp(self, value: bool, expected: str) -> None:
        assert onoff(value) == expected

    @pytest.mark.parametrize("formatter", [number, precise, integer, duration, text, onoff])
    def test_every_formatter_marks_a_missing_reading(self, formatter: object) -> None:
        assert formatter(None) == "--"  # type: ignore[operator]


class TestBar:
    def test_is_empty_without_a_reading(self) -> None:
        assert bar(None, 100) == "░" * DEFAULT_WIDTH

    def test_is_empty_at_zero(self) -> None:
        assert bar(0, 100) == "░" * DEFAULT_WIDTH

    def test_is_full_at_the_maximum(self) -> None:
        assert bar(100, 100) == "█" * DEFAULT_WIDTH

    def test_fills_proportionally(self) -> None:
        assert bar(50, 100, width=10) == "█████░░░░░"

    def test_clamps_a_reading_above_the_maximum(self) -> None:
        assert bar(150, 100, width=10) == "█" * 10

    def test_clamps_a_negative_reading(self) -> None:
        assert bar(-10, 100, width=10) == "░" * 10

    def test_is_empty_for_a_non_positive_maximum(self) -> None:
        assert bar(10, 0, width=10) == "░" * 10

    def test_keeps_the_requested_width(self) -> None:
        assert all(len(bar(value, 100, width=7)) == 7 for value in (None, 0, 33, 100))


class TestPanel:
    def test_an_untouched_panel_is_empty(self) -> None:
        panel = Panel()

        assert not panel
        assert panel.render() == ""

    def test_a_reading_is_labelled_and_right_aligned(self) -> None:
        panel = Panel()

        panel.reading(VehicleState(rpm=1450.0), "rpm", "RPM", integer)

        assert panel.render() == f"  {'RPM':<18} {'1450':>8}"

    def test_a_missing_reading_prints_nothing(self) -> None:
        panel = Panel()

        panel.reading(VehicleState(), "rpm", "RPM")

        assert not panel

    def test_an_unknown_field_prints_nothing(self) -> None:
        panel = Panel()

        panel.reading(VehicleState(), "not_a_field", "NOPE")

        assert not panel

    def test_a_gauge_follows_the_value(self) -> None:
        panel = Panel()

        panel.reading(VehicleState(engine_load=50.0), "engine_load", "LOAD %", gauge_max=100)

        assert panel.render().endswith(bar(50.0, 100))

    def test_a_note_follows_the_value(self) -> None:
        panel = Panel()

        panel.reading(
            VehicleState(egr_error=-3.0), "egr_error", "ERROR %", note="(below commanded)"
        )

        assert panel.render().endswith("(below commanded)")

    def test_a_gauge_is_empty_for_a_non_numeric_reading(self) -> None:
        panel = Panel()

        panel.reading(VehicleState(status="OK"), "status", "STATUS", text, gauge_max=100)

        assert panel.render().endswith(bar(None, 100))

    def test_a_section_prints_once_it_has_a_reading(self) -> None:
        panel = Panel()
        state = VehicleState(rpm=1450.0, coolant_temp=91.0)

        panel.reading(state, "rpm", "RPM", integer)
        panel.section("TEMPERATURES")
        panel.reading(state, "coolant_temp", "COOLANT")

        lines = panel.render().splitlines()
        assert lines[1] == ""
        assert lines[2] == "TEMPERATURES"
        assert lines[3] == "─" * 60
        assert lines[4].startswith("  COOLANT °C")

    def test_an_empty_section_prints_nothing(self) -> None:
        panel = Panel()
        state = VehicleState(rpm=1450.0)

        panel.reading(state, "rpm", "RPM", integer)
        panel.section("TEMPERATURES")
        panel.reading(state, "coolant_temp", "COOLANT")

        assert panel.render().splitlines() == [f"  {'RPM':<18} {'1450':>8}"]

    def test_a_convertible_reading_carries_its_unit(self) -> None:
        panel = Panel()

        panel.reading(VehicleState(coolant_temp=91.0), "coolant_temp", "COOLANT")

        assert panel.render().startswith(f"  {'COOLANT °C':<18}")

    def test_imperial_converts_the_value_and_the_unit(self) -> None:
        panel = Panel(UnitSystem.IMPERIAL)

        panel.reading(VehicleState(coolant_temp=100.0), "coolant_temp", "COOLANT")

        row = panel.render()
        assert "COOLANT °F" in row
        assert "212.0" in row

    def test_a_gauge_is_drawn_from_what_the_vehicle_reported(self) -> None:
        metric = Panel()
        imperial = Panel(UnitSystem.IMPERIAL)
        state = VehicleState(coolant_temp=65.0)

        metric.reading(state, "coolant_temp", "COOLANT", gauge_max=130)
        imperial.reading(state, "coolant_temp", "COOLANT", gauge_max=130)

        assert metric.render().endswith(bar(65.0, 130))
        assert imperial.render().endswith(bar(65.0, 130))

    def test_a_leading_section_has_no_blank_line_above_it(self) -> None:
        panel = Panel()

        panel.section("FUEL")
        panel.line("  anything")

        assert panel.render().splitlines()[0] == "FUEL"

    def test_a_later_section_replaces_an_empty_one(self) -> None:
        panel = Panel()

        panel.section("FUEL")
        panel.section("O2 SENSORS")
        panel.line("  anything")

        assert panel.render().splitlines()[0] == "O2 SENSORS"
