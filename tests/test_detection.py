# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the serial port detection service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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

        assert detect_adapter([port], rfcomm_nodes=list) is None

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
        assert detect_adapter([], rfcomm_nodes=list) is None

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

    def test_returns_none_without_any_port_or_rfcomm_node(self) -> None:
        assert detect_adapter([], rfcomm_nodes=list) is None

    def test_scans_the_system_ports_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            detection.list_ports, "comports", lambda: [FakePort(product="vLinker MC+")]
        )

        assert detect_adapter() is not None


class TestBluetooth:
    def test_falls_back_to_a_bound_rfcomm_node(self) -> None:
        adapter = detect_adapter([], rfcomm_nodes=lambda: ["/dev/rfcomm0"])

        assert adapter is not None
        assert adapter.port == "/dev/rfcomm0"
        assert adapter.label == "RFCOMM"
        assert adapter.usb_id == "-:-"

    def test_prefers_a_recognised_usb_adapter(self) -> None:
        adapter = detect_adapter(
            [FakePort(device="/dev/ttyUSB0", product="vLinker MC+")],
            rfcomm_nodes=lambda: ["/dev/rfcomm0"],
        )

        assert adapter is not None
        assert adapter.port == "/dev/ttyUSB0"

    def test_takes_the_lowest_numbered_node(self) -> None:
        adapter = detect_adapter(
            [], rfcomm_nodes=lambda: ["/dev/rfcomm2", "/dev/rfcomm0", "/dev/rfcomm1"]
        )

        assert adapter is not None
        assert adapter.port == "/dev/rfcomm0"

    def test_the_default_scan_picks_up_bound_nodes_only(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "rfcomm0").touch()
        (tmp_path / "ttyS0").touch()
        monkeypatch.setattr(detection, "RFCOMM_DIRECTORY", tmp_path)

        assert sorted(detection._bound_rfcomm_nodes()) == [str(tmp_path / "rfcomm0")]

    def test_the_default_scan_looks_at_dev(self) -> None:
        assert str(detection.RFCOMM_DIRECTORY) == "/dev"

    def test_the_system_scan_is_used_when_no_nodes_are_given(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "rfcomm3").touch()
        monkeypatch.setattr(detection, "RFCOMM_DIRECTORY", tmp_path)

        adapter = detect_adapter([])

        assert adapter is not None
        assert adapter.port == str(tmp_path / "rfcomm3")
