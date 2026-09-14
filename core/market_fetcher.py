# ───────────────────── core/market_fetcher.py ─────────────────────
from __future__ import annotations
import urllib.parse
import urllib.request
import json
from datetime import date, timedelta

from core.logger import get_logger

# 2026-09-14: 모듈 임포트 시 sys.stdout을 재구성하던 코드는 제거했다.
# 이전 코드는 Temp 진단 스크립트 등에서 "I/O operation on closed file" 오류를
# 유발했고, 콘솔 한글 출력은 run_app.bat(chcp 65001 + PYTHONIOENCODING)에서 처리한다.

log = get_logger(__name__)

# ── 공공데이터포털(금융위원회) 증권 시세 실측 Endpoint (2026-09-13 확인) ──
# 운영 경로: https://apis.data.go.kr/1160100/GetStockSecuritiesInfoService_V2/getStockPriceInfo_V2
# 인증키는 config.json의 fss_stock 값을 그대로 사용한다.
_GOKR_STOCK_BASE = "https://apis.data.go.kr/1160100/GetStockSecuritiesInfoService_V2"
_GOKR_STOCK_OP   = "getStockPriceInfo_V2"

# 실측 응답 JSON 항목 키 (public API 응답 기준)
_GOKR_STOCK_FIELDS = (
    "basDt", "srtnCd", "isinCd", "itmsNm", "mrktCtg",
    "clpr", "vs", "fltRt", "mkp", "hipr", "lopr",
    "trqu", "trPrc", "lstgStCnt", "mrktTotAmt",
)

# UI 표준 형태로 매핑할 때 참고할 별칭/환산 규칙
# - symbol: 종목 코드(srtnCd 우선)
# - name: itmsNm
# - price: clpr(종가)
# - change: vs(전일대비 금액)
# - change_pct: fltRt(등락률)
# - open/high/low: mkp/hipr/lopr
# - volume: trqu
# - market_cap: mrktTotAmt
def _gokr_to_ui(item: dict) -> dict:
    """공공데이터포털 주식 시세 항목 하나를 UI 표준 형태로 변환"""
    if not isinstance(item, dict):
        return {}
    price = _pick(item, ("clpr",))
    change_raw = _pick(item, ("vs",))
    change_pct_raw = _pick(item, ("fltRt",))
    name_raw = _pick(item, ("itmsNm", "isinNm", "cmpyNm", "name", "korSecnNm"))
    name = _clean_kor(name_raw) if name_raw else ""
    return {
        "symbol": _pick(item, ("srtnCd", "isinCd", "shortCode", "code")),
        "name": name,
        "price": price,
        "change": change_raw,
        "change_pct": _fmt_pct(change_pct_raw),
        "open": _pick(item, ("mkp", "open", "startPrice")),
        "high": _pick(item, ("hipr", "high", "highPrice")),
        "low": _pick(item, ("lopr", "low", "lowPrice")),
        "volume": _pick(item, ("trqu", "volume", "trdqnt")),
        "market_cap": _fmt_market_cap(item),
        "market": _pick(item, ("mrktCtg", "marketType", "mrktTp")),
        "base_date": _pick(item, ("basDt", "basDtNm", "date")),
        "raw": item,
    }

def _clean_kor(s: str) -> str:
    """표시용 문자열 정리 (2026-09-14: 한글 보존 방향으로 재작성).

    API(itmsNm 등)의 종목명은 정상 유니코드 한글이므로 그대로 보존하고,
    인코딩 손상 대체 문자(U+FFFD)와 제어 문자만 제거한다.
    Tkinter UI는 유니코드 한글을 정상 표시하며, 콘솔 문제는 run_app.bat에서 해결한다.
    """
    if not s:
        return ""
    keep = []
    for ch in s:
        cp = ord(ch)
        if ch == "\ufffd":                 # 인코딩 손상 대체 문자 → 제거
            continue
        if cp < 32 and ch != "\t":         # 제어 문자 → 공백으로 치환
            keep.append(" ")
            continue
        keep.append(ch)
    return "".join(keep).strip()

