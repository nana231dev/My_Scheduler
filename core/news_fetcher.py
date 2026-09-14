# -*- coding: utf-8 -*-
"""뉴스/RSS 수집 모듈 (2026-09-05 추가)
외부 의존성 없이 Python 표준 라이브러리(urllib + xml.etree)만으로 RSS/Atom 피드 수집.
UI 스레드에서 직접 호출하면 화면이 멈드니 반드시 스레드에서 실행.

2026-09-05 검증 소스: 연합뉴스 종합/IT과학, 한겨레, 한국일간신문, 경향신문, 네이처, 테크크런치
"""
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import html
import re
from datetime import datetime

NEWS_SOURCES = [
    # --- 일반 ---
    {"name": "연합뉴스(종합)", "url": "https://www.yna.co.kr/rss/news.xml", "category": "일반"},
    {"name": "한겨레", "url": "https://www.hani.co.kr/rss/", "category": "일반"},
    # --- 정치 ---
    {"name": "연합뉴스(정치)", "url": "https://www.yna.co.kr/rss/politics.xml", "category": "정치"},
    {"name": "한겨레(정치)", "url": "https://www.hani.co.kr/rss/politics/", "category": "정치"},
    # --- 사회 ---
    {"name": "연합뉴스(사회)", "url": "https://www.yna.co.kr/rss/society.xml", "category": "사회"},
    {"name": "경향신문", "url": "https://www.khan.co.kr/rss/rssdata/total_news.xml", "category": "사회"},
    # --- 경제 ---
    {"name": "연합뉴스(경제)", "url": "https://www.yna.co.kr/rss/economy.xml", "category": "경제"},
    {"name": "한겨레(경제)", "url": "https://www.hani.co.kr/rss/economy/", "category": "경제"},
    {"name": "한국경제", "url": "https://www.hankyung.com/rss", "category": "경제"},
    {"name": "매일경제", "url": "https://www.mk.co.kr/rss/", "category": "경제"},
    # --- 부동산 (Google News 토픽) ---
    {"name": "Google 부동산", "url": "https://news.google.com/rss/search?q=%EB%B6%80%EB%8F%99%EC%82%B0&hl=ko&gl=KR&ceid=KR:ko", "category": "부동산"},
    # --- 재테크 (Google News 토픽) ---
    {"name": "Google 재테크", "url": "https://news.google.com/rss/search?q=%EC%9E%AC%ED%85%8C%ED%81%AC&hl=ko&gl=KR&ceid=KR:ko", "category": "재테크"},
    {"name": "Google 주식", "url": "https://news.google.com/rss/search?q=%EC%A3%BC%EC%8B%9D&hl=ko&gl=KR&ceid=KR:ko", "category": "재테크"},
    {"name": "이데일리", "url": "https://www.edaily.co.kr/rss/rss_0000000007.xml", "category": "재테크"},
    # --- 과학 ---
    {"name": "연합뉴스(IT과학)", "url": "https://www.yna.co.kr/rss/industry.xml", "category": "과학"},
    {"name": "네이처(nature)", "url": "https://www.nature.com/nature.rss", "category": "과학"},
    {"name": "NewScientist", "url": "https://www.newscientist.com/feed/home/", "category": "과학"},
    {"name": "ScienceDaily", "url": "https://www.sciencedaily.com/rss/all.xml", "category": "과학"},
    {"name": "PhysOrg", "url": "https://phys.org/rss-feed/", "category": "과학"},
    # --- IT ---
    {"name": "테크크런치(techcrunch)", "url": "https://techcrunch.com/feed/", "category": "IT"},
    {"name": "TheVerge", "url": "https://www.theverge.com/rss/index.xml", "category": "IT"},
    {"name": "Gizmodo", "url": "https://gizmodo.com/rss", "category": "IT"},
        # --- 건축 ---
    {"name": "ArchDaily", "url": "https://www.archdaily.com/rss", "category": "건축"},
    {"name": "Dezeen", "url": "https://www.dezeen.com/feed/", "category": "건축"},
    # --- 국제 ---
    {"name": "BBC News", "url": "http://feeds.bbci.co.uk/news/world/rss.xml", "category": "국제"},
    {"name": "CNN 국제", "url": "http://rss.cnn.com/rss/edition_world.rss", "category": "국제"},
    {"name": "알자지라", "url": "https://www.aljazeera.com/rss", "category": "국제"},
    {"name": "연합뉴스(국제)", "url": "https://www.yna.co.kr/rss/world.xml", "category": "국제"},
    # --- 문화/예술 ---
    {"name": "한겨레(문화)", "url": "https://www.hani.co.kr/rss/culture/", "category": "문화"},
    {"name": "경향신문(문화)", "url": "https://www.khan.co.kr/rss/rssdata/culture_news.xml", "category": "문화"},
    {"name": "오마이데일리", "url": "https://www.osservatoreroma.it/en/rss", "category": "문화"},
    # --- 교육 ---
    {"name": "한겨레(교육)", "url": "https://www.hani.co.kr/rss/health/", "category": "교육"},
    {"name": "Chosun 교육", "url": "https://news.chosun.com/svc/service_newspaper/rss_www_chosun_edu.xml", "category": "교육"},
    # --- 스포츠 ---
    {"name": "한겨레(스포츠)", "url": "https://www.hani.co.kr/rss/sports/", "category": "스포츠"},
    {"name": "조선일보 스포츠", "url": "https://news.biz.chosun.com/CPB/after5/journallist_21.html?cate=SP", "category": "스포츠"},
    # --- 건강/라이프 ---
    {"name": "한겨레(건강)", "url": "https://www.hani.co.kr/rss/health/", "category": "건강"},
    {"name": "BBC Health", "url": "http://feeds.bbci.co.uk/news/health/rss.xml", "category": "건강"},
    # --- 여행 ---
    {"name": "Google 여행", "url": "https://news.google.com/rss/search?q=여행&hl=ko&gl=KR&ceid=KR:ko", "category": "여행"},
    {"name": "National Geographic", "url": "https://www.nationalgeographic.com/rss/destinations/", "category": "여행"},
    # --- 생활 ---
    {"name": "한겨레(생활)", "url": "https://www.hani.co.kr/rss/society/", "category": "생활"},
    {"name": "Google 생활", "url": "https://news.google.com/rss/search?q=생활%20관리&hl=ko&gl=KR&ceid=KR:ko", "category": "생활"},
]

