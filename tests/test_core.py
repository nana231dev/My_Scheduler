# -*- coding: utf-8 -*-
"""core 모듈 테스트 스위트 (재구축: 2026-09-12)

pytest와 unittest 양쪽 모두에서 동작:
    pytest tests/ -v
    python -m unittest tests.test_core -v
"""
from __future__ import annotations

import logging  # noqa: E402
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import exceptions as ex  # noqa: E402
from core import formulas, glossary, i18n, logger  # noqa: E402
from core.db_manager import DBManager  # noqa: E402


# ── I18n ─────────────────────────────────────────────────────
class TestI18n(unittest.TestCase):
    def test_supported_languages(self):
        self.assertEqual(i18n.get_languages(), ("ko", "en", "ja"))

    def test_lookup_ko_en_ja(self):
        self.assertEqual(i18n.t("btn_save", "ko"), "저장")
        self.assertEqual(i18n.t("btn_save", "en"), "Save")
        self.assertEqual(i18n.t("btn_save", "ja"), "保存")

    def test_unknown_key_returns_key(self):
        self.assertEqual(i18n.t("no_such_key"), "no_such_key")


# ── Formulas ─────────────────────────────────────────────────
class TestFormulas(unittest.TestCase):
    def test_count_160(self):
        self.assertEqual(formulas.count(), 160)

    def test_levels_valid(self):
        for row in formulas.get_all():
            self.assertIn(row[1], formulas.LEVELS)

    def test_filter_by_level(self):
        self.assertEqual(len(formulas.get_by_level("대학")), 19)  # 대학수학 18 + 통계(상관계수) 1
        self.assertEqual(len(formulas.get_by_level("초등")), 12)

    def test_search(self):
        rows = formulas.search("옴의 법칙")
        self.assertTrue(rows)
        self.assertEqual(rows[0][2], "옴의 법칙")


# ── Glossary ─────────────────────────────────────────────────
class TestGlossary(unittest.TestCase):
    def test_count_at_least_100(self):
        self.assertGreaterEqual(glossary.count(), 100)

    def test_categories(self):
        cats = set(glossary.get_categories())
        self.assertTrue(cats.issubset({"원소", "물리상수", "과학용어", "공학법칙"}))

    def test_search(self):
        rows = glossary.search("빛의 속도")
        self.assertTrue(rows)
        self.assertEqual(rows[0][0], "물리상수")


# ── Exceptions ───────────────────────────────────────────────
class TestExceptions(unittest.TestCase):
    def test_hierarchy(self):
        for err in (ex.DatabaseError, ex.NetworkError, ex.ConfigError, ex.FileParseError):
            self.assertTrue(issubclass(err, ex.SchedulerError))

    def test_safe_call_fallback(self):
        @ex.safe_call(context="테스트", fallback=[])
        def boom():
            raise ValueError("fail")

        self.assertEqual(boom(), [])

    def test_safe_call_pass_through(self):
        @ex.safe_call
        def ok():
            return 42

        self.assertEqual(ok(), 42)

    def test_retry_success_after_failure(self):
        calls = {"n": 0}

        @ex.retry_on_error(times=3, delay=0)
        def flaky():
            calls["n"] += 1
            if calls["n"] < 2:
                raise ex.NetworkError("일시 오류")
            return "OK"

        self.assertEqual(flaky(), "OK")


# ── Logger ───────────────────────────────────────────────────
class TestLogger(unittest.TestCase):
    def test_get_logger(self):
        lg = logger.get_logger("test.logger")
        self.assertEqual(lg.name, "test.logger")

    def test_setup_logging_idempotent(self):
        logger.setup_logging()
        logger.setup_logging()  # 2회 호출해도 핸들러 중복 없음
        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if type(h).__name__ == "RotatingFileHandler"]
        self.assertGreaterEqual(len(file_handlers), 1)


