# -*- coding: utf-8 -*-
"""다국어 지원 모듈 (재구축: 2026-09-12)

다른 PC 이력의 `core/i18n.py`를 기능적으로 동등하게 새로 작성.
- 지원 언어: ko(한국어) / en(English) / ja(日本語)
- t(key, lang) 헬퍼로 UI 문자열 조회. 없는 키는 key 그대로 반환.
"""
from __future__ import annotations

SUPPORTED_LANGUAGES = ("ko", "en", "ja")
LANG_NAMES = {"ko": "한국어", "en": "English", "ja": "日本語"}
DEFAULT_LANGUAGE = "ko"

# key: {lang: 문자열}
STRINGS: dict[str, dict[str, str]] = {
    "app_title": {"ko": "나의 스케줄러", "en": "My Scheduler", "ja": "マイ・スケジューラ"},
    "menu_dashboard": {"ko": "대시보드", "en": "Dashboard", "ja": "ダッシュボード"},
    "menu_daily": {"ko": "일간", "en": "Daily", "ja": "日別"},
    "menu_weekly": {"ko": "주간", "en": "Weekly", "ja": "週別"},
    "menu_monthly": {"ko": "월간", "en": "Monthly", "ja": "月別"},
    "menu_news": {"ko": "뉴스 & 정보", "en": "News & Info", "ja": "ニュース＆情報"},
    "menu_market": {"ko": "증권", "en": "Market", "ja": "証券"},
    "menu_study": {"ko": "공부", "en": "Study", "ja": "学習"},
    "menu_wordbook": {"ko": "단어장", "en": "Wordbook", "ja": "単語帳"},
    "menu_phrases": {"ko": "생활용어", "en": "Phrases", "ja": "生活用語"},
    "menu_settings": {"ko": "설정", "en": "Settings", "ja": "設定"},
    "btn_save": {"ko": "저장", "en": "Save", "ja": "保存"},
    "btn_cancel": {"ko": "취소", "en": "Cancel", "ja": "キャンセル"},
    "btn_delete": {"ko": "삭제", "en": "Delete", "ja": "削除"},
    "btn_search": {"ko": "검색", "en": "Search", "ja": "検索"},
    "btn_refresh": {"ko": "새로고침", "en": "Refresh", "ja": "更新"},
    "btn_add": {"ko": "추가", "en": "Add", "ja": "追加"},
    "btn_open_link": {"ko": "링크 열기", "en": "Open Link", "ja": "リンクを開く"},
    "lbl_today": {"ko": "오늘", "en": "Today", "ja": "今日"},
    "lbl_schedule": {"ko": "일정", "en": "Schedule", "ja": "予定"},
    "lbl_content": {"ko": "내용", "en": "Content", "ja": "内容"},
    "lbl_category": {"ko": "분류", "en": "Category", "ja": "分類"},
    "lbl_date": {"ko": "날짜", "en": "Date", "ja": "日付"},
    "lbl_title": {"ko": "제목", "en": "Title", "ja": "タイトル"},
    "lbl_word": {"ko": "단어/숙어", "en": "Word/Idiom", "ja": "単語/熟語"},
    "lbl_meaning": {"ko": "뜻", "en": "Meaning", "ja": "意味"},
    "lbl_sentence": {"ko": "문장", "en": "Sentence", "ja": "文"},
    "lbl_progress": {"ko": "진도", "en": "Progress", "ja": "進度"},
    "lbl_source": {"ko": "출처", "en": "Source", "ja": "出所"},
    "lbl_symbol": {"ko": "심볼", "en": "Symbol", "ja": "銘柄コード"},
    "lbl_price": {"ko": "가격", "en": "Price", "ja": "価格"},
    "lbl_change": {"ko": "변화", "en": "Change", "ja": "変化"},
    "news_loading": {"ko": "뉴스를 가져오는 중…", "en": "Fetching news…", "ja": "ニュース取得中…"},
    "news_none": {"ko": "가져온 뉴스가 없습니다.", "en": "No news fetched.", "ja": "ニュースがありません"},
    "news_saved": {"ko": "저장한 뉴스", "en": "Saved News", "ja": "保存したニュース"},
    "study_none": {"ko": "등록된 학습 기록이 없습니다.", "en": "No study records.", "ja": "学習記録がありません"},
    "market_search_hint": {"ko": "종목 검색", "en": "Stock search", "ja": "銘柄検索"},
    "msg_confirm_delete": {"ko": "삭제할까요?", "en": "Delete?", "ja": "削除しますか？"},
    "msg_saved_ok": {"ko": "저장되었습니다.", "en": "Saved.", "ja": "保存しました。"},
    "msg_select_first": {"ko": "먼저 선택하세요.", "en": "Select first.", "ja": "先に選択してください。"},
    # 시작 리마인더 (2026-09-13)
    "reminder_title": {"ko": "📌 오늘의 요약", "en": "📌 Today's Summary", "ja": "📌 今日のサマリー"},
    "reminder_schedule": {"ko": "📝 오늘 일정", "en": "📝 Today's Schedule", "ja": "📝 今日の予定"},
    "reminder_dday": {"ko": "⏰ D-Day (30일 이내)", "en": "⏰ D-Day (within 30 days)", "ja": "⏰ D-Day（30日以内）"},
    "reminder_review": {"ko": "🔁 오늘 복습할 단어", "en": "🔁 Words to review today", "ja": "🔁 今日の復習単語"},
    "reminder_ledger": {"ko": "💰 이번 달 가계부", "en": "💰 This Month's Ledger", "ja": "💰 今月の家計簿"},
    "reminder_toggle": {"ko": "앱 시작 시 이 요약을 표시", "en": "Show this summary at startup", "ja": "起動時にこのサマリーを表示"},
    "reminder_no_schedule": {"ko": "등록된 일정이 없습니다.", "en": "No schedules.", "ja": "登録された予定はありません"},
    "reminder_no_dday": {"ko": "다가오는 D-Day가 없습니다.", "en": "No upcoming D-Days.", "ja": "迫るD-Dayはありません"},
}


def get_languages() -> tuple[str, ...]:
    """지원 언어 코드 튜플."""
    return SUPPORTED_LANGUAGES


def get_language_names() -> dict[str, str]:
    """코드 → 언어명."""
    return dict(LANG_NAMES)


def t(key: str, lang: str = DEFAULT_LANGUAGE) -> str:
    """UI 문자열 조회. 키나 언어가 없으면 한국어 → key 순으로 반환."""
    row = STRINGS.get(key)
    if not row:
        return key
    return row.get(lang) or row.get(DEFAULT_LANGUAGE) or key
