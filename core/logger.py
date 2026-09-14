# -*- coding: utf-8 -*-
"""공통 로깅 모듈 (재구축: 2026-09-12)

다른 PC 이력의 `core/logger.py`를 기능적으로 동등하게 새로 작성.
- 모든 core 모듈의 print → logging 전환용.
- 레벨: INFO / WARNING / ERROR / CRITICAL (DEBUG 포함).
- 콘솔 + 파일(archive/logs/app.log) 동시 출력.
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_DIR = Path(__file__).resolve().parent.parent / "archive" / "logs"
_LOG_FILE = _LOG_DIR / "app.log"
_configured = False
_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def setup_logging(level: str = "INFO", log_file: Path | None = None) -> None:
    """루트 설정을 1회 구성. 앱 시작 시 1회 호출 권장."""
    global _configured
    if _configured:
        return
    target = Path(log_file) if log_file else _LOG_FILE
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = RotatingFileHandler(
            target, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
    except OSError:  # 파일 불가 환경 → 콘솔만
        handler = logging.NullHandler()

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(fmt)

    console = logging.StreamHandler()
    console.setFormatter(
        logging.Formatter("[%(levelname)s] %(name)s: %(message)s")
    )

    root = logging.getLogger()
    root.setLevel(_LEVELS.get(level.upper(), logging.INFO))
    root.addHandler(handler)
    root.addHandler(console)
    _configured = True


def get_logger(name: str, level: str | None = None) -> logging.Logger:
    """모듈별 로거 반환. setup_logging 전에 호출돼도 동작."""
    logger = logging.getLogger(name)
    if level:
        logger.setLevel(_LEVELS.get(level.upper(), logging.INFO))
    return logger
