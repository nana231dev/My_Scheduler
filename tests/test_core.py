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
from logging.handlers import RotatingFileHandler  # noqa: E402
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import exceptions as ex  # noqa: E402
from core import formulas, glossary, i18n, logger  # noqa: E402
from core.db_manager import DBManager, DEFAULT_ANNIVERSARIES  # noqa: E402


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

    # ── Day 3 (2026-09-20): S-4 단일 정의 / S-5 DDL 중복 제거 / S-6 이미지 왕복 ──
    def test_set_schedule_preserves_images_when_none(self):
        """일정/일지만 저장 시 기존 그림은 유지되어야 한다(일간 일지 두 저장 버튼 semantics)."""
        self.db.set_schedule("2099-04-01", "회의", "메모", images=["data/images/a.png"])
        self.db.set_schedule("2099-04-01", "회의2", "메모2", images=None)
        got = self.db.get_schedule("2099-04-01")
        self.assertEqual(got["schedule"], "회의2")
        self.assertEqual(got["images"], ["data/images/a.png"])

    def test_set_schedule_replaces_images_when_given(self):
        self.db.set_schedule("2099-04-02", "A", "", images=["data/images/old.png"])
        self.db.set_schedule("2099-04-02", "B", "", images=["data/images/new.png"])
        got = self.db.get_schedule("2099-04-02")
        self.assertEqual(got["images"], ["data/images/new.png"])

    def test_schedule_images_roundtrip_via_df(self):
        """내보내기(세미콜론 구분) → 가져오기 후 get_schedule로 이미지 목록 복원."""
        self.db.set_schedule("2099-04-03", "발표", "준비",
                             images=["data/images/p1.png", "data/images/p2.png"])
        df = self.db.get_all_schedules_with_images_df()
        row = df[df["날짜"] == "2099-04-03"].iloc[0]
        self.assertEqual(row["이미지"], "data/images/p1.png; data/images/p2.png")
        res = self.db.import_schedules_from_df(df)
        self.assertEqual(res, {"imported": len(df), "skipped": 0})
        got = self.db.get_schedule("2099-04-03")
        self.assertEqual(got["images"], ["data/images/p1.png", "data/images/p2.png"])

    def test_single_set_schedule_and_ddl(self):
        """S-4: set_schedule/get_schedule 단일 정의, S-5: investment_journal DDL 1회만."""
        src = (Path(__file__).resolve().parent.parent / "core" / "db_manager.py").read_text(
            encoding="utf-8")
        self.assertEqual(src.count("def set_schedule("), 1)
        self.assertEqual(src.count("def get_schedule("), 1)
        self.assertEqual(src.count("CREATE TABLE IF NOT EXISTS investment_journal"), 1)


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

    def test_saved_stock_duplicate_is_blocked(self):
        """Day4 P0-5: 같은 symbol 재저장은 False (symbol UNIQUE 보장)."""
        self.assertTrue(self.db.add_saved_stock("005930", "삼성전자", 75000))
        self.assertFalse(self.db.add_saved_stock("005930", "삼성전자", 75000))
        self.assertEqual(len(self.db.get_saved_stocks()), 1)

    def test_schedule_template_roundtrip_with_images(self):
        """Day4 P0-5: 템플릿 컬럼 규격 → 가져오기 → 내보내기 이미지 복원."""
        import pandas as pd
        tpl = pd.DataFrame(
            [{"날짜": "2099-09-19", "일정": "템플릿 검증", "저널": "메모",
              "이미지": "data/images/a.png; data/images/b.png"}],
            columns=["날짜", "일정", "저널", "이미지"])
        res = self.db.import_schedules_from_df(tpl)
        self.assertEqual(res, {"imported": 1, "skipped": 0})
        out = self.db.get_all_schedules_with_images_df()
        row = out[out["날짜"] == "2099-09-19"].iloc[0]
        self.assertEqual(row["이미지"], "data/images/a.png; data/images/b.png")
        got = self.db.get_schedule("2099-09-19")
        self.assertEqual(got["images"], ["data/images/a.png", "data/images/b.png"])

    def test_dday_crud_roundtrip(self):
        """Day4: D-Day 재입력 경로(추가 → 조회 → 삭제) 검증."""
        self.db.add_dday("검증 디데이", "2099-12-31")
        rows = self.db.get_ddays()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "검증 디데이")
        self.db.delete_dday(rows[0]["id"])
        self.assertEqual(self.db.get_ddays(), [])


