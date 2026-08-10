import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from datetime import datetime


class DailyNamedFileHandler(TimedRotatingFileHandler):
    """Rotate at midnight while keeping the active file named for its day."""

    def __init__(self, log_dir: Path):
        self.log_dir = log_dir.resolve()
        filename = self.log_dir / f"{datetime.now().strftime('%Y-%m-%d')}.log"
        super().__init__(filename, when="midnight", interval=1, backupCount=0,
                         encoding="utf-8", delay=False)

    def doRollover(self):
        if self.stream:
            self.stream.close()
            self.stream = None
        current_time = int(__import__("time").time())
        self.baseFilename = str(
            self.log_dir / f"{datetime.now().strftime('%Y-%m-%d')}.log"
        )
        if not self.delay:
            self.stream = self._open()
        self.rolloverAt = self.computeRollover(current_time)


def setup_logger(name: str = "pair_bot_v2") -> logging.Logger:
    Path("logs").mkdir(exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = DailyNamedFileHandler(Path("logs"))
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
