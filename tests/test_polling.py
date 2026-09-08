# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the sensor polling service."""

from __future__ import annotations

from collections.abc import Collection, Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import obd
import pytest

from obd_tui.models.commands import CommandCatalog, CommandInfo
from obd_tui.models.dpf import DpfLoad, DpfPressure, DpfTemperatures, TemperatureSource
from obd_tui.models.exhaust import ExhaustTemperatures
from obd_tui.models.vehicle import TroubleCode, VehicleState
from obd_tui.obd.registry import KNOWN_CAPABILITIES
from obd_tui.services.connection import AdapterError
from obd_tui.services.polling import (
    ALL_READINGS,
    BANK_READINGS,
    CODE_READINGS,
    DPF_TEMPERATURE_READINGS,
    EGT_FIELD,
    FAMILIES,
    FAST_COMMANDS,
    LINK_LOSS_FAILURES,
    MODEL_READINGS,
    NUMERIC_READINGS,
    POLLED_FIELDS,
    RAW_READINGS,
    SLOW_COMMANDS,
    LinkLost,
    SensorPoller,
    Tier,
    is_due,
    tier_of,
)


class FakeConnection:
    """Answers a fixed set of commands and records what was asked."""

    def __init__(
        self,
        answers: dict[str, Any] | None = None,
        failing: Collection[str] | None = None,
    ) -> None:
        self.answers = answers or {}
        # Commands the adapter cannot carry, as opposed to commands the
        # vehicle simply has no answer for.
        self.failing = set(failing or ())
        self.asked: list[str] = []
        self.sweeps = 0

    @contextmanager
    def sweep(self) -> Iterator[None]:
        self.sweeps += 1
        yield

    def query(self, name: str) -> Any | None:
        self.asked.append(name)
        if name in self.failing:
            raise AdapterError(f"cannot reach the vehicle for {name}")
        return self.answers.get(name)


def poller(
    answers: dict[str, Any] | None = None,
    failing: Collection[str] | None = None,
) -> tuple[SensorPoller, FakeConnection]:
    connection = FakeConnection(answers, failing)
    return SensorPoller(connection), connection  # type: ignore[arg-type]


def catalog_of(*names: str) -> CommandCatalog:
    return CommandCatalog(modes={"Mode 01": [CommandInfo(name, supported=True) for name in names]})


class TestCommandMaps:
    @pytest.mark.parametrize(
        "command",
        sorted({*NUMERIC_READINGS, *RAW_READINGS, *CODE_READINGS}),
    )
    def test_every_mapped_command_exists_in_python_obd(self, command: str) -> None:
        assert hasattr(obd.commands, command)

    @pytest.mark.parametrize(
        "field",
        sorted({*NUMERIC_READINGS.values(), *RAW_READINGS.values(), *CODE_READINGS.values()}),
    )
    def test_every_mapped_field_exists_on_the_state(self, field: str) -> None:
        assert hasattr(VehicleState(), field)

    def test_the_maps_do_not_overlap(self) -> None:
        assert not set(NUMERIC_READINGS) & set(RAW_READINGS)
        assert not set(NUMERIC_READINGS) & set(CODE_READINGS)

    def test_the_polled_fields_are_every_field_a_command_fills(self) -> None:
        assert set(ALL_READINGS.values()) == POLLED_FIELDS

    def test_only_a_family_is_fed_by_several_commands(self) -> None:
        fields = list(ALL_READINGS.values())
        shared = {field for field in fields if fields.count(field) > 1}

        assert shared <= set(FAMILIES)

    @pytest.mark.parametrize(
        "command", sorted({*BANK_READINGS, *MODEL_READINGS, *DPF_TEMPERATURE_READINGS})
    )
    def test_every_capability_read_is_one_the_registry_knows(self, command: str) -> None:
        assert command in KNOWN_CAPABILITIES

    @pytest.mark.parametrize("capability", sorted(KNOWN_CAPABILITIES))
    def test_every_known_capability_is_read(self, capability: str) -> None:
        assert capability in ALL_READINGS

    @pytest.mark.parametrize("field", sorted(MODEL_READINGS.values()))
    def test_every_model_field_exists_on_the_state(self, field: str) -> None:
        assert hasattr(VehicleState(), field)

    def test_every_bank_lands_in_the_exhaust_family(self) -> None:
        assert set(BANK_READINGS.values()) == {EGT_FIELD}
        assert hasattr(VehicleState(), EGT_FIELD)
        assert EGT_FIELD in FAMILIES


