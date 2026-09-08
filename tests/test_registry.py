# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for capability resolution and manufacturer detection."""

from __future__ import annotations

import obd
import pytest
from obd.protocols import ECU

from obd_tui.models.dpf import DpfRole
from obd_tui.obd.manufacturers import PROFILES, GenericProfile, SuzukiProfile, detect
from obd_tui.obd.manufacturers import suzuki as suzuki_module
from obd_tui.obd.manufacturers.base import ManufacturerProfile
from obd_tui.obd.registry import KNOWN_CAPABILITIES, MANUFACTURER_ONLY, capabilities, resolve
from obd_tui.obd.standard import STANDARD_COMMANDS
from obd_tui.obd.uds import Confidence, DataIdentifier, scaled


def proprietary(name: str) -> obd.OBDCommand:
    """Return a command the way a manufacturer might read a bank: mode 22."""
    return obd.OBDCommand(name, "the maker's way", b"22F412", 0, lambda messages: None, ECU.ENGINE)


PROPRIETARY_BANK_1 = proprietary("FAKE_EGT_BANK_1")
PROPRIETARY_BANK_2 = proprietary("FAKE_EGT_BANK_2")
# A capability the standard has no PID for at all.
PROPRIETARY_SOOT = proprietary("FAKE_DPF_SOOT_LOAD")


class FakeProfile(ManufacturerProfile):
    """A manufacturer with its own way of reading both banks."""

    name = "Fake Motors"

    def supports(self, vin: str) -> bool:
        return vin.startswith("FAK")

    def command(self, capability: str) -> obd.OBDCommand | None:
        return {
            "EGT_BANK_1": PROPRIETARY_BANK_1,
            "EGT_BANK_2": PROPRIETARY_BANK_2,
            "DPF_SOOT_LOAD": PROPRIETARY_SOOT,
        }.get(capability)

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset({"EGT_BANK_1", "EGT_BANK_2", "DPF_SOOT_LOAD"})


class TestResolve:
    def test_the_standard_wins_when_the_vehicle_vouches_for_it(self) -> None:
        command = resolve("EGT_BANK_1", frozenset({0x78}), FakeProfile())

        assert command is STANDARD_COMMANDS["EGT_BANK_1"]

    def test_falls_back_to_the_manufacturer_when_the_standard_is_not_vouched(self) -> None:
        command = resolve("EGT_BANK_1", frozenset(), FakeProfile())

        assert command is PROPRIETARY_BANK_1

    def test_falls_back_to_the_manufacturer_when_the_standard_has_no_pid(self) -> None:
        command = resolve("DPF_SOOT_LOAD", frozenset({0x78}), FakeProfile())

        assert command is PROPRIETARY_SOOT

    def test_bank_2_follows_the_same_rule_as_bank_1(self) -> None:
        assert (
            resolve("EGT_BANK_2", frozenset({0x79}), FakeProfile())
            is STANDARD_COMMANDS["EGT_BANK_2"]
        )
        assert resolve("EGT_BANK_2", frozenset({0x78}), FakeProfile()) is PROPRIETARY_BANK_2

    def test_nothing_when_neither_answers(self) -> None:
        assert resolve("EGT_BANK_1", frozenset(), GenericProfile()) is None

    def test_a_generic_vehicle_gets_the_standard_and_nothing_else(self) -> None:
        assert resolve("EGT_BANK_1", frozenset({0x78}), GenericProfile()) is not None
        assert resolve("EGT_BANK_2", frozenset({0x78}), GenericProfile()) is None
        assert resolve("DPF_SOOT_LOAD", frozenset({0x78, 0x79}), GenericProfile()) is None

    def test_an_unknown_capability_goes_to_the_manufacturer(self) -> None:
        assert resolve("NOT_A_CAPABILITY", frozenset({0x78}), FakeProfile()) is None


class TestKnownCapabilities:
    def test_the_standard_never_answers_a_manufacturer_only_capability(self) -> None:
        assert not MANUFACTURER_ONLY & set(STANDARD_COMMANDS)

    def test_the_known_ones_are_the_standard_and_the_manufacturer_only(self) -> None:
        assert frozenset(STANDARD_COMMANDS) | MANUFACTURER_ONLY == KNOWN_CAPABILITIES

    def test_the_internal_temperature_has_no_standard_slot(self) -> None:
        assert "DPF_TEMP_INTERNAL" in MANUFACTURER_ONLY
        assert "DPF_TEMP_INTERNAL" not in capabilities(GenericProfile())

    def test_a_generic_vehicle_is_not_offered_a_manufacturer_only_capability(self) -> None:
        assert "DPF_SOOT_LOAD" not in capabilities(GenericProfile())

    def test_a_manufacturer_can_answer_the_soot_load(self) -> None:
        assert resolve("DPF_SOOT_LOAD", frozenset(), FakeProfile()) is PROPRIETARY_SOOT


class TestCapabilities:
    def test_lists_the_standard_ones_for_a_generic_vehicle(self) -> None:
        assert capabilities(GenericProfile()) == frozenset(STANDARD_COMMANDS)

    def test_adds_what_the_manufacturer_offers(self) -> None:
        assert capabilities(FakeProfile()) == frozenset(STANDARD_COMMANDS) | {"DPF_SOOT_LOAD"}
        assert "DPF_SOOT_LOAD" not in STANDARD_COMMANDS