_HEADERS = {"User-Agent": "Mozilla/5.0 NewsAggregator/1.0"}
_STRIP_TAG = re.compile(r"<[^>]+>")


def _clean(text):
    if not text:
        return ""
    text = _STRIP_TAG.sub("", text)
    return html.unescape(text).strip()


def _pubdate(date_str):
    if not date_str:
        return ""
    for f in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S +0000",
              "%Y-%m-%dT%H:%M:%S%z", "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            return datetime.strptime(date_str.strip(), f).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            continue
    return date_str.strip()[:30]


def _normalize_xml(text):
    """XML에서 네임스페이스 선언/접두사를 모두 제거해 ET.fromstring이 파싱 가능하도록 함."""
    out = []
    for ln in text.splitlines():
        if re.match(r'<\?xml', ln):
            out.append(ln)
            continue
        ln = re.sub(r'\sxmlns(:\w+)?\s*=\s*"[^"]*"', '', ln)
        ln = re.sub(r'(<\/?)([a-zA-Z_][\w.-]*):', r'\1', ln)
        ln = re.sub(r'([a-zA-Z_][\w.-]*):([a-zA-Z_])', r'\2', ln)
        out.append(ln)
    return "\n".join(out)


def fetch_rss(url, timeout=8, max_items=15):
    """단일 RSS/Atom 피드 수집. 실패 시 {"error": str} 반환."""
    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        encoding = resp.headers.get_content_charset() or "utf-8"
        try:
            text = raw.decode(encoding, errors="replace")
        except (LookupError, TypeError):
            text = raw.decode("utf-8", errors="replace")

        cleaned = _normalize_xml(text)
        root = ET.fromstring(cleaned.lstrip())  # BOM/선행 공백 제거 (Dezeen 등)

        node_iter = root.findall(".//item")
        is_atom = False
        if not node_iter:
            node_iter = root.findall(".//entry")
            is_atom = True

        items = []
        for node in node_iter[:max_items]:
            title = (node.findtext("title") or "").strip()
            link = ""
            lt = node.find("link")
            if lt is not None:
                link = (lt.text or lt.get("href") or "").strip()
            if not link and is_atom:
                for l in node.findall("link"):
                    if l.get("rel") == "alternate":
                        link = (l.get("href") or "").strip()
                        break
            summary = node.findtext("description") or node.findtext("summary") or ""
            if not summary:
                ce = node.findtext("content:encoded")
                if ce:
                    summary = ce
            summary = _clean(summary)
            updated = _pubdate(node.findtext("pubDate") or node.findtext("updated") or "")
            if not link:
                link = (node.findtext("link") or "").strip()
            if not link:
                continue
            items.append({
                "title": _clean(title),
                "link": link,
                "description": summary,
                "pubDate": updated,
            })
        if not items:
            return {"error": "기사를 찾을 수 없습니다."}
        return {"items": items, "url": url}

    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code} ({url})"}
    except urllib.error.URLError as e:
        reason = e.reason
        if "getaddrinfo" in str(reason) or "Unknown host" in str(reason) or "Name or service" in str(reason):
            return {"error": "DNS/네트워크 연결 불가. 인터넷을 확인하세요."}
        return {"error": f"URL 오류: {reason}"}
    except ET.ParseError as e:
        return {"error": f"XML 파싱 실패: {e}"}
    except Exception as e:  # noqa: BLE001 - 스레드 풀 경계: 예상 외 오류도 error 결과로 (의도적)
        return {"error": f"{type(e).__name__}: {e}"}