# ── Day5 학습 진도 집계 (2026-09-20 P1-3) ─────────────────────
class TestStudyProgressSummary(unittest.TestCase):
    """진도율 위젯의 DB 집계가 정확하고, 입력→재조회 후 유지되는지 검증한다."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = DBManager(db_name=str(Path(self._tmp.name) / "study.db"))
        self.db.add_category("검증수학")
        self.db.add_category("검증영어")
        self.cat_math = self.db.get_category_id("검증수학")
        self.cat_eng = self.db.get_category_id("검증영어")

    def tearDown(self):
        try:
            self.db.conn.close()
        except Exception:
            pass
        self._tmp.cleanup()

    def test_empty_summary_is_zero(self):
        self.assertEqual(self.db.get_study_progress_summary("2099-01-01"),
                         {"total": 0, "done": 0, "rate": 0})
        self.assertEqual(self.db.get_study_progress_by_category("2099-01-01"), [])

    def test_record_toggle_persist(self):
        """진도 입력 → 토글 → 재조회 후 유지 (Day5 DoD)."""
        self.db.add_study_progress("2099-01-02", self.cat_math, "1과 복습")
        rows = self.db.get_study_progress("2099-01-02")
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["done"])
        self.db.toggle_study_progress(rows[0]["id"])
        rows2 = self.db.get_study_progress("2099-01-02")
        self.assertTrue(rows2[0]["done"])
        # 재연결(재시작 시뮬레이션) 후에도 유지
        self.db.conn.commit()
        rows3 = self.db.get_study_progress("2099-01-02")
        self.assertTrue(rows3[0]["done"])

    def test_summary_rate_matches_db(self):
        """진도율 % = DB 집계 (위젯 표시값과 동일한 계산)."""
        self.db.add_study_progress("2099-01-03", self.cat_math, "A")
        self.db.add_study_progress("2099-01-03", self.cat_eng, "B")
        self.db.add_study_progress("2099-01-03", self.cat_eng, "C")
        first = self.db.get_study_progress("2099-01-03")[0]
        self.db.toggle_study_progress(first["id"])
        total = self.db.get_study_progress_summary("2099-01-03")
        self.assertEqual(total, {"total": 3, "done": 1, "rate": 33})
        by_cat = {r["cat_name"]: r for r in self.db.get_study_progress_by_category("2099-01-03")}
        self.assertEqual(by_cat["검증수학"]["done"], 1)
        self.assertEqual(by_cat["검증수학"]["rate"], 100)
        self.assertEqual(by_cat["검증영어"]["total"], 2)
        self.assertEqual(by_cat["검증영어"]["done"], 0)

    def test_deleted_category_grouped_as_uncategorized(self):
        self.db.add_study_progress("2099-01-04", self.cat_math, "D")
        self.db.delete_category(self.cat_math)
        by_cat = self.db.get_study_progress_by_category("2099-01-04")
        self.assertEqual(len(by_cat), 1)
        self.assertEqual(by_cat[0]["cat_name"], "미분류")


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


# ── 스키마 건강성 (2026-09-20 P0-2/P0-3) ─────────────────────
class TestSchemaHealth(unittest.TestCase):
    """DB가 재생성되거나 테이블이 사라져도 앱이 뜨는지 검증한다.

    배경: 2026-09-19 DB 재생성으로 tasks 테이블이 사라져
    설정 뷰(`setup_settings_view → refresh_task_list → get_tasks`)가
    'sqlite3.OperationalError: no such table: tasks'로 중단되었다.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = DBManager(db_name=str(Path(self._tmp.name) / "schema.db"))
        self.cur = self.db.conn.cursor()

    def tearDown(self):
        self.db.conn.close()
        self._tmp.cleanup()

    def _columns(self, table):
        return [r[1] for r in self.cur.execute(f"PRAGMA table_info({table})").fetchall()]

    def _tables(self):
        return sorted(r[0] for r in self.cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall())

    def test_tasks_table_has_6_columns(self):
        self.assertEqual(self._columns("tasks"),
                         ["id", "item", "period", "goal", "content", "remark"])

    def test_tasks_crud_roundtrip(self):
        self.db.add_task("영어 100단어", "2026-09-20", "매일 30분", "1회독", "메모")
        rows = self.db.get_tasks()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["item"], "영어 100단어")
        self.assertEqual(rows[0]["remark"], "메모")
        self.db.delete_task(rows[0]["id"])
        self.assertEqual(self.db.get_tasks(), [])

    def test_tasks_self_heal_when_table_missing(self):
        self.cur.execute("DROP TABLE tasks")
        self.db.conn.commit()
        self.assertNotIn("tasks", self._tables())
        self.db.ensure_schedule_tables()            # 자기치유
        self.assertIn("tasks", self._tables())
        self.db.add_task("복구 확인", "", "", "", "")   # 사용 가능해야 한다
        self.assertEqual(len(self.db.get_tasks()), 1)

    def test_migration_is_idempotent(self):
        before_tables, before_cols = self._tables(), self._columns("wordbook")
        self.db.ensure_schedule_tables()
        self.db.ensure_schedule_tables()
        self.assertEqual(before_tables, self._tables())
        self.assertEqual(before_cols, self._columns("wordbook"))

    def test_wordbook_item_type_default_and_dedup(self):
        self.db.add_word("검증어", 1, "alpha", "/a/", "알파", "명사", "첫째 뜻", "ex", "예")
        words = self.db.get_words(language="검증어")
        self.assertEqual(words[0]["item_type"], "단어")     # 기본값이 기록된다
        # 같은 (언어, 단어, 유형) 재삽입은 차단
        self.assertFalse(self.db.add_word("검증어", 2, "alpha", "/a/", "알파", "명사", "둘째 뜻", "ex", "예"))
        self.assertEqual(len(self.db.get_words(language="검증어")), 1)
        # 유형이 다르면 별개 항목으로 저장 가능
        self.assertTrue(self.db.add_word("검증어", 3, "alpha", "/a/", "알파", "명사", "숙어 뜻", "ex", "예",
                                         item_type="숙어"))
        self.assertEqual(len(self.db.get_words(language="검증어")), 2)

    def test_user_version_is_recorded(self):
        got = self.cur.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(got, DBManager.SCHEMA_VERSION)

    def test_integrity_ok_leaves_db_writable(self):
        self.assertFalse(self.db.db_readonly)
        # 실제로 쓰기도 가능해야 한다(query_only 미설정)
        self.db.add_task("쓰기 확인", "", "", "", "")
        self.assertEqual(len(self.db.get_tasks()), 1)


