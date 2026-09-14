# -*- coding: utf-8 -*-
"""SQLite 데이터?곕쿋?댁뒪 愿由?紐⑤뱢 (2026-09-04 踰꾩쟾 ?듯빀 ??core ?⑦궎吏濡?異붿텧)

10yp_2.py??DBManager瑜?洹몃?濡??닿?. 理쒖떊 목록留?
- schedules(date PK, schedule, journal)
- anniversaries(id, name, year, month, day, type, is_holiday, is_repeat)
- tasks(id, item, period, goal, content, remark)
- ddays(id, title, target_date)
"""
import sqlite3
from datetime import datetime

import pandas as pd
import json

from core.logger import get_logger

log = get_logger(__name__)


class DBManager:
    def __init__(self, db_name="scheduler.db"):
        self.conn = sqlite3.connect(db_name)
        self.create_tables()
        self.ensure_schedule_tables()
        self.check_default_anniversaries()
        self.check_default_categories()
        self.init_default_words()
        self.init_default_phrases()

    def create_tables(self):
        cursor = self.conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS schedules (
                date TEXT PRIMARY KEY,
                schedule TEXT,
                journal TEXT,
                schedule_images TEXT DEFAULT '[]'
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS anniversaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                year INTEGER DEFAULT 0,
                month INTEGER,
                day INTEGER,
                type INTEGER,
                is_holiday INTEGER,
                is_repeat INTEGER DEFAULT 1
            )
                ''')

        # ?? 利앷텒 ????μ슜 ?뚯씠釉?(Market tab ??μ슜) ?????????????????????
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS saved_markets (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                rank          INTEGER,
                symbol        TEXT,
                name          TEXT,
                price         REAL,
                change_amount REAL,
                category      TEXT,
                source_api    TEXT,
                saved_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ddays (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                target_date TEXT
            )
        ''')

        # --- 怨듬? ??(2026-09-04 異붽?) ---
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS study_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cat_id INTEGER,
                title TEXT,
                content TEXT,
                updated_at TEXT,
                FOREIGN KEY(cat_id) REFERENCES categories(id) ON DELETE CASCADE
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS study_words (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cat_id INTEGER,
                term TEXT,
                definition TEXT,
                FOREIGN KEY(cat_id) REFERENCES categories(id) ON DELETE CASCADE
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS study_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                cat_id INTEGER,
                task TEXT,
                note TEXT,
                done INTEGER DEFAULT 0
            )
        ''')

        # --- 목록??DB (2026-09-05 異붽?) ---
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS wordbook (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                language TEXT,
                rank INTEGER,
                word TEXT,
                pron_en TEXT,
                pron_ko TEXT,
                pos TEXT,
                meaning TEXT,
                example TEXT,
                example_ko TEXT,
                UNIQUE(language, word, pos)
            )
        ''')

        # --- 생활용어?⑹뼱 DB (2026-09-06 異붽?) ---
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS phrases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                language TEXT,
                rank INTEGER,
                sentence TEXT,
                pron_ko TEXT,
                meaning_ko TEXT,
                UNIQUE(language, sentence)
            )
        ''')

        # --- ??ν븳 ?댁뒪 DB (2026-09-06 異붽?) ---
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS saved_news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                link TEXT UNIQUE,
                description TEXT,
                pub_date TEXT,
                source TEXT,
                category TEXT,
                saved_at TEXT
            )
        ''')

        # --- 利먭꺼李얘린 紐낆뼵/怨좎궗?깆뼱/?쒖옄 DB (2026-09-12 異붽?) ---
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS favorite_quotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id TEXT UNIQUE NOT NULL,
                text TEXT NOT NULL,
                meaning TEXT,
                source TEXT,
                kind TEXT,
                added_at TEXT NOT NULL
            )
        ''')

        # --- 媛怨꾨? DB (2026-09-12 異붽?) ---
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                type TEXT NOT NULL,
                category TEXT NOT NULL,
                amount INTEGER NOT NULL,
                memo TEXT,
                saved_at TEXT
            )
        ''')

        # --- 怨쇳븰/IT/?ы쉶?먭뎄 硫붾え DB (2026-09-12 異붽?) ---
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS study_subject_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT NOT NULL,
                keyword TEXT,
                content TEXT,
                updated_at TEXT,
                UNIQUE(subject, keyword)
            )
        ''')

        # --- 투자 일기 DB (2026-09-13 추가) ---
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS investment_journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                type TEXT NOT NULL,
                symbol TEXT,
                name TEXT,
                quantity INTEGER DEFAULT 0,
                price REAL DEFAULT 0,
                commission REAL DEFAULT 0,
                memo TEXT,
                saved_at TEXT
            )
        ''')

        self.conn.commit()

    def check_default_categories(self):
        """怨듬? 怨쇰ぉ 湲곕낯媛?(단어장, 카테고리, 湲고?) ?먮룞 ?앹꽦"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT count(*) FROM categories")
        if cursor.fetchone()[0] == 0:
            cursor.executemany(
                "INSERT INTO categories (name) VALUES (?)",
                [("단어장",), ("카테고리",), ("湲고?",)]
            )
            self.conn.commit()

    def check_default_anniversaries(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT count(*) FROM anniversaries")
        if cursor.fetchone()[0] == 0:
            defaults = [
                ("기념일", 0, 1, 1, 0, 1, 1),
                ("3.1운동", 1919, 3, 1, 0, 1, 1),
                ("만일홍보절", 0, 5, 5, 0, 1, 1),
                ("어린이날", 0, 6, 6, 0, 1, 1),
                ("해방", 1945, 8, 15, 0, 1, 1),
                ("개척절", 0, 10, 3, 0, 1, 1),
                ("서방", 0, 10, 9, 0, 1, 1),
                ("크리스마스", 0, 12, 25, 0, 1, 1),
                ("?ㅻ궇", 0, 1, 1, 1, 1, 1),
                ("근화절", 0, 10, 26, 0, 1, 1),
                ("異붿꽍", 0, 8, 15, 1, 1, 1)
            ]
            cursor.executemany("INSERT INTO anniversaries (name, year, month, day, type, is_holiday, is_repeat) VALUES (?,?,?,?,?,?,?)", defaults)
            self.conn.commit()

    def get_anniversaries(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, name, year, month, day, type, is_holiday, is_repeat FROM anniversaries ORDER BY month, day")
        return [
            {"id": r[0], "name": r[1], "year": r[2], "month": r[3], "day": r[4],
             "type": r[5], "is_holiday": bool(r[6]), "is_repeat": bool(r[7])}
            for r in cursor.fetchall()
        ]

    # --- ?쇱젙 ---
    def get_schedule(self, date_str):
        cursor = self.conn.cursor()
        cursor.execute("SELECT schedule, journal FROM schedules WHERE date=?", (str(date_str),))
        row = cursor.fetchone()
        return {"schedule": row[0], "journal": row[1]} if row else {"schedule": "", "journal": ""}

    def get_schedules_by_month(self, year, month):
        date_pattern = f"{year}-{month:02d}-%"
        cursor = self.conn.cursor()
        cursor.execute("SELECT date, schedule FROM schedules WHERE date LIKE ? ORDER BY date", (date_pattern,))
        return cursor.fetchall()

    def set_schedule(self, date_str, schedule, journal):
        cursor = self.conn.cursor()
        # ?댁슜???놁쑝硫??삭제 (?? ?묒? import?쒖뿉??鍮??댁슜?대씪????뼱?곌린 ?꾪빐 濡쒖쭅 議곗젙 媛?ν븯?? ?ш린???좎?)
        if not str(schedule).strip() and not str(journal).strip():
            self.delete_schedule(date_str)
            return
        cursor.execute("""
            INSERT INTO schedules (date, schedule, journal)
            VALUES (?,?,?)
            ON CONFLICT(date) DO UPDATE SET schedule=excluded.schedule, journal=excluded.journal
        """, (str(date_str), str(schedule), str(journal)))
        self.conn.commit()

    def delete_schedule(self, date_str):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM schedules WHERE date=?", (str(date_str),))
        self.conn.commit()

    def ensure_schedule_tables(self):
        """기존 DB 컬럼/테이블 마이그레이션 (스케줄 이미지, 복습, 뉴스 읽음 등)"""
        cursor = self.conn.cursor()
        try:
            cols = [r[1] for r in cursor.execute("PRAGMA table_info(schedules)").fetchall()]
        except sqlite3.Error:
            cols = []
        if "schedule_images" not in cols:
            cursor.execute("ALTER TABLE schedules ADD COLUMN schedule_images TEXT DEFAULT '[]'")
            self.conn.commit()

        # wordbook 복습 컬럼 (스페이스 반복 시스템)
        try:
            wcols = [r[1] for r in cursor.execute("PRAGMA table_info(wordbook)").fetchall()]
        except sqlite3.Error:
            wcols = []
        if "reviewed_at" not in wcols:
            cursor.execute("ALTER TABLE wordbook ADD COLUMN reviewed_at TEXT")
            self.conn.commit()
        if "ease" not in wcols:
            cursor.execute("ALTER TABLE wordbook ADD COLUMN ease INTEGER DEFAULT 0")
            self.conn.commit()

        # phrases 복습 컬럼
        try:
            pcols = [r[1] for r in cursor.execute("PRAGMA table_info(phrases)").fetchall()]
        except sqlite3.Error:
            pcols = []
        if "reviewed_at" not in pcols:
            cursor.execute("ALTER TABLE phrases ADD COLUMN reviewed_at TEXT")
            self.conn.commit()
        if "ease" not in pcols:
            cursor.execute("ALTER TABLE phrases ADD COLUMN ease INTEGER DEFAULT 0")
            self.conn.commit()

        # saved_news 읽음 표시 컬럼
        try:
            ncols = [r[1] for r in cursor.execute("PRAGMA table_info(saved_news)").fetchall()]
        except sqlite3.Error:
            ncols = []
        if "read_flag" not in ncols:
            cursor.execute("ALTER TABLE saved_news ADD COLUMN read_flag INTEGER DEFAULT 0")
            self.conn.commit()

        # investment_journal 테이블 (구버전 DB 대비)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS investment_journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                type TEXT NOT NULL,
                symbol TEXT,
                name TEXT,
                quantity INTEGER DEFAULT 0,
                price REAL DEFAULT 0,
                commission REAL DEFAULT 0,
                memo TEXT,
                saved_at TEXT
            )
        ''')
        self.conn.commit()

    def get_schedule_images(self, date_str):
        """?쇨컙 ?쇱???泥⑤???洹몃┝?뚯씪 ?곷?寃쎈줈 紐⑸줉??諛섑솚?쒕떎."""
        row = self.conn.execute("SELECT schedule_images FROM schedules WHERE date=?", (str(date_str),)).fetchone()
        if not row or not row[0]:
            return []
        try:
            data = json.loads(row[0])
            if isinstance(data, list):
                return data
        except (ValueError, TypeError):
            pass
        return []

    def set_schedule_images(self, date_str, images):
        """해당 날짜 일정에 그림 목록 저장 (레코드가 없으면 새로 생성)"""
        cursor = self.conn.cursor()
        payload = json.dumps(images, ensure_ascii=False)
        cursor.execute(
            "INSERT OR REPLACE INTO schedules (date, schedule, journal, schedule_images) "
            "VALUES (?, "
            "COALESCE((SELECT schedule FROM schedules WHERE date=?), ''), "
            "COALESCE((SELECT journal FROM schedules WHERE date=?), ''), ?)",
            (str(date_str), str(date_str), str(date_str), payload)
        )
        self.conn.commit()

    def save_diary_image(self, date_str, src_path):
        """洹몃┝?뚯씪??data/images ?꾨옒???좎쭨蹂꾨줈 蹂듭궗?섍퀬 ?곷?寃쎈줈瑜?諛섑솚?쒕떎."""
        import shutil
        from pathlib import Path
        images_dir = Path("data/images").resolve()
        images_dir.mkdir(parents=True, exist_ok=True)
        src = Path(src_path)
        if not src.exists():
            return None
        safe_date = str(date_str).replace(":", "-").replace("/", "-")
        name = src.stem or "img"
        dest_name = f"{safe_date}_{name}{src.suffix}"
        dest = images_dir / dest_name
        counter = 1
        while dest.exists():
            dest_name = f"{safe_date}_{name}_{counter}{src.suffix}"
            dest = images_dir / dest_name
            counter += 1
        shutil.copy2(src, dest)
        return f"data/images/{dest.name}"

    def set_schedule(self, date_str, schedule, journal, images=None):
        cursor = self.conn.cursor()
        images_json = "[]"
        if images:
            try:
                images_json = json.dumps(images, ensure_ascii=False)
            except (ValueError, TypeError):
                images_json = "[]"
        cursor.execute(
            "INSERT OR REPLACE INTO schedules (date, schedule, journal, schedule_images) VALUES (?,?,?,?)",
            (str(date_str), str(schedule) if schedule is not None else "", str(journal) if journal is not None else "", images_json)
        )
        self.conn.commit()

    def get_schedule(self, date_str):
        row = self.conn.execute(
            "SELECT schedule, journal, schedule_images FROM schedules WHERE date=?",
            (str(date_str),)
        ).fetchone()
        if not row:
            return {"schedule": "", "journal": "", "images": []}
        schedule, journal, images_raw = row
        try:
            images = json.loads(images_raw) if images_raw else []
            if not isinstance(images, list):
                images = []
        except (ValueError, TypeError):
            images = []
        return {"schedule": schedule or "", "journal": journal or "", "images": images}

    def get_all_schedules_df(self):
        try:
            query = "SELECT date, schedule, journal FROM schedules ORDER BY date"
            df = pd.read_sql_query(query, self.conn)
            df.columns = ["날짜", "일정", "저널"]
            return df
        except sqlite3.Error: return None

    def get_all_schedules_with_images_df(self):
        """항목吏 ?뺣낫瑜??ы븿???꾩껜 ?쇱젙 DataFrame 諛섑솚 (?묒? ?대낫?닿린??"""
        try:
            query = "SELECT date, schedule, journal, schedule_images FROM schedules ORDER BY date"
            df = pd.read_sql_query(query, self.conn)
            df.columns = ["?좎쭨", "?쇱젙", "鍮꾧퀬", "항목吏"]
            # 항목吏 JSON???쎄린 ?ъ슫 臾몄옄?대줈 蹂??
            def format_images(img_json):
                try:
                    imgs = json.loads(img_json) if img_json else []
                    if isinstance(imgs, list) and imgs:
                        return "; ".join(str(p) for p in imgs)
                    return ""
                except (ValueError, TypeError):
                    return ""
            df["항목吏"] = df["항목吏"].apply(format_images)
            return df
        except sqlite3.Error: return None

    # [異붽?] 문화먯꽌 ?쎌? ?쇱젙 DataFrame??DB??諛섏쁺
    def import_schedules_from_df(self, df):
        # df 而щ읆: "?좎쭨", "?쇱젙", "鍮꾧퀬"
        # NaN 媛믪쓣 鍮?臾몄옄?대줈 蹂??
        df = df.fillna("")
        for _, row in df.iterrows():
            try:
                # ?묒? ?좎쭨 ?뺤떇??datetime??寃쎌슦 臾몄옄?대줈 蹂??
                d_val = row['?좎쭨']
                if isinstance(d_val, datetime):
                    d_val = d_val.strftime("%Y-%m-%d")

                self.set_schedule(str(d_val), str(row['?쇱젙']), str(row['鍮꾧퀬']))
            except (KeyError, ValueError, TypeError, sqlite3.Error) as e:
                log.warning("Import Error on row %s: %s", _, e)
        self.conn.commit()

    def add_anniversary(self, name, year, month, day, type_val, is_holiday_val, is_repeat_val):
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO anniversaries (name, year, month, day, type, is_holiday, is_repeat) VALUES (?,?,?,?,?,?,?)",
                       (name, year, month, day, type_val, is_holiday_val, is_repeat_val))
        self.conn.commit()

    def delete_anniversary(self, ann_id):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM anniversaries WHERE id=?", (ann_id,))
        self.conn.commit()

    def get_all_anniversaries_df(self):
        try:
            query = "SELECT name, year, month, day, type, is_holiday, is_repeat FROM anniversaries"
            df = pd.read_sql_query(query, self.conn)
            return df
        except sqlite3.Error: return None

    def import_anniversaries_from_df(self, df):
        cursor = self.conn.cursor()
        for _, row in df.iterrows():
            try:
                cursor.execute("INSERT INTO anniversaries (name, year, month, day, type, is_holiday, is_repeat) VALUES (?,?,?,?,?,?,?)",
                            (row['name'], row['year'], row['month'], row['day'], row['type'], row['is_holiday'], row['is_repeat']))
            except (KeyError, TypeError, ValueError, sqlite3.Error): pass
        self.conn.commit()

    # --- Tasks ---
    def get_tasks(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, item, period, goal, content, remark FROM tasks ORDER BY id")
        return [
            {"id": r[0], "item": r[1], "period": r[2], "goal": r[3], "content": r[4], "remark": r[5]}
            for r in cursor.fetchall()
        ]

    def add_task(self, item, period, goal, content, remark):
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO tasks (item, period, goal, content, remark) VALUES (?,?,?,?,?)",
                       (item, period, goal, content, remark))
        self.conn.commit()

    def delete_task(self, task_id):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        self.conn.commit()

    # --- D-Day ---
    def get_ddays(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, title, target_date FROM ddays ORDER BY target_date")
        return [{"id": r[0], "title": r[1], "date": r[2]} for r in cursor.fetchall()]

    def add_dday(self, title, target_date):
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO ddays (title, target_date) VALUES (?,?)", (title, target_date))
        self.conn.commit()

    def delete_dday(self, dday_id):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM ddays WHERE id=?", (dday_id,))
        self.conn.commit()

    # --- 怨듬? ??(2026-09-04) ---
    def get_categories(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, name FROM categories ORDER BY id")
        return [{"id": r[0], "name": r[1]} for r in cursor.fetchall()]

    def get_category_id(self, name):
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM categories WHERE name=?", (name,))
        row = cursor.fetchone()
        return row[0] if row else None

    def add_category(self, name):
        if not name.strip():
            return False
        try:
            cursor = self.conn.cursor()
            cursor.execute("INSERT INTO categories (name) VALUES (?)", (name.strip(),))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def delete_category(self, cat_id):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM categories WHERE id=?", (cat_id,))
        self.conn.commit()

    def get_study_notes(self, cat_id):
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, title, content, updated_at FROM study_notes WHERE cat_id=? ORDER BY updated_at DESC",
            (cat_id,))
        return [
            {"id": r[0], "title": r[1], "content": r[2], "updated_at": r[3]}
            for r in cursor.fetchall()
        ]

    def add_study_note(self, cat_id, title, content):
        from datetime import datetime
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO study_notes (cat_id, title, content, updated_at) VALUES (?,?,?,?)",
            (cat_id, title, content, datetime.now().strftime("%Y-%m-%d %H:%M")))
        self.conn.commit()

    def update_study_note(self, note_id, title, content):
        from datetime import datetime
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE study_notes SET title=?, content=?, updated_at=? WHERE id=?",
            (title, content, datetime.now().strftime("%Y-%m-%d %H:%M"), note_id))
        self.conn.commit()

    def delete_study_note(self, note_id):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM study_notes WHERE id=?", (note_id,))
        self.conn.commit()

    def get_study_words(self, cat_id):
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, term, definition FROM study_words WHERE cat_id=? ORDER BY id",
            (cat_id,))
        return [{"id": r[0], "term": r[1], "definition": r[2]} for r in cursor.fetchall()]

    def add_study_word(self, cat_id, term, definition):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO study_words (cat_id, term, definition) VALUES (?,?,?)",
            (cat_id, term, definition))
        self.conn.commit()

    def delete_study_word(self, word_id):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM study_words WHERE id=?", (word_id,))
        self.conn.commit()

    def get_study_progress(self, date_str):
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT p.id, p.date, p.cat_id, c.name, p.task, p.done
               FROM study_progress p
               LEFT JOIN categories c ON p.cat_id = c.id
               WHERE p.date=? ORDER BY p.id""", (date_str,))
        return [
            {"id": r[0], "date": r[1], "cat_id": r[2], "cat_name": r[3],
             "task": r[4], "done": bool(r[5])}
            for r in cursor.fetchall()
        ]

    def add_study_progress(self, date_str, cat_id, task, done=0):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO study_progress (date, cat_id, task, done) VALUES (?,?,?,?)",
            (date_str, cat_id, task, 1 if done else 0))
        self.conn.commit()

    def toggle_study_progress(self, progress_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT done FROM study_progress WHERE id=?", (progress_id,))
        row = cursor.fetchone()
        if row:
            new_done = 0 if row[0] else 1
            cursor.execute("UPDATE study_progress SET done=? WHERE id=?", (new_done, progress_id))
            self.conn.commit()
            return bool(new_done)
        return False

    def delete_study_progress(self, progress_id):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM study_progress WHERE id=?", (progress_id,))
        self.conn.commit()

    # --- 목록??DB (2026-09-05) ---
    def init_default_words(self):
        """?몄뼱蹂?湲곕낯 목록媛 ?놁쑝硫?word_data.py?먯꽌 ?먮룞 ?쎌엯 (단어장 300 쨌 ?쇰낯??以묎뎅??媛?20)"""
        try:
            from core.word_data import LANG_WORDS
        except ImportError:
            return
        cursor = self.conn.cursor()
        for lang, words in LANG_WORDS.items():
            cursor.execute("SELECT COUNT(*) FROM wordbook WHERE language=?", (lang,))
            if cursor.fetchone()[0] > 0:
                continue
            cursor.executemany(
                "INSERT OR IGNORE INTO wordbook (language, rank, word, pron_en, pron_ko, pos, meaning, example, example_ko) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(lang,) + w for w in words])
        self.conn.commit()

    def get_word_languages(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT DISTINCT language FROM wordbook ORDER BY language")
        return [r[0] for r in cursor.fetchall()]

    def get_words(self, language=None, keyword=None):
        cursor = self.conn.cursor()
        sql = ("SELECT id, language, rank, word, pron_en, pron_ko, pos, meaning, example, example_ko "
               "FROM wordbook")
        conds, params = [], []
        if language:
            conds.append("language=?")
            params.append(language)
        if keyword:
            kw = f"%{keyword}%"
            conds.append("(word LIKE ? OR meaning LIKE ? OR pron_ko LIKE ?)")
            params += [kw, kw, kw]
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY rank, word"
        cursor.execute(sql, params)
        return [
            {"id": r[0], "language": r[1], "rank": r[2], "word": r[3], "pron_en": r[4],
             "pron_ko": r[5], "pos": r[6], "meaning": r[7], "example": r[8], "example_ko": r[9]}
            for r in cursor.fetchall()
        ]

    def add_word(self, language, rank, word, pron_en, pron_ko, pos, meaning, example, example_ko):
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT INTO wordbook (language, rank, word, pron_en, pron_ko, pos, meaning, example, example_ko) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (language, rank, word, pron_en, pron_ko, pos, meaning, example, example_ko))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def update_word(self, wid, rank, word, pron_en, pron_ko, pos, meaning, example, example_ko):
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE wordbook SET rank=?, word=?, pron_en=?, pron_ko=?, pos=?, meaning=?, example=?, example_ko=? "
            "WHERE id=?",
            (rank, word, pron_en, pron_ko, pos, meaning, example, example_ko, wid))
        self.conn.commit()

    def delete_word(self, wid):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM wordbook WHERE id=?", (wid,))
        self.conn.commit()

    def count_words(self, language=None):
        cursor = self.conn.cursor()
        if language:
            cursor.execute("SELECT COUNT(*) FROM wordbook WHERE language=?", (language,))
        else:
            cursor.execute("SELECT COUNT(*) FROM wordbook")
        return cursor.fetchone()[0]

    # --- 생활용어?⑹뼱 DB (2026-09-06) ---
    def init_default_phrases(self):
        """?몄뼱蹂?湲곕낯 생활용어?⑹뼱媛 ?놁쑝硫?phrase_data.py?먯꽌 ?먮룞 ?쎌엯 (단어장 300 쨌 ?쇰낯??以묎뎅??媛?20)"""
        try:
            from core.phrase_data import LANG_PHRASES
        except ImportError:
            return
        cursor = self.conn.cursor()
        for lang, phrases in LANG_PHRASES.items():
            cursor.execute("SELECT COUNT(*) FROM phrases WHERE language=?", (lang,))
            if cursor.fetchone()[0] > 0:
                continue
            cursor.executemany(
                "INSERT OR IGNORE INTO phrases (language, rank, sentence, pron_ko, meaning_ko) "
                "VALUES (?, ?, ?, ?, ?)",
                [(lang,) + p for p in phrases])
        self.conn.commit()

    def get_phrase_languages(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT DISTINCT language FROM phrases ORDER BY language")
        return [r[0] for r in cursor.fetchall()]

    def get_phrases(self, language=None, keyword=None):
        cursor = self.conn.cursor()
        sql = "SELECT id, language, rank, sentence, pron_ko, meaning_ko FROM phrases"
        conds, params = [], []
        if language:
            conds.append("language=?")
            params.append(language)
        if keyword:
            kw = f"%{keyword}%"
            conds.append("(sentence LIKE ? OR meaning_ko LIKE ? OR pron_ko LIKE ?)")
            params += [kw, kw, kw]
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY rank, sentence"
        cursor.execute(sql, params)
        return [
            {"id": r[0], "language": r[1], "rank": r[2], "sentence": r[3],
             "pron_ko": r[4], "meaning_ko": r[5]}
            for r in cursor.fetchall()
        ]

    def add_phrase(self, language, rank, sentence, pron_ko, meaning_ko):
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT INTO phrases (language, rank, sentence, pron_ko, meaning_ko) "
                "VALUES (?,?,?,?,?)",
                (language, rank, sentence, pron_ko, meaning_ko))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def update_phrase(self, pid, rank, sentence, pron_ko, meaning_ko):
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE phrases SET rank=?, sentence=?, pron_ko=?, meaning_ko=? WHERE id=?",
            (rank, sentence, pron_ko, meaning_ko, pid))
        self.conn.commit()

    def delete_phrase(self, pid):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM phrases WHERE id=?", (pid,))
        self.conn.commit()

    def count_phrases(self, language=None):
        cursor = self.conn.cursor()
        if language:
            cursor.execute("SELECT COUNT(*) FROM phrases WHERE language=?", (language,))
        else:
            cursor.execute("SELECT COUNT(*) FROM phrases")
        return cursor.fetchone()[0]

    # --- ??ν븳 ?댁뒪 DB (2026-09-06) ---
    def add_saved_news(self, title, link, description="", pub_date="", source="", category=""):
        """湲곗궗 ??? 항목 ?조회 留곹겕硫?False 諛섑솚."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT INTO saved_news (title, link, description, pub_date, source, category, saved_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (title, link, description, pub_date, source, category,
                 datetime.now().strftime("%Y-%m-%d %H:%M")))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_saved_news(self, keyword=None):
        cursor = self.conn.cursor()
        sql = ("SELECT id, title, link, description, pub_date, source, category, saved_at, read_flag "
               "FROM saved_news")
        params = []
        if keyword:
            kw = f"%{keyword}%"
            sql += " WHERE (title LIKE ? OR source LIKE ? OR description LIKE ?)"
            params += [kw, kw, kw]
        sql += " ORDER BY read_flag ASC, saved_at DESC, id DESC"
        cursor.execute(sql, params)
        return [
            {"id": r[0], "title": r[1], "link": r[2], "description": r[3],
             "pub_date": r[4], "source": r[5], "category": r[6], "saved_at": r[7],
             "read_flag": r[8]}
            for r in cursor.fetchall()
        ]

    def is_news_saved(self, link):
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM saved_news WHERE link=?", (link,))
        return cursor.fetchone()[0] > 0

    def delete_saved_news(self, news_id):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM saved_news WHERE id=?", (news_id,))
        self.conn.commit()

    def delete_saved_news_by_link(self, link):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM saved_news WHERE link=?", (link,))
        self.conn.commit()

    def count_saved_news(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM saved_news")
        return cursor.fetchone()[0]

    # --- 利먭꺼李얘린 紐낆뼵/怨좎궗?깆뼱/?쒖옄 DB (2026-09-12) ---
    def add_favorite_quote(self, item_id, text, meaning="", source="", kind="", added_at=None):
        """紐낆뼵/怨좎궗?깆뼱/?쒖옄 利먭꺼李얘린 ??? 항목 추가硫?False."""
        from datetime import datetime
        if added_at is None:
            added_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT INTO favorite_quotes (item_id, text, meaning, source, kind, added_at) VALUES (?,?,?,?,?,?)",
                (item_id, text, meaning, source, kind, added_at),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_favorite_quotes(self):
        """利먭꺼李얘린 紐⑸줉 諛섑솚 (理쒓렐 ??μ닚)."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, item_id, text, meaning, source, kind, added_at FROM favorite_quotes ORDER BY added_at DESC"
        )
        return [
            {
                "id": r[0],
                "item_id": r[1],
                "text": r[2],
                "meaning": r[3],
                "source": r[4],
                "kind": r[5],
                "added_at": r[6],
            }
            for r in cursor.fetchall()
        ]

    def is_favorite_quote(self, item_id):
        """item_id 湲곗? 利먭꺼李얘린 ?щ?."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM favorite_quotes WHERE item_id=?", (item_id,))
        return cursor.fetchone()[0] > 0

    def remove_favorite_quote(self, item_id):
        """item_id 湲곗? 利먭꺼李얘린 ?삭제. 議댁옱?섎㈃ True."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM favorite_quotes WHERE item_id=?", (item_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def remove_favorite_quote_by_id(self, fav_id):
        """DB id 湲곗? 利먭꺼李얘린 ?삭제."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM favorite_quotes WHERE id=?", (int(fav_id),))
        self.conn.commit()
        return cursor.rowcount > 0

    def count_favorite_quotes(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM favorite_quotes")
        return cursor.fetchone()[0]

    # --- 利앷텒 ?????(2026-09-06) ---
    def add_saved_stock(self, symbol, name, price):
        """醫낅ぉ ??? 항목 ?조회 ?щ낵?대㈃ False 諛섑솚."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT INTO saved_markets (symbol, name, price, category, source_api) VALUES (?,?,?,?,?)",
                (symbol, name, price, "二쇱떇", "mock"))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_saved_stocks(self):
        """?조회 醫낅ぉ 紐⑸줉 諛섑솚"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, symbol, name, price FROM saved_markets ORDER BY saved_at DESC")
        return [{"id": r[0], "symbol": r[1], "name": r[2], "price": r[3]} for r in cursor.fetchall()]

    def delete_saved_stock(self, stock_id):
        """ID濡????醫낅ぉ ?삭제"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM saved_markets WHERE id=?", (stock_id,))
        self.conn.commit()

    def delete_saved_stock_by_name(self, name):
        """이름으로 저장된 종목 삭제"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM saved_markets WHERE name=?", (name,))
        self.conn.commit()

    def update_saved_stock(self, stock_id, symbol=None, name=None, price=None):
        """저장된 종목 수정 (stock_id 기준)"""
        sets = []
        params = []
        if symbol is not None:
            sets.append("symbol=?")
            params.append(symbol)
        if name is not None:
            sets.append("name=?")
            params.append(name)
        if price is not None:
            sets.append("price=?")
            params.append(price)
        if not sets:
            return False
        params.append(stock_id)
        cursor = self.conn.cursor()
        cursor.execute(f"UPDATE saved_markets SET {', '.join(sets)} WHERE id=?", params)
        self.conn.commit()
        return cursor.rowcount > 0

    # --- 媛怨꾨? (2026-09-12 異붽?) ---
    def add_transaction(self, date, type_, category, amount, memo=""):
        """?섏엯/吏異?湲곕줉 異붽?"""
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO transactions (date, type, category, amount, memo, saved_at) VALUES (?,?,?,?,?,?)",
            (date, type_, category, int(amount), memo, datetime.now().strftime("%Y-%m-%d %H:%M")))
        self.conn.commit()
        return cursor.lastrowid

    def get_transactions(self, month=None):
        """媛怨꾨? 紐⑸줉 諛섑솚 (???꾪꽣 媛??"""
        cursor = self.conn.cursor()
        if month:
            cursor.execute(
                "SELECT id, date, type, category, amount, memo FROM transactions WHERE date LIKE ? ORDER BY date DESC",
                (f"{month}%",))
        else:
            cursor.execute("SELECT id, date, type, category, amount, memo FROM transactions ORDER BY date DESC")
        return [{"id": r[0], "date": r[1], "type": r[2], "category": r[3], "amount": r[4], "memo": r[5]}
                for r in cursor.fetchall()]

    def delete_transaction(self, trans_id):
        """媛怨꾨? ??ぉ ?삭제"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM transactions WHERE id=?", (int(trans_id),))
        self.conn.commit()

    def get_month_summary(self, year, month):
        """?붾퀎 ?섏엯/吏異??쒖?異??붿빟"""
        ym = f"{year}-{month:02d}"
        cursor = self.conn.cursor()
        cursor.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE date LIKE ? AND type='수입'", (f"{ym}%",))
        income = cursor.fetchone()[0]
        cursor.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE date LIKE ? AND type='지출'", (f"{ym}%",))
        expense = cursor.fetchone()[0]
        return {"income": income, "expense": expense, "savings": income - expense}

    def get_category_summary(self, year, month, type_="지출"):
        """?붾퀎 移댄뀒怨좊━蹂?吏묎퀎"""
        ym = f"{year}-{month:02d}"
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT category, SUM(amount) FROM transactions WHERE date LIKE ? AND type=? GROUP BY category ORDER BY SUM(amount) DESC",
            (f"{ym}%", type_))
        return [{"category": r[0], "amount": r[1]} for r in cursor.fetchall()]

    # --- 과목별 데이터 조회 (2026-09-12 추가) ---
    def get_subject_data(self, subject, keyword=None):
        """怨쇰ぉ蹂?데이터??硫붾え 議고쉶"""
        cursor = self.conn.cursor()
        if keyword:
            cursor.execute("SELECT id, subject, keyword, content, updated_at FROM study_subject_data WHERE subject=? AND keyword=?", (subject, keyword))
            r = cursor.fetchone()
            if r:
                return {"id": r[0], "subject": r[1], "keyword": r[2], "content": r[3], "updated_at": r[4]}
            return None
        cursor.execute("SELECT id, subject, keyword, content, updated_at FROM study_subject_data WHERE subject=? ORDER BY keyword", (subject,))
        return [{"id": r[0], "subject": r[1], "keyword": r[2], "content": r[3], "updated_at": r[4]}
                for r in cursor.fetchall()]

    def set_subject_data(self, subject, keyword, content):
        """怨쇰ぉ蹂?데이터??硫붾え ???(UPSERT)"""
        cursor = self.conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        cursor.execute("""
            INSERT INTO study_subject_data (subject, keyword, content, updated_at)
            VALUES (?,?,?,?)
            ON CONFLICT(subject, keyword) DO UPDATE SET content=excluded.content, updated_at=excluded.updated_at
        """, (subject, keyword, content, now))
        self.conn.commit()

    def search_subject_data(self, subject, query):
        """怨쇰ぉ蹂?데이터??寃??"""
        cursor = self.conn.cursor()
        q = f"%{query}%"
        cursor.execute("SELECT id, subject, keyword, content, updated_at FROM study_subject_data WHERE subject=? AND (keyword LIKE ? OR content LIKE ?) ORDER BY keyword", (subject, q, q))
        return [{"id": r[0], "subject": r[1], "keyword": r[2], "content": r[3], "updated_at": r[4]}
                for r in cursor.fetchall()]
