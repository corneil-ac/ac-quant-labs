import logging
from datetime import datetime as RealDatetime
from pathlib import Path

import logger_setup


class FakeDatetime:
    current = RealDatetime(2026, 8, 7, 23, 59)

    @classmethod
    def now(cls):
        return cls.current


def test_daily_logfile_rotation_uses_calendar_date(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(logger_setup, "datetime", FakeDatetime)
    logger = logger_setup.setup_logger("rotation-test")
    file_handler = next(
        handler for handler in logger.handlers
        if isinstance(handler, logger_setup.DailyNamedFileHandler)
    )
    logger.info("before midnight")
    FakeDatetime.current = RealDatetime(2026, 8, 8, 0, 1)
    file_handler.doRollover()
    logger.info("after midnight")
    for handler in logger.handlers:
        handler.flush()

    assert "before midnight" in Path("logs/2026-08-07.log").read_text()
    next_day = Path("logs/2026-08-08.log").read_text()
    assert "after midnight" in next_day
    assert "before midnight" not in next_day
    assert len(logger.handlers) == 2  # file plus uninterrupted console output

    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)
