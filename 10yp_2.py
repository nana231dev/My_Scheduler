import tkinter as tk
from tkinter import messagebox, filedialog
import tkinter.ttk as tk_ttk 
import calendar
from datetime import datetime, date, timedelta
from pathlib import Path
import sqlite3
import pandas as pd
from korean_lunar_calendar import KoreanLunarCalendar
import os
import zipfile

# =========================================================
# ttkbootstrap 라이브러리 설정
# =========================================================
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

try:
    from ttkbootstrap.widgets import ToastNotification
except ImportError:
    from ttkbootstrap.toast import ToastNotification

try:
    from ttkbootstrap.widgets.tableview import Tableview
except ImportError:
    from ttkbootstrap.tableview import Tableview

try:
    from ttkbootstrap.widgets.scrolled import ScrolledText
except ImportError:
    from ttkbootstrap.scrolled import ScrolledText

# 달력을 일요일부터 시작하도록 설정
calendar.setfirstweekday(calendar.SUNDAY)

# 요일 헤더 칸 배경색 (옅은 블루) - 내용 칸과 구분
LBLUE = "#C9E2F6"
# 옅은 블루 배경 위 요일별 텍스트 색
LBLUE_FG = {
    "danger": "#B00020",
    "primary": "#0d6efd",
    "secondary": "#333333",
    "success": "#0a7a3a",
}

# =========================================================
# 1. 공통 모듈 (24절기 계산, DB 관리) - core 패키지에서 임포트 (2026-09-04 분리)
# =========================================================
from core.solar_terms import SolarTerms
from core.db_manager import DBManager
from core.market_fetcher import MarketFetcher
from core.logger import get_logger, setup_logging

setup_logging()  # 모든 core 모듈 print → logging (archive/logs/app.log)
log = get_logger(__name__)
from core.exceptions import handle_error  # noqa: E402
from core.i18n import t as i18n_t  # noqa: E402
from core import formulas as formulas_lib
from core import glossary as glossary_lib
from core import news_summarizer
from core import quote_data
from core import idiom_data
from core import hanja_data
from core import science_data
from core import history_data
from core.news_fetcher import fetch_sources, get_source_names, get_categories, get_sources_by_category, get_source_category, build_search_sources
import threading
import webbrowser

# =========================================================
# 2. 데이터베이스 관리 클래스 (core 패키지로 이관됨 - 이하 삭제 영역)
# =========================================================
_CORE_MIGRATED_MARKER = True

# =========================================================
# 2. 일정 편집 팝업창
# =========================================================
# ── 일정 편집 팝업: ui/daily_editor.py로 추출 (뷰 분리 1단계, 2026-09-14) ──
from ui.daily_editor import DailyEditor  # noqa: E402

