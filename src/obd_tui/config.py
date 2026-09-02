# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""User configuration, read from a TOML file."""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from platformdirs import user_config_path

from obd_tui.views.units import UnitSystem

logger = logging.getLogger(__name__)

APP_NAME = "obd-tui"
CONFIG_FILE = "config.toml"

# Seconds between two sweeps of the vehicle's sensors.
DEFAULT_POLL_INTERVAL = 1.0

# A sweep faster than this floods the adapter; slower than this and the
# dashboard stops feeling live.
MIN_POLL_INTERVAL = 0.1
MAX_POLL_INTERVAL = 60.0

# Seconds between two attempts to bring a down link back up.
DEFAULT_RECONNECT_INTERVAL = 5.0


@dataclass(frozen=True, slots=True)
class Config:
    """Everything the user can set outside the command line.

    Attributes:
        port: Serial port to open, or ``None`` to scan for an adapter.
        units: Unit system the readings are shown in.
        poll_interval: Seconds between two sweeps.
    """

    port: str | None = None
    units: UnitSystem = UnitSystem.METRIC
    poll_interval: float = DEFAULT_POLL_INTERVAL

    def override(
        self,
        port: str | None = None,
        units: UnitSystem | None = None,
        poll_interval: float | None = None,
    ) -> Config:
        """Return a copy with the given values applied.

        Anything left as ``None`` keeps its configured value: this is how
        the command line wins over the file without having to know which
        of the file's settings were actually present.
        """
        changes: dict[str, Any] = {}
        if port is not None:
            changes["port"] = port
        if units is not None:
            changes["units"] = units
        if poll_interval is not None:
            changes["poll_interval"] = poll_interval
        return replace(self, **changes)


def config_path() -> Path:
    """Return the configuration file's path for this platform."""
    return user_config_path(APP_NAME, appauthor=False) / CONFIG_FILE


def load_config(path: Path | None = None) -> Config:
    """Read the configuration file, falling back to the defaults.

    A missing file is the normal case. A malformed one, an unknown key or a
    value of the wrong type is reported to the log and then ignored: a
    dashboard that starts with default settings is more useful than one
    that refuses to start.

    Args:
        path: File to read. Defaults to the per-user location.
    """
    source = config_path() if path is None else path
    try:
        raw = tomllib.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Config()
    except (OSError, tomllib.TOMLDecodeError):
        logger.warning("ignoring unreadable configuration at %s", source, exc_info=True)
        return Config()

    for key in raw.keys() - {"port", "units", "poll_interval"}:
        logger.warning("ignoring unknown configuration key %r", key)

    return Config(
        port=_port(raw.get("port")),
        units=_units(raw.get("units")),
        poll_interval=_interval(
            "poll_interval",
            raw.get("poll_interval"),
            DEFAULT_POLL_INTERVAL,
            MIN_POLL_INTERVAL,
            MAX_POLL_INTERVAL,
        ),
    )


def _port(value: Any) -> str | None:
    """Read the configured port, ignoring anything that is not one."""
    if value is None:
        return None
    if isinstance(value, str) and value:
        return value
    logger.warning("ignoring configured port %r: expected a device path", value)
    return None


def _units(value: Any) -> UnitSystem:
    """Read the configured unit system, ignoring an unknown name."""
    if value is None:
        return UnitSystem.METRIC
    try:
        return UnitSystem(str(value).lower())
    except ValueError:
        logger.warning(
            "ignoring configured units %r: expected %s",
            value,
            " or ".join(system.value for system in UnitSystem),
        )
        return UnitSystem.METRIC


def _interval(key: str, value: Any, default: float, lowest: float, highest: float) -> float:
    """Read a configured period in seconds, ignoring an unusable one."""
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        logger.warning("ignoring configured %s %r: expected a number", key, value)
        return default
    if not lowest <= value <= highest:
        logger.warning(
            "ignoring configured %s %r: expected %s to %s seconds", key, value, lowest, highest
        )
        return default
    return float(value)