class TestPoll:
    def test_stores_a_pint_quantity_as_a_float(self) -> None:
        poll, _ = poller({"RPM": SimpleNamespace(magnitude=1450.0, units="rpm")})

        state = poll.poll(VehicleState())

        assert state.rpm == pytest.approx(1450.0)

    def test_stores_a_bare_number(self) -> None:
        poll, _ = poller({"COOLANT_TEMP": 91})

        assert poll.poll(VehicleState()).coolant_temp == pytest.approx(91.0)

    def test_ignores_a_reading_that_is_not_numeric(self) -> None:
        poll, _ = poller({"RPM": "garbage"})

        assert poll.poll(VehicleState()).rpm is None

    def test_keeps_the_previous_value_when_a_frame_is_dropped(self) -> None:
        poll, _ = poller({})
        state = VehicleState(rpm=1200.0)

        assert poll.poll(state).rpm == pytest.approx(1200.0)

    def test_stores_a_raw_reading_untouched(self) -> None:
        status = SimpleNamespace(MIL=True, DTC_count=1)
        poll, _ = poller({"STATUS": status})

        assert poll.poll(VehicleState()).status is status

    def test_converts_trouble_codes(self) -> None:
        poll, _ = poller({"GET_DTC": [("P0401", "EGR flow insufficient"), ("P0100", "MAF")]})

        state = poll.poll(VehicleState())

        assert state.stored_codes == (
            TroubleCode("P0401", "EGR flow insufficient"),
            TroubleCode("P0100", "MAF"),
        )

    def test_converts_a_bare_code_without_a_description(self) -> None:
        poll, _ = poller({"GET_CURRENT_DTC": ["P0401"]})

        assert poll.poll(VehicleState()).pending_codes == (TroubleCode("P0401", ""),)

    def test_ignores_a_trouble_code_reading_that_is_not_a_list(self) -> None:
        poll, _ = poller({"GET_DTC": 7})

        assert poll.poll(VehicleState()).stored_codes == ()

    def test_returns_a_new_snapshot_and_leaves_the_old_one_alone(self) -> None:
        poll, _ = poller({"RPM": 900.0})
        state = VehicleState()

        swept = poll.poll(state)

        assert swept is not state
        assert swept.rpm == 900.0
        assert state.rpm is None

    def test_derives_net_boost_from_the_two_pressures(self) -> None:
        poll, _ = poller({"INTAKE_PRESSURE": 175.0, "BAROMETRIC_PRESSURE": 100.0})

        assert poll.poll(VehicleState()).net_boost == pytest.approx(75.0)


