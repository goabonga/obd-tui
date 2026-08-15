#!/usr/bin/env python3

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Retarget the top stanza of a debian/changelog at one Ubuntu series.

    reheader_changelog.py debian/changelog 0.2.0-1~noble1 noble

multicz owns the file: it prepends a stanza with the release's bullets on
every bump, under a single distribution. A PPA needs one upload per series,
each with its own version, so the header — and only the header — of the
newest stanza is rewritten here. The bullets, the trailer and every older
stanza are left exactly as they were.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# package (version) distribution; urgency=medium
HEADER = re.compile(r"^(?P<package>\S+) \((?P<version>[^)]+)\) (?P<series>\S+); (?P<rest>.*)$")


def retarget(changelog: str, version: str, series: str) -> str:
    """Return ``changelog`` with its newest stanza aimed at ``series``."""
    lines = changelog.splitlines()
    if not lines:
        raise ValueError("the changelog is empty")

    header = HEADER.match(lines[0])
    if header is None:
        raise ValueError(f"unreadable changelog header: {lines[0]!r}")

    lines[0] = f"{header['package']} ({version}) {series}; {header['rest']}"
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    """Rewrite the changelog named on the command line."""
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2

    path = Path(argv[0])
    try:
        path.write_text(retarget(path.read_text(encoding="utf-8"), argv[1], argv[2]))
    except (OSError, ValueError) as error:
        print(f"{path}: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - script entry point
    raise SystemExit(main(sys.argv[1:]))
