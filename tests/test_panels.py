# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the dashboard panels."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from obd_tui.models.commands import CommandCatalog, CommandInfo
from obd_tui.models.vehicle import TroubleCode, VehicleState
from obd_tui.services.polling import ALL_READINGS
from obd_tui.views.panel import NO_DATA
from obd_tui.views.panels import PANELS, PANELS_BY_KEY, PanelSpec, air, catalog, egr, engine, faults
from obd_tui.views.panels import diagnostics as diag
from obd_tui.views.units import UnitSystem

EMPTY = CommandCatalog()
METRIC = UnitSystem.METRIC


class TestRegistry:
    def test_keys_are_unique(self) -> None:
        assert len({panel.key for panel in PANELS}) == len(PANELS)

    def test_shortcuts_are_unique(self) -> None:
        assert len({panel.shortcut for panel in PANELS}) == len(PANELS)

    def test_lookup_matches_the_ordered_list(self) -> None:
        assert list(PANELS_BY_KEY.values()) == list(PANELS)

    @pytest.mark.parametrize("panel", PANELS, ids=lambda panel: panel.key)
    def test_every_panel_renders_an_empty_state(self, panel: PanelSpec) -> None:
        assert panel.render(VehicleState(), EMPTY, METRIC).strip()

    @pytest.mark.parametrize("panel", PANELS, ids=lambda panel: panel.key)
    def test_every_panel_renders_in_imperial(self, panel: PanelSpec) -> None:
        state = VehicleState(coolant_temp=90.0, speed=100.0, intake_pressure=180.0)

        assert panel.render(state, EMPTY, UnitSystem.IMPERIAL).strip()

    @pytest.mark.parametrize("panel", PANELS, ids=lambda panel: panel.key)
    def test_the_declared_fields_exist_on_the_state(self, panel: PanelSpec) -> None:
        state = VehicleState()

        assert [field for field in panel.fields if not hasattr(state, field)] == []

    @pytest.mark.parametrize("panel", PANELS, ids=lambda panel: panel.key)
    def test_the_declared_fields_are_ones_the_poller_reads(self, panel: PanelSpec) -> None:
        assert set(panel.fields) <= set(ALL_READINGS.values())

    @pytest.mark.parametrize("panel", PANELS, ids=lambda panel: panel.key)
    def test_a_charted_reading_is_a_declared_field(self, panel: PanelSpec) -> None:
        assert {trend.field for trend in panel.trends} <= set(panel.fields)

    def test_every_reading_the_poller_fills_is_shown_somewhere(self) -> None:
        shown = {field for panel in PANELS for field in panel.fields}

        assert set(ALL_READINGS.values()) - shown == set()


class TestEngine:
    def test_shows_the_readings_the_vehicle_answered(self) -> None:
        state = VehicleState(rpm=1450.0, engine_load=42.5, coolant_temp=91.0)

        text = engine.render(state, EMPTY, METRIC)

        assert "RPM" in text
        assert "1450" in text
        assert "42.5" in text
        assert "TEMPERATURES" in text

    def test_hides_a_section_the_vehicle_did_not_answer(self) -> None:
        text = engine.render(VehicleState(rpm=1450.0), EMPTY, METRIC)

        assert "TEMPERATURES" not in text
        assert "FUEL" not in text
        assert "O2 SENSORS" not in text

    def test_reports_when_nothing_was_read(self) -> None:
        assert engine.render(VehicleState(), EMPTY, METRIC) == NO_DATA

    def test_run_time_is_a_duration(self) -> None:
        assert "01:01:01" in engine.render(VehicleState(run_time=3661), EMPTY, METRIC)


class TestAir:
    def test_gauges_positive_boost(self) -> None:
        state = VehicleState(intake_pressure=180.0, barometric_pressure=100.0)

        text = air.render(state, EMPTY, METRIC)

        assert "NET BOOST kPa" in text
        assert "80.0" in text
        assert "█" in text

    def test_marks_vacuum_instead_of_gauging_it(self) -> None:
        state = VehicleState(intake_pressure=40.0, barometric_pressure=100.0)

        text = air.render(state, EMPTY, METRIC)

        assert "(vacuum)" in text
        assert "-60.0" in text

    def test_shows_the_throttle_section(self) -> None:
        assert "THROTTLE" in air.render(VehicleState(throttle=12.0), EMPTY, METRIC)

    def test_reports_when_nothing_was_read(self) -> None:
        assert air.render(VehicleState(), EMPTY, METRIC) == NO_DATA


