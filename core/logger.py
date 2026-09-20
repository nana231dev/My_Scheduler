# -*- coding: utf-8 -*-
"""공통 로깅 모듈 (재구축: 2026-09-12)

다른 PC 이력의 `core/logger.py`를 기능적으로 동등하게 새로 작성.
- 모든 core 모듈의 print → logging 전환용.
- 레벨: INFO / WARNING / ERROR / CRITICAL (DEBUG 포함).
- 콘솔 + 파일(archive/logs/app.log) 동시 출력.
"""
from __future__ import annotations

import logging
import re
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


# ── 인증키 마스킹 (2026-09-20 P0-6) ─────────────────────────
# app.log 에 API 키가 평문으로 남는 것을 막는다(2026-09-20 실측: serviceKey=… 평문 다수).
_SECRET_RE = re.compile(r"((?:[?&])(?:serviceKey|crtId)=)[^&\s]+", re.IGNORECASE)


def mask_secrets(text: str) -> str:
    """문자열에서 인증키 파라미터 값(serviceKey/crtId)을 '***'로 바꾼다."""
    try:
        return _SECRET_RE.sub(r"\1***", text)
    except (TypeError, ValueError):
        return "***"


class SecretMaskingFilter(logging.Filter):
    """모든 로그 레코드에서 인증키를 마스킹하는 필터(setup_logging의 각 핸들러에 부착)."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if record.args:
                # 인자까지 반영한 완성 문장으로 바꾼 뒤 마스킹한다.
                record.msg = record.getMessage()
                record.args = None
            if isinstance(record.msg, str):
                record.msg = mask_secrets(record.msg)
        except (TypeError, ValueError, AttributeError):
            pass
        return True


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
    handler.addFilter(SecretMaskingFilter())   # 인증키 마스킹 (P0-6)

    console = logging.StreamHandler()
    console.setFormatter(
        logging.Formatter("[%(levelname)s] %(name)s: %(message)s")
    )
    console.addFilter(SecretMaskingFilter())

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
