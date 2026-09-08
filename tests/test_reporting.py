# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the dated report of a session."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from obd_tui import __version__
from obd_tui.models.commands import CommandCatalog, CommandInfo
from obd_tui.models.vehicle import TroubleCode
from obd_tui.services.reporting import Report, build_report, report_stem, write_report
from obd_tui.services.simulation import simulated_session
from obd_tui.views.panels import PANELS
from obd_tui.views.report import render_report
from obd_tui.views.units import UnitSystem

NOW = datetime(2026, 9, 8, 14, 30, 5, tzinfo=UTC)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def connected_session() -> object:
    """Return a demo session that has swept once."""
    session = simulated_session(clock=FakeClock())
    session.connect()
    session.refresh()
    return session


class TestReportStem:
    def test_dates_the_file_to_the_second(self) -> None:
        assert report_stem(NOW) == "obd-tui-report-20260908-143005"

    def test_the_report_goes_by_its_stem(self) -> None:
        assert Report(NOW, {}).stem == report_stem(NOW)


class TestBuildReport:
    def test_dates_and_versions_itself(self) -> None:
        data = build_report(connected_session(), NOW).data  # type: ignore[arg-type]

        assert data["generated_at"] == NOW.isoformat()
        assert data["version"] == __version__

    def test_describes_the_vehicle_as_recognised(self) -> None:
        session = connected_session()

        vehicle = build_report(session, NOW).data["vehicle"]  # type: ignore[arg-type]

        assert vehicle["state"] == "CONNECTED"
        assert vehicle["port"] == "/dev/obd-tui-demo"
        assert vehicle["usb_id"] == "0403:6015"
        assert vehicle["adapter"] == "obd-tui demo adapter"
        assert vehicle["manufacturer"] == "generic"
        assert vehicle["engine"] is None
        assert vehicle["vin"] is None

    def test_lists_the_catalogue_and_what_is_supported(self) -> None:
        session = connected_session()

        data = build_report(session, NOW).data  # type: ignore[arg-type]

        assert "RPM" in data["supported"]
        assert "EGT_BANK_1" in data["supported"]
        modes = data["catalog"]
        assert any(
            command["name"] == "RPM" and command["supported"]
            for command in modes["Mode 01 — Live data"]
        )

    def test_carries_the_latest_readings_and_the_history(self) -> None:
        session = connected_session()

        data = build_report(session, NOW).data  # type: ignore[arg-type]

        assert data["readings"]["rpm"] is not None
        assert data["history"]["rpm"] == [data["readings"]["rpm"]]
        assert set(data["history"]) == set(session.history.fields)  # type: ignore[attr-defined]

    def test_lists_the_trouble_codes(self) -> None:
        data = build_report(connected_session(), NOW).data  # type: ignore[arg-type]

        assert {
            "code": "P0401",
            "description": "Exhaust Gas Recirculation Flow Insufficient Detected",
        } in data["faults"]["stored"]
        assert data["faults"]["pending"][0]["code"] == "P0299"

    def test_an_idle_session_reports_nothing_but_says_so(self) -> None:
        session = simulated_session(clock=FakeClock())

        data = build_report(session, NOW).data

        assert data["vehicle"]["state"] == "DISCONNECTED"
        assert data["vehicle"]["port"] is None
        assert data["supported"] == []
        assert data["faults"] == {"stored": [], "pending": []}

    def test_is_json_serialisable(self) -> None:
        data = build_report(connected_session(), NOW).data  # type: ignore[arg-type]

        assert json.loads(json.dumps(data))["version"] == __version__


