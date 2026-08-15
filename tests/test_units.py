# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the unit table and its conversions."""

from __future__ import annotations

import pytest

from obd_tui.models.vehicle import VehicleState
from obd_tui.services.polling import ALL_READINGS
from obd_tui.views.units import (
    FIELD_QUANTITY,
    Quantity,
    UnitSystem,
    quantity_of,
)

IMPERIAL = UnitSystem.IMPERIAL
METRIC = UnitSystem.METRIC


class TestTable:
    @pytest.mark.parametrize("field", sorted(FIELD_QUANTITY))
    def test_every_measured_field_exists_on_the_state(self, field: str) -> None:
        assert hasattr(VehicleState(), field)

    @pytest.mark.parametrize("field", sorted(FIELD_QUANTITY))
    def test_every_measured_field_is_read_or_derived(self, field: str) -> None:
        assert field in set(ALL_READINGS.values()) | {"net_boost"}

    def test_an_unmeasured_field_converts_to_nothing(self) -> None:
        assert quantity_of("rpm") is Quantity.NONE
        assert quantity_of("not_a_field") is Quantity.NONE

    def test_both_systems_name_every_quantity(self) -> None:
        for system in UnitSystem:
            for quantity in Quantity:
                assert isinstance(system.suffix(quantity), str)


class TestMetric:
    def test_is_what_the_vehicle_reports(self) -> None:
        assert METRIC.convert(Quantity.TEMPERATURE, 90.0) == 90.0
        assert METRIC.convert(Quantity.SPEED, 100.0) == 100.0

    def test_labels_the_units_the_standard_uses(self) -> None:
        assert METRIC.suffix(Quantity.TEMPERATURE) == "°C"
        assert METRIC.suffix(Quantity.SPEED) == "km/h"
        assert METRIC.suffix(Quantity.PRESSURE) == "kPa"

    def test_an_unmeasured_quantity_has_no_suffix(self) -> None:
        assert METRIC.suffix(Quantity.NONE) == ""
        assert IMPERIAL.suffix(Quantity.NONE) == ""


class TestImperial:
    @pytest.mark.parametrize(
        ("quantity", "metric", "expected"),
        [
            (Quantity.TEMPERATURE, 100.0, 212.0),
            (Quantity.TEMPERATURE, 0.0, 32.0),
            (Quantity.SPEED, 100.0, 62.1371),
            (Quantity.DISTANCE, 100.0, 62.1371),
            (Quantity.PRESSURE, 100.0, 14.5038),
            (Quantity.VOLUME_RATE, 10.0, 2.64172),
        ],
    )
    def test_converts_each_quantity(
        self, quantity: Quantity, metric: float, expected: float
    ) -> None:
        assert IMPERIAL.convert(quantity, metric) == pytest.approx(expected)

    def test_leaves_an_unmeasured_quantity_alone(self) -> None:
        assert IMPERIAL.convert(Quantity.NONE, 1450.0) == 1450.0

    def test_labels_the_customary_units(self) -> None:
        assert IMPERIAL.suffix(Quantity.TEMPERATURE) == "°F"
        assert IMPERIAL.suffix(Quantity.SPEED) == "mph"
        assert IMPERIAL.suffix(Quantity.PRESSURE) == "psi"


def test_the_system_is_named_as_the_config_file_spells_it() -> None:
    assert str(METRIC) == "metric"
    assert UnitSystem("imperial") is IMPERIAL