def fetch_sources(sources=None, max_items=15):
    """여러 출처 RSS 수집(병렬) -> {name: result_dict} 반환 (원본 소스 순서 유지)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    if sources is None:
        sources = NEWS_SOURCES
    results = {}
    if not sources:
        return results
    with ThreadPoolExecutor(max_workers=min(6, len(sources))) as ex:
        fut_map = {ex.submit(fetch_rss, s["url"], 8, max_items): s["name"] for s in sources}
        for fut in as_completed(fut_map):
            results[fut_map[fut]] = fut.result()
    ordered = {}
    for s in sources:
        if s["name"] in results:
            ordered[s["name"]] = results[s["name"]]
    return ordered


def get_categories():
    """소스에 존재하는 카테고리 목록 (중복 제거, 등록 순)"""
    cats = []
    for s in NEWS_SOURCES:
        if s.get("category") and s["category"] not in cats:
            cats.append(s["category"])
    return cats


def get_sources_by_category(category):
    """카테고리로 소스 필터링. '전체'/빈값이면 전체 반환."""
    if not category or category == "전체":
        return NEWS_SOURCES
    return [s for s in NEWS_SOURCES if s.get("category") == category]


def get_source_names():
    return [s["name"] for s in NEWS_SOURCES]

def get_source_category(name):
    """소스 이름으로 카테고리 조회 (없으면 '일반')"""
    for s in NEWS_SOURCES:
        if s["name"] == name:
            return s.get("category", "일반")
    return "일반"

def build_search_sources(keyword):
    """검색어로 Google News 검색 RSS 소스 목록 생성.

    Google 뉴스의 검색어 RSS는 keyword가 자동으로 인코딩되어야 하므로
    urllib.parse.quote로 한글/특수문자를 안전하게 인코딩한다.
    """
    kw = urllib.parse.quote(keyword.strip())
    url = f"https://news.google.com/rss/search?q={kw}&hl=ko&gl=KR&ceid=KR:ko"
    return [{"name": f"검색: {keyword.strip()}", "url": url, "category": "검색"}]


if __name__ == "__main__":
    for s in NEWS_SOURCES:
        r = fetch_rss(s["url"])
        if "items" in r:
            print(f"OK   {s['name']}: {len(r['items'])}건 (e.g. {r['items'][0]['title'][:30]})")
        else:
            print(f"FAIL {s['name']}: {r['error']}")