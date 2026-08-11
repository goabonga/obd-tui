# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the plain data models."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from obd_tui.models import (
    AdapterInfo,
    CommandCatalog,
    CommandInfo,
    ConnectionState,
    TroubleCode,
    VehicleState,
)


class TestAdapterInfo:
    def test_usb_id_joins_vid_and_pid(self) -> None:
        adapter = AdapterInfo(port="/dev/ttyUSB0", vid="0403", pid="6015")

        assert adapter.usb_id == "0403:6015"

    def test_usb_id_falls_back_for_a_port_without_usb_ids(self) -> None:
        adapter = AdapterInfo(port="/dev/rfcomm0")

        assert adapter.usb_id == "-:-"


class TestConnectionState:
    def test_str_is_the_footer_label(self) -> None:
        assert str(ConnectionState.NO_DEVICE) == "NO DEVICE"

    @pytest.mark.parametrize(
        ("state", "expected"),
        [
            (ConnectionState.CONNECTED, True),
            (ConnectionState.CONNECTING, False),
            (ConnectionState.DISCONNECTED, False),
            (ConnectionState.NO_DEVICE, False),
            (ConnectionState.FAILED, False),
        ],
    )
    def test_only_connected_is_live(self, state: ConnectionState, expected: bool) -> None:
        assert state.is_live is expected


class TestCommandCatalog:
    @staticmethod
    def _catalog() -> CommandCatalog:
        return CommandCatalog(
            modes={
                "Mode 01": [
                    CommandInfo("RPM", "0x0C", "Engine RPM", supported=True),
                    CommandInfo("SPEED", "0x0D", "Vehicle Speed", supported=False),
                ],
                "Mode 03": [CommandInfo("GET_DTC", description="Stored DTCs", supported=True)],
            }
        )

    def test_len_counts_every_known_command(self) -> None:
        assert len(self._catalog()) == 3

    def test_iteration_walks_modes_in_order(self) -> None:
        assert [command.name for command in self._catalog()] == ["RPM", "SPEED", "GET_DTC"]

    def test_supported_count_ignores_unsupported_commands(self) -> None:
        assert self._catalog().supported_count == 2

    def test_supported_names_lists_only_supported_commands(self) -> None:
        assert self._catalog().supported_names == frozenset({"RPM", "GET_DTC"})

    def test_supports_answers_per_command(self) -> None:
        catalog = self._catalog()

        assert catalog.supports("RPM")
        assert not catalog.supports("SPEED")
        assert not catalog.supports("UNKNOWN")

    def test_an_empty_catalog_is_empty(self) -> None:
        catalog = CommandCatalog()

        assert len(catalog) == 0
        assert catalog.supported_count == 0
        assert catalog.supported_names == frozenset()

    def test_a_command_defaults_to_unsupported(self) -> None:
        assert CommandInfo("RPM") == CommandInfo("RPM", "-", "", supported=False)


class TestVehicleState:
    def test_net_boost_is_manifold_pressure_above_ambient(self) -> None:
        state = VehicleState(intake_pressure=180.0, barometric_pressure=101.0)

        assert state.net_boost == pytest.approx(79.0)

    @pytest.mark.parametrize(
        ("intake", "baro"),
        [(None, 101.0), (180.0, None), (None, None)],
    )
    def test_net_boost_needs_both_pressures(self, intake: float | None, baro: float | None) -> None:
        assert VehicleState(intake_pressure=intake, barometric_pressure=baro).net_boost is None

    def test_status_properties_read_the_ecu_response(self) -> None:
        state = VehicleState(status=SimpleNamespace(MIL=True, DTC_count=2, ignition_type="spark"))

        assert state.mil_on is True
        assert state.code_count == 2
        assert state.ignition_type == "spark"

    def test_status_properties_are_none_without_a_reading(self) -> None:
        state = VehicleState()

        assert state.mil_on is None
        assert state.code_count is None
        assert state.ignition_type is None

    def test_status_properties_tolerate_a_partial_response(self) -> None:
        state = VehicleState(status=SimpleNamespace(MIL=False))

        assert state.mil_on is False
        assert state.code_count is None

    def test_trouble_code_lists_are_per_instance(self) -> None:
        first, second = VehicleState(), VehicleState()
        first.stored_codes.append(TroubleCode("P0401", "EGR flow insufficient"))

        assert second.stored_codes == []
