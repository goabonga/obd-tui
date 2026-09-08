# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the proprietary data identifiers."""

from __future__ import annotations

import pytest
from obd.protocols import ECU
from obd.protocols.protocol import Message

from obd_tui.obd.uds import Confidence, DataIdentifier, scaled

SOOT = DataIdentifier(
    capability="DPF_SOOT_LOAD",
    identifier=0xF412,
    length=2,
    decoder=scaled(0.1),
    unit="%",
    formula="raw / 10",
    ecu="engine",
    engines=frozenset({"D16AA"}),
    confidence=Confidence.EXPERIMENTAL,
    source="a fixture, not a vehicle",
)


def reply(*data: int, ecu: int = ECU.ENGINE) -> Message:
    message = Message([])
    message.data = bytearray(data)
    message.ecu = ecu
    return message


class TestDeclaration:
    def test_is_named_by_capability_and_identifier(self) -> None:
        assert SOOT.name == "DPF_SOOT_LOAD@F412"

    def test_builds_a_service_22_command(self) -> None:
        command = SOOT.command()

        assert command.command == b"22F412"
        assert command.name == SOOT.name
        assert "experimental" in command.desc
        assert "fixture" in command.desc

    def test_the_command_expects_no_fixed_size(self) -> None:
        """python-obd would pad or trim the reply to fit; a wrong length must be refused."""
        assert SOOT.command().bytes == 0

    def test_carries_its_provenance(self) -> None:
        assert SOOT.engines == {"D16AA"}
        assert SOOT.confidence is Confidence.EXPERIMENTAL
        assert SOOT.endianness == "big"
        assert SOOT.unit == "%"
        assert SOOT.formula


class TestDecode:
    def test_decodes_a_positive_response(self) -> None:
        assert SOOT.decode([reply(0x62, 0xF4, 0x12, 0x01, 0xA4)]) == pytest.approx(42.0)

    def test_runs_through_python_obd_as_a_command(self) -> None:
        response = SOOT.command()([reply(0x62, 0xF4, 0x12, 0x01, 0xA4)])

        assert response.value == pytest.approx(42.0)

    def test_refuses_a_negative_response(self) -> None:
        assert SOOT.decode([reply(0x7F, 0x22, 0x31)]) is None

    def test_refuses_a_reply_to_another_identifier(self) -> None:
        assert SOOT.decode([reply(0x62, 0xF4, 0x13, 0x01, 0xA4)]) is None

    def test_refuses_a_payload_too_short(self) -> None:
        assert SOOT.decode([reply(0x62, 0xF4, 0x12, 0x01)]) is None

    def test_refuses_a_payload_too_long(self) -> None:
        assert SOOT.decode([reply(0x62, 0xF4, 0x12, 0x01, 0xA4, 0x00)]) is None

    def test_refuses_an_empty_reply(self) -> None:
        assert SOOT.decode([reply()]) is None
        assert SOOT.decode([]) is None

    def test_a_reply_from_another_ecu_is_ignored(self) -> None:
        message = reply(0x62, 0xF4, 0x12, 0x01, 0xA4, ecu=ECU.TRANSMISSION)

        assert SOOT.command()([message]).is_null()


class TestScaled:
    def test_scales_and_offsets_a_big_endian_integer(self) -> None:
        assert scaled(0.1, -40.0)(bytes([0x01, 0xA4])) == pytest.approx(2.0)

    def test_reads_a_signed_integer_when_told_to(self) -> None:
        assert scaled(1.0, signed=True)(bytes([0xFF, 0xFE])) == -2.0
        assert scaled(1.0)(bytes([0xFF, 0xFE])) == 65534.0

    def test_the_confidence_levels_are_the_documented_ones(self) -> None:
        assert {level.value for level in Confidence} == {
            "validated",
            "experimental",
            "reverse-engineered",
        }