class TestExhaustBanks:
    """A bank PID answers its sensors at once; the banks form one family."""

    def test_holds_the_bank_under_its_number(self) -> None:
        bank = ExhaustTemperatures(1, (184.0, 202.5, 176.0, 150.0))
        poll, _ = poller({"EGT_BANK_1": bank})

        state = poll.poll(VehicleState())

        assert state.egt_banks == {1: bank}

    def test_a_sensor_the_bank_leaves_out_is_left_out(self) -> None:
        poll, _ = poller({"EGT_BANK_1": ExhaustTemperatures(1, (None, 202.5, None, None))})

        assert poll.poll(VehicleState()).egt_banks[1].fitted == ((2, 202.5),)

    def test_a_new_answer_replaces_the_bank_whole(self) -> None:
        # A sensor the new frame leaves out is gone, not carried over: the
        # bank is one reading, and the frame says which sensors it has.
        poll, _ = poller({"EGT_BANK_1": ExhaustTemperatures(1, (184.0, None, None, None))})
        state = VehicleState(egt_banks={1: ExhaustTemperatures(1, (180.0, 200.0, None, None))})

        state = poll.poll(state)

        assert state.egt_banks[1].sensors == (184.0, None, None, None)

    def test_both_banks_of_one_sweep_land_in_the_family(self) -> None:
        bank_1 = ExhaustTemperatures(1, (184.0, None, None, None))
        bank_2 = ExhaustTemperatures(2, (191.0, None, None, None))
        poll, _ = poller({"EGT_BANK_1": bank_1, "EGT_BANK_2": bank_2})

        assert poll.poll(VehicleState()).egt_banks == {1: bank_1, 2: bank_2}

    def test_a_bank_that_is_not_answered_is_kept_from_the_last_sweep(self) -> None:
        bank_1 = ExhaustTemperatures(1, (184.0, None, None, None))
        bank_2 = ExhaustTemperatures(2, (191.0, None, None, None))
        poll, _ = poller({"EGT_BANK_2": bank_2})

        state = poll.poll(VehicleState(egt_banks={1: bank_1}))

        assert state.egt_banks == {1: bank_1, 2: bank_2}

    def test_a_vehicle_vouching_for_one_bank_is_asked_for_that_one(self) -> None:
        poll, connection = poller()

        poll.poll(VehicleState(), catalog_of("EGT_BANK_2"))

        assert connection.asked == ["EGT_BANK_2"]

    def test_ignores_a_reading_that_is_not_a_bank(self) -> None:
        poll, _ = poller({"EGT_BANK_1": 184.0})

        assert poll.poll(VehicleState()).egt_banks == {}

    def test_keeps_the_previous_bank_when_the_frame_is_dropped(self) -> None:
        poll, _ = poller({})
        bank = ExhaustTemperatures(1, (184.0, None, None, None))

        assert poll.poll(VehicleState(egt_banks={1: bank})).egt_banks == {1: bank}

    def test_the_old_snapshot_keeps_its_banks(self) -> None:
        poll, _ = poller({"EGT_BANK_1": ExhaustTemperatures(1, (184.0, None, None, None))})
        state = VehicleState()

        poll.poll(state)

        assert state.egt_banks == {}

    def test_is_asked_for_only_when_the_catalog_lists_it(self) -> None:
        poll, connection = poller()

        poll.poll(VehicleState(), catalog_of("RPM"))

        assert "EGT_BANK_1" not in connection.asked

    def test_is_asked_for_when_the_vehicle_vouched_for_it(self) -> None:
        poll, connection = poller()

        poll.poll(VehicleState(), catalog_of("EGT_BANK_1"))

        assert connection.asked == ["EGT_BANK_1"]

    def test_a_displayed_family_promotes_every_bank(self) -> None:
        poll, connection = poller()
        poll.poll(VehicleState(), priority=("egt_banks",))
        connection.asked.clear()

        poll.poll(VehicleState(), priority=("egt_banks",))

        assert set(BANK_READINGS) <= set(connection.asked)


class TestDpfPressure:
    def test_holds_the_reading_whole(self) -> None:
        pressure = DpfPressure(differential=4.8, inlet=105.2, outlet=100.4)
        poll, _ = poller({"DPF_DIFFERENTIAL_PRESSURE": pressure})

        state = poll.poll(VehicleState())

        assert state.dpf_pressure is pressure
        assert state.dpf_differential_pressure_kpa == pytest.approx(4.8)

    def test_drops_a_negative_differential(self) -> None:
        poll, _ = poller({"DPF_DIFFERENTIAL_PRESSURE": DpfPressure(differential=-2.5)})

        assert poll.poll(VehicleState()).dpf_pressure is None

    def test_keeps_a_reading_without_a_differential(self) -> None:
        pressure = DpfPressure(inlet=105.2)
        poll, _ = poller({"DPF_DIFFERENTIAL_PRESSURE": pressure})

        assert poll.poll(VehicleState()).dpf_pressure is pressure

    def test_ignores_a_reading_that_is_not_a_pressure(self) -> None:
        poll, _ = poller({"DPF_DIFFERENTIAL_PRESSURE": 4.8})

        assert poll.poll(VehicleState()).dpf_pressure is None

    def test_keeps_the_previous_reading_when_the_frame_is_dropped(self) -> None:
        pressure = DpfPressure(differential=4.8)
        poll, _ = poller({})

        assert poll.poll(VehicleState(dpf_pressure=pressure)).dpf_pressure is pressure

    def test_is_read_at_the_medium_cadence(self) -> None:
        assert tier_of("DPF_DIFFERENTIAL_PRESSURE") is Tier.MEDIUM

    def test_a_displayed_filter_is_read_every_sweep(self) -> None:
        poll, connection = poller()
        poll.poll(VehicleState(), priority=("dpf_pressure",))
        connection.asked.clear()

        poll.poll(VehicleState(), priority=("dpf_pressure",))

        assert "DPF_DIFFERENTIAL_PRESSURE" in connection.asked


