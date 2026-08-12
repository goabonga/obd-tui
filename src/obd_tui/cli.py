# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Command line entry point."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from obd_tui import __version__
from obd_tui.app import ObdApp
from obd_tui.services.session import Session


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="obd-tui",
        description="Terminal dashboard for real-time OBD-II vehicle diagnostics.",
    )
    parser.add_argument(
        "--port",
        metavar="DEVICE",
        help="serial port of the adapter, e.g. /dev/ttyUSB0 (default: scan for one)",
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
    ObdApp(Session(port=args.port)).run()
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
