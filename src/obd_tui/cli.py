# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Command line entry point."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from obd_tui import __version__
from obd_tui.app import ObdApp
from obd_tui.config import config_path, load_config
from obd_tui.services.recording import SessionRecorder
from obd_tui.services.session import Session
from obd_tui.services.simulation import simulated_session
from obd_tui.views.units import UnitSystem


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="obd-tui",
        description="Terminal dashboard for real-time OBD-II vehicle diagnostics.",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--port",
        metavar="DEVICE",
        help="serial port of the adapter, e.g. /dev/ttyUSB0 (default: scan for one)",
    )
    source.add_argument(
        "--demo",
        action="store_true",
        help="run against a simulated vehicle, without any adapter",
    )
    parser.add_argument(
        "--units",
        type=UnitSystem,
        choices=list(UnitSystem),
        help="unit system for the readings (default: from the config file, else metric)",
    )
    parser.add_argument(
        "--poll-interval",
        metavar="SECONDS",
        type=float,
        help="seconds between two sweeps (default: from the config file, else 1)",
    )
    parser.add_argument(
        "--config",
        metavar="FILE",
        type=Path,
        help=f"configuration file to read (default: {config_path()})",
    )
    parser.add_argument(
        "--record",
        metavar="FILE",
        type=Path,
        help="append every sweep to FILE as JSON Lines",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the arguments and run the dashboard.

    Args:
        argv: Arguments to parse. Defaults to the process arguments.

    Returns:
        The process exit code.
    """
    args = build_parser().parse_args(argv)
    # The command line wins over the file, the file over the defaults.
    config = load_config(args.config).override(
        port=args.port, units=args.units, poll_interval=args.poll_interval
    )
    recorder = SessionRecorder(args.record) if args.record is not None else None
    session = (
        simulated_session(recorder=recorder)
        if args.demo
        else Session(port=config.port, recorder=recorder)
    )
    ObdApp(
        session,
        poll_interval=config.poll_interval,
        units=config.units,
        # Naming the port says which adapter to use; there is nothing left
        # to wait for before opening it.
        connect_on_start=args.port is not None,
    ).run()
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
