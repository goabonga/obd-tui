# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the dashboard panels."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from obd_tui.models.commands import CommandCatalog, CommandInfo
from obd_tui.models.dpf import (
    DpfLoad,
    DpfPressure,
    DpfRegeneration,
    DpfRegenState,
    DpfTemperatures,
    TemperatureSource,
)
from obd_tui.models.exhaust import ExhaustTemperatures
from obd_tui.models.vehicle import TroubleCode, VehicleState
from obd_tui.services.polling import POLLED_FIELDS
from obd_tui.views.panel import NO_DATA
from obd_tui.views.panels import (
    PANELS,
    PANELS_BY_KEY,
    PanelSpec,
    air,
    catalog,
    dpf,
    egr,
    engine,
    exhaust,
    faults,
)
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
        assert set(panel.fields) <= POLLED_FIELDS

    @pytest.mark.parametrize("panel", PANELS, ids=lambda panel: panel.key)
    def test_a_charted_reading_is_a_declared_field(self, panel: PanelSpec) -> None:
        assert {trend.field for trend in panel.trends} <= set(panel.fields)

    def test_every_reading_the_poller_fills_is_shown_somewhere(self) -> None:
        shown = {field for panel in PANELS for field in panel.fields}

        assert POLLED_FIELDS - shown == set()


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


def banks(*sensors: tuple[int, tuple[float | None, ...]]) -> VehicleState:
    """Return a state holding the given banks, as (number, slots) pairs."""
    return VehicleState(
        egt_banks={number: ExhaustTemperatures(number, slots) for number, slots in sensors}
    )


class TestExhaust:
    def test_shows_each_sensor_the_vehicle_answered(self) -> None:
        text = exhaust.render(banks((1, (184.0, None, 176.5, None))), EMPTY, METRIC)

        assert "B1S1 °C" in text
        assert "184.0" in text
        assert "B1S3 °C" in text
        assert "176.5" in text
        assert "B1S2" not in text
        assert "B1S4" not in text

    def test_shows_every_bank_the_vehicle_answered(self) -> None:
        state = banks((2, (191.0, None, None, None)), (1, (184.0, 202.0, None, None)))

        lines = exhaust.render(state, EMPTY, METRIC).splitlines()

        assert [line.split()[0] for line in lines] == ["B1S1", "B1S2", "B2S1"]

    def test_a_bank_with_no_sensor_fitted_prints_nothing(self) -> None:
        assert exhaust.render(banks((1, (None,) * 4)), EMPTY, METRIC) == NO_DATA

    def test_gauges_each_sensor(self) -> None:
        text = exhaust.render(banks((1, (None, 450.0, None, None))), EMPTY, METRIC)

        assert "█" in text

    def test_lists_the_sensors_upstream_first(self) -> None:
        lines = exhaust.render(banks((1, (184.0, None, None, 150.0))), EMPTY, METRIC).splitlines()

        assert "S1" in lines[0]
        assert "S4" in lines[1]

    def test_converts_to_fahrenheit(self) -> None:
        state = banks((1, (100.0, None, None, None)))

        text = exhaust.render(state, EMPTY, UnitSystem.IMPERIAL)

        assert "°F" in text
        assert "212.0" in text

    def test_reports_when_nothing_was_read(self) -> None:
        assert exhaust.render(VehicleState(), EMPTY, METRIC) == NO_DATA


class TestExhaustSuspects:
    """A sensor far from the others is pointed out, not diagnosed."""

    @staticmethod
    def _flagged(text: str) -> list[str]:
        return [line.split()[0] for line in text.splitlines() if exhaust.SUSPECT in line]

    def test_points_out_the_sensor_that_reads_hot_on_a_cold_engine(self) -> None:
        # P2033: sensor 2's circuit stuck high while the engine is cold.
        state = banks((1, (19.0, 1000.0, 18.0, None)))

        assert self._flagged(exhaust.render(state, EMPTY, METRIC)) == ["B1S2"]

    def test_points_out_a_sensor_stuck_at_the_floor(self) -> None:
        state = banks((1, (420.0, -40.0, 380.0, None)))

        assert self._flagged(exhaust.render(state, EMPTY, METRIC)) == ["B1S2"]

    def test_compares_across_banks(self) -> None:
        state = banks((1, (19.0, 18.0, None, None)), (2, (1000.0, None, None, None)))

        assert self._flagged(exhaust.render(state, EMPTY, METRIC)) == ["B2S1"]

    def test_a_cold_bank_that_agrees_is_left_alone(self) -> None:
        state = banks((1, (19.0, 18.0, 19.0, None)))

        assert exhaust.SUSPECT not in exhaust.render(state, EMPTY, METRIC)

    def test_a_working_bank_under_load_is_left_alone(self) -> None:
        # Upstream of the turbine to downstream of the filter, a spread of
        # a couple of hundred degrees is what a healthy exhaust looks like.
        state = banks((1, (620.0, 450.0, 380.0, None)))

        assert exhaust.SUSPECT not in exhaust.render(state, EMPTY, METRIC)

    def test_a_lone_sensor_has_nothing_to_disagree_with(self) -> None:
        state = banks((1, (None, 1000.0, None, None)))

        assert exhaust.SUSPECT not in exhaust.render(state, EMPTY, METRIC)

    def test_two_sensors_far_apart_are_both_pointed_out(self) -> None:
        state = banks((1, (22.0, 1000.0, None, None)))

        assert self._flagged(exhaust.render(state, EMPTY, METRIC)) == ["B1S1", "B1S2"]

    def test_the_note_survives_a_change_of_units(self) -> None:
        state = banks((1, (19.0, 1000.0, 18.0, None)))

        assert self._flagged(exhaust.render(state, EMPTY, UnitSystem.IMPERIAL)) == ["B1S2"]