# ── DBManager (temp DB) ──────────────────────────────────────
class TestDBManager(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = DBManager(db_name=str(Path(self._tmp.name) / "test.db"))

    def tearDown(self):
        try:
            self.db.conn.close()
        except Exception:
            pass
        self._tmp.cleanup()

    def test_schedule_roundtrip(self):
        self.db.set_schedule("2099-01-01", "회의", "일지")
        row = self.db.get_schedule("2099-01-01")
        self.assertEqual(row["schedule"], "회의")
        self.assertEqual(row["journal"], "일지")
        self.db.delete_schedule("2099-01-01")

    def test_word_roundtrip(self):
        self.db.add_word("테스트어", 1, "hello", "/helo/", "헬로", "감탄", "안녕", "Hello world", "헬로 월드")
        words = self.db.get_words(language="테스트어")
        self.assertTrue(words)
        self.db.delete_word(words[0]["id"])

    def test_phrase_roundtrip(self):
        self.db.add_phrase("테스트어", 1, "안녕하세요", "안녕하세요 발음", "인사")
        rows = self.db.get_phrases(language="테스트어")
        self.assertTrue(rows)
        self.db.delete_phrase(rows[0]["id"])

    def test_saved_news_roundtrip(self):
        self.assertTrue(self.db.add_saved_news("제목", "http://x/1", category="과학"))
        self.assertFalse(self.db.add_saved_news("제목2", "http://x/1"))  # 중복 거부
        self.assertTrue(self.db.is_news_saved("http://x/1"))
        for row in self.db.get_saved_news():
            self.db.delete_saved_news(row["id"])

    def test_saved_stock_roundtrip(self):
        self.db.add_saved_stock("005930", "삼성전자", 75000)
        stocks = self.db.get_saved_stocks()
        self.assertTrue(stocks)
        self.db.delete_saved_stock(stocks[0]["id"])


# ── 신규 기능 (2026-09-13): 뉴스 읽음 / 복습 필드 / 투자 일기 ──
class TestNewFeatures(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = DBManager(db_name=str(Path(self._tmp.name) / "nf.db"))

    def tearDown(self):
        try:
            self.db.conn.close()
        except Exception:
            pass
        self._tmp.cleanup()

    def test_saved_news_read_flag(self):
        self.db.add_saved_news("제목", "http://x/r1")
        rows = self.db.get_saved_news()
        self.assertEqual(rows[0]["read_flag"], 0)
        self.db.mark_news_read(rows[0]["id"])
        self.assertEqual(self.db.get_saved_news()[0]["read_flag"], 1)
        self.db.reset_news_read(rows[0]["id"])
        self.assertEqual(self.db.get_saved_news()[0]["read_flag"], 0)

    def test_review_due_fields(self):
        self.db.add_word("테스트어", 1, "hello", "/helo/", "헬로", "감탄", "안녕", "Hello world", "헬로 월드")
        due = self.db.get_words_due_for_review()
        self.assertTrue(due)
        for key in ("pron_en", "pron_ko", "pos", "example", "example_ko", "ease"):
            self.assertIn(key, due[0])

    def test_investment_roundtrip(self):
        inv_id = self.db.add_investment("2099-01-01", "매수", "005930", "삼성전자", 10, 75000, 100, "테스트")
        items = self.db.get_investments(month="2099-01")
        self.assertEqual(len(items), 1)
        s = self.db.get_investment_summary("2099-01")
        self.assertEqual(s["count"], 1)
        self.assertEqual(s["buy_cost"], 10 * 75000 + 100)
        self.db.delete_investment(inv_id)
        self.assertEqual(self.db.get_investment_summary("2099-01")["count"], 0)


# ── 증권 응답 정규화 (2026-09-13) ──
from core.market_fetcher import normalize_fss_response  # noqa: E402


class TestMarketNormalize(unittest.TestCase):
    def test_passthrough_ui_format(self):
        data = {"result": {"items": [{"symbol": "005930", "name": "삼성전자", "price": "75000",
                                      "change": "+1000", "change_pct": "+1.35%"}]}}
        self.assertEqual(normalize_fss_response(data), data)

    def test_fss_standard_format(self):
        data = {"FWS004C03": {"RESULT": {"CODE": "011000", "MESSAGE": "정상 처리되었습니다."},
                              "list": [{"isinCd": "KR7005930", "isinNm": "삼성전자(보통주)",
                                        "clpr": "75000", "vsFluctuAmt": "1000", "vsFluctuRate": "1.35"}],
                              "totCnt": 1}}
        out = normalize_fss_response(data)
        item = out["result"]["items"][0]
        self.assertEqual(item["name"], "삼성전자(보통주)")
        self.assertEqual(item["price"], "75000")
        self.assertEqual(item["change"], "1000")
        self.assertEqual(item["change_pct"], "1.35")

    def test_fss_result_error(self):
        data = {"FWS004C03": {"RESULT": {"CODE": "011500", "MESSAGE": "인증키가 유효하지 않습니다."},
                              "list": []}}
        out = normalize_fss_response(data)
        self.assertIn("error", out)
        self.assertEqual(out["result"]["items"], [])


# ── 가계부 (2026-09-14 확장) ─────────────────────────────────
class TestLedger(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = DBManager(db_name=str(Path(self._tmp.name) / "ledger.db"))

    def tearDown(self):
        try:
            self.db.conn.close()
        except Exception:
            pass
        self._tmp.cleanup()

    def test_transaction_roundtrip(self):
        tid = self.db.add_transaction("2099-01-05", "지출", "식비", 12000, "점심")
        rows = self.db.get_transactions(month="2099-01")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["category"], "식비")
        self.assertEqual(rows[0]["amount"], 12000)
        self.db.delete_transaction(tid)
        self.assertEqual(self.db.get_transactions(month="2099-01"), [])

    def test_month_summary(self):
        self.db.add_transaction("2099-02-01", "수입", "급여", 1000000)
        self.db.add_transaction("2099-02-03", "지출", "교통", 50000)
        s = self.db.get_month_summary(2099, 2)
        self.assertEqual(s["income"], 1000000)
        self.assertEqual(s["expense"], 50000)
        self.assertEqual(s["savings"], 950000)


# ── 일정 엑셀 왕복 (2026-09-18 Day 1: P0-3 회귀 테스트) ─────────
class TestScheduleExcelRoundTrip(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = DBManager(db_name=str(Path(self._tmp.name) / "excel.db"))

    def tearDown(self):
        try:
            self.db.conn.close()
        except Exception:
            pass
        self._tmp.cleanup()

    def _sample_df(self):
        pd = pytest_pd()
        return pd.DataFrame([
            {"날짜": "2099-03-01", "일정": "회의", "저널": "메모1", "이미지": ""},
            {"날짜": "2099-03-02", "일정": "휴가", "저널": "", "이미지": ""},
        ])

    def test_export_columns_korean(self):
        self.db.set_schedule("2099-03-01", "회의", "메모1")
        df = self.db.get_all_schedules_with_images_df()
        self.assertIsNotNone(df)
        self.assertEqual(list(df.columns), ["날짜", "일정", "저널", "이미지"])

    def test_import_export_roundtrip(self):
        df = self._sample_df()
        res = self.db.import_schedules_from_df(df)
        self.assertEqual(res, {"imported": 2, "skipped": 0})
        back = self.db.get_all_schedules_with_images_df()
        self.assertEqual(len(back), 2)
        self.assertEqual(set(back["날짜"].tolist()), {"2099-03-01", "2099-03-02"})

    def test_import_legacy_bigo_header(self):
        pd = pytest_pd()
        legacy = pd.DataFrame([{"날짜": "2099-03-03", "일정": "출장", "비고": "구버전"}])
        res = self.db.import_schedules_from_df(legacy)
        self.assertEqual(res, {"imported": 1, "skipped": 0})
        got = self.db.get_schedule("2099-03-03")
        self.assertEqual(got["journal"], "구버전")

    def test_import_skips_blank_date(self):
        pd = pytest_pd()
        df = pd.DataFrame([
            {"날짜": "", "일정": "무효", "저널": "", "이미지": ""},
            {"날짜": "2099-03-04", "일정": "유효", "저널": "", "이미지": ""},
        ])
        res = self.db.import_schedules_from_df(df)
        self.assertEqual(res, {"imported": 1, "skipped": 1})

    def test_seed_strings_not_mojibake(self):
        self.db.check_default_categories()
        names = [r["name"] for r in self.db.get_categories()]
        self.assertIn("기타", names)
        anns = {a["name"] for a in self.db.get_anniversaries()}
        self.assertIn("추석", anns)
        self.assertTrue(self.db.add_saved_stock("005930", "삼성전자", 75000))
        row = self.db.get_saved_stocks()[0]
        self.assertEqual(row["category"], "주식")


def pytest_pd():
    import pandas as pd
    return pd


# ── 증권 저장목록 (2026-09-14 확장) ──────────────────────────
class TestSavedStocks(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = DBManager(db_name=str(Path(self._tmp.name) / "stocks.db"))

    def tearDown(self):
        try:
            self.db.conn.close()
        except Exception:
            pass
        self._tmp.cleanup()

    def test_saved_stock_roundtrip(self):
        self.assertTrue(self.db.add_saved_stock("005930", "삼성전자", 75000))
        rows = self.db.get_saved_stocks()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "005930")
        sid = rows[0]["id"]
        self.assertTrue(self.db.update_saved_stock(sid, price=80000))
        self.assertEqual(self.db.get_saved_stocks()[0]["price"], 80000)
        self.db.delete_saved_stock(sid)
        self.assertEqual(self.db.get_saved_stocks(), [])


# ── 증권 유틸/검색 (2026-09-14 확장) ─────────────────────────
from core.market_fetcher import (  # noqa: E402
    MarketFetcher,
    _clean_kor,
    _fmt_market_cap,
    _fmt_pct,
)


class TestMarketUtils(unittest.TestCase):
    def test_fmt_pct(self):
        self.assertEqual(_fmt_pct("0"), "0%")
        self.assertEqual(_fmt_pct("-2.22"), "-2.22%")
        self.assertEqual(_fmt_pct("+0.58"), "0.58%")
        self.assertEqual(_fmt_pct(""), "0%")
        self.assertEqual(_fmt_pct("1,200"), "1200%")

    def test_fmt_market_cap(self):
        self.assertEqual(_fmt_market_cap({"mrktTotAmt": "22142994331"}), "221")
        self.assertEqual(_fmt_market_cap({"mrktTotAmt": "1558452848250000"}), "1558")
        self.assertEqual(_fmt_market_cap({"mrktTotAmt": "1234567"}), "1,234,567")
        self.assertEqual(_fmt_market_cap({"mrktTotAmt": ""}), "")

    def test_clean_kor_preserves_hangul(self):
        self.assertEqual(_clean_kor("삼성전자"), "삼성전자")
        self.assertEqual(_clean_kor("NAVER 네이버 123"), "NAVER 네이버 123")
        self.assertEqual(_clean_kor("삼\ufffd성"), "삼성")

    def test_mock_search(self):
        mf = MarketFetcher("")
        self.assertTrue(mf._mock_mode)
        items = mf.search_stocks("아무거나").get("result", {}).get("items", [])
        self.assertEqual(len(items), 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
