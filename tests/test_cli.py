# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the command line entry point."""

from __future__ import annotations

import pytest

from obd_tui import __version__, cli


class FakeApp:
    """Records the session it was handed and never opens a terminal."""

    instances: list[FakeApp] = []

    def __init__(self, session: object) -> None:
        self.session = session
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

    def test_an_unknown_option_is_rejected(self) -> None:
        with pytest.raises(SystemExit) as exit_info:
            cli.build_parser().parse_args(["--nope"])

        assert exit_info.value.code == 2


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
