# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for capability resolution and manufacturer detection."""

from __future__ import annotations

import obd
import pytest
from obd.protocols import ECU

from obd_tui.obd.manufacturers import PROFILES, GenericProfile, SuzukiProfile, detect
from obd_tui.obd.manufacturers.base import ManufacturerProfile
from obd_tui.obd.registry import capabilities, resolve
from obd_tui.obd.standard import STANDARD_COMMANDS


def proprietary(name: str) -> obd.OBDCommand:
    """Return a command the way a manufacturer might read a bank: mode 22."""
    return obd.OBDCommand(name, "the maker's way", b"22F412", 0, lambda messages: None, ECU.ENGINE)


PROPRIETARY_BANK_1 = proprietary("FAKE_EGT_BANK_1")
PROPRIETARY_BANK_2 = proprietary("FAKE_EGT_BANK_2")


class FakeProfile(ManufacturerProfile):
    """A manufacturer with its own way of reading both banks."""

    name = "Fake Motors"

    def supports(self, vin: str) -> bool:
        return vin.startswith("FAK")

    def command(self, capability: str) -> obd.OBDCommand | None:
        return {"EGT_BANK_1": PROPRIETARY_BANK_1, "EGT_BANK_2": PROPRIETARY_BANK_2}.get(capability)

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset({"EGT_BANK_1", "EGT_BANK_2"})


class TestResolve:
    def test_the_standard_wins_when_the_vehicle_vouches_for_it(self) -> None:
        command = resolve("EGT_BANK_1", frozenset({0x78}), FakeProfile())

        assert command is STANDARD_COMMANDS["EGT_BANK_1"]

    def test_falls_back_to_the_manufacturer_when_the_standard_is_not_vouched(self) -> None:
        command = resolve("EGT_BANK_1", frozenset(), FakeProfile())

        assert command is PROPRIETARY_BANK_1

    def test_falls_back_to_the_manufacturer_when_the_standard_has_no_pid(self) -> None:
        command = resolve("EGT_BANK_2", frozenset({0x78}), FakeProfile())

        assert command is PROPRIETARY_BANK_2

    def test_nothing_when_neither_answers(self) -> None:
        assert resolve("EGT_BANK_1", frozenset(), GenericProfile()) is None

    def test_a_generic_vehicle_gets_the_standard_and_nothing_else(self) -> None:
        assert resolve("EGT_BANK_1", frozenset({0x78}), GenericProfile()) is not None
        assert resolve("EGT_BANK_2", frozenset({0x78, 0x79}), GenericProfile()) is None

    def test_an_unknown_capability_goes_to_the_manufacturer(self) -> None:
        assert resolve("NOT_A_CAPABILITY", frozenset({0x78}), FakeProfile()) is None


class TestCapabilities:
    def test_lists_the_standard_ones_for_a_generic_vehicle(self) -> None:
        assert capabilities(GenericProfile()) == frozenset(STANDARD_COMMANDS)

    def test_adds_what_the_manufacturer_offers(self) -> None:
        assert capabilities(FakeProfile()) == frozenset(STANDARD_COMMANDS) | {"EGT_BANK_2"}
        assert "EGT_BANK_2" not in STANDARD_COMMANDS


class TestProfiles:
    def test_the_generic_profile_answers_no_capability(self) -> None:
        profile = GenericProfile()

        assert profile.supports("ANYTHING")
        assert profile.command("EGT_BANK_1") is None
        assert profile.capabilities == frozenset()

    def test_the_generic_profile_closes_the_list(self) -> None:
        assert isinstance(PROFILES[-1], GenericProfile)

    def test_every_profile_has_a_name(self) -> None:
        assert all(profile.name for profile in PROFILES)


class TestDetect:
    @pytest.mark.parametrize("vin", ["TSMLYE11S00000000", "JSAFJB43V00000000", "MA3FJB43S00000000"])
    def test_recognises_a_suzuki_by_its_vin(self, vin: str) -> None:
        assert isinstance(detect(vin), SuzukiProfile)

    def test_ignores_the_case_of_the_vin(self) -> None:
        assert isinstance(detect("tsmlye11s00000000"), SuzukiProfile)

    def test_an_unknown_make_is_generic(self) -> None:
        assert isinstance(detect("WVWZZZ1KZ00000000"), GenericProfile)

    def test_a_vehicle_without_a_vin_is_generic(self) -> None:
        assert isinstance(detect(None), GenericProfile)
        assert isinstance(detect(""), GenericProfile)

    def test_suzuki_answers_nothing_beyond_the_standard_yet(self) -> None:
        profile = SuzukiProfile()

        assert profile.name == "Suzuki"
        assert profile.command("EGT_BANK_2") is None
        assert profile.capabilities == frozenset()
