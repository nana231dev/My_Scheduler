# -*- coding: utf-8 -*-
"""뉴스 키워드 요약/트렌딩 모듈 (재구축: 2026-09-12)

다른 PC 이력의 `core/news_summarizer.py`를 기능적으로 동등하게 새로 작성.
- 뉴스 결과({출처명: {"items": [...] or "error": ...}})에서
  · 키워드 빈도 추출(한국어 2음절 이상 + 영어 단어, 불용어 제거)
  · 트렌딩 키워드 Top-N
  · 출처별 요약(기사 수 + 주요 키워드)
  · 키워드 매칭 필터
외부 의존성 없음 (표준 라이브러리만 사용).
"""
from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Callable, Iterable

from core.logger import get_logger

log = get_logger(__name__)

# ── 불용어 (한/영 일반·뉴스 빈출 기능어) ──
STOPWORDS = {
    "그리고", "하지만", "그러나", "따라서", "때문에", "위해", "대해", "관한",
    "있다", "있는", "했다", "한다", "이다", "된다", "했다가", "하는", "한",
    "에서", "으로", "하고", "했다는", "이번", "오늘", "어제", "내일", "그런",
    "이런", "저런", "무엇", "어떤", "것으로", "것을", "것이", "에서의",
    "기자", "뉴스", "속보", "전지역", "오전", "오후", "지난", "이후", "현재",
    "등을", "등이", "등의", "이를", "이에", "이와", "다가", "보도", "제보",
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is",
    "are", "was", "were", "be", "been", "with", "at", "by", "from", "as",
    "it", "its", "this", "that", "s", "new", "how", "what", "why",
    "com", "www", "http", "https", "jpg", "png",
}

# 단어 토큰: 한국어 2~30음절 또는 영어 단어
_TOKEN_RE = re.compile(r"[가-힣]{2,30}|[a-zA-Z]{2,30}")


def _extract_tokens(text: str) -> list[str]:
    """텍스트에서 불용어 제외한 단어 토큰 리스트."""
    if not text:
        return []
    tokens = _TOKEN_RE.findall(text)
    return [t.lower() if t.isascii() else t for t in tokens if t.lower() not in STOPWORDS]


def _all_items(results: dict) -> list[dict]:
    """fetch_sources 형식({출처: {"items": [...]}})에서 모든 기사 평탄화."""
    items: list[dict] = []
    for name, res in (results or {}).items():
        if not isinstance(res, dict):
            continue
        for it in res.get("items", []):
            row = dict(it)
            row.setdefault("source", name)
            items.append(row)
    return items


def extract_keywords(texts: Iterable[str], top_n: int = 10) -> list[tuple[str, int]]:
    """문자열 목록에서 키워드 빈도 Top-N."""
    counter: Counter[str] = Counter()
    for text in texts:
        counter.update(_extract_tokens(text))
    return counter.most_common(top_n)


def trending_keywords(results: dict, top_n: int = 15) -> list[tuple[str, int]]:
    """뉴스 전체(제목+요약)에서 트렌딩 키워드 Top-N."""
    items = _all_items(results)
    texts = [
        f"{it.get('title', '')} {it.get('description', '')}" for it in items
    ]
    return extract_keywords(texts, top_n=top_n)


def summarize_sources(results: dict, kw_per_source: int = 5) -> list[dict]:
    """출처별 요약: [{source, count, keywords: [(kw, n)]}] (기사수 내림차순)."""
    summary = []
    for name, res in (results or {}).items():
        items = res.get("items", []) if isinstance(res, dict) else []
        if not items:
            continue
        kws = extract_keywords(
            [f"{it.get('title', '')} {it.get('description', '')}" for it in items],
            top_n=kw_per_source,
        )
        summary.append({"source": name, "count": len(items), "keywords": kws})
    summary.sort(key=lambda s: s["count"], reverse=True)
    return summary


def match_keyword(item: dict, keyword: str) -> bool:
    """기사(제목/요약)에 키워드 포함 여부 (대소문자 무관)."""
    kw = (keyword or "").strip().lower()
    if not kw:
        return True
    hay = f"{item.get('title', '')} {item.get('description', '')}".lower()
    return kw in hay


def filter_by_keyword(results: dict, keyword: str) -> list[dict]:
    """키워드가 포함된 기사만 평탄화 반환 (출처명 포함)."""
    matched = []
    for it in _all_items(results):
        if match_keyword(it, keyword):
            matched.append(it)
    return matched


def format_report(results: dict, top_n: int = 15) -> str:
    """키워드 분석 보고서 문자열 (UI 팝업용)."""
    items = _all_items(results)
    lines = [f"📰 수집 기사 총 {len(items)}건", ""]

    trend = trending_keywords(results, top_n=top_n)
    if trend:
        lines.append("🔥 트렌딩 키워드 Top %d" % len(trend))
        chunks, cur = [], []
        for kw, n in trend:
            cur.append(f"{kw}({n})")
            if len(cur) >= 5:
                chunks.append("  ".join(cur))
                cur = []
        if cur:
            chunks.append("  ".join(cur))
        lines.extend(chunks)
        lines.append("")

    per = summarize_sources(results)
    if per:
        lines.append("📂 출처별 요약")
        for s in per:
            kws = " ".join(f"{k}({n})" for k, n in s["keywords"])
            lines.append(f"  • {s['source']}: {s['count']}건 | {kws}")

    if not trend and not per:
        lines.append("분석할 기사가 없습니다.")
    return "\n".join(lines)


# TF-IDF 스코어링(간단 버전): 문서 내 빈도 × 희소성 — 향후 확장용
def tfidf_keywords(results: dict, top_n: int = 15) -> list[tuple[str, float]]:
    """키워드 TF-IDF 점수 Top-N (로그 스케일 희소성 가중)."""
    items = _all_items(results)
    docs = [
        _extract_tokens(f"{it.get('title', '')} {it.get('description', '')}")
        for it in items
    ]
    docs = [d for d in docs if d]
    if not docs:
        return []
    n_docs = len(docs)
    df: Counter[str] = Counter()
    for doc in docs:
        df.update(set(doc))
    tf_total = Counter()
    for doc in docs:
        tf_total.update(doc)
    scores = {
        kw: (n / n_docs) * math.log(n_docs / df[kw] + 1)
        for kw, n in tf_total.items()
    }
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_n]