class TestEgr:
    def test_explains_a_valve_below_the_command(self) -> None:
        text = egr.render(VehicleState(egr_commanded=30.0, egr_error=-4.5), EMPTY, METRIC)

        assert "(4.5% below commanded)" in text

    def test_explains_a_valve_above_the_command(self) -> None:
        assert "(2.0% above commanded)" in egr.render(VehicleState(egr_error=2.0), EMPTY, METRIC)

    def test_explains_a_valve_on_target(self) -> None:
        assert "(on target)" in egr.render(VehicleState(egr_error=0.0), EMPTY, METRIC)

    def test_reports_when_nothing_was_read(self) -> None:
        assert egr.render(VehicleState(), EMPTY, METRIC) == NO_DATA


class TestDiagnostics:
    def test_reads_the_status_word(self) -> None:
        state = VehicleState(status=SimpleNamespace(MIL=True, DTC_count=3, ignition_type="spark"))

        text = diag.render(state, EMPTY, METRIC)

        assert "MIL" in text
        assert "ON" in text
        assert "3" in text
        assert "spark" in text

    def test_shows_the_counters_section(self) -> None:
        text = diag.render(VehicleState(distance_with_mil=120.0), EMPTY, METRIC)

        assert "COUNTERS" in text
        assert "120" in text

    def test_shows_the_calibration_section(self) -> None:
        assert "CALIBRATION" in diag.render(VehicleState(calibration_id="ABC123"), EMPTY, METRIC)

    def test_reports_when_nothing_was_read(self) -> None:
        assert diag.render(VehicleState(), EMPTY, METRIC) == NO_DATA


class TestFaults:
    def test_lists_stored_codes_with_their_description(self) -> None:
        state = VehicleState(stored_codes=(TroubleCode("P0401", "EGR flow insufficient"),))

        text = faults.render(state, EMPTY, METRIC)

        assert "STORED (1)" in text
        assert "P0401" in text
        assert "EGR flow insufficient" in text

    def test_lists_a_code_without_a_description(self) -> None:
        text = faults.render(VehicleState(stored_codes=(TroubleCode("P0401"),)), EMPTY, METRIC)

        assert text.splitlines()[-1].strip() == "P0401"

    def test_separates_pending_codes(self) -> None:
        state = VehicleState(
            stored_codes=(TroubleCode("P0401"),), pending_codes=(TroubleCode("P0100"),)
        )

        text = faults.render(state, EMPTY, METRIC)

        assert "STORED (1)" in text
        assert "PENDING (1)" in text

    def test_says_so_when_there_is_no_fault(self) -> None:
        assert faults.render(VehicleState(), EMPTY, METRIC) == faults.NO_FAULTS


class TestCatalog:
    @staticmethod
    def _catalog() -> CommandCatalog:
        return CommandCatalog(
            modes={
                "Mode 01 — Live data": [
                    CommandInfo("RPM", "0x0C", "Engine RPM", supported=True),
                    CommandInfo("OIL_TEMP", "0x5C", "Engine oil temperature"),
                ]
            }
        )

    def test_counts_the_supported_commands(self) -> None:
        text = catalog.render(VehicleState(), self._catalog(), METRIC)

        assert "Supported: 1 / 2" in text
        assert "Mode 01 — Live data  (1 / 2)" in text

    def test_marks_each_command(self) -> None:
        lines = catalog.render(VehicleState(), self._catalog(), METRIC).splitlines()

        assert any(line.startswith("  [x]") and "RPM" in line for line in lines)
        assert any(line.startswith("  [ ]") and "OIL_TEMP" in line for line in lines)

    def test_shows_the_pid_and_the_description(self) -> None:
        text = catalog.render(VehicleState(), self._catalog(), METRIC)

        assert "0x0C" in text
        assert "Engine RPM" in text

    def test_asks_for_a_connection_before_discovery(self) -> None:
        assert catalog.render(VehicleState(), EMPTY, METRIC) == catalog.NOT_DISCOVERED