class TestDpfTemperatures:
    """Three capabilities, one place on the filter each, feed one family."""

    def test_picks_each_place_out_of_the_standard_frame(self) -> None:
        frame = DpfTemperatures(inlet=412.0, outlet=365.5)
        poll, _ = poller({"DPF_TEMP_INLET": frame, "DPF_TEMP_OUTLET": frame})

        assert poll.poll(VehicleState()).dpf_temperatures == DpfTemperatures(
            inlet=412.0, outlet=365.5
        )

    def test_a_place_the_frame_leaves_out_stays_unknown(self) -> None:
        frame = DpfTemperatures(inlet=412.0)
        poll, _ = poller({"DPF_TEMP_INLET": frame, "DPF_TEMP_OUTLET": frame})

        assert poll.poll(VehicleState()).dpf_temperatures == DpfTemperatures(inlet=412.0)

    def test_a_manufacturer_answers_one_place_as_a_bare_number(self) -> None:
        poll, _ = poller({"DPF_TEMP_INTERNAL": 390.0})

        assert poll.poll(VehicleState()).dpf_temperatures == DpfTemperatures(internal=390.0)

    def test_the_places_join_whatever_answered_them(self) -> None:
        poll, _ = poller(
            {"DPF_TEMP_INLET": DpfTemperatures(inlet=412.0), "DPF_TEMP_INTERNAL": 390.0}
        )

        assert poll.poll(VehicleState()).dpf_temperatures == DpfTemperatures(
            inlet=412.0, internal=390.0
        )

    def test_a_place_not_answered_this_sweep_is_kept(self) -> None:
        poll, _ = poller({"DPF_TEMP_INLET": DpfTemperatures(inlet=420.0)})
        held = VehicleState(dpf_temperatures=DpfTemperatures(inlet=412.0, outlet=365.5))

        assert poll.poll(held).dpf_temperatures == DpfTemperatures(inlet=420.0, outlet=365.5)

    def test_the_ecu_answering_replaces_a_stand_in_from_the_exhaust(self) -> None:
        poll, _ = poller({"DPF_TEMP_INLET": DpfTemperatures(inlet=420.0)})
        stand_in = DpfTemperatures(inlet=400.0, outlet=350.0, source=TemperatureSource.EXHAUST)

        state = poll.poll(VehicleState(dpf_temperatures=stand_in))

        assert state.dpf_temperatures == DpfTemperatures(inlet=420.0)

    def test_ignores_an_answer_that_is_not_a_temperature(self) -> None:
        poll, _ = poller({"DPF_TEMP_INLET": "hot", "DPF_TEMP_OUTLET": DpfTemperatures()})

        assert poll.poll(VehicleState()).dpf_temperatures is None

    @pytest.mark.parametrize("capability", sorted(DPF_TEMPERATURE_READINGS))
    def test_each_place_is_read_at_the_medium_cadence(self, capability: str) -> None:
        assert tier_of(capability) is Tier.MEDIUM

    def test_a_displayed_filter_promotes_every_place(self) -> None:
        poll, connection = poller()
        poll.poll(VehicleState(), priority=("dpf_temperatures",))
        connection.asked.clear()

        poll.poll(VehicleState(), priority=("dpf_temperatures",))

        assert set(DPF_TEMPERATURE_READINGS) <= set(connection.asked)


class TestDpfLoad:
    def test_holds_a_believable_load(self) -> None:
        load = DpfLoad(percent=42.0, soot_mass_g=18.4)
        poll, _ = poller({"DPF_SOOT_LOAD": load})

        assert poll.poll(VehicleState()).dpf_load == load

    def test_drops_what_is_out_of_range(self) -> None:
        poll, _ = poller({"DPF_SOOT_LOAD": DpfLoad(percent=140.0, soot_mass_g=18.4)})

        assert poll.poll(VehicleState()).dpf_load == DpfLoad(soot_mass_g=18.4)

    def test_keeps_the_last_load_when_nothing_believable_came(self) -> None:
        last = DpfLoad(percent=41.0)
        poll, _ = poller({"DPF_SOOT_LOAD": DpfLoad(percent=-5.0)})

        assert poll.poll(VehicleState(dpf_load=last)).dpf_load is last

    def test_ignores_a_reading_that_is_not_a_load(self) -> None:
        poll, _ = poller({"DPF_SOOT_LOAD": 42.0})

        assert poll.poll(VehicleState()).dpf_load is None

    def test_is_read_at_the_medium_cadence(self) -> None:
        assert tier_of("DPF_SOOT_LOAD") is Tier.MEDIUM


