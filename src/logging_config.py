"""Logging configuration — daily rotating file + console output."""

import logging
import os
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


def setup_logging():
    """Configure daily rotating file logging plus console logging.

    Env vars:
        LOG_LEVEL: log level (default INFO). DEBUG enables verbose output.
    """
    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)

    log_level = getattr(
        logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO
    )

    # Format: time | level | module | message
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler — daily auto rotation, 30-day retention
    file_handler = TimedRotatingFileHandler(
        log_dir / "bot.log",
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.suffix = "%Y-%m-%d"

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # Root logger config
    root = logging.getLogger()
    root.setLevel(log_level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    # Quiet noisy httpx API logs
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext.Application").setLevel(logging.WARNING)