class TestRenderReport:
    def test_opens_with_the_vehicle(self) -> None:
        session = connected_session()
        report = build_report(session, NOW)  # type: ignore[arg-type]

        text = render_report(report.data, session.vehicle, session.catalog, UnitSystem.METRIC)  # type: ignore[attr-defined]

        assert text.startswith("# obd-tui report\n")
        assert f"by obd-tui {__version__}" in text
        assert "- Adapter: /dev/obd-tui-demo (0403:6015), obd-tui demo adapter" in text
        assert "- VIN: -" in text
        assert "- Engine: -" in text

    def test_lists_the_codes_with_their_description(self) -> None:
        session = connected_session()
        report = build_report(session, NOW)  # type: ignore[arg-type]

        text = render_report(report.data, session.vehicle, session.catalog, UnitSystem.METRIC)  # type: ignore[attr-defined]

        assert "    - `P0401` - Exhaust Gas Recirculation Flow Insufficient Detected" in text
        assert "- Pending:\n    - `P0299`" in text

    def test_says_none_when_there_is_no_code(self) -> None:
        session = simulated_session(clock=FakeClock())
        report = build_report(session, NOW)

        text = render_report(report.data, session.vehicle, session.catalog, UnitSystem.METRIC)

        assert "- Stored: none" in text
        assert "- Pending: none" in text

    def test_a_code_without_a_description_stands_alone(self) -> None:
        session = simulated_session(clock=FakeClock())
        report = build_report(session, NOW)
        report.data["faults"]["stored"] = [{"code": "P0401", "description": ""}]

        text = render_report(report.data, session.vehicle, session.catalog, UnitSystem.METRIC)

        assert "    - `P0401`\n" in text

    def test_renders_every_panel_as_it_stood(self) -> None:
        session = connected_session()
        report = build_report(session, NOW)  # type: ignore[arg-type]

        text = render_report(report.data, session.vehicle, session.catalog, UnitSystem.METRIC)  # type: ignore[attr-defined]

        for panel in PANELS:
            assert f"### {panel.title}\n" in text
        assert "RPM" in text
        assert "B1S1" in text

    def test_renders_in_the_units_asked(self) -> None:
        session = connected_session()
        report = build_report(session, NOW)  # type: ignore[arg-type]

        text = render_report(report.data, session.vehicle, session.catalog, UnitSystem.IMPERIAL)  # type: ignore[attr-defined]

        assert "°F" in text

    def test_counts_the_supported_commands(self) -> None:
        session = connected_session()
        report = build_report(session, NOW)  # type: ignore[arg-type]

        text = render_report(report.data, session.vehicle, session.catalog, UnitSystem.METRIC)  # type: ignore[attr-defined]

        supported = session.catalog.supported_count  # type: ignore[attr-defined]
        assert f"## Supported commands ({supported} / {len(session.catalog)})" in text  # type: ignore[attr-defined]
        assert "- EGT_BANK_1\n" in text


class TestWriteReport:
    def test_writes_json_and_markdown_named_by_the_moment(self, tmp_path: Path) -> None:
        report = Report(NOW, {"version": __version__})

        json_path, markdown_path = write_report(report, "# report\n", tmp_path)

        assert json_path == tmp_path / "obd-tui-report-20260908-143005.json"
        assert markdown_path == tmp_path / "obd-tui-report-20260908-143005.md"
        assert json.loads(json_path.read_text(encoding="utf-8")) == {"version": __version__}
        assert markdown_path.read_text(encoding="utf-8") == "# report\n"

    def test_creates_the_directory(self, tmp_path: Path) -> None:
        json_path, _ = write_report(Report(NOW, {}), "", tmp_path / "reports" / "sept")

        assert json_path.exists()

    def test_the_catalogue_of_a_real_session_survives_the_round_trip(self, tmp_path: Path) -> None:
        session = connected_session()
        report = build_report(session, NOW)  # type: ignore[arg-type]

        json_path, _ = write_report(report, "", tmp_path)

        back = json.loads(json_path.read_text(encoding="utf-8"))
        assert back["catalog"] == report.data["catalog"]
        assert CommandCatalog(modes={"Mode 01": [CommandInfo("RPM", supported=True)]}).supports(
            "RPM"
        )
        assert TroubleCode("P0401").code == "P0401"