class TestTiers:
    def test_a_driving_reading_is_fast(self) -> None:
        assert tier_of("RPM") is Tier.FAST

    def test_a_session_wide_reading_is_slow(self) -> None:
        assert tier_of("CALIBRATION_ID") is Tier.SLOW

    def test_anything_else_falls_back_to_medium(self) -> None:
        assert tier_of("COOLANT_TEMP") is Tier.MEDIUM
        assert tier_of("NOT_A_COMMAND") is Tier.MEDIUM

    def test_the_tiers_only_name_commands_the_poller_reads(self) -> None:
        assert set(ALL_READINGS) >= FAST_COMMANDS
        assert set(ALL_READINGS) >= SLOW_COMMANDS

    def test_a_command_has_a_single_tier(self) -> None:
        assert not FAST_COMMANDS & SLOW_COMMANDS

    def test_all_readings_covers_the_six_maps(self) -> None:
        assert set(ALL_READINGS) == {
            *NUMERIC_READINGS,
            *RAW_READINGS,
            *CODE_READINGS,
            *BANK_READINGS,
            *MODEL_READINGS,
            *DPF_TEMPERATURE_READINGS,
        }

    def test_a_bank_is_read_at_the_medium_cadence(self) -> None:
        assert tier_of("EGT_BANK_1") is Tier.MEDIUM

    @pytest.mark.parametrize(
        ("sweep", "fast", "medium", "slow"),
        [
            (0, True, True, True),
            (1, True, False, False),
            (5, True, True, False),
            (59, True, False, False),
            (60, True, True, True),
        ],
    )
    def test_each_tier_comes_round_on_its_own_period(
        self, sweep: int, fast: bool, medium: bool, slow: bool
    ) -> None:
        assert is_due("RPM", sweep) is fast
        assert is_due("COOLANT_TEMP", sweep) is medium
        assert is_due("GET_DTC", sweep) is slow


class TestSweepCadence:
    def test_the_first_sweep_asks_for_everything(self) -> None:
        poll, connection = poller()

        poll.poll(VehicleState())

        assert set(connection.asked) == set(ALL_READINGS)

    def test_the_next_sweep_asks_only_for_the_fast_readings(self) -> None:
        poll, connection = poller()
        poll.poll(VehicleState())
        connection.asked.clear()

        poll.poll(VehicleState())

        assert set(connection.asked) == FAST_COMMANDS

    def test_the_medium_readings_come_back_round(self) -> None:
        poll, connection = poller()
        for _ in range(5):
            poll.poll(VehicleState())
        connection.asked.clear()

        poll.poll(VehicleState())

        assert "COOLANT_TEMP" in connection.asked
        assert "GET_DTC" not in connection.asked

    def test_a_skipped_reading_carries_over(self) -> None:
        poll, connection = poller({"COOLANT_TEMP": 91.0})
        state = poll.poll(VehicleState())

        connection.answers.clear()
        state = poll.poll(state)

        assert state.coolant_temp == pytest.approx(91.0)

    def test_each_poll_runs_inside_one_connection_sweep(self) -> None:
        poll, connection = poller()

        poll.poll(VehicleState())
        poll.poll(VehicleState())

        assert connection.sweeps == 2

    def test_the_sweep_count_follows_the_polls(self) -> None:
        poll, _ = poller()

        assert poll.sweep_count == 0
        poll.poll(VehicleState())
        assert poll.sweep_count == 1


class TestPriority:
    def test_a_displayed_reading_is_read_every_sweep(self) -> None:
        poll, connection = poller()
        poll.poll(VehicleState(), priority=("coolant_temp",))
        connection.asked.clear()

        poll.poll(VehicleState(), priority=("coolant_temp",))

        assert "COOLANT_TEMP" in connection.asked

    def test_a_displayed_slow_reading_is_read_every_sweep(self) -> None:
        poll, connection = poller()
        poll.poll(VehicleState(), priority=("stored_codes",))
        connection.asked.clear()

        poll.poll(VehicleState(), priority=("stored_codes",))

        assert "GET_DTC" in connection.asked

    def test_the_rest_keeps_its_cadence(self) -> None:
        poll, connection = poller()
        poll.poll(VehicleState(), priority=("coolant_temp",))
        connection.asked.clear()

        poll.poll(VehicleState(), priority=("coolant_temp",))

        assert "OIL_TEMP" not in connection.asked
        assert "RPM" in connection.asked

    def test_an_unknown_field_prioritises_nothing(self) -> None:
        poll, connection = poller()
        poll.poll(VehicleState(), priority=("not_a_field",))
        connection.asked.clear()

        poll.poll(VehicleState(), priority=("not_a_field",))

        assert set(connection.asked) == FAST_COMMANDS

    def test_is_due_promotes_a_displayed_field(self) -> None:
        assert is_due("GET_DTC", 1) is False
        assert is_due("GET_DTC", 1, priority=("stored_codes",)) is True


