# -*- coding: utf-8 -*-
"""오늘의 명언/고사성어/한자 데이터 로더 (2026-09-12)

- data/quotes_data.json 을 읽는다.
- 오늘 날짜 기준으로 1개 항목을 골라 반환한다.
  - date_key가 오늘과 일치하면 우선 사용
  - 없으면 오늘 날짜 기반 순번으로 로테이션
  - 같은 날에 여러 항목이 있으면 그중 하나를 반환
- 클릭 시 의미/해설(meaning)을 반환한다.
- 유형별(quote/idiom/hanja) 조회, 태그 검색, 즐겨찾기 연동 보조를 제공한다.
"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib
from collections.abc import Sequence
from typing import Any

_DATA_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "quotes_data.json"

_loaded: list[dict[str, Any]] | None = None


def _load() -> list[dict[str, Any]]:
    global _loaded
    if _loaded is None:
        if not _DATA_PATH.exists():
            _loaded = []
            return _loaded
        raw = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
        _loaded = raw.get("items", [])
        if not isinstance(_loaded, list):
            _loaded = []
    return _loaded


def all_items() -> list[dict[str, Any]]:
    """전체 항목 목록(최신 로드본)."""
    return list(_load())


def by_id(item_id: str) -> dict[str, Any] | None:
    """id 로 항목 1개 찾기."""
    for it in _load():
        if it.get("id") == item_id:
            return it
    return None


def today_items() -> list[dict[str, Any]]:
    """date_key가 오늘인 항목들."""
    today = _today_key()
    out: list[dict[str, Any]] = []
    for it in _load():
        if it.get("date_key") == today:
            out.append(it)
    return out


def today_quote() -> dict[str, Any] | None:
    """오늘의 명언/고사성어/한자 1개 반환.

    - date_key 지정 항목이 있으면 그중 첫 번째
    - 없으면 전체 목록에서 오늘 날짜 기반으로 하나 선택
    """
    items = _load()
    if not items:
        return None

    # 1) 오늘 date_key 지정 항목 우선
    matched = today_items()
    if matched:
        # 여러 개면 첫 번째, 필요하면 나중에 랜덤/순환으로 확장
        return matched[0]

    # 2) 없으면 오늘 날짜 기준으로 로테이션
    idx = _rotate_index(len(items))
    return items[idx]


def _today_key() -> str:
    return _dt.date.today().strftime("%Y-%m-%d")


def _rotate_index(count: int) -> int:
    """오늘 날짜 기반으로 목록 내 인덱스를 하나 고른다.

    요일/일자를 섞어 매일 다른 항목이 보이도록 한다.
    """
    if count <= 0:
        return 0
    today = _dt.date.today()
    # 일자 기준 순환 + 요일 보정
    base = (today.year * 10000 + today.month * 100 + today.day) % count
    return base


def by_type(typ: str) -> list[dict[str, Any]]:
    """유형으로 필터링: quote, idiom, hanja 등."""
    return [it for it in _load() if (it.get("type") or "").strip().lower() == typ.strip().lower()]


def search(query: str, limit: int = 20) -> list[dict[str, Any]]:
    """텍스트/의미/태그에서 키워드 검색."""
    q = (query or "").strip().lower()
    if not q:
        return list(_load())[:limit]
    out: list[dict[str, Any]] = []
    for it in _load():
        hay = " ".join(str(it.get(k, "")) for k in ("text", "meaning", "source", "tags")).lower()
        if q in hay:
            out.append(it)
            if len(out) >= limit:
                break
    return out


def meaningful_text(item: dict[str, Any] | None) -> str:
    """클릭 시 보여줄 의미/해설 문자열."""
    if not item:
        return ""
    parts: list[str] = []
    parts.append(item.get("text", ""))
    meaning = item.get("meaning") or ""
    if meaning:
        parts.append(meaning)
    source = item.get("source") or ""
    if source:
        parts.append(f"— {source}")
    return "\n\n".join(parts)
