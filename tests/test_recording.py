# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the JSON Lines session recorder."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from obd_tui.models.vehicle import TroubleCode, VehicleState
from obd_tui.services.recording import SessionRecorder, as_row, utc_now

STAMP = datetime(2026, 8, 15, 10, 30, 0, tzinfo=UTC)


def recorder(path: Path) -> SessionRecorder:
    """Return a recorder writing to ``path`` with a fixed timestamp."""
    return SessionRecorder(path, timestamps=lambda: STAMP)


def lines(path: Path) -> list[dict[str, Any]]:
    """Return the recorded rows."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class TestAsRow:
    def test_keeps_the_readings_the_vehicle_answered(self) -> None:
        row = as_row(VehicleState(rpm=1450.0, coolant_temp=91.0))

        assert row["rpm"] == 1450.0
        assert row["coolant_temp"] == 91.0

    def test_keeps_a_missing_reading_as_null(self) -> None:
        assert as_row(VehicleState())["rpm"] is None

    def test_every_state_field_is_written(self) -> None:
        row = as_row(VehicleState())

        assert "cvn" in row
        assert "stored_codes" in row

    def test_derived_readings_are_written_too(self) -> None:
        row = as_row(VehicleState(intake_pressure=180.0, barometric_pressure=100.0))

        assert row["net_boost"] == 80.0

    def test_trouble_codes_become_objects(self) -> None:
        state = VehicleState(stored_codes=[TroubleCode("P0401", "EGR flow")])

        assert as_row(state)["stored_codes"] == [{"code": "P0401", "description": "EGR flow"}]

    def test_an_ecu_object_is_reduced_to_its_text(self) -> None:
        state = VehicleState(status=SimpleNamespace(MIL=True))

        assert isinstance(as_row(state)["status"], str)

    def test_the_row_is_json_serialisable(self) -> None:
        state = VehicleState(rpm=1450.0, status=SimpleNamespace(MIL=True))
        state.stored_codes.append(TroubleCode("P0401", "EGR flow"))

        assert json.loads(json.dumps(as_row(state)))["rpm"] == 1450.0


class TestSessionRecorder:
    def test_writes_one_line_per_sweep(self, tmp_path: Path) -> None:
        path = tmp_path / "session.jsonl"
        log = recorder(path)

        log.record(VehicleState(rpm=900.0))
        log.record(VehicleState(rpm=950.0))
        log.close()

        assert [row["rpm"] for row in lines(path)] == [900.0, 950.0]

    def test_stamps_every_line(self, tmp_path: Path) -> None:
        path = tmp_path / "session.jsonl"
        log = recorder(path)

        log.record(VehicleState())
        log.close()

        assert lines(path)[0]["time"] == STAMP.isoformat()

    def test_flushes_each_sweep(self, tmp_path: Path) -> None:
        path = tmp_path / "session.jsonl"
        log = recorder(path)

        log.record(VehicleState(rpm=900.0))

        assert lines(path)[0]["rpm"] == 900.0

    def test_creates_the_parent_directories(self, tmp_path: Path) -> None:
        path = tmp_path / "logs" / "today" / "session.jsonl"

        recorder(path).record(VehicleState())

        assert path.exists()

    def test_creates_nothing_until_the_first_sweep(self, tmp_path: Path) -> None:
        path = tmp_path / "session.jsonl"

        recorder(path)

        assert not path.exists()

    def test_appends_to_an_existing_recording(self, tmp_path: Path) -> None:
        path = tmp_path / "session.jsonl"
        first = recorder(path)
        first.record(VehicleState(rpm=900.0))
        first.close()

        second = recorder(path)
        second.record(VehicleState(rpm=950.0))
        second.close()

        assert [row["rpm"] for row in lines(path)] == [900.0, 950.0]

    def test_closing_twice_is_harmless(self, tmp_path: Path) -> None:
        log = recorder(tmp_path / "session.jsonl")
        log.record(VehicleState())

        log.close()
        log.close()

    def test_closing_before_writing_is_harmless(self, tmp_path: Path) -> None:
        recorder(tmp_path / "session.jsonl").close()

    def test_stamps_in_utc_by_default(self) -> None:
        assert utc_now().tzinfo is UTC