class TestLinkLoss:
    def test_a_silent_vehicle_does_not_lose_the_link(self) -> None:
        """The bug this class exists for: no answer is an answer.

        A vehicle declining every command it advertised is routine — the
        PIDs it reports as supported come from a bitmap that over-reports,
        and a car that is switched off answers nothing at all. Treating
        that as a broken cable dropped live sessions.
        """
        poll, connection = poller()

        poll.poll(VehicleState(), catalog_of(*ALL_READINGS))

        assert len(connection.asked) == len(ALL_READINGS)

    def test_the_counters_a_clear_resets_do_not_lose_the_link(self) -> None:
        # Right after mode 04 the whole counter block goes quiet at once,
        # which is more consecutive silences than the old threshold.
        silent = (
            "STATUS",
            "DISTANCE_W_MIL",
            "RUN_TIME_MIL",
            "WARMUPS_SINCE_DTC_CLEAR",
            "DISTANCE_SINCE_DTC_CLEAR",
            "TIME_SINCE_DTC_CLEARED",
        )
        answers = {command: 1.0 for command in ALL_READINGS if command not in silent}
        poll, _ = poller(answers)

        state = poll.poll(VehicleState(), catalog_of(*ALL_READINGS))

        assert state.rpm == pytest.approx(1.0)

    def test_gives_up_after_enough_commands_never_reach_the_vehicle(self) -> None:
        poll, _ = poller(failing=ALL_READINGS)

        with pytest.raises(LinkLost):
            poll.poll(VehicleState(), catalog_of(*ALL_READINGS))

    def test_stops_the_sweep_where_the_adapter_failed(self) -> None:
        poll, connection = poller(failing=ALL_READINGS)

        with pytest.raises(LinkLost):
            poll.poll(VehicleState(), catalog_of(*ALL_READINGS))

        assert len(connection.asked) == LINK_LOSS_FAILURES

    def test_an_answer_resets_the_failure_count(self) -> None:
        # Every fourth command fails to reach the vehicle: a flaky adapter,
        # not a dead one, and the sweep must run to the end.
        failing = [command for index, command in enumerate(ALL_READINGS) if index % 4]
        answers = {command: 1.0 for command in ALL_READINGS if command not in failing}
        poll, connection = poller(answers, failing=failing)

        poll.poll(VehicleState(), catalog_of(*ALL_READINGS))

        assert len(connection.asked) == len(ALL_READINGS)

    def test_an_abandoned_sweep_leaves_the_last_snapshot_untouched(self) -> None:
        poll, _ = poller(failing=ALL_READINGS)
        state = VehicleState(rpm=900.0)

        with pytest.raises(LinkLost):
            poll.poll(state, catalog_of(*ALL_READINGS))

        assert state.rpm == pytest.approx(900.0)

    def test_a_failure_counts_even_without_a_catalog(self) -> None:
        # Losing the adapter says nothing about capability discovery, so
        # the verdict cannot depend on it.
        poll, _ = poller(failing=ALL_READINGS)

        with pytest.raises(LinkLost):
            poll.poll(VehicleState())


class TestCatalogFiltering:
    def test_queries_only_the_supported_commands(self) -> None:
        poll, connection = poller({"RPM": 900.0})

        poll.poll(VehicleState(), catalog_of("RPM", "SPEED"))

        assert connection.asked == ["RPM", "SPEED"]

    def test_queries_everything_without_a_catalog(self) -> None:
        poll, connection = poller()

        poll.poll(VehicleState())

        assert len(connection.asked) == len(ALL_READINGS)

    def test_queries_everything_when_discovery_came_back_empty(self) -> None:
        poll, connection = poller()

        poll.poll(VehicleState(), CommandCatalog())

        assert "RPM" in connection.asked
