# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Catalogue of the OBD-II commands a vehicle answers to."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field

NO_PID = "-"


@dataclass(frozen=True, slots=True)
class CommandInfo:
    """One OBD-II command and whether the connected vehicle supports it.

    Attributes:
        name: python-obd command name, e.g. ``RPM``.
        pid: Parameter id as ``0xNN``, or ``-`` for commands without one.
        description: Human-readable description from the command table.
        supported: Whether the vehicle reported the command as available.
    """

    name: str
    pid: str = NO_PID
    description: str = ""
    supported: bool = False


@dataclass(frozen=True, slots=True)
class CommandCatalog:
    """Every known command, grouped by OBD-II mode.

    The mapping preserves insertion order, so modes render in the order the
    discovery scan walked them.
    """

    modes: Mapping[str, Sequence[CommandInfo]] = field(default_factory=dict)

    def __iter__(self) -> Iterator[CommandInfo]:
        """Iterate over every command of every mode."""
        for commands in self.modes.values():
            yield from commands

    def __len__(self) -> int:
        """Return the number of known commands, supported or not."""
        return sum(len(commands) for commands in self.modes.values())

    @property
    def supported_count(self) -> int:
        """Return how many commands the vehicle reported as supported."""
        return sum(1 for command in self if command.supported)

    @property
    def supported_names(self) -> frozenset[str]:
        """Return the names of the supported commands."""
        return frozenset(command.name for command in self if command.supported)

    def supports(self, name: str) -> bool:
        """Return whether ``name`` is supported by the vehicle."""
        return name in self.supported_names