# ---------------------------------------------------------------
    # 복습 시스템 (스페이스 반복) — wordbook/phrases
    # ---------------------------------------------------------------
    def get_words_due_for_review(self, limit=20):
        """오늘 복습할 단어 자동 선별 (간격: ease 0→1일, 1→3일, 2→7일, 3→14일, 4→30일)"""
        cursor = self.conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d")
        rows = cursor.execute(
            "SELECT id, language, word, pron_en, pron_ko, pos, meaning, example, example_ko, ease, reviewed_at FROM wordbook "
            "WHERE reviewed_at IS NULL OR DATE(reviewed_at) <= date('now', '-' || CASE ease "
            "WHEN 0 THEN '0' WHEN 1 THEN '1' WHEN 2 THEN '3' WHEN 3 THEN '7' "
            "WHEN 4 THEN '14' WHEN 5 THEN '30' ELSE '60' END || ' days') "
            "ORDER BY reviewed_at IS NULL DESC, id LIMIT ?",
            (limit,)).fetchall()
        return [{"id": r[0], "language": r[1], "word": r[2], "pron_en": r[3], "pron_ko": r[4],
                 "pos": r[5], "meaning": r[6], "example": r[7], "example_ko": r[8],
                 "ease": r[9], "reviewed_at": r[10]} for r in rows]

    def mark_word_reviewed(self, word_id, success=True):
        """복습 결과 반영: success=True면 ease 증가(최대 5), False면 ease=0"""
        cursor = self.conn.cursor()
        if success:
            cursor.execute("UPDATE wordbook SET ease = MIN(ease + 1, 5), reviewed_at=? WHERE id=?",
                           (datetime.now().strftime("%Y-%m-%d %H:%M"), int(word_id)))
        else:
            cursor.execute("UPDATE wordbook SET ease = 0, reviewed_at=? WHERE id=?",
                           (datetime.now().strftime("%Y-%m-%d %H:%M"), int(word_id)))
        self.conn.commit()

    # ---------------------------------------------------------------
    # 투자 일기
    # ---------------------------------------------------------------
    def add_investment(self, date, type_, symbol="", name="", quantity=0, price=0.0, commission=0.0, memo=""):
        cursor = self.conn.cursor()

        def _num(v):
            if v is None:
                return 0.0
            s = str(v).replace(",", "").strip()
            if s == "":
                return 0.0
            try:
                return float(s)
            except (ValueError, TypeError):
                return 0.0

        cursor.execute(
            "INSERT INTO investment_journal (date, type, symbol, name, quantity, price, commission, memo, saved_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (str(date), type_, symbol, name, int(_num(quantity) or 0), _num(price),
             _num(commission), memo, datetime.now().strftime("%Y-%m-%d %H:%M")))
        self.conn.commit()
        return cursor.lastrowid

    def get_investments(self, month=None):
        cursor = self.conn.cursor()
        if month:
            cursor.execute(
                "SELECT id, date, type, symbol, name, quantity, price, commission, memo FROM investment_journal "
                "WHERE date LIKE ? ORDER BY date DESC, id DESC", (f"{month}%",))
        else:
            cursor.execute(
                "SELECT id, date, type, symbol, name, quantity, price, commission, memo FROM investment_journal "
                "ORDER BY date DESC, id DESC")
        return [{"id": r[0], "date": r[1], "type": r[2], "symbol": r[3], "name": r[4],
                 "quantity": r[5], "price": r[6], "commission": r[7], "memo": r[8]}
                for r in cursor.fetchall()]

    def delete_investment(self, inv_id):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM investment_journal WHERE id=?", (int(inv_id),))
        self.conn.commit()

    def get_investment_summary(self, month=None):
        """월별 매수/매도 합계 + 예상 평가손익"""
        items = self.get_investments(month)
        buy_cost = sum(it["price"] * it["quantity"] + it["commission"] for it in items if it["type"] == "매수")
        sell_proceed = sum(it["price"] * it["quantity"] - it["commission"] for it in items if it["type"] == "매도")
        return {"buy_cost": buy_cost, "sell_proceed": sell_proceed,
                "net": sell_proceed - buy_cost, "count": len(items)}

    # ---------------------------------------------------------------
    # 뉴스 읽음 표시
    # ---------------------------------------------------------------
    def mark_news_read(self, news_id):
        cursor = self.conn.cursor()
        cursor.execute("UPDATE saved_news SET read_flag=1 WHERE id=?", (int(news_id),))
        self.conn.commit()

    def reset_news_read(self, news_id=None):
        cursor = self.conn.cursor()
        if news_id is None:
            cursor.execute("UPDATE saved_news SET read_flag=0")
        else:
            cursor.execute("UPDATE saved_news SET read_flag=0 WHERE id=?", (int(news_id),))
        self.conn.commit()
