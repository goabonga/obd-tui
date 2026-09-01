# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for routing log records away from the terminal."""

from __future__ import annotations

import logging
import sys

import pytest

from obd_tui.logs import LEVEL, NOISY_LOGGERS, Notice, NoticeLog, route_to, severity_of


def record(name: str = "obd.elm327", level: int = logging.WARNING) -> logging.LogRecord:
    """Return a record shaped like the ones python-obd emits."""
    return logging.LogRecord(name, level, "elm327.py", 1, "Incorrect response from AT RV", (), None)


class TestSeverity:
    @pytest.mark.parametrize(
        ("level", "expected"),
        [
            (logging.DEBUG, "information"),
            (logging.INFO, "information"),
            (logging.WARNING, "warning"),
            (logging.ERROR, "error"),
            (logging.CRITICAL, "error"),
        ],
    )
    def test_maps_a_level_to_a_notification(self, level: int, expected: str) -> None:
        assert severity_of(level) == expected


class TestNoticeLog:
    def test_keeps_the_source_and_the_message(self) -> None:
        log = NoticeLog()

        log.emit(record())

        assert log.drain() == [Notice("obd.elm327", "Incorrect response from AT RV", "warning")]

    def test_draining_empties_the_queue(self) -> None:
        log = NoticeLog()
        log.emit(record())

        log.drain()

        assert log.drain() == []

    def test_drops_the_oldest_when_they_pile_up(self) -> None:
        log = NoticeLog(capacity=2)

        for _ in range(5):
            log.emit(record())

        assert len(log.drain()) == 2

    def test_ignores_what_is_not_worth_interrupting_for(self) -> None:
        log = NoticeLog()

        logger = logging.getLogger("obd_tui.test-below-level")
        logger.addHandler(log)
        logger.setLevel(logging.DEBUG)
        logger.info("just so you know")
        logger.removeHandler(log)

        assert log.drain() == []


class TestRouting:
    def test_takes_the_stderr_handler_python_obd_installs(self) -> None:
        import obd  # noqa: PLC0415 — the handler appears on import, which is the point

        assert obd.commands is not None
        obd_logger = logging.getLogger("obd")
        assert any(
            isinstance(handler, logging.StreamHandler) and handler.stream is sys.stderr
            for handler in obd_logger.handlers
        ), "python-obd is expected to write to stderr until routed"
        log = NoticeLog()

        restore = route_to(log)
        try:
            assert not any(
                isinstance(handler, logging.StreamHandler) for handler in obd_logger.handlers
            )
            assert log in obd_logger.handlers
        finally:
            restore()

    def test_gives_the_loggers_back_as_they_were(self) -> None:
        before = {name: list(logging.getLogger(name).handlers) for name in NOISY_LOGGERS}
        levels = {name: logging.getLogger(name).level for name in NOISY_LOGGERS}

        route_to(NoticeLog())()

        assert {name: list(logging.getLogger(name).handlers) for name in NOISY_LOGGERS} == before
        assert {name: logging.getLogger(name).level for name in NOISY_LOGGERS} == levels

    def test_a_routed_logger_reaches_the_queue(self) -> None:
        log = NoticeLog()
        restore = route_to(log, loggers=("obd_tui.test-routing",))
        try:
            logging.getLogger("obd_tui.test-routing").warning("the adapter went quiet")
        finally:
            restore()

        assert [notice.message for notice in log.drain()] == ["the adapter went quiet"]

    def test_raises_a_logger_that_would_stay_silent(self) -> None:
        logger = logging.getLogger("obd_tui.test-level")
        logger.setLevel(logging.NOTSET)

        restore = route_to(NoticeLog(), loggers=("obd_tui.test-level",))
        try:
            assert logger.level == LEVEL
        finally:
            restore()

        assert logger.level == logging.NOTSET

    def test_leaves_a_stricter_logger_alone(self) -> None:
        logger = logging.getLogger("obd_tui.test-strict")
        logger.setLevel(logging.CRITICAL)

        restore = route_to(NoticeLog(), loggers=("obd_tui.test-strict",))
        try:
            assert logger.level == logging.CRITICAL
        finally:
            restore()