def _fmt_pct(v: str) -> str:
    """fltRt 등 등락률 문자열 정리 (예: \"0\" -> \"0%\", \"-1.64\" -> \"-1.64%\")"""
    if not v:
        return "0%"
    try:
        num = float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return f"{v}%" if str(v).strip() else "0%"
    return f"{num:g}%"

def _fmt_market_cap(item: dict) -> str:
    """시가총액을 정수 스케일 표기로 정리 (이 환경에선 단위 포함 문자열이 왜곡되므로 숫자만 남긴다)"""
    raw = _pick(item, ("mrktTotAmt", "marketCap"))
    if not raw:
        return ""
    try:
        val = float(str(raw).replace(",", "").strip())
    except (TypeError, ValueError):
        return str(raw)
    if val >= 1_0000_0000_0000:  # 1조 이상
        return f"{int(val / 1_0000_0000_0000)}"
    if val >= 1_0000_0000:  # 1억 이상
        return f"{int(val / 1_0000_0000)}"
    return f"{val:,.0f}"

# 2026-09-13 실측: 기존 BASE(www.fss.or.kr/fss/openapi/*.jsp)는 "페이지가 없거나
# 잘못된 경로" HTML 오류 페이지를 반환 → 폐기/경로 변경 상태.
# 올바른 엔드포인트가 확인되면 BASE만 교체하면 정규화를 통해 즉시 실데이터 사용 가능.


def _pick(d: dict, names) -> str:
    """dict에서 별칭 후보 중 첫 유효값을 문자열로 반환"""
    for n in names:
        v = d.get(n)
        if v not in (None, ""):
            return str(v)
    return ""


# ── FSS 표준 응답 → UI 표준 키 매핑 (2026-09-14: 누락 정의 복원) ──
# normalize_fss_response가 이 표를 사용해 레거시 FWS 응답을 UI 형태로 변환한다.
_FIELD_ALIASES = {
    "symbol":     ("srtnCd", "isinCd", "isin", "shortCode", "code"),
    "name":       ("itmsNm", "isinNm", "isrItmsNm", "cmpyNm", "korSecnNm", "name"),
    "price":      ("clpr", "clsxPrCpr", "closePrice"),
    "change":     ("vs", "vsFluctuAmt", "cprUprVsFlu", "changeAmount"),
    "change_pct": ("fltRt", "vsFluctuRate", "fluRtCpr", "fluctuationRate"),
    "open":       ("mkp", "mktPrCpr", "openPrice"),
    "high":       ("hipr", "sprxCpr", "highPrice"),
    "low":        ("lopr", "lowxCpr", "lowPrice"),
    "volume":     ("trqu", "trVl", "trdqnt", "volume"),
    "market_cap": ("mrktTotAmt", "marketCap"),
    "market":     ("mrktCtg", "mktTp", "marketType"),
    "base_date":  ("basDt", "basDtNm", "date"),
}


def normalize_fss_response(data: dict) -> dict:
    """FSS OpenAPI JSON의 다양한 형태를 UI 표준 형태로 변환.

    지원 형태:
      1) {"result": {"items": [...]}}                 — 기존 UI 형태 (그대로 반환)
      2) {"FWS00XXX": {"RESULT": ..., "list": [...]}} — FSS 표준 형태 (필드 별칭 매핑)
      3) {"list": [...]}                              — 단순 목록
    """
    if not isinstance(data, dict):
        return {"error": "응답 형식이 예상과 다릅니다.", "result": {"items": []}}
    if isinstance(data.get("result"), dict):
        return data
    items = None
    for v in data.values():
        if isinstance(v, dict) and isinstance(v.get("list"), list):
            res = v.get("RESULT")
            code, msg = "011000", ""
            if isinstance(res, dict):
                code, msg = str(res.get("CODE", "011000")), str(res.get("MESSAGE", ""))
            elif isinstance(res, list) and res:
                code = str(res[0].get("CODE", "011000"))
                msg = str(res[0].get("MESSAGE", ""))
            if code not in ("011000", "0"):
                return {"error": f"FSS API 오류: {msg or code}", "result": {"items": []}}
            items = v["list"]
            break
        if isinstance(v, dict) and isinstance(v.get("items"), list):
            return {"result": {"items": v["items"]}}
    if items is None and isinstance(data.get("list"), list):
        items = data["list"]
    if items is None:
        return {"error": "응답에 목록(list/items)이 없습니다.", "result": {"items": []}}
    out = []
    for row in items:
        if not isinstance(row, dict):
            continue
        out.append({k: _pick(row, names) for k, names in _FIELD_ALIASES.items()})
    return {"result": {"items": out}}


