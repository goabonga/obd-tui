# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the user configuration file."""

from __future__ import annotations

from pathlib import Path

import pytest

from obd_tui.config import (
    DEFAULT_POLL_INTERVAL,
    DEFAULT_RECONNECT_INTERVAL,
    Config,
    config_path,
    load_config,
)
from obd_tui.views.units import UnitSystem


def write(path: Path, body: str) -> Path:
    """Write a configuration file and return its path."""
    path.write_text(body, encoding="utf-8")
    return path


class TestDefaults:
    def test_a_missing_file_gives_the_defaults(self, tmp_path: Path) -> None:
        config = load_config(tmp_path / "nowhere.toml")

        assert config == Config()
        assert config.port is None
        assert config.units is UnitSystem.METRIC
        assert config.poll_interval == DEFAULT_POLL_INTERVAL
        assert config.reconnect_interval == DEFAULT_RECONNECT_INTERVAL

    def test_an_empty_file_gives_the_defaults(self, tmp_path: Path) -> None:
        assert load_config(write(tmp_path / "c.toml", "")) == Config()

    def test_the_default_path_is_per_user(self) -> None:
        path = config_path()

        assert path.name == "config.toml"
        assert path.parent.name == "obd-tui"


class TestReading:
    def test_reads_every_setting(self, tmp_path: Path) -> None:
        path = write(
            tmp_path / "c.toml",
            'port = "/dev/ttyUSB1"\nunits = "imperial"\npoll_interval = 2.5\n',
        )

        config = load_config(path)

        assert config.port == "/dev/ttyUSB1"
        assert config.units is UnitSystem.IMPERIAL
        assert config.poll_interval == 2.5

    def test_reads_a_whole_number_interval(self, tmp_path: Path) -> None:
        config = load_config(write(tmp_path / "c.toml", "poll_interval = 2\n"))

        assert config.poll_interval == 2.0

    def test_units_are_case_insensitive(self, tmp_path: Path) -> None:
        config = load_config(write(tmp_path / "c.toml", 'units = "Imperial"\n'))

        assert config.units is UnitSystem.IMPERIAL


class TestTolerance:
    def test_ignores_an_unknown_key(self, tmp_path: Path) -> None:
        config = load_config(write(tmp_path / "c.toml", 'colour = "green"\nport = "/dev/x"\n'))

        assert config.port == "/dev/x"

    def test_ignores_malformed_toml(self, tmp_path: Path) -> None:
        assert load_config(write(tmp_path / "c.toml", "port = [unclosed\n")) == Config()

    def test_ignores_a_directory_in_place_of_the_file(self, tmp_path: Path) -> None:
        assert load_config(tmp_path) == Config()

    @pytest.mark.parametrize("body", ["port = 4", 'port = ""', "port = true"])
    def test_ignores_a_port_that_is_not_a_device_path(self, body: str, tmp_path: Path) -> None:
        assert load_config(write(tmp_path / "c.toml", body)).port is None

    def test_ignores_an_unknown_unit_system(self, tmp_path: Path) -> None:
        config = load_config(write(tmp_path / "c.toml", 'units = "furlongs"\n'))

        assert config.units is UnitSystem.METRIC

    @pytest.mark.parametrize(
        "body",
        [
            'poll_interval = "fast"',
            "poll_interval = 0.001",
            "poll_interval = 3600",
            "poll_interval = true",
        ],
    )
    def test_ignores_an_unusable_interval(self, body: str, tmp_path: Path) -> None:
        config = load_config(write(tmp_path / "c.toml", body))

        assert config.poll_interval == DEFAULT_POLL_INTERVAL

    def test_reads_the_reconnect_interval(self, tmp_path: Path) -> None:
        config = load_config(write(tmp_path / "c.toml", "reconnect_interval = 15\n"))

        assert config.reconnect_interval == 15.0

    @pytest.mark.parametrize(
        "body",
        [
            'reconnect_interval = "soon"',
            "reconnect_interval = 0.5",
            "reconnect_interval = 3600",
            "reconnect_interval = false",
        ],
    )
    def test_ignores_an_unusable_reconnect_interval(self, body: str, tmp_path: Path) -> None:
        config = load_config(write(tmp_path / "c.toml", body))

        assert config.reconnect_interval == DEFAULT_RECONNECT_INTERVAL


class TestOverride:
    def test_the_command_line_wins(self) -> None:
        config = Config(port="/dev/from-file", units=UnitSystem.METRIC, poll_interval=2.0)

        overridden = config.override(port="/dev/from-cli", units=UnitSystem.IMPERIAL)

        assert overridden.port == "/dev/from-cli"
        assert overridden.units is UnitSystem.IMPERIAL
        assert overridden.poll_interval == 2.0

    def test_the_command_line_can_override_the_interval(self) -> None:
        config = Config(poll_interval=2.0)

        assert config.override(poll_interval=0.5).poll_interval == 0.5

    def test_the_command_line_can_override_the_reconnect_interval(self) -> None:
        config = Config(reconnect_interval=20.0)

        assert config.override(reconnect_interval=2.0).reconnect_interval == 2.0

    def test_each_setting_is_overridden_on_its_own(self) -> None:
        config = Config(port="/dev/from-file", units=UnitSystem.IMPERIAL, poll_interval=2.0)

        overridden = config.override(poll_interval=0.5)

        assert overridden.port == "/dev/from-file"
        assert overridden.units is UnitSystem.IMPERIAL
        assert overridden.poll_interval == 0.5

    def test_nothing_given_keeps_the_configured_values(self) -> None:
        config = Config(port="/dev/from-file", poll_interval=2.0)

        assert config.override() == config

    def test_overriding_leaves_the_original_alone(self) -> None:
        config = Config(port="/dev/from-file")

        config.override(port="/dev/from-cli")

        assert config.port == "/dev/from-file"