class TestDpf:
    def test_shows_the_pressures_the_vehicle_answered(self) -> None:
        state = VehicleState(dpf_pressure=DpfPressure(differential=4.8, inlet=105.2, outlet=100.4))

        text = dpf.render(state, EMPTY, METRIC)

        assert "PARTICULATE FILTER" in text
        assert "DIFF PRESSURE kPa" in text
        assert "4.8" in text
        assert "INLET kPa" in text
        assert "OUTLET kPa" in text

    def test_leaves_out_a_pressure_the_vehicle_did_not_report(self) -> None:
        text = dpf.render(VehicleState(dpf_pressure=DpfPressure(differential=4.8)), EMPTY, METRIC)

        assert "INLET" not in text
        assert "OUTLET" not in text

    def test_puts_the_reading_in_context(self) -> None:
        state = VehicleState(
            dpf_pressure=DpfPressure(differential=4.8), rpm=2500.0, mass_air_flow=38.0
        )

        text = dpf.render(state, EMPTY, METRIC)

        assert "CONTEXT" in text
        assert "2500" in text
        assert "38.0" in text

    def test_shows_the_filter_temperatures(self) -> None:
        state = VehicleState(dpf_temperatures=DpfTemperatures(inlet=412.0, outlet=365.5))

        text = dpf.render(state, EMPTY, METRIC)

        assert "DPF INLET °C" in text
        assert "412.0" in text
        assert "DPF OUTLET °C" in text
        assert "DPF INTERNAL" not in text
        assert dpf.FROM_EXHAUST not in text

    def test_says_when_a_temperature_is_an_exhaust_sensor(self) -> None:
        state = VehicleState(
            dpf_temperatures=DpfTemperatures(inlet=412.0, source=TemperatureSource.EXHAUST)
        )

        text = dpf.render(state, EMPTY, METRIC)

        assert dpf.FROM_EXHAUST in text

    def test_shows_an_internal_temperature_when_reported(self) -> None:
        state = VehicleState(dpf_temperatures=DpfTemperatures(internal=390.0))

        assert "DPF INTERNAL °C" in dpf.render(state, EMPTY, METRIC)

    def test_shows_the_soot_load_in_whichever_shape_came(self) -> None:
        text = dpf.render(VehicleState(dpf_load=DpfLoad(percent=42.0)), EMPTY, METRIC)

        assert "SOOT LOAD %" in text
        assert "42.0" in text
        assert "█" in text
        assert "SOOT MASS" not in text

        text = dpf.render(VehicleState(dpf_load=DpfLoad(soot_mass_g=18.4)), EMPTY, METRIC)

        assert "SOOT MASS g" in text
        assert "18.4" in text
        assert "SOOT LOAD" not in text

    def test_shows_a_reported_regeneration_in_capitals(self) -> None:
        state = VehicleState(
            dpf_regeneration=DpfRegeneration(DpfRegenState.ACTIVE, trigger_percent=100.0)
        )

        text = dpf.render(state, EMPTY, METRIC)

        assert "REGENERATION" in text
        assert "ACTIVE" in text
        assert "ECU" in text
        assert "TRIGGER %" in text

    def test_shows_a_guess_as_one(self) -> None:
        state = VehicleState(dpf_regeneration=DpfRegeneration(DpfRegenState.ACTIVE, estimated=True))

        text = dpf.render(state, EMPTY, METRIC)

        assert "probable" in text
        assert "estimated" in text
        assert "ACTIVE" not in text

    def test_an_unlikely_guess_reads_as_such(self) -> None:
        state = VehicleState(
            dpf_regeneration=DpfRegeneration(DpfRegenState.INACTIVE, estimated=True)
        )

        assert "unlikely" in dpf.render(state, EMPTY, METRIC)

    def test_a_guess_of_an_unnamed_state_falls_back_to_its_name(self) -> None:
        state = VehicleState(
            dpf_regeneration=DpfRegeneration(DpfRegenState.REQUESTED, estimated=True)
        )

        assert "requested" in dpf.render(state, EMPTY, METRIC)

    def test_context_alone_is_not_a_filter(self) -> None:
        assert dpf.render(VehicleState(rpm=2500.0, mass_air_flow=38.0), EMPTY, METRIC) == NO_DATA

    def test_converts_to_psi(self) -> None:
        state = VehicleState(dpf_pressure=DpfPressure(differential=10.0))

        text = dpf.render(state, EMPTY, UnitSystem.IMPERIAL)

        assert "psi" in text
        assert "1.5" in text

    def test_reports_when_nothing_was_read(self) -> None:
        assert dpf.render(VehicleState(), EMPTY, METRIC) == NO_DATA


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