class MarketFetcher:
    """금융원 OpenAPI 호출 및 저장용 클래스"""

    BASE = "https://www.fss.or.kr/fss/openapi"

    # 호출 가능한 API 목록 (URL 경로 기준)
    API = {
        "stock":  ("FWS004C03", "주식시세정보"),
        "product":("FWS002C03", "일반상품시세정보"),
        "index":  ("FWS003C01", "지수시세정보"),
        "company":("FWS001C01", "금융회사기본정보"),
    }

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key               # ← 설정 탭에서 입력받은 키
        self._mock_mode = not bool(api_key)  # 키 없으면 목데이터

    # ── API 호출 (JSON) ─────────────────────────────────────────────
    def _call(self, api_name: str, params: dict | None = None) -> dict:
        """금융원 API에 GET 요청 → 정규화된 JSON 반환 (에러 시 {'error': ...} 반환)"""
        url = f"{self.BASE}/{api_name}.jsp"
        # API 키는 이미 URL인코딩된 상태이므로 직접 추가, 나머지 파라미터만 urlencode
        url += f"?crtId={self.api_key}"
        if params:
            url += "&" + urllib.parse.urlencode(params)
        log.info("[MarketFetcher] 요청: %s", url)

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            log.warning("[MarketFetcher] 네트워크 오류: %s", e)
            return {"error": f"네트워크 오류: {type(e).__name__}: {e}", "result": {"items": []}}
        if raw.lstrip().startswith("<"):
            # 2026-09-13 실측: FSS 엔드포인트가 HTML 오류 페이지 반환 (폐기/경로 변경 의심)
            log.error("[MarketFetcher] HTML 오류 페이지 반환 (엔드포인트 폐기 의심): %s", api_name)
            return {"error": ("금융감독원 OpenAPI가 HTML 오류 페이지를 반환했습니다 "
                              "(엔드포인트 폐기/경로 변경 의심). Mock 데이터로 대체합니다."),
                    "result": {"items": []}}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            return {"error": f"JSON 파싱 실패: {e}", "result": {"items": []}}
        normalized = normalize_fss_response(data)
        log.info("[MarketFetcher] 정규화 완료: %d건", len(normalized.get("result", {}).get("items", [])))
        return normalized

    # ── 샘플 데이터 (키 없을 때 UI 테스트용) ────────────────────────────
    def _mock(self, api_key: str) -> dict:
        label = self.API[api_key][1]
        return {
            "result": {
                "items": [
                    {"symbol": "005930", "name": "삼성전자", "price": "75000", "change": "+1000", "change_pct": "+1.35%"},
                    {"symbol": "000660", "name": "SK하이닉스", "price": "120000", "change": "-2000", "change_pct": "-1.64%"},
                    {"symbol": "035420", "name": "네이버", "price": "180000", "change": "+3000", "change_pct": "+1.69%"},
                    {"symbol": "000270", "name": "기아", "price": "95000", "change": "+500", "change_pct": "+0.53%"},
                    {"symbol": "005380", "name": "현대차", "price": "210000", "change": "-1500", "change_pct": "-0.71%"},
                ]
            }
        }

    def _mock_detail(self, symbol: str) -> dict:
        """종목 상세 정보 Mock 데이터 (투자자별 매매동향 포함)"""
        details = {
            "005930": {
                "name": "삼성전자", "price": "75,000", "change": "+1,000", "change_pct": "+1.35%",
                "open": "74,500", "high": "75,800", "low": "74,200", "volume": "12,345,678",
                "market_cap": "447조 원", "per": "12.5", "pbr": "1.15", "dividend": "3.2%",
                "investors": [
                    {"type": "기관", "net_buy": "+1,234,567", "amount": "92,500백만"},
                    {"type": "외국인", "net_buy": "+567,890", "amount": "42,600백만"},
                    {"type": "개인", "net_buy": "-1,802,457", "amount": "-135,100백만"},
                    {"type": "금융투자", "net_buy": "+890,123", "amount": "66,800백만"},
                    {"type": "연기금", "net_buy": "+456,789", "amount": "34,300백만"},
                ]
            },
            "000660": {
                "name": "SK하이닉스", "price": "120,000", "change": "-2,000", "change_pct": "-1.64%",
                "open": "122,000", "high": "122,500", "low": "119,800", "volume": "8,765,432",
                "market_cap": "87조 원", "per": "8.3", "pbr": "1.45", "dividend": "2.1%",
                "investors": [
                    {"type": "기관", "net_buy": "-567,890", "amount": "-68,100백만"},
                    {"type": "외국인", "net_buy": "-345,678", "amount": "-41,500백만"},
                    {"type": "개인", "net_buy": "+913,568", "amount": "+109,600백만"},
                    {"type": "금융투자", "net_buy": "-234,567", "amount": "-28,100백만"},
                    {"type": "연기금", "net_buy": "+123,456", "amount": "+14,800백만"},
                ]
            },
        }
        # 기본 상세 정보 (없는 종목용)
        return details.get(symbol, {
            "name": f"종목({symbol})", "price": "100,000", "change": "0", "change_pct": "0%",
            "open": "100,000", "high": "101,000", "low": "99,000", "volume": "1,000,000",
            "market_cap": "10조 원", "per": "10.0", "pbr": "1.0", "dividend": "2.5%",
            "investors": [
                {"type": "기관", "net_buy": "+100,000", "amount": "+10,000백만"},
                {"type": "외국인", "net_buy": "+50,000", "amount": "+5,000백만"},
                {"type": "개인", "net_buy": "-150,000", "amount": "-15,000백만"},
                {"type": "금융투자", "net_buy": "+30,000", "amount": "+3,000백만"},
                {"type": "연기금", "net_buy": "+20,000", "amount": "+2,000백만"},
            ]
        })

    def _gokr_stock_list(self, bas_dt: str = "20260910", num_of_rows: int = 50,
                         page_no: int = 1, itms_nm: str = "") -> dict:
        """공공데이터포털 주식 시세 목록 호출 (GetStockSecuritiesInfoService_V2/getStockPriceInfo_V2)

        실측 기반 운영 경로:
          https://apis.data.go.kr/1160100/GetStockSecuritiesInfoService_V2/getStockPriceInfo_V2

        itms_nm: 종목명 검색 조건(공개 API itmsNm 파라미터). 지정 시 basDt는 생략해
                 최신 기준일의 검색 결과를 받는다 (2026-09-14 검색어 전달 수정).
        """
        if not self.api_key:
            return {"error": "API 키가 없습니다.", "result": {"items": []}}
        params = {
            "serviceKey": self.api_key,
            "resultType": "json",
            "numOfRows": str(num_of_rows),
            "pageNo": str(page_no),
        }
        if itms_nm:
            # 부분일치 검색(likeItmsNm) + 최근 30일 기간 제한.
            # 2026-09-14 실측: 결과는 basDt 내림차순 정렬(최신 우선)이며,
            # 기간 미지정 시 전 기간(수만 건)이 반환되므로 30일로 제한한다.
            end_dt = date.today()
            begin_dt = end_dt - timedelta(days=30)
            params["likeItmsNm"] = itms_nm
            params["beginBasDt"] = begin_dt.strftime("%Y%m%d")
            params["endBasDt"] = end_dt.strftime("%Y%m%d")
        elif bas_dt:
            params["basDt"] = bas_dt
        url = f"{_GOKR_STOCK_BASE}/{_GOKR_STOCK_OP}?{urllib.parse.urlencode(params)}"
        log.info("[MarketFetcher] [gokr-stock] 요청: %s", url)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            log.warning("[MarketFetcher] [gokr-stock] 네트워크 오류: %s", e)
            return {"error": f"네트워크 오류: {type(e).__name__}: {e}", "result": {"items": []}}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            log.warning("[MarketFetcher] [gokr-stock] JSON 파싱 실패: %s", e)
            return {"error": f"JSON 파싱 실패: {e}", "result": {"items": []}}

        # 응답 형태: {"response":{"header":{...},"body":{"numOfRows":...,"items":{"item":[...]}}}}
        items = []
        try:
            body = data.get("response", {}).get("body", {})
            raw_items = body.get("items", {})
            item_list = raw_items.get("item", [])
            if isinstance(item_list, list):
                items = [_gokr_to_ui(i) for i in item_list if isinstance(i, dict)]
        except (AttributeError, TypeError, ValueError) as e:
            log.warning("[MarketFetcher] [gokr-stock] 응답 정규화 중 오류: %s", e)
            return {"error": f"응답 정규화 오류: {e}", "result": {"items": []}}

        total = 0
        try:
            total = int(body.get("totalCount", 0))
        except (TypeError, ValueError):
            pass

        log.info("[MarketFetcher] [gokr-stock] 정규화 완료: totalCount=%d, 가져온 건수=%d",
                 total, len(items))
        return {"result": {"items": items}, "totalCount": total, "raw": data}

    def get_stock_list(self, bas_dt: str = "20260910", num_of_rows: int = 50,
                       page_no: int = 1, keyword: str = "") -> dict:
        """종목 시세 목록 반환 (실데이터 우선, 실패 시 Mock 폴백)

        keyword: 종목명 검색어 → 공공데이터포털 itmsNm 파라미터로 전달.
                 지정 시 basDt를 생략하고 최신 기준일 기준으로 검색한다.
        """
        if self._mock_mode:
            return self._mock("stock")
        result = self._gokr_stock_list(bas_dt, num_of_rows, page_no, itms_nm=keyword)
        if "error" in result:
            log.warning("[MarketFetcher] [gokr-stock] 실데이터 실패 → Mock 폴백: %s", result["error"])
            return self._mock("stock")
        return result


    def get_stock_detail(self, symbol: str) -> dict:
        """종목 상세 정보 (현재가 + 투자자별 매매동향)"""
        if self._mock_mode:
            return self._mock_detail(symbol)
        # 실제 API 호출 (추후 구현)
        url = f"{self.BASE}/FWS004C03.jsp"
        params = {"crtId": self.api_key, "searchWord": symbol}
        result = self._call("FWS004C03", params)
        if "error" in result:
            return self._mock_detail(symbol)
        return result

    # ── 공개 API 메서드 ────────────────────────────────────────────────
    def search_stocks(self, kw: str = "삼성") -> dict:
        """종목명 검색 (실데이터 우선, 실패 시 Mock 폴백)

        2026-09-14 수정: 기존에는 kw를 무시하고 전체 목록만 반환했으나,
        이제 kw를 공공데이터포털 itmsNm 검색 조건으로 API에 전달한다.
        """
        return self.get_stock_list(bas_dt="", keyword=(kw or "").strip())

    def search_products  (self, kw: str): return self._call(self.API["product"][0], {"searchWord": kw}) if not self._mock_mode else self._mock("product")
    def get_indices      (self         ): return self._call(self.API["index"][0])                    if not self._mock_mode else self._mock("index")
    def search_companies  (self, kw: str): return self._call(self.API["company"][0], {"cmpyName": kw}) if not self._mock_mode else self._mock("company")


# ──────────────────────[ 사용 예시 ]─────────────────────
if __name__ == "__main__":
    # API 키는 config.json에서만 로드 (소스 코드에 키를 두지 않는다 — 2026-09-13 보안 정리)
    try:
        from core.config_manager import get_api_key
    except ImportError:  # 스크립트 직접 실행 시 (core 패키지 경로 없음)
        from config_manager import get_api_key
    mf = MarketFetcher(get_api_key("fss_stock") or "")
    if not mf.api_key:
        print("config.json에 fss_stock 키가 없습니다 → Mock 모드로 동작합니다.")
    result = mf.search_stocks("삼성")
    print("결과:", result.get("result", {}).get("items", []))