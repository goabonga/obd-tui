# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Route log records to the interface instead of the terminal.

A full-screen application owns the terminal, so anything written to stdout
or stderr lands on top of it — python-obd attaches a stderr handler to its
own logger the moment it is imported, and Python's last-resort handler
prints warnings from everything else. Both painted over the dashboard.

Records are collected here instead, and the application shows them as
notifications.
"""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Literal

# The loggers whose output would otherwise reach the terminal: python-obd's
# own, and ours.
NOISY_LOGGERS: tuple[str, ...] = ("obd", "obd_tui")

Severity = Literal["information", "warning", "error"]

# Records worth interrupting someone reading live data for.
LEVEL = logging.WARNING

# How many notices to keep when they arrive faster than they are shown. A
# failing adapter can log every sweep, and the oldest matter least.
CAPACITY = 20


@dataclass(frozen=True, slots=True)
class Notice:
    """One log record, ready to be shown.

    Attributes:
        source: The logger's name, e.g. ``obd.elm327`` — which part of the
            stack is complaining is most of the diagnosis.
        message: The formatted message.
        severity: A Textual notification severity.
    """

    source: str
    message: str
    severity: Severity


def severity_of(level: int) -> Severity:
    """Return the notification severity matching a logging level."""
    if level >= logging.ERROR:
        return "error"
    if level >= logging.WARNING:
        return "warning"
    return "information"


class NoticeLog(logging.Handler):
    """Collect log records for the interface to show.

    Args:
        capacity: How many unseen notices to keep before dropping the
            oldest.
    """

    def __init__(self, capacity: int = CAPACITY) -> None:
        super().__init__(level=LEVEL)
        self._notices: deque[Notice] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        """Store a record rather than writing it anywhere."""
        self._notices.append(
            Notice(
                source=record.name,
                message=self.format(record),
                severity=severity_of(record.levelno),
            )
        )

    def drain(self) -> list[Notice]:
        """Return the notices collected since the last call, oldest first."""
        drained = list(self._notices)
        self._notices.clear()
        return drained


def _writes_to_terminal(handler: logging.Handler) -> bool:
    """Return whether ``handler`` would paint over the interface."""
    return isinstance(handler, logging.StreamHandler)


def route_to(
    handler: logging.Handler, loggers: Iterable[str] = NOISY_LOGGERS
) -> Callable[[], None]:
    """Send the noisy loggers to ``handler`` and away from the terminal.

    Returns:
        A callable restoring every logger to how it was found. The library
        loggers are shared process state, so a session that ends — or a
        test — has to be able to put them back.
    """
    restore: list[Callable[[], None]] = []

    for name in loggers:
        logger = logging.getLogger(name)
        removed = [existing for existing in logger.handlers if _writes_to_terminal(existing)]
        for existing in removed:
            logger.removeHandler(existing)
        logger.addHandler(handler)

        # Below WARNING nothing is shown anyway; leaving the level alone
        # would let a DEBUG-configured logger flood the queue.
        previous_level = logger.level
        if previous_level == logging.NOTSET or previous_level < LEVEL:
            logger.setLevel(LEVEL)

        def undo(
            logger: logging.Logger = logger,
            removed: list[logging.Handler] = removed,
            previous_level: int = previous_level,
        ) -> None:
            logger.removeHandler(handler)
            for existing in removed:
                logger.addHandler(existing)
            logger.setLevel(previous_level)

        restore.append(undo)

    def restore_all() -> None:
        for undo in restore:
            undo()

    return restore_all