# =========================================================
# 4. 메인 애플리케이션
# =========================================================
class SchedulerApp(ttk.Window):
    def __init__(self):
        super().__init__(themename="darkly")
        self.title("Smart Scheduler Pro")
        self.geometry("1600x950")
        
        self.db = DBManager()
        self._auto_backup_on_start()   # 시작 시 일 1회 자동 백업 (2026-09-20 P0-1)
        self.lunar = KoreanLunarCalendar()
        self.solar_term = SolarTerms()
        # 금융원 OpenAPI 인증키: config.json에서 로드, 없으면 빈 문자열(Mock 모드)
        try:
            from core.config_manager import get_api_key
            self.api_key = get_api_key("fss_stock") or ""
        except (OSError, ValueError, KeyError):
            self.api_key = ""
        self.api_keys = {
            "fss_stock": self.api_key,
            "fss_product": "",
            "fss_index": "",
            "fss_company": "",
        }
        try:
            from core.config_manager import get_all_api_keys
            saved = get_all_api_keys()
            if isinstance(saved, dict):
                self.api_keys.update({k: v for k, v in saved.items() if v})
                if self.api_keys.get("fss_stock"):
                    self.api_key = self.api_keys["fss_stock"]
        except (OSError, ValueError, KeyError):
            pass
        
        self.now = datetime.now()
        self.today = self.now.date()
        self.curr_year = self.now.year
        self.curr_month = self.now.month
        self.curr_week_start = self.get_sunday(self.now)
        
        self.current_view_name = "monthly"
        self.setup_layout()
        self.after(600, self.show_startup_reminder)  # 시작 리마인더 (2026-09-13)

    # --- 시작 시 요약 알림 (리마인더, 2026-09-13 — 설정: config.json show_reminder) ---
    def show_startup_reminder(self):
        """오늘 일정/D-Day(30일)/복습 대상/이번 달 지출 요약 팝업"""
        try:
            from core.config_manager import load_config
            if not load_config().get("show_reminder", True):
                return
        except (OSError, ValueError, KeyError):
            pass
        today_str = self.today.strftime("%Y-%m-%d")
        sch = self.db.get_schedule(today_str)
        sched_lines = [ln.strip() for ln in (sch.get("schedule") or "").splitlines() if ln.strip()]
        dday_items = []
        for d in self.db.get_ddays():
            try:
                target = datetime.strptime(d["date"], "%Y-%m-%d").date()
            except (ValueError, KeyError, TypeError):
                continue
            diff = (target - self.today).days
            if 0 <= diff <= 30:
                txt = "D-Day" if diff == 0 else f"D-{diff}"
                dday_items.append((diff, f"{d['title']} ({txt}, {d['date']})"))
        dday_items.sort()
        try:
            due_n = len(self.db.get_words_due_for_review(limit=200))
        except sqlite3.Error:
            due_n = 0
        s = self.db.get_month_summary(self.today.year, self.today.month)

        win = tk.Toplevel(self)
        win.title(i18n_t("reminder_title"))
        win.geometry("560x500")
        win.transient(self)
        ttk.Label(win, text=f"📅 {self.today.year}년 {self.today.month}월 {self.today.day}일",
                  font=("Malgun Gothic", 16, "bold"), bootstyle="primary").pack(pady=(14, 6))
        body = ScrolledText(win, font=("Malgun Gothic", 11), height=17, bootstyle="secondary")
        body.pack(fill=BOTH, expand=YES, padx=12, pady=4)
        lines = [i18n_t("reminder_schedule"),
                 "   " + ("\n   ".join(sched_lines[:8]) if sched_lines else i18n_t("reminder_no_schedule")),
                 "",
                 i18n_t("reminder_dday"),
                 "   " + ("\n   ".join(x for _, x in dday_items[:6]) if dday_items else i18n_t("reminder_no_dday")),
                 "",
                 f"{i18n_t('reminder_review')}: {due_n}개" + ("  → 공부 탭 '🔁 오늘 복습'!" if due_n else " 🎉"),
                 "",
                 i18n_t("reminder_ledger"),
                 f"   수입 {s['income']:,}원 · 지출 {s['expense']:,}원 · 순저축 {s['savings']:,}원"]
        body.insert("1.0", "\n".join(lines))
        body.text.configure(state="disabled")
        foot = ttk.Frame(win)
        foot.pack(fill=X, padx=12, pady=(0, 10))
        var_show = tk.BooleanVar(value=True)
        ttk.Checkbutton(foot, text=i18n_t("reminder_toggle"), variable=var_show,
                        bootstyle="secondary-round-toggle").pack(side=LEFT)

        def on_close():
            try:
                from core.config_manager import load_config, save_config
                cfg = load_config()
                cfg["show_reminder"] = bool(var_show.get())
                save_config(cfg)
            except (OSError, ValueError, KeyError):
                pass
            win.destroy()

        ttk.Button(foot, text="닫기", command=on_close, bootstyle="secondary-outline").pack(side=RIGHT)

    def get_sunday(self, dt):
        if isinstance(dt, datetime): dt = dt.date()
        idx = (dt.weekday() + 1) % 7
        return dt - timedelta(days=idx)

    # --- 날짜/기념일 계산 로직 (연도, 반복, 연휴, 대체공휴일) ---
    def get_ann_display_list(self, date_obj):
        anns = self.db.get_anniversaries()
        matched = []
        
        # 1. 양력 체크
        for ann in anns:
            if ann["type"] == 0:
                if ann["is_repeat"] or ann["year"] == date_obj.year:
                    if ann["month"] == date_obj.month and ann["day"] == date_obj.day:
                        matched.append(ann)

        # 2. 음력 변환 및 체크
        self.lunar.setSolarDate(date_obj.year, date_obj.month, date_obj.day)
        iso = self.lunar.LunarIsoFormat()
        is_leap = "Intercalation" in iso
        clean_iso = iso.replace(" Intercalation", "")
        
        try: lm, ld = map(int, clean_iso.split('-')[1:3])
        except (ValueError, IndexError): lm, ld = 0, 0
        
        if not is_leap:
            for ann in anns:
                if ann["type"] == 1: # 음력
                    if ann["is_repeat"] or ann["year"] == date_obj.year:
                        if ann["month"] == lm and ann["day"] == ld:
                            matched.append(ann)

        # 3. 설날/추석 연휴 자동 생성 (음력 1.1, 8.15 앞뒤 날짜)
        # 내일 날짜 체크 (내일이 명절 당일이면 오늘은 연휴)
        tom_solar = date_obj + timedelta(days=1)
        self.lunar.setSolarDate(tom_solar.year, tom_solar.month, tom_solar.day)
        tom_iso = self.lunar.LunarIsoFormat()
        if "Intercalation" not in tom_iso:
            try: 
                tlm, tld = map(int, tom_iso.split('-')[1:3])
                if (tlm==1 and tld==1): matched.append({"name": "설날 연휴", "is_holiday": 1, "year":0, "is_repeat":1})
                if (tlm==8 and tld==15): matched.append({"name": "추석 연휴", "is_holiday": 1, "year":0, "is_repeat":1})
            except (ValueError, IndexError): pass

        # 어제 날짜 체크 (어제가 명절 당일이면 오늘은 연휴)
        yest_solar = date_obj - timedelta(days=1)
        self.lunar.setSolarDate(yest_solar.year, yest_solar.month, yest_solar.day)
        yest_iso = self.lunar.LunarIsoFormat()
        if "Intercalation" not in yest_iso:
            try:
                ylm, yld = map(int, yest_iso.split('-')[1:3])
                if (ylm==1 and yld==1): matched.append({"name": "설날 연휴", "is_holiday": 1, "year":0, "is_repeat":1})
                if (ylm==8 and yld==15): matched.append({"name": "추석 연휴", "is_holiday": 1, "year":0, "is_repeat":1})
            except (ValueError, IndexError): pass

        return matched, f"{'윤' if is_leap else '음'} {lm}.{ld}"

    def get_day_info(self, date_obj):
        matched_anns, lunar_txt = self.get_ann_display_list(date_obj)
        term = self.solar_term.get_solar_term(date_obj.month, date_obj.day)
        
        final_list = []
        is_holiday = False
        
        for ann in matched_anns:
            final_list.append(ann)
            if ann.get("is_holiday"): is_holiday = True
            
        # 대체 공휴일 로직
        if not is_holiday:
            # 1. 월요일 체크 (일요일이 국경일 등인 경우)
            if date_obj.weekday() == 0: 
                yesterday = date_obj - timedelta(days=1)
                y_anns, _ = self.get_ann_display_list(yesterday)
                for ya in y_anns:
                    if ya.get("is_holiday") and "신정" not in ya["name"]:
                        final_list.append({"name": "대체공휴일", "is_holiday": True, "year":0, "is_repeat":1})
                        break
            
            # 2. 설날/추석 연휴 중 일요일이 껴있으면 다음 평일까지 밀림
            yesterday = date_obj - timedelta(days=1)
            y_anns, _ = self.get_ann_display_list(yesterday)
            is_y_sc = any(("설날" in a["name"] or "추석" in a["name"]) and a.get("is_holiday") for a in y_anns)

            if is_y_sc:
                found_sunday_overlap = False
                for k in range(4): # 4일 전까지 체크
                    past = date_obj - timedelta(days=k+1)
                    p_anns, _ = self.get_ann_display_list(past)
                    if any(("설날" in a["name"] or "추석" in a["name"]) and a.get("is_holiday") for a in p_anns):
                        if past.weekday() == 6: 
                            found_sunday_overlap = True
                    else:
                        break 
                
                if found_sunday_overlap:
                    final_list.append({"name": "대체공휴일", "is_holiday": True, "year":0, "is_repeat":1})

        return lunar_txt, term, final_list

    # --- UI Layout ---
    def setup_layout(self):
        container = ttk.Frame(self)
        container.pack(fill=BOTH, expand=YES)

        # 1. 사이드바
        sidebar = ttk.Frame(container, width=280, bootstyle="secondary")
        sidebar.pack(side=LEFT, fill=Y)
        sidebar.pack_propagate(False) 
        
        ttk.Label(sidebar, text="📅 Plan Master", font=("Arial", 20, "bold"), bootstyle="inverse-secondary").pack(pady=40)

        menu_frame = ttk.Frame(sidebar, bootstyle="secondary")
        menu_frame.pack(fill=X, padx=10)

        ttk.Button(menu_frame, text="📅 월간 달력", command=lambda: self.switch_view("monthly"), bootstyle="light-outline", width=25).pack(pady=3)
        ttk.Button(menu_frame, text="📆 주간 플래너", command=lambda: self.switch_view("weekly"), bootstyle="light-outline", width=25).pack(pady=3)
        ttk.Button(menu_frame, text="📄 일간 일지", command=lambda: self.switch_view("daily"), bootstyle="light-outline", width=25).pack(pady=3)
        ttk.Button(menu_frame, text="📋 전체 목록", command=lambda: self.switch_view("report"), bootstyle="light-outline", width=25).pack(pady=3)
        ttk.Separator(menu_frame, bootstyle="secondary").pack(fill=X, pady=6)
        ttk.Button(menu_frame, text="📚 공부 (Study)", command=lambda: self.switch_view("study"), bootstyle="primary-outline", width=25).pack(pady=3)
        ttk.Button(menu_frame, text="📰 뉴스 & 정보", command=lambda: self.switch_view("news"), bootstyle="light-outline", width=25).pack(pady=3)
        ttk.Button(menu_frame, text="📈 증권 (Market)", command=lambda: self.switch_view("market"), bootstyle="info-outline", width=25).pack(pady=3)
        ttk.Button(menu_frame, text="💰 가계부", command=lambda: self.switch_view("ledger"), bootstyle="warning-outline", width=25).pack(pady=3)
        ttk.Separator(menu_frame, bootstyle="secondary").pack(fill=X, pady=6)
        ttk.Button(menu_frame, text="⚙️ 설정 (Settings)", command=lambda: self.switch_view("settings"), bootstyle="light-outline", width=25).pack(pady=3)

        ttk.Label(sidebar, text="📌 이번 달 일정/기념일", bootstyle="inverse-secondary", font=("Malgun Gothic", 11, "bold")).pack(pady=(20, 5), padx=10, anchor="w")
        
        self.sidebar_list = ttk.Treeview(sidebar, columns=("date", "sch"), show="headings", height=6, selectmode="none")
        self.sidebar_list.column("date", width=60, anchor="center")
        self.sidebar_list.column("sch", width=180, anchor="w")
        self.sidebar_list.heading("date", text="날짜")
        self.sidebar_list.heading("sch", text="내용")
        self.sidebar_list.pack(fill=BOTH, expand=True, padx=10, pady=(0, 10))
        
        # D-Day 리스트
        ttk.Label(sidebar, text="⏳ D-Day", bootstyle="inverse-secondary", font=("Malgun Gothic", 11, "bold")).pack(pady=(10, 5), padx=10, anchor="w")
        self.sidebar_dday_list = ttk.Treeview(sidebar, columns=("dday", "title"), show="headings", height=4, selectmode="none")
        self.sidebar_dday_list.column("dday", width=70, anchor="center")
        self.sidebar_dday_list.column("title", width=170, anchor="w")
        self.sidebar_dday_list.heading("dday", text="D-Day")
        self.sidebar_dday_list.heading("title", text="목표")
        self.sidebar_dday_list.pack(fill=BOTH, expand=True, padx=10, pady=(0, 20))

        progress_frame = ttk.Frame(sidebar, bootstyle="secondary")
        progress_frame.pack(side=BOTTOM, pady=20, fill=X, padx=10)
        
        ttk.Label(progress_frame, text="Year Progress", bootstyle="inverse-secondary", font=("Arial", 11, "bold")).pack(pady=(0, 5))
        
        self.progress_bar = ttk.Progressbar(
            progress_frame, 
            orient="horizontal",
            maximum=100,
            value=0,
            bootstyle="info-striped"
        )
        self.progress_bar.pack(fill=X, pady=(0, 5))
        
        self.year_progress_label = ttk.Label(progress_frame, text="계산 중...", bootstyle="inverse-secondary", font=("Arial", 9))
        self.year_progress_label.pack()
        self.update_year_progress()

        # 2. 메인 콘텐츠
        self.content_area = ttk.Frame(container, padding=15)
        self.content_area.pack(side=RIGHT, fill=BOTH, expand=YES)
        
        self.switch_view("monthly")

    def update_year_progress(self):
        start = date(self.curr_year, 1, 1)
        end = date(self.curr_year, 12, 31)
        total = (end - start).days + 1
        passed = (self.today - start).days
        remaining = total - passed
        percent = int((passed / total) * 100)
        self.progress_bar.config(value=percent)
        self.year_progress_label.config(text=f"{passed}일 지남 / {remaining}일 남음 ({percent}%)")

    def update_sidebar_summary(self):
        # 일정 리스트 업데이트
        for item in self.sidebar_list.get_children():
            self.sidebar_list.delete(item)
            
        _, last_day = calendar.monthrange(self.curr_year, self.curr_month)
        
        for day in range(1, last_day + 1):
            curr_date = date(self.curr_year, self.curr_month, day)
            date_str = curr_date.strftime("%Y-%m-%d")
            
            _, _, anns = self.get_day_info(curr_date)
            sch = self.db.get_schedule(date_str)
            
            for ann in anns:
                tag = "★" if ann.get('is_holiday') else "☆"
                self.sidebar_list.insert("", "end", values=(f"{self.curr_month}/{day}", f"{tag} {ann['name']}"))
            
            if sch["schedule"]:
                lines = sch["schedule"].strip().split("\n")
                if lines:
                    self.sidebar_list.insert("", "end", values=(f"{self.curr_month}/{day}", f"• {lines[0]}"))

        # D-Day 리스트 업데이트
        for item in self.sidebar_dday_list.get_children():
            self.sidebar_dday_list.delete(item)
        ddays = self.db.get_ddays()
        for d in ddays:
            try:
                target = datetime.strptime(d["date"], "%Y-%m-%d").date()
                diff = (target - self.today).days
                if diff > 0: txt = f"D-{diff}"
                elif diff < 0: txt = f"D+{abs(diff)}"
                else: txt = "D-Day"
                self.sidebar_dday_list.insert("", "end", values=(txt, d["title"]))
            except (ValueError, KeyError): pass

    def switch_view(self, view_name):
        self.current_view_name = view_name
        for widget in self.content_area.winfo_children():
            widget.destroy()

        try:
            self.update_sidebar_summary()
        except Exception as e:  # noqa: BLE001 - 사이드바 실패가 뷰 전환을 막지 않게 한다(P0-4)
            log.exception("[사이드바] 요약 갱신 실패: %s", e)

        builders = {
            "monthly": self.setup_monthly_view,
            "weekly": self.setup_weekly_view,
            "daily": self.setup_daily_view,
            "report": self.setup_report_view,
            "study": self.setup_study_view,
            "news": self.setup_news_view,
            "market": self.setup_market_view,
            "ledger": self.setup_ledger_view,
            "settings": self.setup_settings_view,
        }
        builder = builders.get(view_name)
        if builder is None:
            return

        try:
            builder()
            self._view_error_lbl = None
        except Exception as e:  # noqa: BLE001 - 한 뷰의 오류가 앱 전체를 죽이지 않게 격리한다(P0-4)
            log.exception("[%s] 뷰 생성 실패: %s", view_name, e)
            self._view_error_lbl = ttk.Label(
                self.content_area,
                text=(f"⚠️ '{view_name}' 화면을 여는 중 오류가 발생했습니다.\n"
                      f"{type(e).__name__}: {e}\n"
                      "상세 내용은 archive/logs/app.log 에 기록되었습니다."),
                bootstyle="danger", padding=20, justify="left",
            )
            self._view_error_lbl.pack(fill=BOTH, expand=YES, padx=20, pady=20)
    
    # -------------------------------------------------------------
    # 뷰: 공식집 (수학/과학 160공식) — 재구축 2026-09-12
    # -------------------------------------------------------------
    def setup_formulas_view(self):
        header = ttk.Frame(self.content_area)
        header.pack(fill=X, pady=(0, 10))
        ttk.Label(header, text="📐 공식집", font=("Malgun Gothic", 18, "bold")).pack(side=LEFT)

        ctrl = ttk.Frame(self.content_area)
        ctrl.pack(fill=X, pady=(0, 5))
        ttk.Label(ctrl, text="주가:").pack(side=LEFT, padx=(0, 3))
        levels = ["전체"] + list(formulas_lib.LEVELS)
        self.formula_level_var = tk.StringVar(value="전체")
        level_combo = ttk.Combobox(ctrl, textvariable=self.formula_level_var, values=levels, width=8, state="readonly")
        level_combo.pack(side=LEFT, padx=(0, 10))
        level_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_formula_tree())

        ttk.Label(ctrl, text="분야:").pack(side=LEFT, padx=(0, 3))
        cats = ["전체"] + formulas_lib.get_categories()
        self.formula_cat_var = tk.StringVar(value="전체")
        cat_combo = ttk.Combobox(ctrl, textvariable=self.formula_cat_var, values=cats, width=12, state="readonly")
        cat_combo.pack(side=LEFT, padx=(0, 10))
        cat_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_formula_tree())

        ttk.Label(ctrl, text="검색:").pack(side=LEFT, padx=(0, 3))
        self.formula_search_entry = ttk.Entry(ctrl, width=24)
        self.formula_search_entry.pack(side=LEFT, padx=(0, 5))
        self.formula_search_entry.bind("<Return>", lambda e: self._refresh_formula_tree())
        ttk.Button(ctrl, text="🔎 검색", command=self._refresh_formula_tree, bootstyle="info-outline").pack(side=LEFT, padx=(0, 5))
        ttk.Button(ctrl, text="전체보기", command=lambda: (self.formula_search_entry.delete(0, "end"), self._refresh_formula_tree()), bootstyle="secondary-outline").pack(side=LEFT)

        self.formula_count_lbl = ttk.Label(self.content_area, text="", bootstyle="secondary")
        self.formula_count_lbl.pack(anchor="w", pady=(0, 3))

        tree_box = ttk.Frame(self.content_area)
        tree_box.pack(fill=BOTH, expand=YES)
        cols = ("cat", "level", "name", "expr")
        self.formula_tree = ttk.Treeview(tree_box, columns=cols, show="headings", bootstyle="info")
        self.formula_tree.heading("cat", text="분야")
        self.formula_tree.heading("level", text="주가")
        self.formula_tree.heading("name", text="공식 이름")
        self.formula_tree.heading("expr", text="식")
        self.formula_tree.column("cat", width=100, anchor="center")
        self.formula_tree.column("level", width=60, anchor="center")
        self.formula_tree.column("name", width=220, anchor="w")
        self.formula_tree.column("expr", width=430, anchor="w")
        vsb = ttk.Scrollbar(tree_box, orient=VERTICAL, command=self.formula_tree.yview, bootstyle="round-info")
        self.formula_tree.configure(yscrollcommand=vsb.set)
        self.formula_tree.pack(side=LEFT, fill=BOTH, expand=YES)
        vsb.pack(side=RIGHT, fill=Y)
        self._refresh_formula_tree()

    def _refresh_formula_tree(self):
        keyword = self.formula_search_entry.get().strip()
        level = self.formula_level_var.get()
        cat = self.formula_cat_var.get()
        rows = formulas_lib.search(keyword) if keyword else formulas_lib.get_all()
        if level != "전체":
            rows = [r for r in rows if r[1] == level]
        if cat != "전체":
            rows = [r for r in rows if r[0] == cat]
        for item in self.formula_tree.get_children():
            self.formula_tree.delete(item)
        for r in rows:
            self.formula_tree.insert("", "end", values=(r[0], r[1], r[2], r[3]))
        self.formula_count_lbl.config(text=f"총 {len(rows)}개 공식")

    # -------------------------------------------------------------
    # 뷰: 용어집 (과학/공학 100용어) — 재구축 2026-09-12
    # -------------------------------------------------------------
    def setup_glossary_view(self):
        header = ttk.Frame(self.content_area)
        header.pack(fill=X, pady=(0, 10))
        ttk.Label(header, text="🔬 용어집", font=("Malgun Gothic", 18, "bold")).pack(side=LEFT)

        ctrl = ttk.Frame(self.content_area)
        ctrl.pack(fill=X, pady=(0, 5))
        ttk.Label(ctrl, text="구분:").pack(side=LEFT, padx=(0, 3))
        cats = ["전체"] + glossary_lib.get_categories()
        self.glossary_cat_var = tk.StringVar(value="전체")
        cat_combo = ttk.Combobox(ctrl, textvariable=self.glossary_cat_var, values=cats, width=12, state="readonly")
        cat_combo.pack(side=LEFT, padx=(0, 10))
        cat_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_glossary_tree())

        ttk.Label(ctrl, text="검색:").pack(side=LEFT, padx=(0, 3))
        self.glossary_search_entry = ttk.Entry(ctrl, width=28)
        self.glossary_search_entry.pack(side=LEFT, padx=(0, 5))
        self.glossary_search_entry.bind("<Return>", lambda e: self._refresh_glossary_tree())
        ttk.Button(ctrl, text="🔎 검색", command=self._refresh_glossary_tree, bootstyle="info-outline").pack(side=LEFT, padx=(0, 5))
        ttk.Button(ctrl, text="전체보기", command=lambda: (self.glossary_search_entry.delete(0, "end"), self._refresh_glossary_tree()), bootstyle="secondary-outline").pack(side=LEFT)

        self.glossary_count_lbl = ttk.Label(self.content_area, text="", bootstyle="secondary")
        self.glossary_count_lbl.pack(anchor="w", pady=(0, 3))

        tree_box = ttk.Frame(self.content_area)
        tree_box.pack(fill=BOTH, expand=YES)
        cols = ("cat", "term", "desc")
        self.glossary_tree = ttk.Treeview(tree_box, columns=cols, show="headings", bootstyle="success")
        self.glossary_tree.heading("cat", text="구분")
        self.glossary_tree.heading("term", text="용어")
        self.glossary_tree.heading("desc", text="설명")
        self.glossary_tree.column("cat", width=100, anchor="center")
        self.glossary_tree.column("term", width=260, anchor="w")
        self.glossary_tree.column("desc", width=450, anchor="w")
        vsb = ttk.Scrollbar(tree_box, orient=VERTICAL, command=self.glossary_tree.yview, bootstyle="round-success")
        self.glossary_tree.configure(yscrollcommand=vsb.set)
        self.glossary_tree.pack(side=LEFT, fill=BOTH, expand=YES)
        vsb.pack(side=RIGHT, fill=Y)
        self._refresh_glossary_tree()

    def _refresh_glossary_tree(self):
        keyword = self.glossary_search_entry.get().strip()
        cat = self.glossary_cat_var.get()
        rows = glossary_lib.search(keyword) if keyword else glossary_lib.get_all()
        if cat != "전체":
            rows = [r for r in rows if r[0] == cat]
        for item in self.glossary_tree.get_children():
            self.glossary_tree.delete(item)
        for r in rows:
            self.glossary_tree.insert("", "end", values=(r[0], r[1], r[2]))
        self.glossary_count_lbl.config(text=f"총 {len(rows)}개 용어")

    # -------------------------------------------------------------
    # 뷰 1: 월간 달력
    # -------------------------------------------------------------
    def setup_monthly_view(self):
        header = ttk.Frame(self.content_area)
        header.pack(fill=X, pady=(0, 20))
        
        nav_box = ttk.Frame(header)
        nav_box.pack(side=LEFT)
        
        ttk.Button(nav_box, text="◀", command=self.prev_mon, bootstyle="secondary-outline").pack(side=LEFT)
        self.lbl_mon = ttk.Label(nav_box, text="", font=("Arial", 24, "bold"), width=12, anchor="center")
        self.lbl_mon.pack(side=LEFT, padx=10)
        ttk.Button(nav_box, text="▶", command=self.next_mon, bootstyle="secondary-outline").pack(side=LEFT)
        
        ttk.Button(header, text="오늘 (Today)", command=self.go_today, bootstyle="info").pack(side=RIGHT)

        days_frame = tk.Frame(self.content_area, bg=LBLUE)
        days_frame.pack(fill=X, pady=(0, 5))
        days = ["일", "월", "화", "수", "목", "금", "토"]
        cols = ["danger", "secondary", "secondary", "secondary", "secondary", "secondary", "primary"]
        
        for i, d in enumerate(days):
            lbl = tk.Label(days_frame, text=d, bg=LBLUE, fg=LBLUE_FG.get(cols[i], "#333333"),
                           font=("Malgun Gothic", 11, "bold"), anchor="center")
            lbl.pack(side=LEFT, expand=YES, fill=X)

        # --- 오늘의 명언/고사성어/한자 영역 (월간 표 위) ---
        self.quote_frame = ttk.Labelframe(header, text=" 💡 오늘의 명언/고사성어/한자 ")
        self.quote_frame.pack(fill=X, pady=(0, 8))
        self.lbl_quote_text = ttk.Label(self.quote_frame, text="", wraplength=760, font=("Malgun Gothic", 12, "bold"))
        self.lbl_quote_text.pack(side=LEFT, fill=X, padx=8, pady=6)
        self.lbl_quote_text.bind("<Button-1>", lambda e: self._show_quote_meaning())
        self.btn_quote_fav = ttk.Button(self.quote_frame, text="⭐ 즐겨찾기", command=self._toggle_quote_favorite, bootstyle="success", width=12)
        self.btn_quote_fav.pack(side=RIGHT, padx=4, pady=4)
        self.btn_quote_meaning = ttk.Button(self.quote_frame, text="📖 의미 보기", command=self._show_quote_meaning, bootstyle="info-outline", width=12)
        self.btn_quote_meaning.pack(side=RIGHT, padx=4, pady=4)
        self.btn_quote_fav_list = ttk.Button(self.quote_frame, text="⭐ 목록", command=self.show_favorite_quotes, bootstyle="warning-outline", width=9)
        self.btn_quote_fav_list.pack(side=RIGHT, padx=4, pady=4)
        # 현재 표시된 명언 id 저장(즐겨찾기 토글용)
        self._cur_quote_id = None

        self.cal_frame = ttk.Frame(self.content_area)
        self.cal_frame.pack(fill=BOTH, expand=YES)
        self.update_monthly_grid()
        self.refresh_today_quote()

    # --- 오늘의 명언/고사성어/한자 표시 + 즐겨찾기 (2026-09-12) ---
    def refresh_today_quote(self):
        """월간 뷰 상단에 오늘의 명언/고사성어/한자 1개를 표시한다."""
        q = quote_data.today_quote()
        if not q:
            self.lbl_quote_text.config(text="오늘의 명언을 불러오지 못했습니다.")
            self._cur_quote_id = None
            self._update_quote_fav_button()
            return
        self._cur_quote_id = q.get("id")
        self.lbl_quote_text.config(text=q.get("text", ""))
        self._update_quote_fav_button()

    def _update_quote_fav_button(self):
        if not hasattr(self, "btn_quote_fav"):
            return
        if self._cur_quote_id and self.db.is_favorite_quote(self._cur_quote_id):
            self.btn_quote_fav.config(text="🗑 즐겨찾기 해제", bootstyle="danger")
        else:
            self.btn_quote_fav.config(text="⭐ 즐겨찾기", bootstyle="success")

    def show_favorite_quotes(self):
        """⭐ 즐겨찾기 목록 팝업 (명언/고사성어/한자 — 조회/삭제, 2026-09-13)"""
        win = tk.Toplevel(self)
        win.title("⭐ 즐겨찾기 목록")
        win.geometry("780x440")
        win.transient(self)
        top = ttk.Frame(win, padding=(10, 8))
        top.pack(fill=X)
        count_lbl = ttk.Label(top, text="", bootstyle="info", font=("Malgun Gothic", 10, "bold"))
        count_lbl.pack(side=LEFT)
        cols = ("kind", "text", "source", "added_at")
        tree = ttk.Treeview(win, columns=cols, show="headings", bootstyle="warning")
        for col, txt, w in [("kind", "유형", 80), ("text", "내용", 400), ("source", "출처", 150), ("added_at", "추가일시", 130)]:
            tree.heading(col, text=txt)
            tree.column(col, width=w, anchor="w" if col in ("text", "source") else "center")
        tree.pack(fill=BOTH, expand=YES, padx=10, pady=(0, 6))

        def refresh():
            for it in tree.get_children():
                tree.delete(it)
            favs = self.db.get_favorite_quotes()
            for f in favs:
                tree.insert("", "end", iid=str(f["id"]),
                            values=(f["kind"] or "-", f["text"], f["source"] or "-", f["added_at"] or "-"))
            count_lbl.config(text=f"총 {len(favs)}건")

        def del_selected():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("알림", "삭제할 항목을 선택하세요.", parent=win)
                return
            if not messagebox.askyesno("즐겨찾기 삭제", f"선택한 {len(sel)}건을 즐겨찾기에서 삭제할까요?", parent=win):
                return
            for fid in sel:
                self.db.remove_favorite_quote_by_id(int(fid))
            refresh()
            self._update_quote_fav_button()
            ToastNotification("즐겨찾기", f"{len(sel)}건 삭제", bootstyle="danger").show_toast()

        btn_box = ttk.Frame(win, padding=(10, 0, 10, 10))
        btn_box.pack(fill=X)
        ttk.Button(btn_box, text="🗑 선택 삭제", command=del_selected, bootstyle="danger-outline").pack(side=LEFT)
        ttk.Button(btn_box, text="닫기", command=win.destroy, bootstyle="secondary-outline").pack(side=RIGHT)
        refresh()

    def _show_quote_meaning(self):
        """현재 표시된 명언/고사성어/한자의 의미/해설을 팝업으로 보여준다."""
        if not self._cur_quote_id:
            messagebox.showinfo("의미 보기", "표시할 명언이 없습니다.")
            return
        q = quote_data.by_id(self._cur_quote_id)
        if not q:
            messagebox.showinfo("의미 보기", "해당 명언을 찾을 수 없습니다.")
            return
        text = quote_data.meaningful_text(q)
        if not text:
            messagebox.showinfo("의미 보기", "해설이 없는 항목입니다.")
            return
        win = tk.Toplevel(self)
        win.title("📖 의미/해설")
        win.geometry("460x220")
        win.transient(self)
        try:
            win.grab_set()
        except tk.TclError:
            pass
        ttk.Label(win, text=f"📌 {q.get('type','')} 항목", font=("Malgun Gothic", 10, "bold")).pack(pady=(8, 2))
        txt = tk.Text(win, wrap="char", font=("Malgun Gothic", 11), padx=10, pady=8)
        txt.pack(fill=BOTH, expand=True)
        txt.insert("1.0", text)
        txt.config(state="disabled")
        ttk.Button(win, text="닫기", command=win.destroy, bootstyle="secondary").pack(pady=6)

    def _toggle_quote_favorite(self):
        """현재 표시된 명언/고사성어/한자를 즐겨찾기 추가/해제한다."""
        if not self._cur_quote_id:
            messagebox.showinfo("즐겨찾기", "즐겨찾기할 명언이 없습니다.")
            return
        q = quote_data.by_id(self._cur_quote_id)
        if not q:
            messagebox.showinfo("즐겨찾기", "해당 명언을 찾을 수 없습니다.")
            return
        text = q.get("text") or ""
        meaning = q.get("meaning") or ""
        source = q.get("source") or ""
        kind = q.get("type") or q.get("kind") or ""
        if self.db.is_favorite_quote(self._cur_quote_id):
            ok = self.db.remove_favorite_quote(self._cur_quote_id)
            if ok:
                messagebox.showinfo("즐겨찾기 해제", "즐겨찾기에서 삭제했습니다.", parent=self)
                self._update_quote_fav_button()
            return
        ok = self.db.add_favorite_quote(self._cur_quote_id, text, meaning, source, kind)
        if ok:
            messagebox.showinfo("즐겨찾기 저장", "즐겨찾기에 추가했습니다.", parent=self)
            self._update_quote_fav_button()
        else:
            messagebox.showwarning("즐겨찾기", "이미 즐겨찾기에 있습니다.", parent=self)

    def update_monthly_grid(self):
        for w in self.cal_frame.winfo_children(): w.destroy()
        self.update_sidebar_summary()
        
        self.lbl_mon.config(text=f"{self.curr_year}. {self.curr_month:02d}")
        cal_data = calendar.monthcalendar(self.curr_year, self.curr_month)
        
        for r in range(6): self.cal_frame.rowconfigure(r, weight=1, uniform="row")
        for c in range(7): self.cal_frame.columnconfigure(c, weight=1, uniform="col")

        for r, week in enumerate(cal_data):
            for c, day in enumerate(week):
                if day == 0: continue
                
                dt = datetime(self.curr_year, self.curr_month, day)
                date_str = dt.strftime("%Y-%m-%d")
                lunar, term, anns = self.get_day_info(dt)
                sch = self.db.get_schedule(date_str)
                
                is_sun = (c == 0)
                is_sat = (c == 6)
                is_holiday_ann = any(a.get("is_holiday") for a in anns)
                is_vacation_txt = "휴가" in sch["schedule"] or "연차" in sch["schedule"]

                # [배경색/색상 로직] - 전체목록(Tableview)과 동일한 테마 기본색 사용 (테마 연동)
                C = self.style.colors
                if is_holiday_ann or is_sun or is_vacation_txt:
                    txt_color = "danger"
                    bg_color = C.bg
                elif is_sat:
                    txt_color = "primary" 
                    bg_color = C.bg
                else:
                    txt_color = "secondary"
                    bg_color = C.bg

                highlight = 0
                highlight_bg = "black"
                if dt.date() == self.today:
                    highlight = 2
                    highlight_bg = "#3498db" 

                cell = tk.Frame(self.cal_frame, bg=bg_color, highlightbackground=highlight_bg, highlightthickness=highlight, borderwidth=1, relief="solid")
                cell.grid(row=r, column=c, sticky="nsew", padx=0, pady=0)
                
                top = tk.Frame(cell, bg=bg_color)
                top.pack(fill=X)
                ttk.Label(top, text=str(day), bootstyle=txt_color, font=("Arial", 12, "bold"), background=bg_color).pack(side=LEFT)
                
                if term: ttk.Label(top, text=term, bootstyle="success", font=("Malgun Gothic", 8), background=bg_color).pack(side=RIGHT)
                elif lunar: ttk.Label(top, text=lunar, bootstyle="secondary", font=("Arial", 8), background=bg_color).pack(side=RIGHT)

                content_box = tk.Frame(cell, bg=bg_color)
                content_box.pack(fill=BOTH, expand=YES, pady=2)
                
                for ann in anns:
                    yr_txt = f"{ann['year']} " if not ann.get('is_repeat') and ann.get('year',0)>0 else ""
                    ttk.Label(content_box, text=f"★{yr_txt}{ann['name']}", bootstyle="danger" if ann.get('is_holiday') else "warning", font=("Malgun Gothic", 8), background=bg_color).pack(anchor="w")
                
                if sch["schedule"]:
                    lines = sch["schedule"].strip().split('\n')
                    for line in lines[:3]:
                        s_color = "danger" if ("휴가" in line or "연차" in line) else "primary"
                        ttk.Label(content_box, text=f"• {line}", bootstyle=s_color, font=("Malgun Gothic", 9), background=bg_color).pack(anchor="w")

                # 이미지 표시
                images = sch.get("images", [])
                if images:
                    ttk.Label(content_box, text="📷", bootstyle="warning", font=("Arial", 8), background=bg_color).pack(anchor="w")

                for w in [cell, top, content_box] + content_box.winfo_children() + top.winfo_children():
                    w.bind("<Button-1>", lambda e, d=date_str: self.open_pop(d))

    def prev_mon(self): 
        self.curr_month -= 1
        if self.curr_month == 0: self.curr_month = 12; self.curr_year -= 1
        self.update_monthly_grid()
        self.refresh_today_quote()

    def next_mon(self): 
        self.curr_month += 1
        if self.curr_month == 13: self.curr_month = 1; self.curr_year += 1
        self.update_monthly_grid()
        self.refresh_today_quote()

    def go_today(self):
        self.curr_year, self.curr_month = self.now.year, self.now.month
        self.update_monthly_grid()
        self.refresh_today_quote()

    # -------------------------------------------------------------
    # 뷰 2: 주간 플래너
    # -------------------------------------------------------------
    def setup_weekly_view(self):
        header = ttk.Frame(self.content_area)
        header.pack(fill=X, pady=(0, 20))

        nav_box = ttk.Frame(header)
        nav_box.pack(side=LEFT)

        ttk.Button(nav_box, text="◀ 이전 주", command=self.prev_week, bootstyle="secondary-outline").pack(side=LEFT)
        self.lbl_week = ttk.Label(nav_box, text="", font=("Arial", 18, "bold"), width=25, anchor="center")
        self.lbl_week.pack(side=LEFT, padx=10)
        ttk.Button(nav_box, text="다음 주 ▶", command=self.next_week, bootstyle="secondary-outline").pack(side=LEFT)
        
        ttk.Button(header, text="이번 주", command=self.go_today_week, bootstyle="info").pack(side=RIGHT)

        self.week_frame = ttk.Frame(self.content_area)
        self.week_frame.pack(fill=BOTH, expand=YES)
        
        self.update_weekly_grid()

    def update_weekly_grid(self):
        for w in self.week_frame.winfo_children(): w.destroy()
        self.update_sidebar_summary()

        week_end = self.curr_week_start + timedelta(days=6)
        period_str = f"{self.curr_week_start.strftime('%Y.%m.%d')} ~ {week_end.strftime('%m.%d')}"
        self.lbl_week.config(text=period_str)

        for i in range(8):
            self.week_frame.columnconfigure(i, weight=1)
            self.week_frame.rowconfigure(0, weight=1) 
            self.week_frame.rowconfigure(1, weight=10) 

            # 주간 요약
            if i == 0:
                summary_key = f"W-{self.curr_week_start.strftime('%Y-%m-%d')}" # 주간 DB 키 (W-YYYY-MM-DD, 주 시작 일요일 기준 표준 포맷)
                saved_summary = self.db.get_schedule(summary_key)
                
                weekly_list_text = ""
                for d_idx in range(7):
                    target_d = self.curr_week_start + timedelta(days=d_idx)
                    d_sch = self.db.get_schedule(target_d.strftime("%Y-%m-%d"))
                    if d_sch["schedule"]:
                        day_n = ["일", "월", "화", "수", "목", "금", "토"][d_idx]
                        weekly_list_text += f"[{day_n}] {d_sch['schedule'].splitlines()[0]}\n"

                # 주간 요약 셀 - 테마 기본색 (전체목록 스타일)
                C = self.style.colors
                col_frame = tk.Frame(self.week_frame, bg=C.bg, borderwidth=1, relief="solid")
                col_frame.grid(row=0, rowspan=2, column=i, sticky="nsew", padx=0, pady=0)
                
                tk.Label(col_frame, text="Weekly\nSummary", bg=LBLUE, fg="#2c3e50", font=("Arial", 12, "bold"), justify="center").pack(fill=X, pady=0)
                
                c_box = tk.Frame(col_frame, bg=C.bg, padx=5)
                c_box.pack(fill=BOTH, expand=YES)
                
                tk.Label(c_box, text="[이번 주 일정]", font=("Malgun Gothic", 9, "bold"), bg=C.bg, fg=C.fg).pack(anchor="w", pady=(5,0))
                tk.Label(c_box, text=weekly_list_text if weekly_list_text else "일정 없음", font=("Malgun Gothic", 9), wraplength=150, justify="left", bg=C.bg, fg=C.fg).pack(anchor="w", pady=(0, 10))

                tk.Label(c_box, text="[주간 메모]", font=("Malgun Gothic", 9, "bold"), bg=C.bg, fg=C.fg).pack(anchor="w")
                memo = saved_summary["schedule"] if saved_summary["schedule"] else "메모 없음"
                tk.Label(c_box, text=memo, font=("Malgun Gothic", 9), wraplength=150, justify="left", bg=C.bg, fg=C.fg).pack(anchor="w")

                for w in [col_frame, c_box] + c_box.winfo_children():
                    w.bind("<Button-1>", lambda e, k=summary_key, s=weekly_list_text: DailyEditor(self, k, "주간 요약 편집", self.db, lambda: self.switch_view("weekly"), s))

            # 요일 컬럼
            else:
                day_idx = i - 1
                curr_date = self.curr_week_start + timedelta(days=day_idx)
                date_str = curr_date.strftime("%Y-%m-%d")
                
                lunar, term, anns = self.get_day_info(curr_date)
                sch = self.db.get_schedule(date_str)
                
                is_sun = (day_idx == 0)
                is_sat = (day_idx == 6)
                is_hol_ann = any(a.get("is_holiday") for a in anns)
                is_vacation = "휴가" in sch["schedule"] or "연차" in sch["schedule"]

                # 전체목록(Tableview)과 동일한 테마 기본색 사용 (테마 연동)
                C = self.style.colors
                if is_hol_ann or is_sun or is_vacation: 
                    date_color = "danger"
                    bg_color = C.bg
                elif is_sat: 
                    date_color = "primary"
                    bg_color = C.bg
                else: 
                    date_color = "secondary"
                    bg_color = C.bg
                
                border_color = "black"
                thickness = 1
                if curr_date == self.today:
                    border_color = "#3498db"
                    thickness = 2

                col_frame = tk.Frame(self.week_frame, bg=bg_color, borderwidth=1, relief="solid", highlightbackground=border_color, highlightthickness=thickness)
                col_frame.grid(row=0, rowspan=2, column=i, sticky="nsew", padx=0, pady=0)
                
                header_frame = tk.Frame(col_frame, bg=LBLUE)
                header_frame.pack(fill=X, pady=5)
                
                day_name = ["일", "월", "화", "수", "목", "금", "토"][day_idx]
                tk.Label(header_frame, text=f"{curr_date.day} ({day_name})", bg=LBLUE,
                         fg=LBLUE_FG.get(date_color, "#333333"), font=("Arial", 11, "bold")).pack(anchor="center")
                
                if term: tk.Label(header_frame, text=term, bg=LBLUE, fg=LBLUE_FG["success"], font=("Malgun Gothic", 9)).pack(anchor="center")
                if lunar: tk.Label(header_frame, text=lunar, bg=LBLUE, fg="#333333", font=("Arial", 8)).pack(anchor="center")
                
                ttk.Separator(col_frame).pack(fill=X, pady=5)
                
                content = tk.Frame(col_frame, bg=bg_color)
                content.pack(fill=BOTH, expand=YES)
                
                for ann in anns:
                    ttk.Label(content, text=f"★{ann['name']}", bootstyle="danger" if ann.get('is_holiday') else "warning", font=("Malgun Gothic", 9), background=bg_color).pack(anchor="w")
                
                if sch["schedule"]:
                    sch_lines = sch["schedule"].strip().split("\n")
                    for line in sch_lines:
                        s_color = "danger" if ("휴가" in line or "연차" in line) else "primary"
                        ttk.Label(content, text=line, bootstyle=s_color, font=("Malgun Gothic", 9), wraplength=150, background=bg_color).pack(anchor="w", pady=(2, 0))
                
                if sch["journal"]:
                     ttk.Label(content, text="[비고있음]", bootstyle="secondary", font=("Malgun Gothic", 8), background=bg_color).pack(anchor="w", pady=(2, 0))

                # 이미지 표시
                images = sch.get("images", [])
                if images:
                    ttk.Label(content, text=f"📷 {len(images)}", bootstyle="warning", font=("Arial", 8), background=bg_color).pack(anchor="w", pady=(2, 0))

                for w in [col_frame, header_frame, content] + content.winfo_children() + header_frame.winfo_children():
                    w.bind("<Button-1>", lambda e, d=date_str: self.open_pop(d))

    def prev_week(self):
        self.curr_week_start -= timedelta(days=7)
        self.update_weekly_grid()

    def next_week(self):
        self.curr_week_start += timedelta(days=7)
        self.update_weekly_grid()
        
    def go_today_week(self):
        self.curr_week_start = self.get_sunday(self.now)
        self.update_weekly_grid()

    def open_pop(self, date_key):
        DailyEditor(self, date_key, f"일정 편집: {date_key}", self.db, lambda: self.switch_view(self.current_view_name))

    # -------------------------------------------------------------
    # 뷰 2.5: 일간 일지 (일정 + 일지 + 그림파일 삽입)
    # -------------------------------------------------------------
    def setup_daily_view(self):
        header = ttk.Frame(self.content_area)
        header.pack(fill=X, pady=(0, 15))

        nav = ttk.Frame(header)
        nav.pack(side=LEFT)

        ttk.Button(nav, text="◀", command=self.daily_prev, bootstyle="secondary-outline").pack(side=LEFT)
        self.lbl_daily_date = ttk.Label(nav, text="", font=("Malgun Gothic", 18, "bold"), width=16, anchor="center")
        self.lbl_daily_date.pack(side=LEFT, padx=10)
        ttk.Button(nav, text="▶", command=self.daily_next, bootstyle="secondary-outline").pack(side=LEFT)
        ttk.Button(nav, text="오늘 (Today)", command=self.daily_today, bootstyle="info").pack(side=LEFT, padx=(10, 0))

        self.daily_date_str = self.today.strftime("%Y-%m-%d")
        self.daily_curr_images = []
        self.daily_frame = ttk.Frame(self.content_area)
        self.daily_frame.pack(fill=BOTH, expand=YES)

        self._refresh_daily_view()

    def daily_prev(self):
        d = datetime.strptime(self.daily_date_str, "%Y-%m-%d").date()
        d = d - timedelta(days=1)
        self.daily_date_str = d.strftime("%Y-%m-%d")
        self._refresh_daily_view()

    def daily_next(self):
        d = datetime.strptime(self.daily_date_str, "%Y-%m-%d").date()
        d = d + timedelta(days=1)
        self.daily_date_str = d.strftime("%Y-%m-%d")
        self._refresh_daily_view()

    def daily_today(self):
        self.daily_date_str = self.today.strftime("%Y-%m-%d")
        self._refresh_daily_view()

    def _refresh_daily_view(self):
        for w in self.daily_frame.winfo_children():
            w.destroy()

        d = datetime.strptime(self.daily_date_str, "%Y-%m-%d").date()
        self.lbl_daily_date.config(text=f"{d.year}년 {d.month}월 {d.day}일")

        saved = self.db.get_schedule(self.daily_date_str)
        schedule_txt = saved.get("schedule", "")
        journal_txt = saved.get("journal", "")
        images = saved.get("images", [])
        if not isinstance(images, list):
            images = []
        self.daily_curr_images = images

        paned = tk_ttk.PanedWindow(self.daily_frame, orient=HORIZONTAL)
        paned.pack(fill=BOTH, expand=YES, pady=(0, 10))

        frame_left = ttk.Labelframe(paned, text=" 📝 일정 (Schedule) ", padding=10, bootstyle="info")
        paned.add(frame_left, weight=1)

        self.daily_txt_sch = ScrolledText(frame_left, font=("Malgun Gothic", 11), height=22, bootstyle="info")
        self.daily_txt_sch.pack(fill=BOTH, expand=YES)
        self.daily_txt_sch.insert("1.0", schedule_txt)

        frame_right = ttk.Labelframe(paned, text=" 📖 일지 (Diary) ", padding=10, bootstyle="secondary")
        paned.add(frame_right, weight=2)

        self.daily_txt_jnl = ScrolledText(frame_right, font=("Malgun Gothic", 11), height=22, bootstyle="secondary")
        self.daily_txt_jnl.pack(fill=BOTH, expand=YES)
        self.daily_txt_jnl.insert("1.0", journal_txt)

        img_bar = ttk.Frame(self.daily_frame)
        img_bar.pack(fill=X, pady=(0, 8))

        ttk.Label(img_bar, text="🖼 첨부된 그림", bootstyle="secondary", font=("Malgun Gothic", 10, "bold")).pack(side=LEFT, padx=(0, 8))
        self.daily_img_list = ttk.Frame(img_bar)
        self.daily_img_list.pack(side=LEFT, fill=X, expand=YES)

        if images:
            for img_path in images:
                fp = Path(img_path) if isinstance(img_path, str) else None
                if not fp or not fp.exists():
                    continue
                box = ttk.Frame(self.daily_img_list, bootstyle="secondary")
                box.pack(side=LEFT, padx=4, pady=4)

                ttk.Label(box, text=fp.name, font=("Malgun Gothic", 8), bootstyle="secondary", wraplength=72, justify="center").pack()

                ttk.Button(box, text="보기", bootstyle="info-outline", width=6, command=lambda p=str(fp): self._show_image_viewer(p)).pack(pady=2)
                ttk.Button(box, text="삭제", bootstyle="danger", width=6, command=lambda p=str(fp): self._remove_diary_image(p)).pack(pady=2)
        else:
            ttk.Label(self.daily_img_list, text="첨부된 그림이 없습니다.", bootstyle="secondary", font=("Malgun Gothic", 9)).pack(side=LEFT)

        btn_box = ttk.Frame(self.daily_frame)
        btn_box.pack(fill=X, pady=(0, 4))
        ttk.Button(btn_box, text="🖼 그림 추가", bootstyle="warning-outline", command=self._insert_diary_image).pack(side=LEFT, padx=5)
        ttk.Button(btn_box, text="저장 (Save)", bootstyle="success", command=self._daily_save).pack(side=RIGHT, padx=5)
        ttk.Button(btn_box, text="일정/일지만 저장", bootstyle="light-outline", command=self._daily_save_text_only).pack(side=RIGHT, padx=5)

    def _daily_save(self):
        schedule = self.daily_txt_sch.get("1.0", "end-1c")
        journal = self.daily_txt_jnl.get("1.0", "end-1c")
        images = list(self.daily_curr_images) if self.daily_curr_images else []
        self.db.set_schedule(self.daily_date_str, schedule, journal, images=images)
        messagebox.showinfo("저장 완료", f"날짜 {self.daily_date_str}의 일정/일지/그림을 저장했습니다.")

    def _daily_save_text_only(self):
        schedule = self.daily_txt_sch.get("1.0", "end-1c")
        journal = self.daily_txt_jnl.get("1.0", "end-1c")
        self.db.set_schedule(self.daily_date_str, schedule, journal, images=None)
        messagebox.showinfo("저장 완료", f"날짜 {self.daily_date_str}의 일정/일지만 저장했습니다.")

    # -------------------------------------------------------------
    def _insert_diary_image(self):
        path = filedialog.askopenfilename(
            title="그림파일 선택",
            filetypes=[
                ("이미지", "*.png;*.jpg;*.jpeg;*.gif;*.bmp;*.webp"),
                ("모든 파일", "*.*"),
            ]
        )
        if not path:
            return
        rel = self.db.save_diary_image(self.daily_date_str, path)
        if not rel:
            messagebox.showwarning("오류", "그림 저장에 실패했습니다.")
            return
        images = list(self.daily_curr_images) if self.daily_curr_images else []
        if rel not in images:
            images.append(rel)
        self.daily_curr_images = images
        self.db.set_schedule_images(self.daily_date_str, images)
        self._refresh_daily_view()
        messagebox.showinfo("그림 삽입", "그림이 추가되었습니다.")

    def _remove_diary_image(self, rel_path):
        images = list(self.daily_curr_images) if self.daily_curr_images else []
        if rel_path in images:
            images.remove(rel_path)
        self.daily_curr_images = images
        self.db.set_schedule_images(self.daily_date_str, images)
        self._refresh_daily_view()

    def _show_image_viewer(self, target_rel=None):
        images = list(self.daily_curr_images) if self.daily_curr_images else []
        if target_rel:
            picks = [target_rel]
        else:
            picks = images

        if not picks:
            messagebox.showinfo("그림 보기", "표시할 그림이 없습니다.")
            return

        win = ttk.Toplevel(self)
        win.title("그림 보기")
        win.geometry("760x560")
        win.place_window_center()

        frame = ttk.Frame(win, padding=10)
        frame.pack(fill=BOTH, expand=YES)

        self.diary_viewer_photo = None
        viewer = ttk.Label(frame, bootstyle="secondary", text="그림을 불러오지 못했습니다.", font=("Malgun Gothic", 11))
        viewer.pack(expand=YES)

        nav = ttk.Frame(frame)
        nav.pack(fill=X, pady=(8, 0))
        ttk.Button(nav, text="◀ 이전", bootstyle="secondary-outline", command=lambda: self._viewer_nav(-1)).pack(side=LEFT)
        ttk.Label(nav, text="", width=2, bootstyle="secondary").pack(side=LEFT)
        self.diary_viewer_idx_lbl = ttk.Label(nav, text="", bootstyle="secondary", font=("Malgun Gothic", 9))
        self.diary_viewer_idx_lbl.pack(side=LEFT)
        ttk.Label(nav, text="", width=2, bootstyle="secondary").pack(side=LEFT)
        ttk.Button(nav, text="다음 ▶", bootstyle="secondary-outline", command=lambda: self._viewer_nav(1)).pack(side=LEFT)
        ttk.Button(nav, text="닫기", bootstyle="light-outline", command=win.destroy).pack(side=RIGHT)

        self._viewer_picks = picks
        self._viewer_index = 0
        self._viewer_target = viewer
        self._show_viewer_image()

    def _viewer_nav(self, delta):
        if not hasattr(self, "_viewer_picks"):
            return
        self._viewer_index = max(0, min(len(self._viewer_picks) - 1, self._viewer_index + delta))
        self._show_viewer_image()

    def _show_viewer_image(self):
        if not hasattr(self, "_viewer_picks") or not self._viewer_picks:
            return
        idx = self._viewer_index
        rel = self._viewer_picks[idx]
        fp = Path(rel)
        if not fp.exists():
            self._viewer_target.config(text=f"[파일을 찾을 수 없음]\n{rel}")
            self.diary_viewer_idx_lbl.config(text=f"{idx+1} / {len(self._viewer_picks)}")
            return
        try:
            from PIL import Image, ImageTk
            im = Image.open(fp)
            max_w, max_h = 720, 480
            scale = min(max_w / im.width, max_h / im.height, 1.0)
            new_size = (max(1, int(im.width * scale)), max(1, int(im.height * scale)))
            im = im.resize(new_size, Image.LANCZOS)
            photo = ImageTk.PhotoImage(im)
            self.diary_viewer_photo = photo
            self._viewer_target.config(image=photo, text="")
        except (OSError, ValueError, tk.TclError) as e:
            self._viewer_target.config(text=f"[그림 보기 오류]\n{str(e)}")
        self.diary_viewer_idx_lbl.config(text=f"{idx+1} / {len(self._viewer_picks)}")

    # -------------------------------------------------------------
    def setup_report_view(self):
        header = ttk.Frame(self.content_area)
        header.pack(fill=X, pady=(0, 20))
        ttk.Label(header, text="📊 전체 일정 목록", font=("Malgun Gothic", 18, "bold"), bootstyle="dark").pack(side=LEFT)
        
        btn_box = ttk.Frame(header)
        btn_box.pack(side=RIGHT)
        ttk.Button(btn_box, text="엑셀 가져오기", command=self.import_schedule_excel, bootstyle="info").pack(side=RIGHT, padx=5)
        ttk.Button(btn_box, text="엑셀 내보내기", command=self.export_schedule_excel, bootstyle="success").pack(side=RIGHT, padx=5)
        
        df = self.db.get_all_schedules_df()
        
        if df is not None and not df.empty:
            coldata = [
                {"text": "날짜", "stretch": False, "width": 120},
                {"text": "일정 내용", "stretch": True},
                {"text": "비고(일지)", "stretch": True}
            ]
            rowdata = df.values.tolist()
            
            table = Tableview(
                master=self.content_area,
                coldata=coldata,
                rowdata=rowdata,
                paginated=True,
                pagesize=15,
                searchable=True,
                bootstyle="primary",
                stripecolor=(self.style.colors.light, None),
            )
            table.pack(fill=BOTH, expand=YES)
        else:
            ttk.Label(self.content_area, text="저장된 일정이 없습니다.", font=("Malgun Gothic", 14), bootstyle="secondary").pack(pady=50)

    # [추가] 일정 엑셀 내보내기/가져오기 핸들러
    def export_schedule_excel(self):
        df = self.db.get_all_schedules_with_images_df()
        if df is not None:
            path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")])
            if path:
                df.to_excel(path, index=False)
                ToastNotification("내보내기 성공", "일정 리스트가 저장되었습니다. (이미지 경로 포함)", bootstyle="success").show_toast()

    def import_schedule_excel(self):
        path = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx")])
        if path:
            try:
                df = pd.read_excel(path)
                # 컬럼 유효성 검사 (기본적으로 '날짜', '일정', '비고' 컬럼이 있어야 함)
                required = ['날짜', '일정', '비고']
                if not all(col in df.columns for col in required):
                    messagebox.showerror("오류", f"엑셀 파일에 다음 컬럼이 있어야 합니다: {required}")
                    return
                
                self.db.import_schedules_from_df(df)
                self.setup_report_view() # 화면 갱신
                ToastNotification("가져오기 성공", "일정 데이터가 병합되었습니다.", bootstyle="success").show_toast()
            except (OSError, ValueError, KeyError, zipfile.BadZipFile) as e:
                messagebox.showerror("오류", f"파일을 읽는 중 오류가 발생했습니다.\n{e}")
    # -------------------------------------------------------------
    # 뷰: 단어장 DB (언어별 단어/숙어 관리)
    # -------------------------------------------------------------
    def setup_wordbook_view(self):
        ttk.Label(self.content_area, text="📕 단어장 DB", font=("Malgun Gothic", 18, "bold")).pack(anchor="w", pady=(0, 5))

        # --- 상단: 언어 선택/추가/검색 ---
        top = ttk.Frame(self.content_area)
        top.pack(fill=X, pady=(0, 10))
        ttk.Label(top, text="언어:").pack(side=LEFT)
        self.wb_lang_combo = ttk.Combobox(top, state="readonly", width=10)
        self.wb_lang_combo.pack(side=LEFT, padx=5)
        self.wb_lang_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_wordbook())
        self.wb_new_lang = ttk.Entry(top, width=9)
        self.wb_new_lang.pack(side=LEFT, padx=(10, 2))
        self.wb_new_lang.insert(0, "새 언어")
        ttk.Button(top, text="언어 추가", command=self.add_wb_language, bootstyle="success-outline").pack(side=LEFT, padx=2)
        ttk.Button(top, text="언어 삭제", command=self.delete_wb_language, bootstyle="danger-outline").pack(side=LEFT, padx=2)

        ttk.Label(top, text="검색:").pack(side=LEFT, padx=(15, 2))
        self.wb_search = ttk.Entry(top, width=16)
        self.wb_search.pack(side=LEFT, padx=2)
        self.wb_search.bind("<Return>", lambda e: self.refresh_wordbook())
        ttk.Button(top, text="검색", command=self.refresh_wordbook, bootstyle="secondary-outline").pack(side=LEFT, padx=2)
        ttk.Button(top, text="전체보기", command=self.show_all_words, bootstyle="secondary-outline").pack(side=LEFT, padx=2)

        ttk.Label(self.content_area, text="※ 표에서 단어를 클릭하면 아래 입력창으로 불러와 수정할 수 있습니다.",
                  bootstyle="secondary", font=("Malgun Gothic", 9)).pack(anchor="w", pady=(0, 5))

        # --- 단어 목록 표 ---
        self.tree_words_db = ttk.Treeview(
            self.content_area,
            columns=("rank", "word", "pron_en", "pron_ko", "pos", "meaning", "example", "example_ko"),
            show="headings", height=12)
        heads = ["순위", "단어/숙어", "발음(영어)", "발음(한국어)", "품사", "뜻(한국어)", "예제", "예제뜻"]
        widths = [55, 130, 120, 110, 60, 150, 220, 220]
        for col, txt, w in zip(("rank", "word", "pron_en", "pron_ko", "pos", "meaning", "example", "example_ko"), heads, widths):
            self.tree_words_db.heading(col, text=txt)
            self.tree_words_db.column(col, width=w, anchor="w" if w > 100 else "center")
        self.tree_words_db.pack(fill=BOTH, expand=YES, pady=(0, 10))
        self.tree_words_db.bind("<<TreeviewSelect>>", lambda e: self.select_word())

        # --- 단어장 입력 폼 ---
        form = ttk.Labelframe(self.content_area, text=" 단어 추가 / 수정 ", padding=10)
        form.pack(fill=X, pady=(0, 10))

        row1 = ttk.Frame(form); row1.pack(fill=X, pady=2)
        ttk.Label(row1, text="순위:").pack(side=LEFT)
        self.e_w_rank = ttk.Entry(row1, width=6); self.e_w_rank.pack(side=LEFT, padx=2)
        ttk.Label(row1, text="단어/숙어:").pack(side=LEFT, padx=(10, 0))
        self.e_w_word = ttk.Entry(row1, width=18); self.e_w_word.pack(side=LEFT, padx=2)
        ttk.Label(row1, text="발음(영어):").pack(side=LEFT, padx=(10, 0))
        self.e_w_pron_en = ttk.Entry(row1, width=16); self.e_w_pron_en.pack(side=LEFT, padx=2)
        ttk.Label(row1, text="발음(한국어):").pack(side=LEFT, padx=(10, 0))
        self.e_w_pron_ko = ttk.Entry(row1, width=14); self.e_w_pron_ko.pack(side=LEFT, padx=2)
        ttk.Label(row1, text="품사:").pack(side=LEFT, padx=(10, 0))
        self.e_w_pos = ttk.Entry(row1, width=8); self.e_w_pos.pack(side=LEFT, padx=2); self.e_w_pos.insert(0, "동사")

        row2 = ttk.Frame(form); row2.pack(fill=X, pady=2)
        ttk.Label(row2, text="뜻(한국어):").pack(side=LEFT)
        self.e_w_meaning = ttk.Entry(row2, width=30); self.e_w_meaning.pack(side=LEFT, padx=2)

        row3 = ttk.Frame(form); row3.pack(fill=X, pady=2)
        ttk.Label(row3, text="예제:").pack(side=LEFT)
        self.e_w_example = ttk.Entry(row3, width=40); self.e_w_example.pack(side=LEFT, padx=2)
        ttk.Label(row3, text="예제뜻:").pack(side=LEFT, padx=(10, 0))
        self.e_w_example_ko = ttk.Entry(row3, width=40); self.e_w_example_ko.pack(side=LEFT, padx=2)

        btns = ttk.Frame(form); btns.pack(fill=X, pady=(6, 0))
        ttk.Button(btns, text="추가", command=self.add_word_ui, bootstyle="success").pack(side=LEFT, padx=3)
        ttk.Button(btns, text="수정", command=self.update_word_ui, bootstyle="info").pack(side=LEFT, padx=3)
        ttk.Button(btns, text="삭제", command=self.delete_word_ui, bootstyle="danger").pack(side=LEFT, padx=3)
        ttk.Button(btns, text="입력창 비우기", command=self.clear_word_form, bootstyle="secondary-outline").pack(side=LEFT, padx=3)
        self.wb_count_label = ttk.Label(btns, text="", bootstyle="secondary", font=("Malgun Gothic", 9))
        self.wb_count_label.pack(side=RIGHT)

        self.refresh_wordbook()

    def refresh_wordbook(self):
        # 언어 콤보 갱신 (선택 유지)
        langs = self.db.get_word_languages() or ["영어"]
        current = self.wb_lang_combo.get()
        self.wb_lang_combo.config(values=langs)
        if current in langs:
            self.wb_lang_combo.set(current)
        else:
            self.wb_lang_combo.set(langs[0])

        keyword = self.wb_search.get().strip()
        words = self.db.get_words(language=self.wb_lang_combo.get() or None, keyword=keyword or None)

        for item in self.tree_words_db.get_children():
            self.tree_words_db.delete(item)
        for w in words:
            self.tree_words_db.insert("", "end", iid=str(w["id"]),
                values=(w["rank"], w["word"], w["pron_en"], w["pron_ko"],
                        w["pos"], w["meaning"], w["example"], w["example_ko"]))
        self.wb_count_label.config(text=f"총 {len(words)}개 단어")

    def show_all_words(self):
        self.wb_search.delete(0, "end")
        self.refresh_wordbook()

    def select_word(self):
        sel = self.tree_words_db.selection()
        if not sel:
            return
        wid = int(sel[0])
        for w in self.db.get_words(language=self.wb_lang_combo.get() or None):
            if w["id"] == wid:
                self.clear_word_form()
                self.e_w_rank.insert(0, str(w["rank"]))
                self.e_w_word.insert(0, w["word"])
                self.e_w_pron_en.insert(0, w["pron_en"] or "")
                self.e_w_pron_ko.insert(0, w["pron_ko"] or "")
                self.e_w_pos.insert(0, w["pos"] or "")
                self.e_w_meaning.insert(0, w["meaning"] or "")
                self.e_w_example.insert(0, w["example"] or "")
                self.e_w_example_ko.insert(0, w["example_ko"] or "")
                break

    def clear_word_form(self):
        for e in (self.e_w_rank, self.e_w_word, self.e_w_pron_en, self.e_w_pron_ko,
                  self.e_w_meaning, self.e_w_example, self.e_w_example_ko):
            e.delete(0, "end")
        self.e_w_pos.delete(0, "end"); self.e_w_pos.insert(0, "동사")
        self.tree_words_db.selection_remove(self.tree_words_db.selection())
    def _word_form_values(self):
        rank = self.e_w_rank.get().strip()
        if not rank.isdigit():
            messagebox.showwarning("알림", "순위를 숫자로 입력하세요.")
            return None
        word = self.e_w_word.get().strip()
        if not word:
            messagebox.showwarning("알림", "단어/숙어를 입력하세요.")
            return None
        return (int(rank), word, self.e_w_pron_en.get().strip(), self.e_w_pron_ko.get().strip(),
                self.e_w_pos.get().strip() or "동사", self.e_w_meaning.get().strip(),
                self.e_w_example.get().strip(), self.e_w_example_ko.get().strip())

    def add_word_ui(self):
        vals = self._word_form_values()
        if not vals:
            return
        language = self.wb_lang_combo.get() or "영어"
        if self.db.add_word(language, *vals):
            self.refresh_wordbook()
            self.clear_word_form()
            ToastNotification("단어 추가", f"'{vals[1]}' 추가 완료", bootstyle="success").show_toast()
        else:
            messagebox.showerror("오류", "이미 존재하는 단어입니다(같은 언어+품사).")

    def update_word_ui(self):
        sel = self.tree_words_db.selection()
        if not sel:
            messagebox.showwarning("알림", "수정할 단어를 표에서 선택하세요.")
            return
        vals = self._word_form_values()
        if not vals:
            return
        self.db.update_word(int(sel[0]), *vals)
        self.refresh_wordbook()
        self.clear_word_form()
        ToastNotification("단어 수정", f"'{vals[1]}' 수정 완료", bootstyle="info").show_toast()

    def delete_word_ui(self):
        sel = self.tree_words_db.selection()
        if not sel:
            messagebox.showwarning("알림", "삭제할 단어를 표에서 선택하세요.")
            return
        if messagebox.askyesno("단어 삭제", "선택한 단어를 삭제하시겠습니까?"):
            self.db.delete_word(int(sel[0]))
            self.refresh_wordbook()
            self.clear_word_form()

    def add_wb_language(self):
        name = self.wb_new_lang.get().strip()
        if not name or name == "새 언어":
            messagebox.showwarning("알림", "언어명을 입력하세요.")
            return
        langs = list(dict.fromkeys(self.db.get_word_languages() + [name]))
        self.wb_lang_combo.config(values=langs)
        self.wb_lang_combo.set(name)
        messagebox.showinfo("언어 추가", f"'{name}' 언어가 선택되었습니다.\n첫 단어를 추가하면 단어장이 생성됩니다.")

    def delete_wb_language(self):
        language = self.wb_lang_combo.get()
        if not language:
            return
        if messagebox.askyesno("언어 삭제", f"'{language}' 언어의 모든 단어를 삭제하시겠습니까?"):
            for w in self.db.get_words(language=language):
                self.db.delete_word(w["id"])
            self.refresh_wordbook()

