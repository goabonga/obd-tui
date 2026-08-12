# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the serial port detection service."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from obd_tui.services import detection
from obd_tui.services.detection import detect_adapter


@dataclass
class FakePort:
    """Stand-in for ``serial.tools.list_ports_common.ListPortInfo``."""

    device: str = "/dev/ttyUSB0"
    vid: int | None = None
    pid: int | None = None
    product: str | None = None
    manufacturer: str | None = None
    description: str | None = None


class TestDetectAdapter:
    def test_matches_a_known_usb_id(self) -> None:
        port = FakePort(device="/dev/ttyUSB1", vid=0x0403, pid=0x6015)

        adapter = detect_adapter([port])

        assert adapter is not None
        assert adapter.port == "/dev/ttyUSB1"
        assert adapter.usb_id == "0403:6015"

    @pytest.mark.parametrize(
        "port",
        [
            FakePort(product="vLinker MC+"),
            FakePort(manufacturer="Vgate"),
            FakePort(description="OBDLink SX"),
            FakePort(description="ELM327 v1.5 interface"),
        ],
        ids=["product", "manufacturer", "description", "elm327"],
    )
    def test_matches_a_known_descriptor_keyword(self, port: FakePort) -> None:
        assert detect_adapter([port]) is not None

    def test_keyword_matching_ignores_case(self) -> None:
        assert detect_adapter([FakePort(product="VLINKER FD")]) is not None

    def test_ignores_an_unrelated_serial_port(self) -> None:
        port = FakePort(vid=0x2341, pid=0x0043, product="Arduino Uno")

        assert detect_adapter([port]) is None

    def test_returns_the_first_match(self) -> None:
        ports = [
            FakePort(device="/dev/ttyACM0", product="Arduino Uno"),
            FakePort(device="/dev/ttyUSB0", product="vLinker MC+"),
            FakePort(device="/dev/ttyUSB1", product="ELM327"),
        ]

        adapter = detect_adapter(ports)

        assert adapter is not None
        assert adapter.port == "/dev/ttyUSB0"

    def test_returns_none_without_any_port(self) -> None:
        assert detect_adapter([]) is None

    def test_reports_a_bluetooth_port_without_usb_ids(self) -> None:
        port = FakePort(device="/dev/rfcomm0", description="OBDII bluetooth link")

        adapter = detect_adapter([port])

        assert adapter is not None
        assert adapter.vid is None
        assert adapter.pid is None
        assert adapter.usb_id == "-:-"

    def test_label_prefers_the_product_string(self) -> None:
        port = FakePort(product="vLinker MC+", description="USB Serial")

        adapter = detect_adapter([port])

        assert adapter is not None
        assert adapter.label == "vLinker MC+"

    def test_label_falls_back_to_the_description(self) -> None:
        adapter = detect_adapter([FakePort(description="ELM327 v1.5")])

        assert adapter is not None
        assert adapter.label == "ELM327 v1.5"

    def test_scans_the_system_ports_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            detection.list_ports, "comports", lambda: [FakePort(product="vLinker MC+")]
        )

        assert detect_adapter() is not None
