"""로깅 설정 모듈 — 날짜별 파일 + 콘솔 동시 로깅."""

import logging
import os
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


def setup_logging():
    """날짜별 파일 + 콘솔 동시 로깅 설정.

    환경변수:
        LOG_LEVEL: 로그 레벨 (기본 INFO). DEBUG 시 상세 출력.
    """
    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)

    log_level = getattr(
        logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO
    )

    # 포맷: 시간 | 레벨 | 모듈 | 메시지
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 파일 핸들러 — 날짜별 자동 로테이션, 30일 보존
    file_handler = TimedRotatingFileHandler(
        log_dir / "bot.log",
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.suffix = "%Y-%m-%d"

    # 콘솔 핸들러
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # 루트 로거 설정
    root = logging.getLogger()
    root.setLevel(log_level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    # httpx 로그 레벨 조정 (API 콜 로그 너무 시끄러움)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext.Application").setLevel(logging.WARNING)
