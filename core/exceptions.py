# -*- coding: utf-8 -*-
"""표준화된 에러 핸들링 모듈 (재구축: 2026-09-12)

다른 PC 이력의 `core/exceptions.py` 기능을 기능적으로 동등하게 새로 작성.
- 예외 계층: SchedulerError 기본 + DatabaseError/NetworkError/ConfigError/FileParseError
- safe_call / handle_error / retry_on_error 데코레이터
"""
from __future__ import annotations

import functools
import logging
import time

from core.logger import get_logger

log = get_logger(__name__)


class SchedulerError(Exception):
    """앱 공통 기본 예외"""


class DatabaseError(SchedulerError):
    """DB 접근/쿼리 오류"""


class NetworkError(SchedulerError):
    """네트워크(RSS/API) 오류"""


class ConfigError(SchedulerError):
    """설정 파일(config.json) 오류"""


class FileParseError(SchedulerError):
    """파일 파싱(RSS/XML/문서) 오류"""


def handle_error(err: Exception, context: str = "", fallback=None):
    """예외를 로깅하고 fallback 값을 반환하는 헬퍼.

    - UI 코드에서 try/except 중복을 줄이기 위한 표준 진입점.
    - fallback이 지정되면 그 값을, 없으면 None을 반환.
    """
    log.error("[%s] %s: %s", context or "에러", type(err).__name__, err)
    return fallback


def safe_call(func=None, *, context: str = "", fallback=None, log_traceback: bool = False):
    """예외를 삼켜서 fallback을 반환하는 데코레이터.

    사용:
        @safe_call(context="뉴스 수집", fallback=[])
        def fetch(...): ...
    """

    def _wrap(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as e:  # noqa: BLE001 - 표준화된 삼킴 지점
                if log_traceback:
                    log.exception("[%s] 처리 실패", context or fn.__name__)
                else:
                    log.error("[%s] %s: %s", context or fn.__name__, type(e).__name__, e)
                return fallback

        return wrapper

    if func is not None:  # @safe_call 형태(괄호 없음)
        return _wrap(func)
    return _wrap  # @safe_call(...) 형태


def retry_on_error(times: int = 3, delay: float = 1.0, exceptions=(Exception,)):
    """지정 예외 발생 시 times회, delay초 간격으로 재시도하는 데코레이터."""

    def _wrap(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last_err = None
            for attempt in range(1, times + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as e:  # noqa: PERF203
                    last_err = e
                    log.warning("[%s] 시도 %d/%d 실패: %s", fn.__name__, attempt, times, e)
                    if attempt < times and delay > 0:
                        time.sleep(delay)
            raise SchedulerError(f"{fn.__name__} 재시도 {times}회 실패") from last_err

        return wrapper

    return _wrap
