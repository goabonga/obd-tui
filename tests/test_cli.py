# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the command line entry point."""

from __future__ import annotations

import importlib
import json
import runpy
import sys
from pathlib import Path

import pytest

from obd_tui import __version__, cli
from obd_tui.services.simulation import SIMULATED_ADAPTER
from obd_tui.views.units import UnitSystem


class FakeApp:
    """Records what it was handed and never opens a terminal."""

    instances: list[FakeApp] = []

    def __init__(
        self,
        session: object,
        poll_interval: float = 1.0,
        units: UnitSystem = UnitSystem.METRIC,
    ) -> None:
        self.session = session
        self.poll_interval = poll_interval
        self.units = units
        self.ran = False
        FakeApp.instances.append(self)

    def run(self) -> None:
        self.ran = True


@pytest.fixture(autouse=True)
def fake_app(monkeypatch: pytest.MonkeyPatch) -> type[FakeApp]:
    """Replace the Textual app so main() stays headless."""
    FakeApp.instances = []
    monkeypatch.setattr(cli, "ObdApp", FakeApp)
    return FakeApp


class TestParser:
    def test_port_defaults_to_scanning(self) -> None:
        assert cli.build_parser().parse_args([]).port is None

    def test_port_can_be_given(self) -> None:
        assert cli.build_parser().parse_args(["--port", "/dev/ttyUSB1"]).port == "/dev/ttyUSB1"

    def test_version_prints_and_exits(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exit_info:
            cli.build_parser().parse_args(["--version"])

        assert exit_info.value.code == 0
        assert __version__ in capsys.readouterr().out

    def test_record_defaults_to_off(self) -> None:
        assert cli.build_parser().parse_args([]).record is None

    def test_units_default_to_the_configuration(self) -> None:
        assert cli.build_parser().parse_args([]).units is None

    def test_units_take_a_system_name(self) -> None:
        assert cli.build_parser().parse_args(["--units", "imperial"]).units is UnitSystem.IMPERIAL

    def test_an_unknown_unit_system_is_rejected(self) -> None:
        with pytest.raises(SystemExit) as exit_info:
            cli.build_parser().parse_args(["--units", "furlongs"])

        assert exit_info.value.code == 2

    def test_the_poll_interval_takes_seconds(self) -> None:
        assert cli.build_parser().parse_args(["--poll-interval", "2.5"]).poll_interval == 2.5

    def test_record_takes_a_path(self) -> None:
        assert cli.build_parser().parse_args(["--record", "a.jsonl"]).record == Path("a.jsonl")

    def test_an_unknown_option_is_rejected(self) -> None:
        with pytest.raises(SystemExit) as exit_info:
            cli.build_parser().parse_args(["--nope"])

        assert exit_info.value.code == 2

    def test_demo_defaults_to_off(self) -> None:
        assert cli.build_parser().parse_args([]).demo is False

    def test_demo_and_port_are_mutually_exclusive(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exit_info:
            cli.build_parser().parse_args(["--demo", "--port", "/dev/ttyUSB0"])

        assert exit_info.value.code == 2
        assert "not allowed with" in capsys.readouterr().err


class TestModuleEntryPoint:
    """`python -m obd_tui`, the form the documentation gives for a checkout."""

    def test_importing_it_starts_nothing(self) -> None:
        module = importlib.import_module("obd_tui.__main__")

        assert module.main is cli.main

    def test_runs_the_command_line(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "argv", ["obd-tui", "--version"])
        # runpy warns when the module it is about to execute is already
        # imported, which another test in this class does.
        monkeypatch.delitem(sys.modules, "obd_tui.__main__", raising=False)

        with pytest.raises(SystemExit) as exit_info:
            runpy.run_module("obd_tui", run_name="__main__")

        assert exit_info.value.code == 0
        assert __version__ in capsys.readouterr().out


class TestMain:
    def test_runs_the_dashboard(self, fake_app: type[FakeApp]) -> None:
        assert cli.main([]) == 0
        assert fake_app.instances[0].ran

    def test_scans_for_an_adapter_by_default(self, fake_app: type[FakeApp]) -> None:
        cli.main([])

        assert fake_app.instances[0].session._requested_port is None  # type: ignore[attr-defined]

    def test_passes_the_requested_port_to_the_session(self, fake_app: type[FakeApp]) -> None:
        cli.main(["--port", "/dev/rfcomm0"])

        session = fake_app.instances[0].session
        assert session._requested_port == "/dev/rfcomm0"  # type: ignore[attr-defined]

    def test_records_nothing_by_default(self, fake_app: type[FakeApp]) -> None:
        cli.main([])

        assert fake_app.instances[0].session._recorder is None  # type: ignore[attr-defined]

    def test_record_logs_every_sweep_to_the_given_file(
        self, fake_app: type[FakeApp], tmp_path: Path
    ) -> None:
        path = tmp_path / "drive.jsonl"

        cli.main(["--demo", "--record", str(path)])

        session = fake_app.instances[0].session
        session.connect()  # type: ignore[attr-defined]
        session.refresh()  # type: ignore[attr-defined]

        assert json.loads(path.read_text(encoding="utf-8"))["rpm"] is not None

    def test_reads_the_settings_from_the_configuration_file(
        self, fake_app: type[FakeApp], tmp_path: Path
    ) -> None:
        config = tmp_path / "config.toml"
        config.write_text('units = "imperial"\npoll_interval = 3\n', encoding="utf-8")

        cli.main(["--config", str(config)])

        assert fake_app.instances[0].units is UnitSystem.IMPERIAL
        assert fake_app.instances[0].poll_interval == 3.0

    def test_the_command_line_wins_over_the_file(
        self, fake_app: type[FakeApp], tmp_path: Path
    ) -> None:
        config = tmp_path / "config.toml"
        config.write_text('port = "/dev/from-file"\nunits = "imperial"\n', encoding="utf-8")

        cli.main(["--config", str(config), "--port", "/dev/from-cli", "--units", "metric"])

        session = fake_app.instances[0].session
        assert session._requested_port == "/dev/from-cli"  # type: ignore[attr-defined]
        assert fake_app.instances[0].units is UnitSystem.METRIC

    def test_falls_back_to_the_defaults_without_a_file(self, fake_app: type[FakeApp]) -> None:
        cli.main(["--config", "/nowhere/obd-tui.toml"])

        assert fake_app.instances[0].units is UnitSystem.METRIC
        assert fake_app.instances[0].poll_interval == 1.0

    def test_demo_runs_against_the_simulated_vehicle(self, fake_app: type[FakeApp]) -> None:
        cli.main(["--demo"])

        session = fake_app.instances[0].session
        session.connect()  # type: ignore[attr-defined]

        assert session.adapter == SIMULATED_ADAPTER  # type: ignore[attr-defined]
        assert session.refresh().rpm is not None  # type: ignore[attr-defined]
