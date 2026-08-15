# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the bounded reading history."""

from __future__ import annotations

import pytest

from obd_tui.models.history import (
    HISTORY_LENGTH,
    TRACKED_FIELDS,
    History,
    ReadingHistory,
)
from obd_tui.models.vehicle import VehicleState


class TestHistory:
    def test_starts_empty(self) -> None:
        history = History()

        assert len(history) == 0
        assert not history
        assert history.values == []
        assert history.latest is None

    def test_keeps_the_points_in_order(self) -> None:
        history = History()

        for value in (1.0, 2.0, 3.0):
            history.push(value)

        assert history.values == [1.0, 2.0, 3.0]
        assert history.latest == 3.0
        assert list(history) == [1.0, 2.0, 3.0]

    def test_drops_the_oldest_point_once_full(self) -> None:
        history = History(length=3)

        for value in (1.0, 2.0, 3.0, 4.0):
            history.push(value)

        assert history.values == [2.0, 3.0, 4.0]
        assert len(history) == 3

    def test_ignores_a_reading_the_vehicle_did_not_report(self) -> None:
        history = History()

        history.push(1.0)
        history.push(None)

        assert history.values == [1.0]

    def test_clearing_drops_every_point(self) -> None:
        history = History()
        history.push(1.0)

        history.clear()

        assert not history

    def test_defaults_to_five_minutes_of_one_second_sweeps(self) -> None:
        assert History().length == HISTORY_LENGTH == 300


class TestReadingHistory:
    def test_follows_the_tracked_fields(self) -> None:
        history = ReadingHistory()

        assert history.fields == TRACKED_FIELDS
        assert "rpm" in history
        assert "cvn" not in history

    @pytest.mark.parametrize("name", TRACKED_FIELDS)
    def test_every_tracked_field_exists_on_the_state(self, name: str) -> None:
        assert hasattr(VehicleState(), name)

    def test_records_a_sweep(self) -> None:
        history = ReadingHistory()

        history.record(VehicleState(rpm=900.0, coolant_temp=70.0))
        history.record(VehicleState(rpm=950.0, coolant_temp=71.0))

        assert history.series("rpm") == [900.0, 950.0]
        assert history.series("coolant_temp") == [70.0, 71.0]

    def test_skips_a_reading_the_vehicle_did_not_report(self) -> None:
        history = ReadingHistory()

        history.record(VehicleState(rpm=900.0))

        assert history.series("rpm") == [900.0]
        assert history.series("speed") == []

    def test_an_untracked_field_has_no_series(self) -> None:
        assert ReadingHistory().series("cvn") == []

    def test_clearing_drops_every_series(self) -> None:
        history = ReadingHistory()
        history.record(VehicleState(rpm=900.0))

        history.clear()

        assert history.series("rpm") == []

    def test_the_length_applies_to_every_series(self) -> None:
        history = ReadingHistory(length=2)

        for rpm in (1.0, 2.0, 3.0):
            history.record(VehicleState(rpm=rpm))

        assert history.series("rpm") == [2.0, 3.0]

    def test_the_followed_fields_can_be_chosen(self) -> None:
        history = ReadingHistory(fields=("rpm",))

        assert history.fields == ("rpm",)
        assert "coolant_temp" not in history