class TestProfiles:
    def test_the_generic_profile_answers_no_capability(self) -> None:
        profile = GenericProfile()

        assert profile.supports("ANYTHING")
        assert profile.command("EGT_BANK_1") is None
        assert profile.capabilities == frozenset()

    def test_a_profile_places_no_exhaust_sensor_by_default(self) -> None:
        assert GenericProfile().exhaust_sensor_role(1, 2) is None
        assert FakeProfile().exhaust_sensor_role(1, 2) is None

    def test_the_generic_profile_closes_the_list(self) -> None:
        assert PROFILES[-1] is GenericProfile

    def test_every_profile_has_a_name(self) -> None:
        assert all(cls.name for cls in PROFILES)

    def test_a_profile_carries_the_engine_it_was_bound_to(self) -> None:
        assert GenericProfile("D16AA").engine == "D16AA"
        assert GenericProfile().engine is None

    def test_a_profile_answers_from_its_identifiers(self) -> None:
        class Tabled(ManufacturerProfile):
            name = "Tabled"

            def supports(self, vin: str) -> bool:
                return True

            @property
            def identifiers(self) -> tuple[DataIdentifier, ...]:
                return (FIXTURE_SOOT,)

        profile = Tabled("D16AA")

        assert profile.capabilities == frozenset({"DPF_SOOT_LOAD"})
        assert profile.command("DPF_SOOT_LOAD").command == b"22F412"  # type: ignore[union-attr]
        assert profile.command("DPF_REGEN_STATUS") is None


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

    def test_binds_the_profile_to_the_declared_engine(self) -> None:
        assert detect("TSMLYE11S00000000", "D16AA").engine == "D16AA"
        assert detect(None, "D16AA").engine == "D16AA"
        assert detect("TSMLYE11S00000000").engine is None


FIXTURE_SOOT = DataIdentifier(
    capability="DPF_SOOT_LOAD",
    identifier=0xF412,
    length=2,
    decoder=scaled(0.1),
    unit="%",
    formula="raw / 10",
    ecu="engine",
    engines=frozenset({"D16AA"}),
    confidence=Confidence.EXPERIMENTAL,
    source="a test fixture, not a vehicle",
)

# Declared under one engine's table but naming another: never sent.
FIXTURE_MISFILED = DataIdentifier(
    capability="DPF_REGEN_STATUS",
    identifier=0xF413,
    length=1,
    decoder=scaled(1.0),
    unit="",
    formula="raw",
    ecu="engine",
    engines=frozenset({"K14C"}),
    confidence=Confidence.REVERSE_ENGINEERED,
    source="a test fixture, not a vehicle",
)


class TestSuzuki:
    """Suzuki's tables are empty until an identifier is validated; a fixture stands in."""

    @pytest.fixture
    def tables(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(suzuki_module, "ENGINES", {"D16AA": (FIXTURE_SOOT, FIXTURE_MISFILED)})
        monkeypatch.setattr(suzuki_module, "SENSOR_ROLES", {"D16AA": {(1, 2): DpfRole.INLET}})

    def test_declares_nothing_yet(self) -> None:
        assert suzuki_module.ENGINES == {}
        assert suzuki_module.SENSOR_ROLES == {}
        assert SuzukiProfile("D16AA").capabilities == frozenset()

    def test_answers_for_a_declared_engine(self, tables: None) -> None:
        profile = SuzukiProfile("D16AA")

        assert profile.capabilities == frozenset({"DPF_SOOT_LOAD"})
        assert profile.command("DPF_SOOT_LOAD").command == b"22F412"  # type: ignore[union-attr]

    def test_never_sends_an_identifier_to_an_engine_it_does_not_name(self, tables: None) -> None:
        profile = SuzukiProfile("D16AA")

        assert FIXTURE_MISFILED not in profile.identifiers
        assert profile.command("DPF_REGEN_STATUS") is None

    def test_an_unknown_engine_gets_nothing(self, tables: None) -> None:
        assert SuzukiProfile("K14C").identifiers == ()
        assert SuzukiProfile("K14C").command("DPF_SOOT_LOAD") is None

    def test_no_engine_gets_nothing(self, tables: None) -> None:
        assert SuzukiProfile().identifiers == ()
        assert SuzukiProfile().exhaust_sensor_role(1, 2) is None

    def test_places_the_sensors_of_a_declared_engine(self, tables: None) -> None:
        profile = SuzukiProfile("D16AA")

        assert profile.exhaust_sensor_role(1, 2) is DpfRole.INLET
        assert profile.exhaust_sensor_role(1, 1) is None
        assert SuzukiProfile("K14C").exhaust_sensor_role(1, 2) is None

    def test_the_standard_still_wins_on_a_suzuki(self, tables: None) -> None:
        profile = SuzukiProfile("D16AA")

        assert resolve("EGT_BANK_1", frozenset({0x78}), profile) is STANDARD_COMMANDS["EGT_BANK_1"]
        assert resolve("DPF_SOOT_LOAD", frozenset(), profile) is not None

    def test_is_named(self) -> None:
        assert SuzukiProfile().name == "Suzuki"