# -------------------------------------------------------------
    # 뷰: 생활용어 DB (언어별 기본 문장/표현 관리)
    # -------------------------------------------------------------
    def setup_phrase_view(self):
        ttk.Label(self.content_area, text="💬 생활용어 DB", font=("Malgun Gothic", 18, "bold")).pack(anchor="w", pady=(0, 5))

        # --- 상단: 언어 선택/추가/검색 ---
        top = ttk.Frame(self.content_area)
        top.pack(fill=X, pady=(0, 10))
        ttk.Label(top, text="언어:").pack(side=LEFT)
        self.pf_lang_combo = ttk.Combobox(top, state="readonly", width=10)
        self.pf_lang_combo.pack(side=LEFT, padx=5)
        self.pf_lang_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_phrasebook())
        self.pf_new_lang = ttk.Entry(top, width=9)
        self.pf_new_lang.pack(side=LEFT, padx=(10, 2))
        self.pf_new_lang.insert(0, "새 언어")
        ttk.Button(top, text="언어 추가", command=self.add_pf_language, bootstyle="success-outline").pack(side=LEFT, padx=2)
        ttk.Button(top, text="언어 삭제", command=self.delete_pf_language, bootstyle="danger-outline").pack(side=LEFT, padx=2)

        ttk.Label(top, text="검색:").pack(side=LEFT, padx=(15, 2))
        self.pf_search = ttk.Entry(top, width=16)
        self.pf_search.pack(side=LEFT, padx=2)
        self.pf_search.bind("<Return>", lambda e: self.refresh_phrasebook())
        ttk.Button(top, text="검색", command=self.refresh_phrasebook, bootstyle="secondary-outline").pack(side=LEFT, padx=2)
        ttk.Button(top, text="전체보기", command=self.show_all_phrases, bootstyle="secondary-outline").pack(side=LEFT, padx=2)

        ttk.Label(self.content_area, text="※ 표에서 문장을 클릭하면 아래 입력창으로 불러와 수정할 수 있습니다.",
                  bootstyle="secondary", font=("Malgun Gothic", 9)).pack(anchor="w", pady=(0, 5))

        # --- 생활용어 목록 표 ---
        self.tree_phrases_db = ttk.Treeview(
            self.content_area,
            columns=("rank", "sentence", "pron_ko", "meaning_ko"),
            show="headings", height=14)
        heads = ["순위", "문장", "발음(한국어)", "뜻(한국어)"]
        widths = [55, 340, 160, 240]
        for col, txt, w in zip(("rank", "sentence", "pron_ko", "meaning_ko"), heads, widths):
            self.tree_phrases_db.heading(col, text=txt)
            self.tree_phrases_db.column(col, width=w, anchor="w" if w > 100 else "center")
        self.tree_phrases_db.pack(fill=BOTH, expand=YES, pady=(0, 10))
        self.tree_phrases_db.bind("<<TreeviewSelect>>", lambda e: self.select_phrase())

        # --- 문장 입력 폼 ---
        form = ttk.Labelframe(self.content_area, text=" 문장 추가 / 수정 ", padding=10)
        form.pack(fill=X, pady=(0, 10))

        row1 = ttk.Frame(form); row1.pack(fill=X, pady=2)
        ttk.Label(row1, text="순위:").pack(side=LEFT)
        self.e_pf_rank = ttk.Entry(row1, width=6); self.e_pf_rank.pack(side=LEFT, padx=2)
        ttk.Label(row1, text="문장:").pack(side=LEFT, padx=(10, 0))
        self.e_pf_sentence = ttk.Entry(row1, width=42); self.e_pf_sentence.pack(side=LEFT, padx=2)
        ttk.Label(row1, text="발음(한국어):").pack(side=LEFT, padx=(10, 0))
        self.e_pf_pron_ko = ttk.Entry(row1, width=22); self.e_pf_pron_ko.pack(side=LEFT, padx=2)

        row2 = ttk.Frame(form); row2.pack(fill=X, pady=2)
        ttk.Label(row2, text="뜻(한국어):").pack(side=LEFT)
        self.e_pf_meaning_ko = ttk.Entry(row2, width=60); self.e_pf_meaning_ko.pack(side=LEFT, padx=2)

        btns = ttk.Frame(form); btns.pack(fill=X, pady=(6, 0))
        ttk.Button(btns, text="추가", command=self.add_phrase_ui, bootstyle="success").pack(side=LEFT, padx=3)
        ttk.Button(btns, text="수정", command=self.update_phrase_ui, bootstyle="info").pack(side=LEFT, padx=3)
        ttk.Button(btns, text="삭제", command=self.delete_phrase_ui, bootstyle="danger").pack(side=LEFT, padx=3)
        ttk.Button(btns, text="입력창 비우기", command=self.clear_phrase_form, bootstyle="secondary-outline").pack(side=LEFT, padx=3)
        self.pf_count_label = ttk.Label(btns, text="", bootstyle="secondary", font=("Malgun Gothic", 9))
        self.pf_count_label.pack(side=RIGHT)

        self.refresh_phrasebook()

    def refresh_phrasebook(self):
        # 언어 콤보 갱신 (선택 유지)
        langs = self.db.get_phrase_languages() or ["영어"]
        current = self.pf_lang_combo.get()
        self.pf_lang_combo.config(values=langs)
        if current in langs:
            self.pf_lang_combo.set(current)
        else:
            self.pf_lang_combo.set(langs[0])

        keyword = self.pf_search.get().strip()
        phrases = self.db.get_phrases(language=self.pf_lang_combo.get() or None, keyword=keyword or None)

        for item in self.tree_phrases_db.get_children():
            self.tree_phrases_db.delete(item)
        for p in phrases:
            self.tree_phrases_db.insert("", "end", iid=str(p["id"]),
                values=(p["rank"], p["sentence"], p["pron_ko"], p["meaning_ko"]))
        self.pf_count_label.config(text=f"총 {len(phrases)}개 문장")

    def show_all_phrases(self):
        self.pf_search.delete(0, "end")
        self.refresh_phrasebook()

    def select_phrase(self):
        sel = self.tree_phrases_db.selection()
        if not sel:
            return
        pid = int(sel[0])
        for p in self.db.get_phrases(language=self.pf_lang_combo.get() or None):
            if p["id"] == pid:
                self.clear_phrase_form()
                self.e_pf_rank.insert(0, str(p["rank"]))
                self.e_pf_sentence.insert(0, p["sentence"])
                self.e_pf_pron_ko.insert(0, p["pron_ko"] or "")
                self.e_pf_meaning_ko.insert(0, p["meaning_ko"] or "")
                break

    def clear_phrase_form(self):
        for e in (self.e_pf_rank, self.e_pf_sentence, self.e_pf_pron_ko, self.e_pf_meaning_ko):
            e.delete(0, "end")
        self.tree_phrases_db.selection_remove(self.tree_phrases_db.selection())

    def _phrase_form_values(self):
        rank = self.e_pf_rank.get().strip()
        if not rank.isdigit():
            messagebox.showwarning("알림", "순위를 숫자로 입력하세요.")
            return None
        sentence = self.e_pf_sentence.get().strip()
        if not sentence:
            messagebox.showwarning("알림", "문장을 입력하세요.")
            return None
        return (int(rank), sentence, self.e_pf_pron_ko.get().strip(), self.e_pf_meaning_ko.get().strip())

    def add_phrase_ui(self):
        vals = self._phrase_form_values()
        if not vals:
            return
        language = self.pf_lang_combo.get() or "영어"
        if self.db.add_phrase(language, *vals):
            self.refresh_phrasebook()
            self.clear_phrase_form()
            ToastNotification("문장 추가", f"'{vals[1]}' 추가 완료", bootstyle="success").show_toast()
        else:
            messagebox.showerror("오류", "이미 존재하는 문장입니다(같은 언어+문장).")

    def update_phrase_ui(self):
        sel = self.tree_phrases_db.selection()
        if not sel:
            messagebox.showwarning("알림", "수정할 문장을 표에서 선택하세요.")
            return
        vals = self._phrase_form_values()
        if not vals:
            return
        self.db.update_phrase(int(sel[0]), *vals)
        self.refresh_phrasebook()
        self.clear_phrase_form()
        ToastNotification("문장 수정", f"'{vals[1]}' 수정 완료", bootstyle="info").show_toast()

    def delete_phrase_ui(self):
        sel = self.tree_phrases_db.selection()
        if not sel:
            messagebox.showwarning("알림", "삭제할 문장을 표에서 선택하세요.")
            return
        if messagebox.askyesno("문장 삭제", "선택한 문장을 삭제하시겠습니까?"):
            self.db.delete_phrase(int(sel[0]))
            self.refresh_phrasebook()
            self.clear_phrase_form()

    def add_pf_language(self):
        name = self.pf_new_lang.get().strip()
        if not name or name == "새 언어":
            messagebox.showwarning("알림", "언어명을 입력하세요.")
            return
        langs = list(dict.fromkeys(self.db.get_phrase_languages() + [name]))
        self.pf_lang_combo.config(values=langs)
        self.pf_lang_combo.set(name)
        messagebox.showinfo("언어 추가", f"'{name}' 언어가 선택되었습니다.\n첫 문장을 추가하면 생활용어장이 생성됩니다.")

    def delete_pf_language(self):
        language = self.pf_lang_combo.get()
        if not language:
            return
        if messagebox.askyesno("언어 삭제", f"'{language}' 언어의 모든 문장을 삭제하시겠습니까?"):
            for p in self.db.get_phrases(language=language):
                self.db.delete_phrase(p["id"])
            self.refresh_phrasebook()

    # -------------------------------------------------------------
    # 뷰 5: 증권 탭 (금융원 Open API 호출 / 실시간 시세 / 저장)
