# -*- coding: utf-8 -*-
"""UI smoke tests (Day-4 P1-8): 9 views + market tab essentials.

Run:
    python -m unittest tests.test_ui_smoke -v
Market search is stubbed at class level so the suite is offline and deterministic.
Note: Treeview cells that look like pure numbers are coerced to int by Tk on
read-back (display is unaffected), so assertions use the formatters.
"""
from __future__ import annotations

import runpy
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_G = None


def _load():
    """Load 10yp_2.py once (module name starts with a digit, so use runpy)."""
    global _G
    if _G is None:
        _G = runpy.run_path(str(ROOT / "10yp_2.py"), run_name="sched_ui_smoke")
    return _G


STUB_ITEMS = [
    {"symbol": "000810", "name": "테스트가", "price": "900",
     "change": "-10", "change_pct": "-1.0", "volume": "50",
     "market": "KOSPI", "base_date": "20260919"},
    {"symbol": "000810", "name": "테스트가", "price": "1000",
     "change": "+10", "change_pct": "+1.0", "volume": "100",
     "market": "KOSPI", "base_date": "20260920"},
    {"symbol": "005930", "name": "테스트나", "price": "75000",
     "change": "0", "change_pct": "0", "volume": "1000",
     "market": "KOSPI", "base_date": "20260920"},
]


class TestUISmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._g = _load()
        from core.market_fetcher import MarketFetcher
        cls._patcher = mock.patch.object(MarketFetcher, "search_stocks",
                                         return_value={"result": {"items": STUB_ITEMS}})
        cls._patcher.start()
        cls.app = cls._g["SchedulerApp"]()

    @classmethod
    def tearDownClass(cls):
        cls._patcher.stop()
        try:
            cls.app.destroy()
        except Exception:
            pass

    VIEWS = ("monthly", "weekly", "daily", "report", "study", "news",
             "market", "ledger", "settings")

    def test_all_views_switch_without_exception(self):
        for view in self.VIEWS:
            self.app.switch_view(view)
            self.app.update_idletasks()
        # re-entering a view must not duplicate widgets (switch_view clears first)
        self.app.switch_view("market")
        self.app.switch_view("market")
        self.assertTrue(self.app.content_area.winfo_children())

    def test_market_widgets_present(self):
        self.app.switch_view("market")
        app = self.app
        self.assertTrue(hasattr(app, "_market_tree"))
        tree = app._market_tree
        self.assertEqual(list(tree["columns"]),
                         ["symbol", "name", "price", "change", "change_pct",
                          "volume", "market"])
        heads = [tree.heading(c)["text"] for c in tree["columns"]]
        self.assertEqual(heads, ["종목코드", "종목명", "종가", "전일대비",
                                 "등락률", "거래량", "시장"])
        for attr in ("_market_info_lbl", "_market_status_lbl", "_market_chart_canvas",
                     "market_search_var", "_market_meta"):
            self.assertTrue(hasattr(app, attr), attr)
        parent_children = tree.master.winfo_children()
        classes = [w.winfo_class() for w in parent_children]
        self.assertTrue(any(c in ("Scrollbar", "TScrollbar") for c in classes),
                        f"vertical scrollbar missing: {classes}")

    def test_market_search_rows_iids_and_format(self):
        self.app.switch_view("market")
        self.app.market_search_var.set("스텁")
        self.app._search_market()
        end = time.time() + 10
        while time.time() < end and not self.app._market_tree.get_children():
            try:
                self.app.update()
            except Exception:
                pass
            time.sleep(0.05)
        tree = self.app._market_tree
        rows = list(tree.get_children())
        self.assertEqual(sorted(rows), ["000810", "005930"])  # deduped, iid == symbol
        vals = tree.item("000810")["values"]
        self.assertEqual(self.app._cell_str(vals[0]), "000810")   # leading zeros kept
        self.assertEqual(str(vals[1]), "테스트가")
        self.assertEqual(str(vals[2]), "1,000")                    # latest base_date row
        # Tk coerces "+10" to int 10 on read-back; the formatter must recover the sign
        self.assertEqual(self.app._fmt_signed(vals[3]), "+10")
        self.assertEqual(str(vals[4]), "+1.00%")
        self.assertEqual(str(vals[5]), "100")
        self.assertEqual(self.app.market_mode, "search")
        self.assertIn("실데이터", self.app._market_status_lbl.cget("text"))

    def test_market_stale_token_discarded(self):
        self.app.switch_view("market")
        before = len(self.app._market_tree.get_children())
        self.app._apply_market_rows([{"symbol": "999999", "name": "오래된",
                                      "price": "1", "market": ""}],
                                    "", "old", False, 0)
        self.assertEqual(len(self.app._market_tree.get_children()), before)
        self.assertNotIn("999999", self.app._market_tree.get_children())

    def test_market_select_summary(self):
        self.app.switch_view("market")
        token = self.app._market_search_token
        self.app._apply_market_rows([{"symbol": "000810", "name": "요약테스트",
                                      "price": "2000", "change": "+100",
                                      "change_pct": "+5.0", "volume": "10",
                                      "market": "KOSPI"}],
                                    "", "kw", False, token)
        tree = self.app._market_tree
        self.assertIn("000810", tree.get_children())
        tree.selection_set("000810")
        self.app._on_market_select()
        text = self.app._market_info_lbl.cget("text")
        self.assertIn("요약테스트", text)
        self.assertIn("000810", text)
        self.assertIn("2,000", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)