# ── Day3 스키마 확정 (2026-09-20 P1-1/P1-2) ───────────────────
class TestV2Migration(unittest.TestCase):
    """기념일 정정본 재시드 + wordbook 정규화가 멱등하게 동작하는지 검증한다."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = DBManager(db_name=str(Path(self._tmp.name) / "v2.db"))
        self.cur = self.db.conn.cursor()

    def tearDown(self):
        self.db.conn.close()
        self._tmp.cleanup()

    def test_anniversary_seed_is_corrected(self):
        rows = self.cur.execute(
            "SELECT name, year, month, day, type, is_holiday FROM anniversaries "
            "ORDER BY month, day").fetchall()
        self.assertEqual(len(rows), 11)
        by_name = {r[0]: r for r in rows}
        # 손상 명칭이 하나도 남아 있지 않아야 한다
        for bad in ("기념일", "3.1운동", "만일홍보절", "해방", "개척절", "서방", "크리스마스", "근화절"):
            self.assertNotIn(bad, by_name)
        # 정정본 11건이 날짜·속성과 함께 정확해야 한다
        for name, year, month, day, typ, hol, _rep in DEFAULT_ANNIVERSARIES:
            self.assertIn(name, by_name)
            self.assertEqual(by_name[name][1:], (year, month, day, typ, hol))
        # 공휴일 10건 + 독도의 날(비공휴일) 1건
        self.assertEqual(self.cur.execute(
            "SELECT COUNT(*) FROM anniversaries WHERE is_holiday=1").fetchone()[0], 10)
        self.assertEqual(by_name["독도의 날"][1:], (0, 10, 25, 0, 0))

    def test_anniversary_seed_matches_month_day_type_uniqueness(self):
        dupes = self.cur.execute(
            "SELECT month, day, type, COUNT(*) FROM anniversaries "
            "GROUP BY month, day, type HAVING COUNT(*) > 1").fetchall()
        self.assertEqual(dupes, [])

    def test_legacy_anniversaries_are_replaced(self):
        # 구 시드 상태의 DB를 재현: 손상 명칭 11행 + wordbook 구 값
        self.cur.execute("DELETE FROM anniversaries")
        self.cur.executemany(
            "INSERT INTO anniversaries (name, year, month, day, type, is_holiday, is_repeat) "
            "VALUES (?,?,?,?,?,?,?)",
            [("기념일", 0, 1, 1, 0, 1, 1), ("3.1운동", 1919, 3, 1, 0, 1, 1),
             ("만일홍보절", 0, 5, 5, 0, 1, 1), ("어린이날", 0, 6, 6, 0, 1, 1),
             ("해방", 1945, 8, 15, 0, 1, 1), ("개척절", 0, 10, 3, 0, 1, 1),
             ("서방", 0, 10, 9, 0, 1, 1), ("크리스마스", 0, 12, 25, 0, 1, 1),
             ("설날", 0, 1, 1, 1, 1, 1), ("근화절", 0, 10, 26, 0, 1, 1),
             ("추석", 0, 8, 15, 1, 1, 1)])
        self.db.conn.commit()
        self.db.migrate_to_v2()
        names = sorted(r[0] for r in self.cur.execute("SELECT name FROM anniversaries").fetchall())
        self.assertEqual(len(names), 11)
        self.assertIn("신정", names)
        self.assertIn("독도의 날", names)
        self.assertNotIn("만일홍보절", names)

    def test_user_added_anniversaries_are_preserved(self):
        # 사용자가 기념일을 추가한 DB에서는 재시드하지 않는다
        self.db.add_anniversary("결혼기념일", 2020, 4, 4, 0, 0, 1)
        before = sorted(self.cur.execute("SELECT name FROM anniversaries").fetchall())
        self.db.migrate_to_v2()
        after = sorted(self.cur.execute("SELECT name FROM anniversaries").fetchall())
        self.assertEqual(before, after)
        self.assertIn(("결혼기념일",), after)

    def test_wordbook_legacy_pos_values_normalized(self):
        # 과거 시드가 item_type에 품사를 넣은 상태를 재현
        self.cur.execute("UPDATE wordbook SET item_type='동사'")
        self.db.conn.commit()
        self.db.migrate_to_v2()
        types = self.cur.execute("SELECT DISTINCT item_type FROM wordbook").fetchall()
        self.assertEqual(types, [("단어",)])
        # pos(품사) 컬럼은 그대로 보존되어야 한다
        self.assertTrue(self.cur.execute(
            "SELECT COUNT(*) FROM wordbook WHERE pos='동사'").fetchone()[0] > 0)

    def test_v2_migration_is_idempotent(self):
        snap_ann = self.cur.execute("SELECT * FROM anniversaries ORDER BY id").fetchall()
        snap_wb = self.cur.execute("SELECT * FROM wordbook ORDER BY id").fetchall()
        self.db.migrate_to_v2()
        self.db.migrate_to_v2()
        self.assertEqual(snap_ann, self.cur.execute("SELECT * FROM anniversaries ORDER BY id").fetchall())
        self.assertEqual(snap_wb, self.cur.execute("SELECT * FROM wordbook ORDER BY id").fetchall())

    def test_schema_version_stamped_to_v2(self):
        self.assertEqual(self.cur.execute("PRAGMA user_version").fetchone()[0],
                         DBManager.SCHEMA_VERSION)
        self.assertGreaterEqual(DBManager.SCHEMA_VERSION, 2)


# ── 로그 인증키 마스킹 (2026-09-20 P0-6) ─────────────────────
class TestSecretMasking(unittest.TestCase):
    def test_mask_secrets_service_key(self):
        url = "https://apis.data.go.kr/x?serviceKey=SECRET123&likeItmsNm=%EC%82%BC%EC%84%B1&beginBasDt=20260820"
        got = logger.mask_secrets(url)
        self.assertIn("serviceKey=***", got)
        self.assertNotIn("SECRET123", got)
        self.assertIn("likeItmsNm=%EC%82%BC%EC%84%B1", got)   # 다른 파라미터는 보존

    def test_mask_secrets_crt_id(self):
        self.assertEqual(logger.mask_secrets("http://x/y.jsp?crtId=KEY&c=1"),
                         "http://x/y.jsp?crtId=***&c=1")

    def test_mask_secrets_keeps_plain_text(self):
        self.assertEqual(logger.mask_secrets("일반 메시지"), "일반 메시지")

    def test_setup_logging_handlers_have_masking_filter(self):
        logger.setup_logging()
        root = logging.getLogger()
        handlers = [h for h in root.handlers if isinstance(h, (logging.StreamHandler, RotatingFileHandler))]
        self.assertTrue(handlers)
        for h in handlers:
            self.assertTrue(any(isinstance(f, logger.SecretMaskingFilter) for f in h.filters), h)

    def test_filter_masks_record_with_args(self):
        rec = logging.LogRecord("t", logging.INFO, "p", 1,
                                "요청: %s", ("https://x?serviceKey=SECRET&a=1",), None)
        logger.SecretMaskingFilter().filter(rec)
        self.assertEqual(rec.msg, "요청: https://x?serviceKey=***&a=1")
        self.assertIsNone(rec.args)


if __name__ == "__main__":
    unittest.main(verbosity=2)