# -------------------------------------------------------------
    # 뷰 5: 증권  (공공데이터포털 주식시세 API / 비동기 검색 / 저장목록)
    #   2026-09-18 복원: Treeview 7열(종목코드/종목명/종가/전일대비/등락률/거래량/시장)
    # -------------------------------------------------------------
    # Treeview column spec: (key, heading, width, anchor)
    _MARKET_COLS = (
        ("symbol", "종목코드", 90, "center"),
        ("name", "종목명", 180, "w"),
        ("price", "종가", 110, "e"),
        ("change", "전일대비", 110, "e"),
        ("change_pct", "등락률", 90, "e"),
        ("volume", "거래량", 130, "e"),
        ("market", "시장", 90, "center"),
    )
    # 종목코드 셀 보존용 제로폭 공백.
    # 2026-09-18 실측(Temp/tk_symbol_probe.json): Tkinter Treeview는 숫자로 보이는 셀 값을
    # int로 변환해 앞자리 0을 잃는다. "000810" → int 810, "000810\n" → int 810 이지만
    # "000810\u200b" → str 유지(화면에는 000810로 보임). 따라서 ZWSP를 붙인다.
    _SYM_ZWSP = "\u200b"
    # 상태 라벨 색상 (ttkbootstrap bootstyle 대신 직접 색상 지정 → 스타일 영향 없음)
    _STATUS_FG = {
        "info": "#0d6efd",
        "success": "#0a7a3a",
        "warning": "#b8860b",
        "danger": "#b00020",
        "secondary": "#666666",
    }

    def load_market_data(self):
        """증권 데이터 새로고침 (검색과 동일한 비동기 경로 재사용)"""
        self._search_market()

    def _clear_tree(self, tree):
        """Treeview 위젯의 모든 행 삭제"""
        for item in tree.get_children():
            tree.delete(item)

    def _clear_market_tree(self):
        """증권 Treeview + 원본 메타 초기화"""
        if hasattr(self, "_market_tree"):
            self._clear_tree(self._market_tree)
        self._market_meta = {}

    # ── 표시값 포맷/복원 헬퍼 (2026-09-18 신규) ──
    @classmethod
    def _cell_str(cls, v) -> str:
        """Treeview 셀 값 → 표시용 문자열 (ZWSP 제거, int 변환 흔적 복원)"""
        if v is None:
            return ""
        return str(v).replace(cls._SYM_ZWSP, "").strip()

    @classmethod
    def _sym_cell(cls, v) -> str:
        """종목코드 셀 값: 앞자리 0 보존을 위해 ZWSP를 덧붙인다."""
        s = cls._cell_str(v)
        return (s + cls._SYM_ZWSP) if s else "-"

    @classmethod
    def _raw_symbol(cls, v) -> str:
        """셀/문자열 → 종목코드 (6자리 미만 숫자는 앞자리 0 복원)"""
        s = cls._cell_str(v)
        if s.isdigit() and len(s) <= 6:
            return s.zfill(6)
        return s

    @classmethod
    def _norm_symbol(cls, v) -> str:
        """API symbol normalization: 12-char ISIN -> 6-digit short code; pad short digits."""
        s = cls._cell_str(v)
        if len(s) == 12 and s[:2].isalpha() and s[2].isdigit():
            core = s[3:9]
            if core.isdigit():
                return core
        if s.isdigit() and len(s) <= 6:
            return s.zfill(6)
        return s

    @staticmethod
    def _to_num(v):
        """'1,234' / '-12.5' / '+1.35%' → float (변환 불가 시 None)"""
        if v is None:
            return None
        s = str(v).replace(",", "").replace("%", "").strip()
        if s.startswith("+"):
            s = s[1:]
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            return None

    @classmethod
    def _fmt_price(cls, v) -> str:
        """종가: 천단위 구분 (숫자가 아니면 '-')"""
        n = cls._to_num(v)
        return f"{n:,.0f}" if n is not None else "-"

    @classmethod
    def _fmt_signed(cls, v) -> str:
        """전일대비: 부호 유지 + 천단위 구분"""
        n = cls._to_num(v)
        return f"{n:+,.0f}" if n is not None else "-"

    @classmethod
    def _fmt_vol(cls, v) -> str:
        """거래량: 천단위 구분"""
        n = cls._to_num(v)
        return f"{n:,.0f}" if n is not None else "-"

    @classmethod
    def _fmt_pct(cls, v) -> str:
        """등락률: '%' 유무와 무관하게 항상 부호 + % 로 통일"""
        if v is None:
            return "-"
        s = str(v).strip()
        if not s:
            return "-"
        n = cls._to_num(s)
        return f"{n:+.2f}%" if n is not None else s

    @classmethod
    def _market_tag(cls, row: dict) -> str:
        """등락 방향 색상 태그 (한국 관례: 상승=빨강, 하락=파랑)"""
        n = cls._to_num((row or {}).get("change"))
        if n is None:
            return "flat"
        if n > 0:
            return "up"
        if n < 0:
            return "down"
        return "flat"

    @classmethod
    def _market_row(cls, row: dict) -> tuple:
        """검색 결과 dict → Treeview 7열 표시값 (숫자는 반드시 포맷해 문자열 유지)"""
        row = row or {}
        return (
            cls._sym_cell(row.get("symbol", "")),
            row.get("name", "") or "-",
            cls._fmt_price(row.get("price")),
            cls._fmt_signed(row.get("change")),
            cls._fmt_pct(row.get("change_pct")),
            cls._fmt_vol(row.get("volume")),
            row.get("market", "") or "-",
        )

    def setup_market_view(self):
        """📈 증권 (Market) 탭 - 검색/저장/수정/삭제 + 비동기 조회"""
        container = ttk.LabelFrame(self.content_area, text="📈 증권 (Market)")
        container.pack(fill=BOTH, expand=YES, padx=10, pady=10)

        top = ttk.Frame(container)
        top.pack(fill=X, pady=(0, 5))
        ttk.Label(top, text="🔍 검색:", font=("Malgun Gothic", 9)).pack(side=LEFT, padx=(0, 5))
        self.market_search_var = tk.StringVar(value="삼성")
        self.market_search_entry = ttk.Entry(top, textvariable=self.market_search_var, width=15)
        self.market_search_entry.pack(side=LEFT, padx=(0, 5))
        self.market_search_entry.bind("<Return>", lambda e: self._search_market())
        ttk.Button(top, text="🔎 검색", command=self._search_market,
                   bootstyle="info").pack(side=LEFT, padx=(0, 5))
        ttk.Button(top, text="💾 저장", command=self._save_selected_market,
                   bootstyle="success-outline").pack(side=LEFT, padx=(0, 5))
        ttk.Button(top, text="🗑 삭제", command=self._delete_selected_market,
                   bootstyle="danger-outline").pack(side=LEFT, padx=(0, 5))
        ttk.Button(top, text="📋 저장목록", command=self._toggle_market_saver,
                   bootstyle="secondary-outline").pack(side=RIGHT)
        ttk.Button(top, text="📔 투자일기", command=self.show_investment_journal,
                   bootstyle="success-outline").pack(side=RIGHT, padx=(0, 6))

        self.market_mode = "search"          # "search" 또는 "saved"
        self._market_search_token = 0        # 비동기 결과 폐기용 토큰
        self._market_pending = None          # 워커 결과 보관소 (Tk 호출 없는 전달 경로)
        self._market_poll_job = None         # 결과 회수용 after 작업 id
        self._market_meta = {}               # iid -> 원본 row dict (Tk 셀 int 변환 우회)

        tree_wrap = ttk.Frame(container)
        tree_wrap.pack(fill=BOTH, expand=YES, pady=(0, 5))
        cols = tuple(spec[0] for spec in self._MARKET_COLS)
        self._market_tree = ttk.Treeview(tree_wrap, columns=cols, show="headings", height=12)
        for key, heading, width, anchor in self._MARKET_COLS:
            self._market_tree.heading(key, text=heading)
            self._market_tree.column(key, width=width, anchor=anchor, stretch=(key == "name"))
        vsb = ttk.Scrollbar(tree_wrap, orient=VERTICAL, command=self._market_tree.yview)
        self._market_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=RIGHT, fill=Y)
        self._market_tree.pack(side=LEFT, fill=BOTH, expand=YES)
        self._market_tree.tag_configure("up", foreground="#c0392b")
        self._market_tree.tag_configure("down", foreground="#1f4e9c")
        self._market_tree.tag_configure("flat", foreground="#555555")
        self._market_tree.bind("<<TreeviewSelect>>", lambda e: self._on_market_select())
        self._market_tree.bind("<Double-1>", lambda e: self._edit_selected_market())

        self._market_info_lbl = ttk.Label(container, text="종목을 선택하세요.",
                                          font=("Malgun Gothic", 9))
        self._market_info_lbl.pack(anchor="w", pady=2)
        self._market_status_lbl = ttk.Label(container, text="", font=("Malgun Gothic", 8),
                                            foreground=self._STATUS_FG["secondary"])
        self._market_status_lbl.pack(anchor="w", pady=(0, 2))

        self._market_chart_canvas = tk.Canvas(container, height=100, bg="#f8f9fa", highlightthickness=1)
        self._market_chart_canvas.pack(fill=X, pady=3)

        self._search_market()

    def _set_market_info(self, text: str, kind: str | None = None):
        """하단 요약 라벨 갱신 (위젯이 없으면 무시)"""
        lbl = getattr(self, "_market_info_lbl", None)
        if lbl is None:
            return
        try:
            if kind:
                lbl.config(text=text, foreground=self._STATUS_FG.get(kind, "#000000"))
            else:
                lbl.config(text=text)
        except tk.TclError:
            pass

    def _set_market_status(self, text: str, kind: str = "secondary"):
        """상태(진행/경고) 라벨 갱신 (위젯이 없으면 무시)"""
        lbl = getattr(self, "_market_status_lbl", None)
        if lbl is None:
            return
        try:
            lbl.config(text=text, foreground=self._STATUS_FG.get(kind, self._STATUS_FG["secondary"]))
        except tk.TclError:
            pass

    # ── 검색 (비동기: 네트워크는 워커 스레드, UI 갱신은 after) ──
    def _search_market(self, keyword=None):
        """종목 검색 시작 (2026-09-18: UI 멈춤 방지를 위해 스레드로 위임)"""
        if keyword is None:
            keyword = self.market_search_var.get().strip() or "삼성"
        keyword = str(keyword).strip() or "삼성"
        self.market_mode = "search"
        self._market_search_token = getattr(self, "_market_search_token", 0) + 1
        token = self._market_search_token
        self._set_market_status(f"🔎 '{keyword}' 조회 중...", "info")
        self._market_pending = None
        threading.Thread(target=self._run_market_search,
                         args=(keyword, token), daemon=True).start()
        self._schedule_market_poll()

    def _schedule_market_poll(self):
        """워커 결과를 UI 스레드에서 회수하기 위한 폴링 예약 (스레드 경계 안전)"""
        if getattr(self, "_market_poll_job", None) is not None:
            return
        try:
            self._market_poll_job = self.after(120, self._poll_market_result)
        except tk.TclError:
            self._market_poll_job = None

    def _poll_market_result(self):
        """UI 스레드: 워커가 넘긴 결과를 회수 (미도착 시 계속 폴링)"""
        self._market_poll_job = None
        pending = getattr(self, "_market_pending", None)
        if pending is None:
            self._schedule_market_poll()
            return
        self._market_pending = None
        try:
            self._apply_market_rows(*pending)
        except tk.TclError:
            pass  # 창 종료 중

    def _run_market_search(self, keyword, token):
        """워커 스레드: API 호출만 담당 → 결과 반영은 UI 스레드(_apply_market_rows)로 위임"""
        api_error = ""
        items = []
        try:
            fetcher = MarketFetcher(self.api_key or "")
        except Exception as e:  # noqa: BLE001 - 의도적 폴백: 생성 실패 시에도 화면은 살린다
            fetcher = MarketFetcher("")
            api_error = handle_error(e, context="증권 검색(초기화)", fallback=str(e))
        if not api_error:
            try:
                result = fetcher.search_stocks(keyword) or {}
                items = list(result.get("result", {}).get("items", []) or [])
                api_error = result.get("error", "") or ""
            except Exception as e:  # noqa: BLE001 - 워커 스레드 경계: 예상 외 오류도 폴백
                items = []
                api_error = handle_error(e, context="증권 검색", fallback=str(e))
        mock_used = False
        if not items:
            mock_used = True
            try:
                items = list(fetcher._mock("stock")["result"]["items"])
            except Exception:  # noqa: BLE001 - 샘플 데이터까지 실패하면 빈 화면
                items = []
        payload = [dict(x) for x in items if isinstance(x, dict)]
        # Tk 호출은 메인 스레드에서만: 워커는 결과만 넘기고 UI가 폴링으로 회수한다
        self._market_pending = (payload, api_error, keyword, mock_used, token)

    def _apply_market_rows(self, items, api_error, keyword, mock_used, token):
        """UI 스레드: 검색 결과를 Treeview에 반영 (오래된 토큰 결과는 폐기)"""
        if token != getattr(self, "_market_search_token", -1):
            return
        if not hasattr(self, "_market_tree"):
            return
        # 동일 종목이 기준일만 달리해 여러 건 오므로 base_date 최신 1건만 남긴다
        best = {}
        order = []
        for row in items:
            symbol = self._norm_symbol(row.get("symbol"))
            if not symbol:
                continue
            row = dict(row)
            row["symbol"] = symbol
            prev = best.get(symbol)
            if prev is None:
                best[symbol] = row
                order.append(symbol)
            elif self._cell_str(row.get("base_date")) > self._cell_str(prev.get("base_date")):
                best[symbol] = row
        self._clear_market_tree()
        rows = 0
        for symbol in order:
            row = best[symbol]
            self._market_meta[symbol] = row
            try:
                self._market_tree.insert("", "end", iid=symbol,
                                         values=self._market_row(row),
                                         tags=(self._market_tag(row),))
            except tk.TclError:
                self._market_meta.pop(symbol, None)
                continue
            rows += 1
        self.market_mode = "search"
        if rows == 0:
            self._set_market_status("검색 결과가 없습니다.", "secondary")
            self._set_market_info(f"'{keyword}' 검색 결과가 없습니다.", "warning")
        elif mock_used:
            self._set_market_status(f"⚠️ 실데이터 조회 실패 → 샘플 데이터 {rows}건 표시", "warning")
            self._set_market_info(f"⚠️ {api_error[:90]}" if api_error
                                  else "⚠️ API 키/네트워크를 확인하세요. 샘플 데이터 표시 중.", "warning")
        else:
            self._set_market_status(f"✅ '{keyword}' 실데이터 {rows}건", "success")
            self._set_market_info(f"🔍 '{keyword}' 검색 결과 {rows}건")
        self._draw_market_chart()

    # ── 선택/저장/수정/삭제/전환 ──
    def _sel_market(self):
        """선택 행 → (iid, meta dict). 선택이 없으면 (None, None)"""
        if not hasattr(self, "_market_tree"):
            return None, None
        sel = self._market_tree.selection()
        if not sel:
            return None, None
        iid = sel[0]
        meta = getattr(self, "_market_meta", {}).get(iid)
        if meta is None:  # 메타 유실 시 iid에서 복원 (검색 모드 iid = 종목코드)
            meta = {"id": iid, "symbol": self._raw_symbol(iid)}
        return iid, meta

    def _market_cell(self, iid, index):
        """Treeview iid의 index열 표시값 (없으면 '-')"""
        try:
            vals = list(self._market_tree.item(iid)["values"])
        except tk.TclError:
            return "-"
        return self._cell_str(vals[index]) if len(vals) > index else "-"

    def _save_selected_market(self):
        """선택 종목을 저장목록(DB)에 추가"""
        iid, meta = self._sel_market()
        if not iid:
            messagebox.showwarning("경고", "저장할 종목을 표에서 선택하세요.")
            return
        symbol = self._raw_symbol(meta.get("symbol") or iid)
        name = meta.get("name") or symbol
        if not symbol:
            messagebox.showwarning("경고", "종목코드를 확인할 수 없어 저장할 수 없습니다.")
            return
        price_val = self._to_num(meta.get("price")) or 0.0
        if self.db.add_saved_stock(symbol, name, price_val) is False:
            messagebox.showinfo("알림", f"{name}({symbol})은(는) 이미 저장되어 있습니다.")
            return
        self._set_market_status(f"{name}({symbol}) 저장 완료", "success")
        messagebox.showinfo("완료", f"{name}({symbol})을(를) 저장했습니다.")

    def _edit_selected_market(self):
        """저장된 종목 수정 (저장목록 모드 전용 - id 기준 갱신)"""
        if self.market_mode != "saved":
            messagebox.showinfo("알림", "수정은 '📋 저장목록' 상태에서 종목을 선택해 주세요.")
            return
        iid, meta = self._sel_market()
        if not iid:
            return
        symbol = self._raw_symbol(meta.get("symbol") or "")
        name = meta.get("name") or symbol
        price = meta.get("price")

        edit_win = ttk.Toplevel(self)
        edit_win.title(f"종목 수정: {name}")
        edit_win.geometry("400x220")
        edit_win.grab_set()

        ttk.Label(edit_win, text="종목명:").grid(row=0, column=0, padx=10, pady=8)
        edit_name = ttk.Entry(edit_win, width=20)
        edit_name.grid(row=0, column=1, padx=10, pady=8)
        edit_name.insert(0, name)

        ttk.Label(edit_win, text="종목코드:").grid(row=1, column=0, padx=10, pady=8)
        edit_symbol = ttk.Entry(edit_win, width=20)
        edit_symbol.grid(row=1, column=1, padx=10, pady=8)
        edit_symbol.insert(0, symbol)

        ttk.Label(edit_win, text="가격:").grid(row=2, column=0, padx=10, pady=8)
        edit_price = ttk.Entry(edit_win, width=20)
        edit_price.grid(row=2, column=1, padx=10, pady=8)
        edit_price.insert(0, str(price if price is not None else 0))

        def do_update():
            new_symbol = self._raw_symbol(edit_symbol.get()) or symbol
            price_val = self._to_num(edit_price.get()) or 0.0
            ok = self.db.update_saved_stock(iid, symbol=new_symbol,
                                            name=edit_name.get().strip(), price=price_val)
            edit_win.destroy()
            self._refresh_saved_list()
            if not ok:
                messagebox.showwarning("경고", "수정할 항목을 찾지 못했습니다.")

        ttk.Button(edit_win, text="저장", command=do_update,
                   bootstyle="success").grid(row=3, column=0, columnspan=2, pady=10)

    def _delete_selected_market(self):
        """선택 종목 삭제 (검색: 표에서만 / 저장목록: DB에서 삭제)"""
        iid, meta = self._sel_market()
        if not iid:
            messagebox.showwarning("경고", "삭제할 종목을 선택하세요.")
            return
        name = meta.get("name") or self._raw_symbol(iid)
        if self.market_mode == "saved":
            if not messagebox.askyesno("삭제 확인", f"저장된 종목 '{name}'을(를) 삭제하시겠습니까?"):
                return
            self.db.delete_saved_stock(iid)
            self._refresh_saved_list()
        else:
            self._market_tree.delete(iid)
            getattr(self, "_market_meta", {}).pop(iid, None)

    def _on_market_select(self):
        """종목 선택 시 하단 요약 라벨 + 차트 갱신"""
        if not hasattr(self, "_market_tree") or not hasattr(self, "_market_info_lbl"):
            return
        iid, meta = self._sel_market()
        if not iid:
            return
        symbol = self._raw_symbol(meta.get("symbol") or iid)
        name = meta.get("name") or symbol
        price = meta.get("price")
        if price is None:  # 메타 유실 시 표시값에서 복원
            price = self._market_cell(iid, 2)
        change = meta.get("change")
        if change is None:
            change = self._market_cell(iid, 3)
        pct = meta.get("change_pct")
        if pct is None:
            pct = self._market_cell(iid, 4)
        vol = meta.get("volume")
        if vol is None:
            vol = self._market_cell(iid, 5)
        market = meta.get("market") or self._market_cell(iid, 6)
        self._set_market_info(
            f"📌 {name} ({symbol}) | 종가 {self._fmt_price(price)}원 | "
            f"전일대비 {self._fmt_signed(change)} ({self._fmt_pct(pct)}) | "
            f"거래량 {self._fmt_vol(vol)} | {market}"
        )
        self._draw_market_chart()

    def _draw_market_chart(self):
        """선택 종목 차트 (현재는 Mock 추세선 - 실데이터 차트는 P2 과제)"""
        canvas = getattr(self, "_market_chart_canvas", None)
        if canvas is None:
            return
        try:
            canvas.delete("all")
        except tk.TclError:
            return
        w, h = 400, 100
        prices = [75000, 75500, 74800, 76200, 75900, 76500, 77000]
        y_max, y_min = max(prices), min(prices)
        span = (y_max - y_min) or 1
        x_step = w / len(prices)
        pts = [(i * x_step, h - ((p - y_min) / span * (h - 20) + 10))
               for i, p in enumerate(prices)]
        canvas.create_line(pts, fill="#0d6efd", width=2, smooth=True)

    def _toggle_market_saver(self):
        """검색결과 ↔ 저장목록 전환"""
        if self.market_mode != "search":
            self._search_market()
            return
        self._refresh_saved_list()

    def _refresh_saved_list(self):
        """저장목록 모드 화면 그리기 (검색 요청 없이 DB에서만)"""
        self._market_search_token = getattr(self, "_market_search_token", 0) + 1
        self._clear_market_tree()
        saved = self.db.get_saved_stocks()
        for s in saved:
            symbol = self._raw_symbol(s.get("symbol"))
            sid = str(s.get("id"))
            if not symbol or not sid:
                continue
            self._market_meta[sid] = {"id": s.get("id"), "symbol": symbol,
                                      "name": s.get("name") or symbol,
                                      "price": s.get("price")}
            try:
                self._market_tree.insert("", "end", iid=sid, values=(
                    self._sym_cell(symbol), s.get("name") or "-",
                    self._fmt_price(s.get("price")), "-", "-", "-", "-",
                ))
            except tk.TclError:
                self._market_meta.pop(sid, None)
                continue
        self.market_mode = "saved"
        self._set_market_status(f"저장목록 {len(saved)}건 (DB)", "secondary")
        self._set_market_info(f"저장된 종목 {len(saved)}개 - 더블클릭: 수정 / 🗑 삭제")

    # ── 투자 일기 팝업 (매수/매도 기록 + 월별 실현손익 — DB: investment_journal, 2026-09-13) ──
    def show_investment_journal(self):
        win = tk.Toplevel(self)
        win.title("📔 투자 일기")
        win.geometry("1020x600")
        win.transient(self)

        form = ttk.Labelframe(win, text=" 매매 기록 추가 ", padding=8)
        form.pack(fill=X, padx=10, pady=(10, 4))
        e_date = ttk.Entry(form, width=11); e_date.insert(0, self.today.strftime("%Y-%m-%d"))
        cb_type = ttk.Combobox(form, values=["매수", "매도"], width=6, state="readonly"); cb_type.set("매수")
        e_sym = ttk.Entry(form, width=10)
        e_name = ttk.Entry(form, width=12)
        e_qty = ttk.Entry(form, width=8)
        e_price = ttk.Entry(form, width=11)
        e_fee = ttk.Entry(form, width=8); e_fee.insert(0, "0")
        e_memo = ttk.Entry(form, width=18)
        fields = [("날짜", e_date), ("구분", cb_type), ("종목코드", e_sym), ("종목명", e_name),
                  ("수량", e_qty), ("단가", e_price), ("수수료", e_fee), ("메모", e_memo)]
        for i, (lbl, w) in enumerate(fields):
            ttk.Label(form, text=lbl).grid(row=0, column=i * 2, padx=(10 if i else 2, 2), pady=2)
            w.grid(row=0, column=i * 2 + 1, padx=(0, 2), pady=2)

        ctrl = ttk.Frame(win)
        ctrl.pack(fill=X, padx=10, pady=2)
        ttk.Label(ctrl, text="월 필터 (YYYY-MM):").pack(side=LEFT)
        month_var = tk.StringVar(value=self.today.strftime("%Y-%m"))
        month_entry = ttk.Entry(ctrl, textvariable=month_var, width=9)
        month_entry.pack(side=LEFT, padx=4)
        sum_lbl = ttk.Label(ctrl, text="", font=("Malgun Gothic", 10, "bold"), bootstyle="info")
        sum_lbl.pack(side=LEFT, padx=10)

        cols = ("date", "type", "symbol", "name", "qty", "price", "fee", "memo")
        tree = ttk.Treeview(win, columns=cols, show="headings", bootstyle="info")
        for col, txt, w in [("date", "날짜", 90), ("type", "구분", 60), ("symbol", "코드", 80),
                            ("name", "종목명", 110), ("qty", "수량", 70), ("price", "단가", 100),
                            ("fee", "수수료", 80), ("memo", "메모", 200)]:
            tree.heading(col, text=txt)
            tree.column(col, width=w, anchor="center" if col in ("date", "type", "qty", "fee") else "w")
        tree.pack(fill=BOTH, expand=YES, padx=10, pady=(2, 4))
        tree.tag_configure("sell", foreground="#dc3545")
        tree.tag_configure("buy", foreground="#0a7a3a")

        def refresh():
            month = month_var.get().strip()
            items = self.db.get_investments(month=month or None)
            for it in tree.get_children():
                tree.delete(it)
            for it in items:
                tree.insert("", "end", iid=str(it["id"]), tags=("sell" if it["type"] == "매도" else "buy"),
                            values=(it["date"], it["type"], it["symbol"], it["name"],
                                    f"{it['quantity']:,}", f"{it['price']:,.0f}", f"{it['commission']:,.0f}", it["memo"] or ""))
            s = self.db.get_investment_summary(month or None)
            net = s["net"]
            net_txt = f"+{net:,.0f}" if net >= 0 else f"{net:,.0f}"
            sum_lbl.config(text=f"매수합 {s['buy_cost']:,.0f}원 · 매도합 {s['sell_proceed']:,.0f}원 · 실현손익 {net_txt}원 · {s['count']}건")

        def add():
            try:
                d = e_date.get().strip()
                datetime.strptime(d, "%Y-%m-%d")
                qty = int(str(e_qty.get() or "").replace(",", "").strip() or 0)
                s_price = str(e_price.get() or "").replace(",", "").strip()
                s_fee = str(e_fee.get() or "").replace(",", "").strip()
                try:
                    price = float(s_price) if s_price else 0.0
                    fee = float(s_fee) if s_fee else 0.0
                except ValueError:
                    messagebox.showwarning(
                        "입력 오류",
                        "단가/수수료는 숫자로 입력하세요.",
                        parent=win,
                    )
                    return
            except ValueError:
                messagebox.showwarning(
                    "입력 오류",
                    "날짜는 YYYY-MM-DD, 수량/단가/수수료는 숫자로 입력하세요.",
                    parent=win,
                )
                return
            if not e_name.get().strip():
                messagebox.showwarning("입력 오류", "종목명을 입력하세요.", parent=win)
                return
            self.db.add_investment(d, cb_type.get(), e_sym.get().strip(), e_name.get().strip(), qty, price, fee, e_memo.get().strip())
            for e in (e_qty, e_price, e_memo):
                e.delete(0, "end")
            e_fee.delete(0, "end"); e_fee.insert(0, "0")
            refresh()
            ToastNotification("투자일기", "매매 기록이 추가되었습니다", bootstyle="success").show_toast()

        def delete_sel():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("알림", "삭제할 기록을 선택하세요.", parent=win)
                return
            if not messagebox.askyesno("삭제", f"선택한 {len(sel)}건의 기록을 삭제할까요?", parent=win):
                return
            for iid in sel:
                self.db.delete_investment(int(iid))
            refresh()

        btn_box = ttk.Frame(win, padding=(10, 0, 10, 10))
        btn_box.pack(fill=X)
        ttk.Button(btn_box, text="➕ 기록 추가", command=add, bootstyle="success").pack(side=LEFT, padx=(0, 8))
        ttk.Button(btn_box, text="🗑 선택 삭제", command=delete_sel, bootstyle="danger-outline").pack(side=LEFT)
        ttk.Button(btn_box, text="🔄 새로고침", command=refresh, bootstyle="info-outline").pack(side=LEFT, padx=8)
        ttk.Button(btn_box, text="닫기", command=win.destroy, bootstyle="secondary-outline").pack(side=RIGHT)
        month_entry.bind("<Return>", lambda e: refresh())
        refresh()
    # -------------------------------------------------------------
    # 뷰: 가계부 (수입/지출 관리)
    # -------------------------------------------------------------
    def setup_ledger_view(self):
        """💰 가계부 탭"""
        header = ttk.Frame(self.content_area)
        header.pack(fill=X, pady=(0, 10))
        ttk.Label(header, text="💰 가계부", font=("Malgun Gothic", 18, "bold")).pack(side=LEFT)
        # 월별 요약
        summary_frame = ttk.Labelframe(self.content_area, text=" 📊 월별 요약 ", padding=10, bootstyle="info")
        summary_frame.pack(fill=X, pady=(0, 10))
        self.ledger_month_var = tk.StringVar(value=f"{self.curr_year}-{self.curr_month:02d}")
        month_ctrl = ttk.Frame(summary_frame)
        month_ctrl.pack(fill=X, pady=(0, 5))
        ttk.Label(month_ctrl, text="월 선택:").pack(side=LEFT, padx=(0, 5))
        months = [f"{self.curr_year}-{m:02d}" for m in range(1, 13)]
        ttk.Combobox(month_ctrl, textvariable=self.ledger_month_var, values=months, width=10, state="readonly").pack(side=LEFT, padx=(0, 10))
        ttk.Button(month_ctrl, text="조회", command=self._refresh_ledger_summary, bootstyle="info-outline").pack(side=LEFT)
        summary_inner = ttk.Frame(summary_frame)
        summary_inner.pack(fill=X, pady=5)
        self.ledger_summary_labels = {}
        for i, (key, text, style) in enumerate([("income", "총수입:", "success"), ("expense", "총지출:", "danger"), ("savings", "순저축:", "warning")]):
            ttk.Label(summary_inner, text=text, font=("Malgun Gothic", 11)).grid(row=0, column=i*2, padx=(10, 2), pady=5, sticky="e")
            self.ledger_summary_labels[key] = ttk.Label(summary_inner, text="0원", font=("Malgun Gothic", 11, "bold"), bootstyle=style)
            self.ledger_summary_labels[key].grid(row=0, column=i*2+1, padx=(0, 10), pady=5, sticky="w")

        # 입력 폼
        form_frame = ttk.Labelframe(self.content_area, text=" ✏️ 내역 입력 ", padding=10, bootstyle="success")
        form_frame.pack(fill=X, pady=(0, 10))
        row1 = ttk.Frame(form_frame); row1.pack(fill=X, pady=2)
        ttk.Label(row1, text="날짜:").pack(side=LEFT)
        self.ledger_date_entry = ttk.Entry(row1, width=12); self.ledger_date_entry.pack(side=LEFT, padx=(2, 10))
        self.ledger_date_entry.insert(0, self.today.strftime("%Y-%m-%d"))
        ttk.Label(row1, text="구분:").pack(side=LEFT)
        self.ledger_type_var = tk.StringVar(value="지출")
        ttk.Combobox(row1, textvariable=self.ledger_type_var, values=["수입", "지출"], width=6, state="readonly").pack(side=LEFT, padx=(2, 10))
        ttk.Label(row1, text="카테고리:").pack(side=LEFT)
        self.ledger_cat_var = tk.StringVar(value="식비")
        ttk.Combobox(row1, textvariable=self.ledger_cat_var,
                     values=["식비", "교통", "통신", "주거", "학습", "건강", "문화", "기타", "급여", "용돈", "기타수입"],
                     width=10, state="readonly").pack(side=LEFT, padx=(2, 10))
        row2 = ttk.Frame(form_frame); row2.pack(fill=X, pady=2)
        ttk.Label(row2, text="금액:").pack(side=LEFT)
        self.ledger_amount_entry = ttk.Entry(row2, width=12); self.ledger_amount_entry.pack(side=LEFT, padx=(2, 10))
        ttk.Label(row2, text="메모:").pack(side=LEFT)
        self.ledger_memo_entry = ttk.Entry(row2, width=30); self.ledger_memo_entry.pack(side=LEFT, padx=(2, 10))
        row3 = ttk.Frame(form_frame); row3.pack(fill=X, pady=(5, 0))
        ttk.Button(row3, text="➕ 추가", command=self._add_transaction, bootstyle="success").pack(side=LEFT, padx=3)
        ttk.Button(row3, text="🗑 선택삭제", command=self._delete_transaction, bootstyle="danger-outline").pack(side=LEFT, padx=3)

        # 목록
        list_frame = ttk.Labelframe(self.content_area, text=" 📋 거래 내역 ", padding=8, bootstyle="secondary")
        list_frame.pack(fill=BOTH, expand=YES)
        cols = ("date", "type", "category", "amount", "memo")
        self.ledger_tree = ttk.Treeview(list_frame, columns=cols, show="headings", height=12)
        self.ledger_tree.heading("date", text="날짜"); self.ledger_tree.column("date", width=100, anchor="center")
        self.ledger_tree.heading("type", text="구분"); self.ledger_tree.column("type", width=60, anchor="center")
        self.ledger_tree.heading("category", text="카테고리"); self.ledger_tree.column("category", width=80, anchor="center")
        self.ledger_tree.heading("amount", text="금액"); self.ledger_tree.column("amount", width=100, anchor="e")
        self.ledger_tree.heading("memo", text="메모"); self.ledger_tree.column("memo", width=250, anchor="w")
        vsb = ttk.Scrollbar(list_frame, orient=VERTICAL, command=self.ledger_tree.yview, bootstyle="round-info")
        self.ledger_tree.configure(yscrollcommand=vsb.set)
        self.ledger_tree.pack(side=LEFT, fill=BOTH, expand=YES); vsb.pack(side=RIGHT, fill=Y)
        self._refresh_ledger_summary(); self._refresh_ledger_tree()

    def _refresh_ledger_summary(self):
        ym = self.ledger_month_var.get()
        try: year, month = map(int, ym.split("-"))
        except (ValueError, AttributeError): return
        s = self.db.get_month_summary(year, month)
        self.ledger_summary_labels["income"].config(text=f"{s['income']:,}원")
        self.ledger_summary_labels["expense"].config(text=f"{s['expense']:,}원")
        self.ledger_summary_labels["savings"].config(text=f"{s['savings']:,}원")

    def _refresh_ledger_tree(self):
        for item in self.ledger_tree.get_children(): self.ledger_tree.delete(item)
        ym = self.ledger_month_var.get()
        for t in self.db.get_transactions(month=ym):
            tag = "수입" if t["type"] == "수입" else "지출"
            self.ledger_tree.insert("", "end", iid=str(t["id"]),
                                    values=(t["date"], t["type"], t["category"], f"{t['amount']:,}원", t["memo"] or ""), tags=(tag,))
        self.ledger_tree.tag_configure("수입", foreground="#28a745")
        self.ledger_tree.tag_configure("지출", foreground="#dc3545")

    def _add_transaction(self):
        date = self.ledger_date_entry.get().strip()
        type_ = self.ledger_type_var.get(); category = self.ledger_cat_var.get()
        amount_str = self.ledger_amount_entry.get().strip(); memo = self.ledger_memo_entry.get().strip()
        if not date or not amount_str: messagebox.showwarning("알림", "날짜와 금액을 입력하세요."); return
        try: amount = int(amount_str)
        except ValueError: messagebox.showwarning("알림", "금액은 숫자로 입력하세요."); return
        self.db.add_transaction(date, type_, category, amount, memo)
        self._refresh_ledger_summary(); self._refresh_ledger_tree()
        self.ledger_amount_entry.delete(0, "end"); self.ledger_memo_entry.delete(0, "end")

    def _delete_transaction(self):
        sel = self.ledger_tree.selection()
        if not sel: messagebox.showwarning("알림", "삭제할 항목을 선택하세요."); return
        if messagebox.askyesno("삭제 확인", "선택한 항목을 삭제하시겠습니까?"):
            for item in sel: self.db.delete_transaction(int(item))
            self._refresh_ledger_summary(); self._refresh_ledger_tree()





    # 뷰 4: 공부 탭 (과목별 노트 / 단어·용어 / 매일 진도 체크)
    # -------------------------------------------------------------
    def setup_study_view(self):
        ttk.Label(self.content_area, text="📚 기본학습", font=("Malgun Gothic", 20, "bold"), bootstyle="primary").pack(anchor="w", pady=(0, 5))
        ttk.Label(self.content_area, text="과목별 자료와 메모를 탭으로 정리한 학습 공간", bootstyle="secondary",
                  font=("Malgun Gothic", 10)).pack(anchor="w", pady=(0, 12))

        # ── 진도율 위젯 (2026-09-20 Day5 P1-3) ──
        # study_progress 집계(전체 + 과목별)를 한 줄로 보여준다.
        # refresh_study_progress 계열 동작이 끝날 때마다 갱신된다.
        self.study_rate_var = tk.StringVar(value="오늘 진도: 기록 없음")
        rate_bar = ttk.Frame(self.content_area)
        rate_bar.pack(fill=X, pady=(0, 8))
        ttk.Label(rate_bar, textvariable=self.study_rate_var,
                  font=("Malgun Gothic", 11, "bold"), bootstyle="info").pack(side=LEFT)
        ttk.Button(rate_bar, text="🔄", width=3, bootstyle="secondary-outline",
                   command=self.refresh_study_rate).pack(side=RIGHT)
        self.refresh_study_rate()

        self.study_notebook = ttk.Notebook(self.content_area)
        self.study_notebook.pack(fill=BOTH, expand=YES, pady=(0, 10))

        self.study_tabs = {}
        self.subject_widgets = {}
        self._build_study_tabs()

    def _build_study_tabs(self):
        for name in ["단어장", "생활용어", "공식집", "용어집", "사자성어", "한자", "과학", "IT", "화학", "물리", "지구과학", "사회탐구", "역사"]:
            if not self.db.get_category_id(name):
                self.db.add_category(name)

        subjects = [
            ("단어장", "📕", "단어/표현의 뜻, 예문, 발음을 정리합니다."),
            ("생활용어", "💬", "일상에서 자주 쓰는 문장/표현을 정리합니다."),
            ("공식집", "📐", "수학/과학/기타 공식을 분야별로 정리합니다."),
            ("용어집", "🔬", "과학/공학/사회 등 전문 용어를 정리합니다."),
            ("사자성어", "🦉", "사자성어의 뜻과 용례를 정리합니다."),
            ("한자", " 한자", "한자/한문 읽기, 부수, 훈음을 정리합니다."),
            ("과학", "🔬", "과학 일반 개념과 실험/관찰 메모를 정리합니다."),
            ("IT", "💻", "정보기술, 프로그래밍, 기기 관련 메모를 정리합니다."),
            ("화학", "🧪", "화학식, 반응, 주기율 관련 자료를 정리합니다."),
            ("물리", "⚡", "물리 법칙, 공식, 문제 메모를 정리합니다."),
            ("지구과학", "🌍", "지구, 천문, 기상, 지질 관련 자료를 정리합니다."),
            ("사회탐구", "🌐", "사회/역사/지리/윤리 등 탐구 자료를 정리합니다."),
            ("역사", "📜", "한국사 연대기 (고조선~현대)"),
        ]

        for title, icon, desc in subjects:
            tab = ttk.Frame(self.study_notebook)
            self.study_notebook.add(tab, text=f"{icon} {title}")
            self.study_tabs[title] = tab
            self._setup_subject_tab(tab, title, icon, desc)

    def _setup_subject_tab(self, tab, title, icon, desc):
        top = ttk.Frame(tab)
        top.pack(fill=X, pady=(0, 8))
        ttk.Label(top, text=f"{icon} {title}", font=("Malgun Gothic", 14, "bold")).pack(side=LEFT)
        ttk.Label(top, text=desc, bootstyle="secondary", font=("Malgun Gothic", 9)).pack(side=LEFT, padx=(12, 0), anchor="n")

        ttk.Separator(top, orient="vertical").pack(side=LEFT, fill=Y, expand=YES, padx=8)
        ttk.Button(top, text="🔄 새로고침", command=lambda: self._refresh_subject_view(title), bootstyle="secondary-outline").pack(side=RIGHT, padx=3)

        body = ttk.Frame(tab)
        body.pack(fill=BOTH, expand=YES)
        self.subject_widgets[title] = {}

        # ── 단어장 서브탭 ──
        if title == "단어장":
            self._build_wordbook_subtab(body, title)
        # ── 생활용어 서브탭 ──
        elif title == "생활용어":
            self._build_phrases_subtab(body, title)
        # ── 공식집 서브탭 ──
        elif title == "공식집":
            self._build_formulas_subtab(body, title)
        # ── 용어집 서브탭 ──
        elif title == "용어집":
            self._build_glossary_subtab(body, title)
        # ── 사자성어 서브탭 ──
        elif title == "사자성어":
            self._build_idiom_subtab(body, title)
        # ── 한자 서브탭 ──
        elif title == "한자":
            self._build_hanja_subtab(body, title)
        # ── 역사 서브탭 ──
        elif title == "역사":
            self._build_history_subtab(body, title)
        # ── 과학/IT/화학/물리/지구과학/사회탐구 서브탭 ──
        else:
            self._build_science_subtab(body, title)

    def _refresh_subject_view(self, title):
        """서브탭 새로고침"""
        widgets = self.subject_widgets.get(title)
        if widgets is None:
            return
        if title == "단어장":
            self._refresh_subtab_wordbook()
        elif title == "생활용어":
            self._refresh_subtab_phrases()
        elif title == "공식집":
            self._refresh_subtab_formulas()
        elif title == "용어집":
            self._refresh_subtab_glossary()
        elif title == "사자성어":
            self._refresh_subtab_idioms()
        elif title == "한자":
            self._refresh_subtab_hanja()
        elif title == "역사":
            self._refresh_subtab_history()
        else:
            self._refresh_subtab_science(title)

    # ── 단어장 서브탭 ─────────────────────────────────────────
    def _build_wordbook_subtab(self, parent, title):
        ctrl = ttk.Frame(parent)
        ctrl.pack(fill=X, pady=(0, 5))
        ttk.Label(ctrl, text="언어:").pack(side=LEFT, padx=(0, 3))
        self.subject_widgets[title]["lang_var"] = tk.StringVar(value="전체")
        lang_combo = ttk.Combobox(ctrl, textvariable=self.subject_widgets[title]["lang_var"],
                                  values=["전체"] + (self.db.get_word_languages() or ["영어"]),
                                  width=10, state="readonly")
        lang_combo.pack(side=LEFT, padx=(0, 10))
        lang_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_subtab_wordbook())
        ttk.Label(ctrl, text="검색:").pack(side=LEFT, padx=(0, 3))
        self.subject_widgets[title]["search_entry"] = ttk.Entry(ctrl, width=20)
        self.subject_widgets[title]["search_entry"].pack(side=LEFT, padx=(0, 5))
        self.subject_widgets[title]["search_entry"].bind("<Return>", lambda e: self._refresh_subtab_wordbook())
        ttk.Button(ctrl, text="🔎", command=self._refresh_subtab_wordbook, bootstyle="info-outline", width=3).pack(side=LEFT)
        ttk.Button(ctrl, text="🔁 오늘 복습", command=self.show_review_popup, bootstyle="warning-outline").pack(side=RIGHT)
        self.subject_widgets[title]["count_lbl"] = ttk.Label(parent, text="", bootstyle="secondary")
        self.subject_widgets[title]["count_lbl"].pack(anchor="w", pady=(0, 3))
        tree_box = ttk.Frame(parent)
        tree_box.pack(fill=BOTH, expand=YES)
        cols = ("rank", "word", "pron_en", "pron_ko", "pos", "meaning", "example")
        self.subject_widgets[title]["tree"] = ttk.Treeview(tree_box, columns=cols, show="headings", bootstyle="info")
        for col, txt, w in [("rank","순위",50),("word","단어",120),("pron_en","발음(영)",100),("pron_ko","발음(한)",100),("pos","품사",60),("meaning","뜻",200),("example","예문",250)]:
            self.subject_widgets[title]["tree"].heading(col, text=txt)
            self.subject_widgets[title]["tree"].column(col, width=w, anchor="center" if col in ("rank","pos") else "w")
        vsb = ttk.Scrollbar(tree_box, orient=VERTICAL, command=self.subject_widgets[title]["tree"].yview, bootstyle="round-info")
        self.subject_widgets[title]["tree"].configure(yscrollcommand=vsb.set)
        self.subject_widgets[title]["tree"].pack(side=LEFT, fill=BOTH, expand=YES); vsb.pack(side=RIGHT, fill=Y)
        self._refresh_subtab_wordbook()

    def _refresh_subtab_wordbook(self):
        w = self.subject_widgets.get("단어장")
        if not w: return
        for item in w["tree"].get_children(): w["tree"].delete(item)
        lang = w["lang_var"].get()
        keyword = w["search_entry"].get().strip()
        words = self.db.get_words(language=None if lang == "전체" else lang, keyword=keyword or None)
        for word in words:
            w["tree"].insert("", "end", iid=str(word["id"]),
                             values=(word["rank"], word["word"], word["pron_en"] or "", word["pron_ko"] or "", word["pos"] or "", word["meaning"] or "", word["example"] or ""))
        w["count_lbl"].config(text=f"총 {len(words)}개 단어")

    # ── 단어장 복습 팝업 (스페이스 반복: ease 0→1일, 1→3일, 2→7일, 3→14일, 4→30일 — 2026-09-13) ──
    def show_review_popup(self):
        due = self.db.get_words_due_for_review(limit=50)
        if not due:
            messagebox.showinfo("오늘 복습", "오늘 복습할 단어가 없습니다. 🎉")
            return
        win = tk.Toplevel(self)
        win.title(f"🔁 오늘의 복습 ({len(due)}개)")
        win.geometry("560x380")
        win.grab_set()
        state = {"idx": 0, "ok": 0, "fail": 0, "items": due}
        info = ttk.Label(win, text="", font=("Malgun Gothic", 10), bootstyle="secondary")
        info.pack(anchor="w", padx=14, pady=(12, 0))
        word_lbl = ttk.Label(win, text="", font=("Malgun Gothic", 24, "bold"))
        word_lbl.pack(pady=(8, 0))
        pron_lbl = ttk.Label(win, text="", font=("Malgun Gothic", 11), bootstyle="secondary")
        pron_lbl.pack()
        ans_lbl = ttk.Label(win, text="", font=("Malgun Gothic", 12), bootstyle="warning", wraplength=500, justify="left")
        ans_lbl.pack(pady=8, padx=14)
        btns = ttk.Frame(win)
        btns.pack(pady=4)

        def show():
            if state["idx"] >= len(state["items"]):
                word_lbl.config(text="복습 완료! 🎉")
                pron_lbl.config(text=f"성공 {state['ok']}건 / 실패 {state['fail']}건")
                ans_lbl.config(text="모든 카드를 확인했습니다. 창을 닫아주세요.")
                for b in (reveal_btn, ok_btn, fail_btn):
                    b.config(state=DISABLED)
                self._refresh_subtab_wordbook()
                return
            w = state["items"][state["idx"]]
            info.config(text=f"{state['idx'] + 1} / {len(state['items'])} · {w['language']}")
            word_lbl.config(text=w["word"])
            pron = " ".join(x for x in (w.get("pron_en") or "", w.get("pron_ko") or "") if x)
            pron_lbl.config(text=pron or "-")
            ans_lbl.config(text="뜻을 떠올려 보세요 → [🫣 뜻 확인]")
            reveal_btn.config(state=NORMAL)
            ok_btn.config(state=DISABLED)
            fail_btn.config(state=DISABLED)

        def reveal():
            w = state["items"][state["idx"]]
            ans_lbl.config(text=f"[{w.get('pos') or '-'}] {w['meaning']}\n예문: {w.get('example') or '-'}\n해석: {w.get('example_ko') or '-'}")
            reveal_btn.config(state=DISABLED)
            ok_btn.config(state=NORMAL)
            fail_btn.config(state=NORMAL)

        def grade(success):
            w = state["items"][state["idx"]]
            self.db.mark_word_reviewed(w["id"], success=success)
            state["ok" if success else "fail"] += 1
            state["idx"] += 1
            show()

        reveal_btn = ttk.Button(btns, text="🫣 뜻 확인", command=reveal, bootstyle="info", width=12)
        reveal_btn.pack(side=LEFT, padx=4)
        ok_btn = ttk.Button(btns, text="✅ 성공", command=lambda: grade(True), bootstyle="success", width=10)
        ok_btn.pack(side=LEFT, padx=4)
        fail_btn = ttk.Button(btns, text="❌ 실패", command=lambda: grade(False), bootstyle="danger", width=10)
        fail_btn.pack(side=LEFT, padx=4)
        ttk.Button(win, text="닫기", command=win.destroy, bootstyle="secondary-outline").pack(pady=(6, 12))
        show()

    # ── 생활용어 서브탭 ─────────────────────────────────────────
    def _build_phrases_subtab(self, parent, title):
        ctrl = ttk.Frame(parent)
        ctrl.pack(fill=X, pady=(0, 5))
        ttk.Label(ctrl, text="언어:").pack(side=LEFT, padx=(0, 3))
        self.subject_widgets[title]["lang_var"] = tk.StringVar(value="전체")
        lang_combo = ttk.Combobox(ctrl, textvariable=self.subject_widgets[title]["lang_var"],
                                  values=["전체"] + (self.db.get_phrase_languages() or ["영어"]),
                                  width=10, state="readonly")
        lang_combo.pack(side=LEFT, padx=(0, 10))
        lang_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_subtab_phrases())
        ttk.Label(ctrl, text="검색:").pack(side=LEFT, padx=(0, 3))
        self.subject_widgets[title]["search_entry"] = ttk.Entry(ctrl, width=20)
        self.subject_widgets[title]["search_entry"].pack(side=LEFT, padx=(0, 5))
        self.subject_widgets[title]["search_entry"].bind("<Return>", lambda e: self._refresh_subtab_phrases())
        ttk.Button(ctrl, text="🔎", command=self._refresh_subtab_phrases, bootstyle="info-outline", width=3).pack(side=LEFT)
        self.subject_widgets[title]["count_lbl"] = ttk.Label(parent, text="", bootstyle="secondary")
        self.subject_widgets[title]["count_lbl"].pack(anchor="w", pady=(0, 3))
        tree_box = ttk.Frame(parent)
        tree_box.pack(fill=BOTH, expand=YES)
        cols = ("rank", "sentence", "pron_ko", "meaning_ko")
        self.subject_widgets[title]["tree"] = ttk.Treeview(tree_box, columns=cols, show="headings", bootstyle="success")
        for col, txt, w in [("rank","순위",50),("sentence","문장",300),("pron_ko","발음",150),("meaning_ko","뜻",300)]:
            self.subject_widgets[title]["tree"].heading(col, text=txt)
            self.subject_widgets[title]["tree"].column(col, width=w, anchor="center" if col == "rank" else "w")
        vsb = ttk.Scrollbar(tree_box, orient=VERTICAL, command=self.subject_widgets[title]["tree"].yview, bootstyle="round-success")
        self.subject_widgets[title]["tree"].configure(yscrollcommand=vsb.set)
        self.subject_widgets[title]["tree"].pack(side=LEFT, fill=BOTH, expand=YES); vsb.pack(side=RIGHT, fill=Y)
        self._refresh_subtab_phrases()

    def _refresh_subtab_phrases(self):
        w = self.subject_widgets.get("생활용어")
        if not w: return
        for item in w["tree"].get_children(): w["tree"].delete(item)
        lang = w["lang_var"].get()
        keyword = w["search_entry"].get().strip()
        phrases = self.db.get_phrases(language=None if lang == "전체" else lang, keyword=keyword or None)
        for p in phrases:
            w["tree"].insert("", "end", iid=str(p["id"]),
                             values=(p["rank"], p["sentence"], p["pron_ko"] or "", p["meaning_ko"] or ""))
        w["count_lbl"].config(text=f"총 {len(phrases)}개 문장")



    def _current_cat_id(self, name=None):
        if name is None:
            if hasattr(self, "combo_cat") and self.combo_cat.get():
                return self.db.get_category_id(self.combo_cat.get())
            return None
        return self.db.get_category_id(name)

    def on_study_cat_change(self):
        self.refresh_study_notes()
        self.refresh_study_words()
    def _build_formulas_subtab(self, parent, title):
        ctrl = ttk.Frame(parent)
        ctrl.pack(fill=X, pady=(0, 5))
        ttk.Label(ctrl, text="주가:").pack(side=LEFT, padx=(0, 3))
        self.subject_widgets[title]["level_var"] = tk.StringVar(value="전체")
        level_combo = ttk.Combobox(ctrl, textvariable=self.subject_widgets[title]["level_var"],
                                   values=["전체"] + list(formulas_lib.LEVELS), width=8, state="readonly")
        level_combo.pack(side=LEFT, padx=(0, 10))
        level_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_subtab_formulas())
        ttk.Label(ctrl, text="분야:").pack(side=LEFT, padx=(0, 3))
        self.subject_widgets[title]["cat_var"] = tk.StringVar(value="전체")
        cat_combo = ttk.Combobox(ctrl, textvariable=self.subject_widgets[title]["cat_var"],
                                 values=["전체"] + formulas_lib.get_categories(), width=12, state="readonly")
        cat_combo.pack(side=LEFT, padx=(0, 10))
        cat_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_subtab_formulas())
        ttk.Label(ctrl, text="검색:").pack(side=LEFT, padx=(0, 3))
        self.subject_widgets[title]["search_entry"] = ttk.Entry(ctrl, width=20)
        self.subject_widgets[title]["search_entry"].pack(side=LEFT, padx=(0, 5))
        self.subject_widgets[title]["search_entry"].bind("<Return>", lambda e: self._refresh_subtab_formulas())
        ttk.Button(ctrl, text="🔎", command=self._refresh_subtab_formulas, bootstyle="info-outline", width=3).pack(side=LEFT)
        self.subject_widgets[title]["count_lbl"] = ttk.Label(parent, text="", bootstyle="secondary")
        self.subject_widgets[title]["count_lbl"].pack(anchor="w", pady=(0, 3))
        tree_box = ttk.Frame(parent)
        tree_box.pack(fill=BOTH, expand=YES)
        cols = ("cat", "level", "name", "expr")
        self.subject_widgets[title]["tree"] = ttk.Treeview(tree_box, columns=cols, show="headings", bootstyle="warning")
        for col, txt, w in [("cat","분야",100),("level","주가",60),("name","공식 이름",200),("expr","식",400)]:
            self.subject_widgets[title]["tree"].heading(col, text=txt)
            self.subject_widgets[title]["tree"].column(col, width=w, anchor="center" if col == "level" else "w")
        vsb = ttk.Scrollbar(tree_box, orient=VERTICAL, command=self.subject_widgets[title]["tree"].yview, bootstyle="round-warning")
        self.subject_widgets[title]["tree"].configure(yscrollcommand=vsb.set)
        self.subject_widgets[title]["tree"].pack(side=LEFT, fill=BOTH, expand=YES); vsb.pack(side=RIGHT, fill=Y)
        self._refresh_subtab_formulas()

    def _refresh_subtab_formulas(self):
        w = self.subject_widgets.get("공식집")
        if not w: return
        for item in w["tree"].get_children(): w["tree"].delete(item)
        keyword = w["search_entry"].get().strip()
        level = w["level_var"].get()
        cat = w["cat_var"].get()
        rows = formulas_lib.search(keyword) if keyword else formulas_lib.get_all()
        if level != "전체": rows = [r for r in rows if r[1] == level]
        if cat != "전체": rows = [r for r in rows if r[0] == cat]
        for r in rows:
            w["tree"].insert("", "end", values=(r[0], r[1], r[2], r[3]))
        w["count_lbl"].config(text=f"총 {len(rows)}개 공식")

    def _build_glossary_subtab(self, parent, title):
        ctrl = ttk.Frame(parent)
        ctrl.pack(fill=X, pady=(0, 5))
        ttk.Label(ctrl, text="구분:").pack(side=LEFT, padx=(0, 3))
        self.subject_widgets[title]["cat_var"] = tk.StringVar(value="전체")
        cat_combo = ttk.Combobox(ctrl, textvariable=self.subject_widgets[title]["cat_var"],
                                 values=["전체"] + glossary_lib.get_categories(), width=12, state="readonly")
        cat_combo.pack(side=LEFT, padx=(0, 10))
        cat_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_subtab_glossary())
        ttk.Label(ctrl, text="검색:").pack(side=LEFT, padx=(0, 3))
        self.subject_widgets[title]["search_entry"] = ttk.Entry(ctrl, width=24)
        self.subject_widgets[title]["search_entry"].pack(side=LEFT, padx=(0, 5))
        self.subject_widgets[title]["search_entry"].bind("<Return>", lambda e: self._refresh_subtab_glossary())
        ttk.Button(ctrl, text="🔎", command=self._refresh_subtab_glossary, bootstyle="info-outline", width=3).pack(side=LEFT)
        self.subject_widgets[title]["count_lbl"] = ttk.Label(parent, text="", bootstyle="secondary")
        self.subject_widgets[title]["count_lbl"].pack(anchor="w", pady=(0, 3))
        tree_box = ttk.Frame(parent)
        tree_box.pack(fill=BOTH, expand=YES)
        cols = ("cat", "term", "desc")
        self.subject_widgets[title]["tree"] = ttk.Treeview(tree_box, columns=cols, show="headings", bootstyle="success")
        for col, txt, w in [("cat","구분",100),("term","용어",250),("desc","설명",450)]:
            self.subject_widgets[title]["tree"].heading(col, text=txt)
            self.subject_widgets[title]["tree"].column(col, width=w, anchor="center" if col == "cat" else "w")
        vsb = ttk.Scrollbar(tree_box, orient=VERTICAL, command=self.subject_widgets[title]["tree"].yview, bootstyle="round-success")
        self.subject_widgets[title]["tree"].configure(yscrollcommand=vsb.set)
        self.subject_widgets[title]["tree"].pack(side=LEFT, fill=BOTH, expand=YES); vsb.pack(side=RIGHT, fill=Y)
        self._refresh_subtab_glossary()

    def _refresh_subtab_glossary(self):
        w = self.subject_widgets.get("용어집")
        if not w: return
        for item in w["tree"].get_children(): w["tree"].delete(item)
        keyword = w["search_entry"].get().strip()
        cat = w["cat_var"].get()
        rows = glossary_lib.search(keyword) if keyword else glossary_lib.get_all()
        if cat != "전체": rows = [r for r in rows if r[0] == cat]
        for r in rows:
            w["tree"].insert("", "end", values=(r[0], r[1], r[2]))
        w["count_lbl"].config(text=f"총 {len(rows)}개 용어")


    def _build_idiom_subtab(self, parent, title):
        ctrl = ttk.Frame(parent)
        ctrl.pack(fill=X, pady=(0, 5))
        ttk.Label(ctrl, text="검색:").pack(side=LEFT, padx=(0, 3))
        self.subject_widgets[title]["search_entry"] = ttk.Entry(ctrl, width=28)
        self.subject_widgets[title]["search_entry"].pack(side=LEFT, padx=(0, 5))
        self.subject_widgets[title]["search_entry"].bind("<Return>", lambda e: self._refresh_subtab_idioms())
        ttk.Button(ctrl, text="🔎 검색", command=self._refresh_subtab_idioms, bootstyle="info-outline").pack(side=LEFT, padx=(0, 5))
        ttk.Button(ctrl, text="전체보기", command=lambda: (self.subject_widgets[title]["search_entry"].delete(0, "end"), self._refresh_subtab_idioms()), bootstyle="secondary-outline").pack(side=LEFT)
        self.subject_widgets[title]["count_lbl"] = ttk.Label(parent, text="", bootstyle="secondary")
        self.subject_widgets[title]["count_lbl"].pack(anchor="w", pady=(0, 3))
        tree_box = ttk.Frame(parent)
        tree_box.pack(fill=BOTH, expand=YES)
        cols = ("idiom", "reading", "meaning", "source")
        self.subject_widgets[title]["tree"] = ttk.Treeview(tree_box, columns=cols, show="headings", bootstyle="warning")
        for col, txt, w in [("idiom","사자성어",150),("reading","읽기",120),("meaning","뜻/해설",350),("source","유래",200)]:
            self.subject_widgets[title]["tree"].heading(col, text=txt)
            self.subject_widgets[title]["tree"].column(col, width=w, anchor="center" if col == "reading" else "w")
        vsb = ttk.Scrollbar(tree_box, orient=VERTICAL, command=self.subject_widgets[title]["tree"].yview, bootstyle="round-warning")
        self.subject_widgets[title]["tree"].configure(yscrollcommand=vsb.set)
        self.subject_widgets[title]["tree"].pack(side=LEFT, fill=BOTH, expand=YES); vsb.pack(side=RIGHT, fill=Y)
        self._refresh_subtab_idioms()

    def _refresh_subtab_idioms(self):
        w = self.subject_widgets.get("사자성어")
        if not w: return
        for item in w["tree"].get_children(): w["tree"].delete(item)
        keyword = w["search_entry"].get().strip()
        rows = idiom_data.search(keyword) if keyword else idiom_data.get_all()
        for r in rows:
            w["tree"].insert("", "end", values=(r[0], r[1], r[2], r[3]))
        w["count_lbl"].config(text=f"총 {len(rows)}개 사자성어")

    def _build_hanja_subtab(self, parent, title):
        ctrl = ttk.Frame(parent)
        ctrl.pack(fill=X, pady=(0, 5))
        ttk.Label(ctrl, text="검색:").pack(side=LEFT, padx=(0, 3))
        self.subject_widgets[title]["search_entry"] = ttk.Entry(ctrl, width=28)
        self.subject_widgets[title]["search_entry"].pack(side=LEFT, padx=(0, 5))
        self.subject_widgets[title]["search_entry"].bind("<Return>", lambda e: self._refresh_subtab_hanja())
        ttk.Button(ctrl, text="🔎 검색", command=self._refresh_subtab_hanja, bootstyle="info-outline").pack(side=LEFT, padx=(0, 5))
        ttk.Button(ctrl, text="전체보기", command=lambda: (self.subject_widgets[title]["search_entry"].delete(0, "end"), self._refresh_subtab_hanja()), bootstyle="secondary-outline").pack(side=LEFT)
        self.subject_widgets[title]["count_lbl"] = ttk.Label(parent, text="", bootstyle="secondary")
        self.subject_widgets[title]["count_lbl"].pack(anchor="w", pady=(0, 3))
        tree_box = ttk.Frame(parent)
        tree_box.pack(fill=BOTH, expand=YES)
        cols = ("level", "hanja", "sound", "meaning", "radical", "strokes")
        self.subject_widgets[title]["tree"] = ttk.Treeview(tree_box, columns=cols, show="headings", bootstyle="info")
        for col, txt, w in [("level","급수",50),("hanja","한자",60),("sound","음",80),("meaning","뜻",250),("radical","부수",80),("strokes","획수",50)]:
            self.subject_widgets[title]["tree"].heading(col, text=txt)
            self.subject_widgets[title]["tree"].column(col, width=w, anchor="center")
        vsb = ttk.Scrollbar(tree_box, orient=VERTICAL, command=self.subject_widgets[title]["tree"].yview, bootstyle="round-info")
        self.subject_widgets[title]["tree"].configure(yscrollcommand=vsb.set)
        self.subject_widgets[title]["tree"].pack(side=LEFT, fill=BOTH, expand=YES); vsb.pack(side=RIGHT, fill=Y)
        self._refresh_subtab_hanja()

    def _refresh_subtab_hanja(self):
        w = self.subject_widgets.get("한자")
        if not w: return
        for item in w["tree"].get_children(): w["tree"].delete(item)
        keyword = w["search_entry"].get().strip()
        rows = hanja_data.search(keyword) if keyword else hanja_data.get_all()
        for r in rows:
            w["tree"].insert("", "end", values=(r[0], r[1], r[2], r[3], r[4], r[5]))
        w["count_lbl"].config(text=f"총 {len(rows)}개 한자")


    def _build_science_subtab(self, parent, title):
        ctrl = ttk.Frame(parent)
        ctrl.pack(fill=X, pady=(0, 5))
        ttk.Label(ctrl, text="검색:").pack(side=LEFT, padx=(0, 3))
        self.subject_widgets[title]["search_entry"] = ttk.Entry(ctrl, width=28)
        self.subject_widgets[title]["search_entry"].pack(side=LEFT, padx=(0, 5))
        self.subject_widgets[title]["search_entry"].bind("<Return>", lambda t=title: self._refresh_subtab_science(t))
        ttk.Button(ctrl, text="🔎 검색", command=lambda t=title: self._refresh_subtab_science(t), bootstyle="info-outline").pack(side=LEFT, padx=(0, 5))
        ttk.Button(ctrl, text="전체보기", command=lambda t=title: (self.subject_widgets[t]["search_entry"].delete(0, "end"), self._refresh_subtab_science(t)), bootstyle="secondary-outline").pack(side=LEFT)
        self.subject_widgets[title]["count_lbl"] = ttk.Label(parent, text="", bootstyle="secondary")
        self.subject_widgets[title]["count_lbl"].pack(anchor="w", pady=(0, 3))
        tree_box = ttk.Frame(parent)
        tree_box.pack(fill=BOTH, expand=YES)
        cols = ("category", "topic", "content")
        self.subject_widgets[title]["tree"] = ttk.Treeview(tree_box, columns=cols, show="headings", bootstyle="success")
        for col, txt, w in [("category","분야",100),("topic","주제",200),("content","내용",500)]:
            self.subject_widgets[title]["tree"].heading(col, text=txt)
            self.subject_widgets[title]["tree"].column(col, width=w, anchor="center" if col == "category" else "w")
        vsb = ttk.Scrollbar(tree_box, orient=VERTICAL, command=self.subject_widgets[title]["tree"].yview, bootstyle="round-success")
        self.subject_widgets[title]["tree"].configure(yscrollcommand=vsb.set)
        self.subject_widgets[title]["tree"].pack(side=LEFT, fill=BOTH, expand=YES); vsb.pack(side=RIGHT, fill=Y)
        self._refresh_subtab_science(title)

    def _refresh_subtab_science(self, title):
        w = self.subject_widgets.get(title)
        if not w: return
        for item in w["tree"].get_children(): w["tree"].delete(item)
        keyword = w["search_entry"].get().strip()
        rows = science_data.get_by_category(title)
        if keyword:
            rows = [r for r in rows if keyword.lower() in r[1].lower() or keyword.lower() in r[2].lower()]
        for r in rows:
            w["tree"].insert("", "end", values=(r[0], r[1], r[2]))
        w["count_lbl"].config(text=f"총 {len(rows)}개 항목")

    # ── 역사 서브탭 ─────────────────────────────────────────
    def _build_history_subtab(self, parent, title):
        ctrl = ttk.Frame(parent)
        ctrl.pack(fill=X, pady=(0, 5))
        ttk.Label(ctrl, text="시대:").pack(side=LEFT, padx=(0, 3))
        self.subject_widgets[title]["era_var"] = tk.StringVar(value="전체")
        era_combo = ttk.Combobox(ctrl, textvariable=self.subject_widgets[title]["era_var"],
                                 values=["전체"] + history_data.get_eras(), width=12, state="readonly")
        era_combo.pack(side=LEFT, padx=(0, 10))
        era_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_subtab_history())
        ttk.Label(ctrl, text="검색:").pack(side=LEFT, padx=(0, 3))
        self.subject_widgets[title]["search_entry"] = ttk.Entry(ctrl, width=24)
        self.subject_widgets[title]["search_entry"].pack(side=LEFT, padx=(0, 5))
        self.subject_widgets[title]["search_entry"].bind("<Return>", lambda e: self._refresh_subtab_history())
        ttk.Button(ctrl, text="🔎", command=self._refresh_subtab_history, bootstyle="info-outline", width=3).pack(side=LEFT)

        self.subject_widgets[title]["count_lbl"] = ttk.Label(parent, text="", bootstyle="secondary")
        self.subject_widgets[title]["count_lbl"].pack(anchor="w", pady=(0, 3))

        tree_box = ttk.Frame(parent)
        tree_box.pack(fill=BOTH, expand=YES)
        cols = ("era", "year", "event", "desc")
        self.subject_widgets[title]["tree"] = ttk.Treeview(tree_box, columns=cols, show="headings", bootstyle="warning")
        for col, txt, w in [("era","시대",80),("year","연도",100),("event","사건",200),("desc","설명",400)]:
            self.subject_widgets[title]["tree"].heading(col, text=txt)
            self.subject_widgets[title]["tree"].column(col, width=w, anchor="center" if col != "desc" else "w")
        vsb = ttk.Scrollbar(tree_box, orient=VERTICAL, command=self.subject_widgets[title]["tree"].yview, bootstyle="round-warning")
        self.subject_widgets[title]["tree"].configure(yscrollcommand=vsb.set)
        self.subject_widgets[title]["tree"].pack(side=LEFT, fill=BOTH, expand=YES); vsb.pack(side=RIGHT, fill=Y)
        self._refresh_subtab_history()

    def _refresh_subtab_history(self):
        w = self.subject_widgets.get("역사")
        if not w: return
        for item in w["tree"].get_children(): w["tree"].delete(item)
        keyword = w["search_entry"].get().strip()
        era = w["era_var"].get()
        rows = history_data.search(keyword) if keyword else history_data.get_all()
        if era != "전체":
            rows = [r for r in rows if r[0] == era]
        for r in rows:
            w["tree"].insert("", "end", values=(r[0], r[1], r[2], r[3]))
        w["count_lbl"].config(text=f"총 {len(rows)}개 사건")



    # --- 과목별 메모 (기본학습 탭) ---
    def _subject_cat_id(self, title):
        return self.db.get_category_id(title)

    def _subject_refresh_note(self, title):
        cat_id = self._subject_cat_id(title)
        widgets = self.subject_widgets.get(title)
        if widgets is None:
            return
        for item in widgets["list"].get_children():
            widgets["list"].delete(item)
        if cat_id is None:
            return
        for n in self.db.get_study_notes(cat_id):
            summary = n["title"] or n["content"][:40]
            widgets["list"].insert("", "end", iid=str(n["id"]), values=(n["updated_at"], summary))

    def _subject_save_note(self, title):
        cat_id = self._subject_cat_id(title)
        widgets = self.subject_widgets.get(title)
        if cat_id is None or widgets is None:
            messagebox.showwarning("과목 없음", f"'{title}' 과목이 없습니다.")
            return
        content = widgets["txt"].get("1.0", "end-1c").strip()
        if not content:
            messagebox.showwarning("알림", "메모 내용을 입력하세요.")
            return
        self.db.add_study_note(cat_id, title, content)
        self._subject_refresh_note(title)
        widgets["txt"].delete("1.0", "end")
        widgets["txt"].insert("1.0", f"[{title}] 자료를 여기에 정리하세요.")
        ToastNotification("메모 저장", f"'{title}' 메모 저장 완료", bootstyle="success").show_toast()

    def _subject_load_note(self, title):
        cat_id = self._subject_cat_id(title)
        widgets = self.subject_widgets.get(title)
        if cat_id is None or widgets is None:
            return
        sel = widgets["list"].selection()
        if not sel:
            return
        note_id = int(sel[0])
        for n in self.db.get_study_notes(cat_id):
            if n["id"] == note_id:
                widgets["txt"].delete("1.0", "end")
                widgets["txt"].insert("1.0", n["content"] or "")
                return

    def _subject_delete_note(self, title):
        cat_id = self._subject_cat_id(title)
        widgets = self.subject_widgets.get(title)
        if cat_id is None or widgets is None:
            return
        sel = widgets["list"].selection()
        if not sel:
            return
        if not messagebox.askyesno("메모 삭제", "선택한 메모를 삭제하시겠습니까?"):
            return
        for item in sel:
            self.db.delete_study_note(int(item))
        self._subject_refresh_note(title)
        widgets["txt"].delete("1.0", "end")
        widgets["txt"].insert("1.0", f"[{title}] 자료를 여기에 정리하세요.")

    # --- 과목 관리 ---
    def add_study_category(self):
        name = self.entry_new_cat.get().strip()
        if not name or name == "새 과목":
            messagebox.showwarning("알림", "과목명을 입력하세요.")
            return
        if self.db.add_category(name):
            self.refresh_study_categories()
            ToastNotification("과목 추가", f"'{name}' 과목이 추가되었습니다.", bootstyle="success").show_toast()
        else:
            messagebox.showerror("오류", "같은 이름의 과목이 이미 존재합니다.")

    def delete_study_category(self):
        name = self.combo_cat.get()
        cat_id = self._current_cat_id()
        if not name or cat_id is None:
            return
        if messagebox.askyesno("과목 삭제", f"'{name}' 과목과 해당 노트/단어/진도를 삭제하시겠습니까?"):
            self.db.delete_category(cat_id)
            self.refresh_study_categories()

    def refresh_study_categories(self):
        self.study_cats = self.db.get_categories()
        names = [c["name"] for c in self.study_cats]
        self.combo_cat.config(values=names)
        if names:
            self.combo_cat.set(names[0])
        self.on_study_cat_change()

    # --- 노트 ---
    def refresh_study_notes(self):
        cat_id = self._current_cat_id()
        for item in self.tree_notes.get_children():
            self.tree_notes.delete(item)
        if cat_id is None:
            return
        for n in self.db.get_study_notes(cat_id):
            self.tree_notes.insert("", "end", iid=str(n["id"]), values=(n["title"], n["updated_at"]))

    def new_study_note(self):
        self.entry_note_title.delete(0, "end"); self.entry_note_title.insert(0, "")
        self.txt_note.delete("1.0", "end")
        self.entry_note_title.focus_set()

    def select_study_note(self):
        sel = self.tree_notes.selection()
        if not sel:
            return
        note_id = int(sel[0])
        cat_id = self._current_cat_id()
        for n in self.db.get_study_notes(cat_id):
            if n["id"] == note_id:
                self.entry_note_title.delete(0, "end"); self.entry_note_title.insert(0, n["title"])
                self.txt_note.delete("1.0", "end"); self.txt_note.insert("1.0", n["content"])
                break

    def save_study_note(self):
        cat_id = self._current_cat_id()
        if cat_id is None:
            messagebox.showwarning("알림", "과목을 먼저 선택하세요.")
            return
        title = self.entry_note_title.get().strip()
        content = self.txt_note.get("1.0", "end-1c")
        if not title:
            messagebox.showwarning("알림", "노트 제목을 입력하세요.")
            return
        sel = self.tree_notes.selection()
        if sel:
            self.db.update_study_note(int(sel[0]), title, content)
        else:
            self.db.add_study_note(cat_id, title, content)
        self.refresh_study_notes()
        ToastNotification("노트 저장", f"'{title}' 저장 완료", bootstyle="success").show_toast()

    def delete_study_note_ui(self):
        sel = self.tree_notes.selection()
        if not sel:
            return
        if messagebox.askyesno("노트 삭제", "선택한 노트를 삭제하시겠습니까?"):
            self.db.delete_study_note(int(sel[0]))
            self.refresh_study_notes()
            self.new_study_note()

    # --- 단어 / 용어 ---
    def refresh_study_words(self):
        cat_id = self._current_cat_id()
        for item in self.tree_words.get_children():
            self.tree_words.delete(item)
        if cat_id is None:
            return
        for w in self.db.get_study_words(cat_id):
            self.tree_words.insert("", "end", iid=str(w["id"]), values=(w["term"], w["definition"]))

    def add_study_word_ui(self):
        cat_id = self._current_cat_id()
        if cat_id is None:
            messagebox.showwarning("알림", "과목을 먼저 선택하세요.")
            return
        term = self.entry_word_term.get().strip()
        definition = self.entry_word_def.get().strip()
        if not term:
            messagebox.showwarning("알림", "용어/단어를 입력하세요.")
            return
        self.db.add_study_word(cat_id, term, definition)
        self.entry_word_term.delete(0, "end"); self.entry_word_term.insert(0, "")
        self.entry_word_def.delete(0, "end"); self.entry_word_def.insert(0, "")
        self.refresh_study_words()

    def delete_study_word_ui(self):
        sel = self.tree_words.selection()
        if not sel:
            return
        for item in sel:
            self.db.delete_study_word(int(item))
        self.refresh_study_words()

    def refresh_study_progress(self):
        for item in self.tree_progress.get_children():
            self.tree_progress.delete(item)
        date_str = self.entry_prog_date.get().strip()
        if not date_str:
            return
        for p in self.db.get_study_progress(date_str):
            done_txt = "✅" if p["done"] else "⬜"
            self.tree_progress.insert("", "end", iid=str(p["id"]),
                                      values=(done_txt, p["cat_name"] or "?", p["task"]))
        self.refresh_study_rate(date_str)

    def refresh_study_rate(self, date_str=None):
        """진도율 위젯 갱신 (2026-09-20 Day5 P1-3).

        date_str이 없으면 진도 탭 입력값 → 비어 있으면 오늘 날짜를 사용한다.
        표시 형식: '오늘 진도: 2/3 (67%) · 수학 1/1 · 영어 1/2'
        DB 집계(get_study_progress_summary/by_category)와 같은 값을 보여준다.
        """
        try:
            if not date_str and hasattr(self, "entry_prog_date"):
                date_str = self.entry_prog_date.get().strip()
            if not date_str:
                date_str = datetime.now().strftime("%Y-%m-%d")
            total = self.db.get_study_progress_summary(date_str)
            if total["total"] == 0:
                self.study_rate_var.set(f"{date_str} 진도: 기록 없음")
                return
            parts = [f"{r['cat_name']} {r['done']}/{r['total']}"
                     for r in self.db.get_study_progress_by_category(date_str)]
            detail = (" · " + " · ".join(parts)) if parts else ""
            self.study_rate_var.set(
                f"{date_str} 진도: {total['done']}/{total['total']} ({total['rate']}%){detail}")
        except (AttributeError, sqlite3.Error, ValueError, TypeError, tk.TclError):
            pass  # 위젯은 보조 표시 — 실패해도 진도 기록을 막지 않는다

    def add_study_progress_ui(self):
        cat_id = self._current_cat_id()
        if cat_id is None:
            messagebox.showwarning("알림", "과목을 먼저 선택하세요.")
            return
        date_str = self.entry_prog_date.get().strip()
        task = self.entry_prog_task.get().strip()
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("오류", "날짜 형식은 YYYY-MM-DD 입니다.")
            return
        if not task or task == "예) 문법 2과 복습":
            messagebox.showwarning("알림", "진도 내용을 입력하세요.")
            return
        self.db.add_study_progress(date_str, cat_id, task)
        self.entry_prog_task.delete(0, "end"); self.entry_prog_task.insert(0, "")
        self.refresh_study_progress()
        self.refresh_study_rate(date_str)

    def toggle_study_progress_ui(self):
        sel = self.tree_progress.selection()
        if not sel:
            return
        self.db.toggle_study_progress(int(sel[0]))
        self.refresh_study_progress()
        self.refresh_study_rate()

    def delete_study_progress_ui(self):
        sel = self.tree_progress.selection()
        if not sel:
            return
        for item in sel:
            self.db.delete_study_progress(int(item))
        self.refresh_study_progress()
        self.refresh_study_rate()

    # 뷰: 뉴스 & 정보
    # -------------------------------------------------------------
    def setup_news_view(self):
        header = ttk.Frame(self.content_area)
        header.pack(fill=X, pady=(0, 10))

        ttk.Label(header, text="📰 뉴스 & 정보", font=("Malgun Gothic", 16, "bold")).pack(side=LEFT, padx=10)

        filter_box = ttk.Frame(header)
        filter_box.pack(side=RIGHT)
        ttk.Label(filter_box, text="검색:").pack(side=LEFT)
        self.news_search_entry = ttk.Entry(filter_box, width=16)
        self.news_search_entry.pack(side=LEFT, padx=2)
        self.news_search_entry.bind("<Return>", lambda e: self._load_news_threaded())
        ttk.Button(filter_box, text="검색", command=self._load_news_threaded, bootstyle="secondary").pack(side=LEFT, padx=2)
        ttk.Button(filter_box, text="초기화", command=self.reset_news_search, bootstyle="secondary-outline").pack(side=LEFT, padx=2)
        ttk.Label(filter_box, text="카테고리:").pack(side=LEFT, padx=(10, 0))
        self.news_cat_combo = ttk.Combobox(filter_box, values=["전체"] + get_categories(), state="readonly", width=10)
        self.news_cat_combo.set("전체")
        self.news_cat_combo.pack(side=LEFT, padx=5)
        self.news_cat_combo.bind("<<ComboboxSelected>>", lambda e: self._load_news_threaded())
        self.news_refresh_btn = ttk.Button(filter_box, text="🔄 새로고침", command=self._load_news_threaded, bootstyle="primary-outline")
        self.news_refresh_btn.pack(side=LEFT, padx=5)
        self.news_status = ttk.Label(header, text="준비 중...", font=("Malgun Gothic", 9))
        self.news_status.pack(side=RIGHT, padx=(0, 10))

        # --- 상단: 실시간 수집 뉴스 (선택 후 저장) ---
        live_frame = ttk.Labelframe(self.content_area, text=" 📥 실시간 수집 뉴스 (선택 후 ⭐저장 / 더블클릭 브라우저 열기) ",
                                    padding=8, bootstyle="info")
        live_frame.pack(fill=BOTH, expand=YES, pady=(0, 10))

        live_btn = ttk.Frame(live_frame)
        live_btn.pack(fill=X, pady=(0, 5))
        ttk.Button(live_btn, text="⭐ 선택 저장", command=self.save_selected_news, bootstyle="success", width=14).pack(side=LEFT, padx=(0, 5))
        ttk.Button(live_btn, text="🔗 링크 열기", command=self._open_selected_live, bootstyle="info-outline", width=14).pack(side=LEFT)
        ttk.Button(live_btn, text="🔑 키워드 분석", command=self.show_news_keywords, bootstyle="warning-outline", width=14).pack(side=LEFT, padx=(5, 0))
        self.live_count_label = ttk.Label(live_btn, text="", bootstyle="secondary")
        self.live_count_label.pack(side=RIGHT)

        self.tree_news_live = ttk.Treeview(live_frame, columns=("mark", "src", "date", "title"), show="headings", height=9)
        self.tree_news_live.heading("mark", text="★"); self.tree_news_live.column("mark", width=40, anchor="center")
        self.tree_news_live.heading("src", text="출처"); self.tree_news_live.column("src", width=150, anchor="w")
        self.tree_news_live.heading("date", text="날짜"); self.tree_news_live.column("date", width=140, anchor="center")
        self.tree_news_live.heading("title", text="제목"); self.tree_news_live.column("title", width=620, anchor="w")
        self.tree_news_live.pack(fill=BOTH, expand=YES)
        self.tree_news_live.bind("<Double-1>", lambda e: self._open_selected_live())

        # --- 하단: 저장한 뉴스 (선택 후 삭제) ---
        self._saved_news = []  # 저장 기사 목록 캐시

        saved_frame = ttk.Labelframe(self.content_area, text=" ⭐ 저장한 뉴스 (선택 후 🗑삭제 / 더블클릭 브라우저 열기) ",
                                     padding=8, bootstyle="success")
        saved_frame.pack(fill=BOTH, expand=YES)

        saved_btn = ttk.Frame(saved_frame)
        saved_btn.pack(fill=X, pady=(0, 5))
        ttk.Button(saved_btn, text="🗑 선택 삭제", command=self.delete_selected_saved_news, bootstyle="danger", width=14).pack(side=LEFT, padx=(0, 5))
        ttk.Button(saved_btn, text="🔗 링크 열기", command=self._open_selected_saved, bootstyle="info-outline", width=14).pack(side=LEFT)
        ttk.Button(saved_btn, text="✅ 읽음", command=self._mark_selected_news_read, bootstyle="success-outline", width=9).pack(side=LEFT, padx=(6, 0))
        ttk.Button(saved_btn, text="↩ 읽음 초기화", command=self._reset_selected_news_read, bootstyle="secondary-outline", width=13).pack(side=LEFT, padx=(6, 0))
        self.saved_news_search = ttk.Entry(saved_btn, width=18)
        self.saved_news_search.pack(side=RIGHT, padx=(5, 0))
        self.saved_news_search.insert(0, "저장 뉴스 검색")
        self.saved_news_search.bind("<Return>", lambda e: self.refresh_saved_news())
        ttk.Button(saved_btn, text="검색", command=self.refresh_saved_news, bootstyle="secondary-outline").pack(side=RIGHT)
        self.saved_count_label = ttk.Label(saved_btn, text="", bootstyle="secondary")
        self.saved_count_label.pack(side=RIGHT, padx=(0, 10))

        self.tree_news_saved = ttk.Treeview(saved_frame, columns=("read", "saved_at", "src", "category", "title"), show="headings", height=7)
        self.tree_news_saved.heading("read", text="읽음"); self.tree_news_saved.column("read", width=50, anchor="center")
        self.tree_news_saved.heading("saved_at", text="저장일시"); self.tree_news_saved.column("saved_at", width=140, anchor="center")
        self.tree_news_saved.heading("src", text="출처"); self.tree_news_saved.column("src", width=150, anchor="w")
        self.tree_news_saved.heading("category", text="분류"); self.tree_news_saved.column("category", width=70, anchor="center")
        self.tree_news_saved.heading("title", text="제목"); self.tree_news_saved.column("title", width=560, anchor="w")
        self.tree_news_saved.tag_configure("read", foreground="#6c757d")
        self.tree_news_saved.pack(fill=BOTH, expand=YES)
        self.tree_news_saved.bind("<Double-1>", lambda e: self._open_selected_saved())

                # 초기 로드
        self.refresh_saved_news()

        # 저장된 스레드 결과가 있으면 재렌더링 (탭 전환 후 결과 복구)
        if hasattr(self, "_pending_news_results") and self._pending_news_results:
            cat, kw, results = self._pending_news_results
            self.after(100, lambda: self._render_news(cat, kw, results))

        # 최초 또는 검색어 변경 시 뉴스 수집 스레드 시작
        self._load_news_threaded()

    def _load_news_threaded(self):
        """뉴스 수집은 스레드에서 수행 -> UI 블로킹 방지"""
        category = self.news_cat_combo.get() if hasattr(self, "news_cat_combo") else "전체"
        # 검색어가 있으면 검색 모드로 우선
        keyword = self.news_search_entry.get().strip() if hasattr(self, "news_search_entry") else ""
        if keyword and keyword == "초기화":
            keyword = ""
        self.news_refresh_btn.config(state=DISABLED)
        self.news_status.config(text="뉴스를 가져오는 중...")
        threading.Thread(target=self._fetch_and_render_news, args=(category, keyword), daemon=True).start()

    def reset_news_search(self):
        if hasattr(self, "news_search_entry"):
            self.news_search_entry.delete(0, "end")
        if hasattr(self, "news_cat_combo") and hasattr(self, "news_cat_combo"):
            self.news_cat_combo.set("전체")
        self._load_news_threaded()

    def _fetch_and_render_news(self, category, keyword=""):
        if keyword:
            sources = build_search_sources(keyword)
        else:
            sources = get_sources_by_category(category)
        try:
            results = fetch_sources(sources, max_items=10)
        except Exception as e:  # noqa: BLE001 - UI 스레드 경계: 예상 외 오류도 폴백으로 (의도적 광범위)
            results = handle_error(e, context="뉴스 수집", fallback={})
        self.after(0, self._render_news, category, keyword, results)

    def _open_link(self, url):
        try:
            webbrowser.open(url)
        except (webbrowser.Error, OSError) as e:
            messagebox.showerror("오류", f"브라우저를 열 수 없습니다:\n{e}")

    def show_news_keywords(self):
        """현재 수집된 뉴스에서 트렌딩 키워드 + 출처별 요약 팝업 (재구축 2026-09-12)."""
        results = getattr(self, "_pending_news_results", None)
        if not results or not results[2]:
            messagebox.showinfo("키워드 분석", "먼저 뉴스를 가져오세요 (🔄 새로고침).")
            return
        report = news_summarizer.format_report(results[2], top_n=15)

        win = tk.Toplevel(self)
        win.title("🔑 뉴스 키워드 분석")
        win.geometry("560x420")
        win.transient(self)
        try:
            win.grab_set()
        except tk.TclError:
            pass

        txt = tk.Text(win, wrap="char", font=("Malgun Gothic", 11), padx=12, pady=10)
        txt.pack(fill=BOTH, expand=YES, side=TOP)
        txt.insert("1.0", report)
        txt.config(state="disabled")
        ttk.Button(win, text="닫기", command=win.destroy, bootstyle="secondary").pack(pady=6)

    def _render_news(self, category, keyword, results):
        # 위젯 파괴 전 결과 저장 (재렌더링 대비)
        self._pending_news_results = (category, keyword, results)

        # [1] 가드: 현재 위젯이 활성 상태일 때만 즉시 렌더링
        if not hasattr(self, "news_refresh_btn") or not self.news_refresh_btn.winfo_exists():
            return
        if not hasattr(self, "tree_news_live") or not self.tree_news_live.winfo_exists():
            return
        mode_txt = f"검색: {keyword}" if keyword else f"[{category}]"
        self.news_status.config(text=f"마지막 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ({mode_txt})")

        for item in self.tree_news_live.get_children():
            self.tree_news_live.delete(item)

        self._live_news = []  # [{source, category, pubDate, title, description, link, saved}]
        total = 0
        for name, res in results.items():
            if "error" in res:
                continue
            cat = get_source_category(name) if not name.startswith("검색:") else "검색"
            for it in res["items"]:
                total += 1
                self._live_news.append({
                    "source": name,
                    "category": cat,
                    "pubDate": it["pubDate"],
                    "title": it["title"],
                    "description": it["description"],
                    "link": it["link"],
                    "saved": self.db.is_news_saved(it["link"]),
                })
        for idx, n in enumerate(self._live_news):
            mark = "★" if n["saved"] else ""
            self.tree_news_live.insert("", "end", iid=str(idx),
                values=(mark, n["source"], n["pubDate"], n["title"]))

        self.live_count_label.config(text=f"수집 {total}건")

    def _get_selected_live_news(self):
        """선택된 행의 기사 dict 목록 반환"""
        out = []
        for iid in self.tree_news_live.selection():
            idx = int(iid)
            if 0 <= idx < len(self._live_news):
                out.append(self._live_news[idx])
        return out

    def save_selected_news(self):
        items = self._get_selected_live_news()
        if not items:
            messagebox.showwarning("알림", "저장할 기사를 위 목록에서 선택하세요.")
            return
        added = 0
        for it in items:
            if self.db.add_saved_news(
                    title=it["title"], link=it["link"], description=it["description"],
                    pub_date=it["pubDate"], source=it["source"],
                    category=it.get("category") or "일반"):
                added += 1
                it["saved"] = True
                # 수집 목록의 저장 표시 갱신
                for iid in self.tree_news_live.get_children():
                    if int(iid) == self._live_news.index(it):
                        self.tree_news_live.set(iid, "mark", "★")
                        break
        self.refresh_saved_news()
        if added:
            ToastNotification("뉴스 저장", f"{added}건 저장 완료", bootstyle="success").show_toast()
        else:
            messagebox.showinfo("알림", "이미 저장된 기사입니다.")

    def delete_selected_saved_news(self):
        sel = self.tree_news_saved.selection()
        if not sel:
            messagebox.showwarning("알림", "삭제할 기사를 아래 목록에서 선택하세요.")
            return
        if not messagebox.askyesno("뉴스 삭제", f"선택한 기사 {len(sel)}건을 삭제하시겠습니까?"):
            return
        for iid in sel:
            self.db.delete_saved_news(int(iid))
        self.refresh_saved_news()
        # 수집 목록의 저장 표시 갱신
        if hasattr(self, "_live_news"):
            for n in self._live_news:
                if not self.db.is_news_saved(n["link"]):
                    if self._live_news.index(n) in [int(r) for r in self.tree_news_live.get_children()]:
                        self.tree_news_live.set(str(self._live_news.index(n)), "mark", "")
        ToastNotification("뉴스 삭제", "삭제 완료", bootstyle="info").show_toast()

    def refresh_saved_news(self):
        keyword = self.saved_news_search.get().strip()
        if keyword == "저장 뉴스 검색":
            keyword = ""
        self._saved_news = self.db.get_saved_news(keyword=keyword or None)
        for item in self.tree_news_saved.get_children():
            self.tree_news_saved.delete(item)
        for n in self._saved_news:
            read_txt = "✅" if n.get("read_flag") else ""
            self.tree_news_saved.insert("", "end", iid=str(n["id"]),
                values=(read_txt, n["saved_at"], n["source"], n["category"], n["title"]),
                tags=("read",) if n.get("read_flag") else ())
        unread = sum(1 for n in self._saved_news if not n.get("read_flag"))
        self.saved_count_label.config(text=f"저장 {len(self._saved_news)}건 (안읽음 {unread})")

    def _open_selected_live(self):
        for it in self._get_selected_live_news():
            self._open_link(it["link"])

    def _open_selected_saved(self):
        for iid in self.tree_news_saved.selection():
            for n in self._saved_news:
                if str(n["id"]) == iid:
                    self._open_link(n["link"])
                    self._set_news_read_state(iid, n, True)
                    break

    # --- 뉴스 읽음 표시 (2026-09-13 — DB: mark_news_read / reset_news_read) ---
    def _set_news_read_state(self, iid, n, read):
        """항목 1건의 읽음 상태를 DB와 화면에 동시 반영"""
        if read and not n.get("read_flag"):
            self.db.mark_news_read(n["id"])
        elif not read and n.get("read_flag"):
            self.db.reset_news_read(n["id"])
        n["read_flag"] = 1 if read else 0
        self.tree_news_saved.set(str(iid), "read", "✅" if read else "")
        self.tree_news_saved.item(str(iid), tags=("read",) if read else ())
        unread = sum(1 for x in self._saved_news if not x.get("read_flag"))
        if hasattr(self, "saved_count_label"):
            self.saved_count_label.config(text=f"저장 {len(self._saved_news)}건 (안읽음 {unread})")

    def _mark_selected_news_read(self):
        sel = self.tree_news_saved.selection()
        if not sel:
            messagebox.showwarning("알림", "읽음 표시할 기사를 목록에서 선택하세요.")
            return
        for iid in sel:
            for n in self._saved_news:
                if str(n["id"]) == iid:
                    self._set_news_read_state(iid, n, True)
                    break
        ToastNotification("읽음 표시", f"{len(sel)}건 읽음 처리", bootstyle="success").show_toast()

    def _reset_selected_news_read(self):
        sel = self.tree_news_saved.selection()
        if not sel:
            messagebox.showwarning("알림", "초기화할 기사를 목록에서 선택하세요.")
            return
        for iid in sel:
            for n in self._saved_news:
                if str(n["id"]) == iid:
                    self._set_news_read_state(iid, n, False)
                    break
        ToastNotification("읽음 초기화", f"{len(sel)}건 초기화", bootstyle="secondary").show_toast()

    # 뷰 5: 설정 (Settings)
    # -------------------------------------------------------------
    def setup_settings_view(self):
        main_canvas = tk.Canvas(self.content_area)
        scrollbar = ttk.Scrollbar(self.content_area, orient="vertical", command=main_canvas.yview)
        scroll_frame = ttk.Frame(main_canvas)
        scroll_frame.bind(
            "<Configure>",
            lambda e: main_canvas.configure(scrollregion=main_canvas.bbox("all"))
        )
        main_canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        main_canvas.configure(yscrollcommand=scrollbar.set)

        main_canvas.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)

        ttk.Label(scroll_frame, text="⚙️ 설정 (Settings)", font=("Malgun Gothic", 18, "bold")).pack(pady=(0, 20), anchor="w")

        # 1. 테마 설정
        theme_frame = ttk.Labelframe(scroll_frame, text=" 테마 변경 ", padding=15)
        theme_frame.pack(fill=X, pady=(0, 15))
        ttk.Label(theme_frame, text="스타일 선택: ").pack(side=LEFT)
        self.combo_theme = ttk.Combobox(theme_frame, values=self.style.theme_names(), state="readonly", width=15)
        self.combo_theme.set(self.style.theme.name)
        self.combo_theme.pack(side=LEFT, padx=10)
        ttk.Button(theme_frame, text="적용", command=self.change_theme, bootstyle="secondary").pack(side=LEFT)

        # 1-2. API 키 관리
        api_frame = ttk.Labelframe(scroll_frame, text=" 🔑 금융원 OpenAPI 인증키 관리 ", padding=15)
        api_frame.pack(fill=X, pady=(0, 15))

        api_keys_frame = ttk.Frame(api_frame)
        api_keys_frame.pack(fill=X)

        api_fields = [
            ("fss_stock", "주식시세정보"),
            ("fss_product", "일반상품시세정보"),
            ("fss_index", "지수시세정보"),
            ("fss_company", "금융회사기본정보"),
        ]
        self.api_key_entries = {}
        for key_id, label in api_fields:
            row = ttk.Frame(api_keys_frame)
            row.pack(fill=X, pady=2)
            ttk.Label(row, text=f"{label}:", width=18).pack(side=LEFT)
            entry = ttk.Entry(row, width=50, show="*")
            entry.pack(side=LEFT, padx=5)
            entry.insert(0, self.api_keys.get(key_id, ""))
            self.api_key_entries[key_id] = entry

        btn_row = ttk.Frame(api_frame)
        btn_row.pack(fill=X, pady=(10, 0))
        ttk.Button(btn_row, text="💾 API 키 저장", command=self._save_api_keys, bootstyle="success").pack(side=LEFT)
        ttk.Button(btn_row, text="🔄 새로고침", command=self._refresh_api_keys, bootstyle="info-outline").pack(side=LEFT, padx=5)
        ttk.Label(btn_row, text="* 키는 config.json에 안전하게 저장됩니다", font=("Malgun Gothic", 8), foreground="gray").pack(side=RIGHT)

        # 1-3. 데이터 백업 / 복원 (2026-09-13)
        bak_frame = ttk.Labelframe(scroll_frame, text=" 💾 데이터 백업 / 복원 ", padding=15)
        bak_frame.pack(fill=X, pady=(0, 15))
        ttk.Label(bak_frame, text="scheduler.db + config.json → backup/ 폴더에 타임스탬프 파일명으로 저장합니다.",
                  font=("Malgun Gothic", 9)).pack(anchor="w")
        bak_btn = ttk.Frame(bak_frame)
        bak_btn.pack(fill=X, pady=(6, 0))
        ttk.Button(bak_btn, text="💾 지금 백업", command=self._backup_data, bootstyle="success").pack(side=LEFT, padx=(0, 8))
        ttk.Button(bak_btn, text="↩ 백업 파일에서 복원", command=self._restore_data, bootstyle="warning-outline").pack(side=LEFT)
        # 마지막 백업 상태 표시 (2026-09-20 P0-1): 백업이 없으면 경고를 상시 노출한다.
        self.bak_last_lbl = ttk.Label(bak_frame, text=self._backup_label_text(), bootstyle="secondary")
        self.bak_last_lbl.pack(anchor="w", pady=(8, 0))

        # 2. 기념일 관리
        ann_frame = ttk.Labelframe(scroll_frame, text=" 기념일 관리 ", padding=15)
        ann_frame.pack(fill=X, pady=(0, 15))

        btn_box = ttk.Frame(ann_frame)
        btn_box.pack(fill=X, pady=(0, 10))
        ttk.Button(btn_box, text="엑셀로 내보내기", command=self.export_ann_excel, bootstyle="success-outline").pack(side=RIGHT, padx=5)
        ttk.Button(btn_box, text="엑셀에서 가져오기", command=self.import_ann_excel, bootstyle="info-outline").pack(side=RIGHT, padx=5)

        f_ann = ttk.Frame(ann_frame)
        f_ann.pack(fill=X, pady=(0, 5))
        
        self.entry_ann_name = ttk.Entry(f_ann, width=15); self.entry_ann_name.pack(side=LEFT, padx=5); self.entry_ann_name.insert(0, "이름")
        self.entry_ann_year = ttk.Entry(f_ann, width=6); self.entry_ann_year.pack(side=LEFT, padx=2); self.entry_ann_year.insert(0, str(self.curr_year))
        ttk.Label(f_ann, text="년").pack(side=LEFT)

        self.combo_month = ttk.Combobox(f_ann, values=[str(i) for i in range(1, 13)], width=3); self.combo_month.set("1"); self.combo_month.pack(side=LEFT, padx=2)
        ttk.Label(f_ann, text="월").pack(side=LEFT)
        self.combo_day = ttk.Combobox(f_ann, values=[str(i) for i in range(1, 32)], width=3); self.combo_day.set("1"); self.combo_day.pack(side=LEFT, padx=2)
        ttk.Label(f_ann, text="일").pack(side=LEFT)
        
        self.var_lunar = tk.BooleanVar(); ttk.Checkbutton(f_ann, text="음력", variable=self.var_lunar).pack(side=LEFT, padx=5)
        self.var_holiday = tk.BooleanVar(); ttk.Checkbutton(f_ann, text="공휴일", variable=self.var_holiday).pack(side=LEFT, padx=5)
        self.var_repeat = tk.BooleanVar(value=True); ttk.Checkbutton(f_ann, text="매년반복", variable=self.var_repeat).pack(side=LEFT, padx=5)

        ttk.Button(f_ann, text="추가", command=self.add_anniversary, bootstyle="success").pack(side=LEFT, padx=10)
        ttk.Button(f_ann, text="삭제", command=self.delete_anniversary, bootstyle="danger").pack(side=LEFT)

        cols_ann = ("ID", "이름", "연도", "날짜", "음/양", "공휴일", "반복")
        self.tree_ann = ttk.Treeview(ann_frame, columns=cols_ann, show="headings", height=5)
        self.tree_ann.heading("ID", text="ID"); self.tree_ann.column("ID", width=30)
        self.tree_ann.heading("이름", text="이름"); self.tree_ann.column("이름", width=120)
        self.tree_ann.heading("연도", text="연도"); self.tree_ann.column("연도", width=60)
        self.tree_ann.heading("날짜", text="날짜"); self.tree_ann.column("날짜", width=60)
        self.tree_ann.heading("음/양", text="음/양"); self.tree_ann.column("음/양", width=60)
        self.tree_ann.heading("공휴일", text="공휴일"); self.tree_ann.column("공휴일", width=60)
        self.tree_ann.heading("반복", text="반복"); self.tree_ann.column("반복", width=60)
        self.tree_ann.pack(fill=X)
        self.refresh_ann_list()

        # 3. 목표 및 해야 할 일
        task_frame = ttk.Labelframe(scroll_frame, text=" 목표 및 해야 할 일 (To-Do) ", padding=15)
        task_frame.pack(fill=X, pady=(0, 15))

        f_task = ttk.Frame(task_frame)
        f_task.pack(fill=X, pady=(0, 10))
        self.e_todo = ttk.Entry(f_task, width=15); self.e_todo.pack(side=LEFT, padx=2); self.e_todo.insert(0, "해야할 것")
        self.e_period = ttk.Entry(f_task, width=15); self.e_period.pack(side=LEFT, padx=2); self.e_period.insert(0, "일정")
        self.e_goal = ttk.Entry(f_task, width=15); self.e_goal.pack(side=LEFT, padx=2); self.e_goal.insert(0, "목표")
        self.e_content = ttk.Entry(f_task, width=20); self.e_content.pack(side=LEFT, padx=2); self.e_content.insert(0, "내용")
        self.e_remark = ttk.Entry(f_task, width=15); self.e_remark.pack(side=LEFT, padx=2); self.e_remark.insert(0, "비고")
        ttk.Button(f_task, text="추가", command=self.add_task, bootstyle="info").pack(side=LEFT, padx=10)
        ttk.Button(f_task, text="삭제", command=self.delete_task, bootstyle="danger").pack(side=LEFT)

        cols_task = ("ID", "해야할 것", "일정", "목표", "내용", "비고")
        self.tree_task = ttk.Treeview(task_frame, columns=cols_task, show="headings", height=5)
        for c in cols_task: self.tree_task.heading(c, text=c)
        self.tree_task.pack(fill=X)
        self.refresh_task_list()

        # 4. D-Day 관리
        dday_frame = ttk.Labelframe(scroll_frame, text=" D-Day 관리 ", padding=15)
        dday_frame.pack(fill=X, pady=(0, 15))

        f_dday = ttk.Frame(dday_frame)
        f_dday.pack(fill=X, pady=(0, 10))
        self.e_dday_title = ttk.Entry(f_dday, width=20); self.e_dday_title.pack(side=LEFT, padx=2); self.e_dday_title.insert(0, "목표 이름")
        self.e_dday_date = ttk.Entry(f_dday, width=15); self.e_dday_date.pack(side=LEFT, padx=2); self.e_dday_date.insert(0, "YYYY-MM-DD")
        ttk.Button(f_dday, text="추가", command=self.add_dday, bootstyle="success").pack(side=LEFT, padx=10)
        ttk.Button(f_dday, text="삭제", command=self.delete_dday, bootstyle="danger").pack(side=LEFT)

        cols_dday = ("ID", "목표", "날짜", "D-Day")
        self.tree_dday = ttk.Treeview(dday_frame, columns=cols_dday, show="headings", height=5)
        for c in cols_dday: self.tree_dday.heading(c, text=c)
        self.tree_dday.pack(fill=X)
        self.refresh_dday_list()

    # --- 핸들러 ---
    def change_theme(self):
        self.style.theme_use(self.combo_theme.get())
        try:
            from core.config_manager import set_theme
            set_theme(self.combo_theme.get())
        except (OSError, ValueError, KeyError):
            pass

    def refresh_ann_list(self):
        for item in self.tree_ann.get_children(): self.tree_ann.delete(item)
        for a in self.db.get_anniversaries():
            d_type = "음력" if a["type"] == 1 else "양력"
            is_h = "O" if a["is_holiday"] else "X"
            rep = "매년" if a["is_repeat"] else "X"
            self.tree_ann.insert("", "end", values=(a["id"], a["name"], a["year"], f"{a['month']}.{a['day']}", d_type, is_h, rep))

    def add_anniversary(self):
        if not self.entry_ann_name.get(): return
        self.db.add_anniversary(
            self.entry_ann_name.get(), int(self.entry_ann_year.get()), int(self.combo_month.get()), int(self.combo_day.get()),
            1 if self.var_lunar.get() else 0, 1 if self.var_holiday.get() else 0, 1 if self.var_repeat.get() else 0
        )
        self.refresh_ann_list()

    def delete_anniversary(self):
        for item in self.tree_ann.selection():
            self.db.delete_anniversary(self.tree_ann.item(item, "values")[0])
        self.refresh_ann_list()

    def export_ann_excel(self):
        df = self.db.get_all_anniversaries_df()
        if df is not None:
            path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")])
            if path:
                df.to_excel(path, index=False)
                ToastNotification("내보내기 성공", "기념일 리스트가 저장되었습니다.", bootstyle="success").show_toast()

    def import_ann_excel(self):
        path = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx")])
        if path:
            try:
                df = pd.read_excel(path)
                self.db.import_anniversaries_from_df(df)
                self.refresh_ann_list()
                ToastNotification("가져오기 성공", "기념일 데이터가 추가되었습니다.", bootstyle="success").show_toast()
            except (OSError, ValueError, KeyError, zipfile.BadZipFile) as e:
                messagebox.showerror("오류", f"파일을 읽는 중 오류가 발생했습니다.\n{e}")

    def refresh_task_list(self):
        for item in self.tree_task.get_children(): self.tree_task.delete(item)
        for t in self.db.get_tasks():
            self.tree_task.insert("", "end", values=(t["id"], t["item"], t["period"], t["goal"], t["content"], t["remark"]))

    def add_task(self):
        self.db.add_task(self.e_todo.get(), self.e_period.get(), self.e_goal.get(), self.e_content.get(), self.e_remark.get())
        self.refresh_task_list()

    def delete_task(self):
        for item in self.tree_task.selection():
            self.db.delete_task(self.tree_task.item(item, "values")[0])
        self.refresh_task_list()

    # D-Day 핸들러
    def refresh_dday_list(self):
        for item in self.tree_dday.get_children(): self.tree_dday.delete(item)
        ddays = self.db.get_ddays()
        today = date.today()
        for d in ddays:
            try:
                target = datetime.strptime(d["date"], "%Y-%m-%d").date()
                diff = (target - today).days
                if diff > 0: txt = f"D-{diff}"
                elif diff < 0: txt = f"D+{abs(diff)}"
                else: txt = "D-Day"
            except (ValueError, KeyError): txt = "날짜오류"
            self.tree_dday.insert("", "end", values=(d["id"], d["title"], d["date"], txt))

    def add_dday(self):
        try:
            datetime.strptime(self.e_dday_date.get(), "%Y-%m-%d")
            self.db.add_dday(self.e_dday_title.get(), self.e_dday_date.get())
            self.refresh_dday_list()
        except ValueError:
            messagebox.showerror("오류", "날짜 형식이 올바르지 않습니다 (YYYY-MM-DD).")

    def delete_dday(self):
        for item in self.tree_dday.selection():
            self.db.delete_dday(self.tree_dday.item(item, "values")[0])
        self.refresh_dday_list()

    # API 키 관리 핸들러
    def _save_api_keys(self):
        """API 키를 config.json에 저장"""
        if not hasattr(self, "api_key_entries"):
            return
        try:
            from core.config_manager import save_config, load_config
            cfg = load_config()
            if "api_keys" not in cfg:
                cfg["api_keys"] = {}
            for key_id, entry in self.api_key_entries.items():
                cfg["api_keys"][key_id] = entry.get().strip()
            save_config(cfg)
            self.api_keys = cfg["api_keys"]
            self.api_key = cfg["api_keys"].get("fss_stock", "")
            messagebox.showinfo("저장 완료", "API 키가 config.json에 저장되었습니다.\n증권 탭에서 즉시 적용됩니다.")
        except (OSError, ValueError, KeyError) as e:
            messagebox.showerror("오류", f"API 키 저장 중 오류가 발생했습니다:\n{e}")

    def _refresh_api_keys(self):
        """config.json에서 API 키 새로고침"""
        try:
            from core.config_manager import load_config
            cfg = load_config()
            api_keys = cfg.get("api_keys", {})
            self.api_keys = api_keys
            self.api_key = api_keys.get("fss_stock", "")
            if hasattr(self, "api_key_entries"):
                for key_id, entry in self.api_key_entries.items():
                    entry.delete(0, "end")
                    entry.insert(0, api_keys.get(key_id, ""))
            messagebox.showinfo("새로고침 완료", "API 키를 다시 불러왔습니다.")
        except (OSError, ValueError, KeyError) as e:
            messagebox.showerror("오류", f"API 키 로드 중 오류가 발생했습니다:\n{e}")

    # --- 데이터 백업 / 복원 (2026-09-13) ---
    def _backup_data(self):
        """scheduler.db + config.json → backup/ 폴더에 타임스탬프 사본 저장"""
        import shutil
        bak_dir = Path("backup")
        try:
            bak_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            messagebox.showerror("백업 실패", f"backup/ 폴더 생성 실패:\n{e}")
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        saved = []
        for src in ("scheduler.db", "config.json"):
            if os.path.exists(src):
                dst = bak_dir / f"{Path(src).stem}_{ts}{Path(src).suffix}"
                try:
                    shutil.copy2(src, dst)
                    saved.append(dst.name)
                except (shutil.Error, OSError) as e:
                    messagebox.showerror("백업 실패", f"{src} 복사 중 오류:\n{e}")
                    return
        if saved:
            if hasattr(self, "bak_last_lbl"):
                self.bak_last_lbl.config(text=self._backup_label_text())
            messagebox.showinfo("백업 완료", "backup/ 폴더에 저장했습니다:\n" + "\n".join(saved))
        else:
            messagebox.showwarning("백업 실패", "백업할 파일(scheduler.db, config.json)을 찾지 못했습니다.")

    # --- 시작 시 자동 백업 (2026-09-20 P0-1 / R-1) ---
    BACKUP_KEEP = 7   # 보관 개수

    def _auto_backup_on_start(self):
        """앱 시작 시 오늘 날짜 백업이 없으면 생성한다(일 1회). 실패해도 앱은 계속 뜬다."""
        try:
            saved = self._run_backup(daily=True)
            if saved:
                log.info("[백업] 시작 자동 백업 완료: %s", ", ".join(saved))
        except Exception as e:  # noqa: BLE001 - 백업 실패가 앱 기동을 막지 않게 한다
            log.warning("[백업] 시작 자동 백업 중 오류: %s", e)

    def _run_backup(self, daily=True):
        """scheduler.db + config.json을 backup/에 복사한다.

        daily=True면 오늘 날짜 백업이 이미 있으면 복사를 건너뛴다(일 1회).
        반환: 확보된 백업 파일명 목록(실패 시 빈 목록, 원인은 로그로 남긴다).
        """
        import shutil
        try:
            bak_dir = Path("backup")
            bak_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d")
            saved = []
            for src in ("scheduler.db", "config.json"):
                if not os.path.exists(src):
                    continue
                dst = bak_dir / f"{Path(src).stem}_{stamp}{Path(src).suffix}"
                if daily and dst.exists():
                    saved.append(dst.name)
                    continue
                shutil.copy2(src, dst)
                saved.append(dst.name)
            if saved:
                self._rotate_backups(bak_dir)
            return saved
        except (OSError, shutil.Error) as e:
            log.warning("[백업] 자동 백업 실패: %s", e)
            return []

    def _rotate_backups(self, bak_dir: Path, keep: int = BACKUP_KEEP):
        """타임스탬프 백업 사본을 최근 keep개만 남긴다(baseline 등 다른 이름은 보존)."""
        import re
        for prefix, suffix in (("scheduler_", ".db"), ("config_", ".json")):
            pattern = re.compile(rf"^{prefix}\d{{8}}(?:_\d{{6}})?{re.escape(suffix)}$")
            try:
                files = sorted(
                    (p for p in bak_dir.iterdir() if pattern.match(p.name)),
                    key=lambda p: p.stat().st_mtime, reverse=True)
            except OSError as e:
                log.warning("[백업] 회전 목록 조회 실패: %s", e)
                continue
            for old in files[keep:]:
                try:
                    old.unlink()
                except OSError as e:
                    log.warning("[백업] 오래된 백업 삭제 실패: %s", e)

    def _last_backup_info(self):
        """backup/에서 가장 최근 scheduler_*.db의 (이름, 수정시각)을 반환. 없으면 None."""
        bak_dir = Path("backup")
        if not bak_dir.is_dir():
            return None
        try:
            cands = sorted(bak_dir.glob("scheduler_*.db"),
                           key=lambda p: p.stat().st_mtime, reverse=True)
            if not cands:
                return None
            newest = cands[0]
            return newest.name, datetime.fromtimestamp(newest.stat().st_mtime)
        except (OSError, ValueError):
            return None

    def _backup_label_text(self):
        info = self._last_backup_info()
        if not info:
            return "⚠️ 백업 기록이 없습니다 — '💾 지금 백업'을 눌러 데이터를 보호하세요."
        return f"마지막 백업: {info[1]:%Y-%m-%d %H:%M}  ({info[0]})"

    def _restore_data(self):
        """backup/ 폴더의 백업 파일을 선택해 scheduler.db 또는 config.json 복원"""
        path = filedialog.askopenfilename(
            title="복원할 백업 파일 선택",
            initialdir="backup" if os.path.isdir("backup") else ".",
            filetypes=[("백업 파일", "*.db;*.json"), ("모든 파일", "*.*")],
        )
        if not path:
            return
        p = Path(path)
        target = "scheduler.db" if p.suffix.lower() == ".db" else "config.json" if p.suffix.lower() == ".json" else None
        if not target:
            messagebox.showwarning("복원 실패", ".db 또는 .json 백업 파일을 선택하세요.")
            return
        if not messagebox.askyesno("복원 확인", f"'{p.name}' 파일로 {target}을(를) 덮어씁니다.\n현재 데이터가 백업 시점으로 되돌아갑니다. 계속할까요?"):
            return
        import shutil
        try:
            if target == "scheduler.db":
                try:
                    self.db.conn.close()  # 덮어쓰기 오류 방지
                except sqlite3.Error:
                    pass
            shutil.copy2(p, target)
        except (shutil.Error, OSError) as e:
            messagebox.showerror("복원 실패", f"복원 중 오류가 발생했습니다:\n{e}")
            return
        if target == "scheduler.db":
            self.db = DBManager()
        messagebox.showinfo("복원 완료", f"{target} 복원이 완료되었습니다.\n각 탭을 다시 열면 최신 데이터로 갱신됩니다.")

if __name__ == "__main__":
    app = SchedulerApp()
    app.mainloop()