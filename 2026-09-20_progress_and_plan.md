# My_Scheduler 진행 상황 점검 및 실행 계획 (2026-09-20)

> 작성일: **2026-09-20 (일)** / 대상: `f:\Git_home\My_Scheduler` / 방식: **코드·DB·Git·로그 실측 기반**
> 직전 문서: `2026-09-18_expert_review_and_plan.md` (Day 1~4 체크 갱신 완료 상태)
> 이 문서의 모든 수치는 **명령으로 재현 가능**하다. "추정"은 §11-C에 따로 표시했다.

---

## 0. 이 문서를 다시 쓰는 이유와 검증 방식

### 0-1. 배경

- `Temp/` 폴더 내용이 **전부 삭제**되었다. 09-18 문서가 근거로 삼았던 `Temp/smoke_views.json`, `Temp/ut_now.txt`, `Temp/state_probe.json`, `Temp/diag_final.json`, `Temp/10yp_2_initial.py`(증권 복구 원본)가 **모두 사라졌다.**
- 따라서 09-18 이후의 "완료" 주장은 **재검증 없이는 신뢰할 수 없다** → 오늘 다시 전수 실측했다.
- 결과: **긍정적 진척(Day 1~4)** 과 **치명적 사고 1건(사용자 데이터 소실)** 이 동시에 확인되었다.

### 0-2. 오늘 재생성한 실측 산출물 (모두 `Temp/`, gitignore 대상)

| 산출물 | 측정 내용 |
|---|---|
| `Temp/probe_state.json` | DB 15테이블 행수/스키마/무결성, 소스 손상 스캔, 결함 마커, config, git 상태 |
| `Temp/recent_changes.txt` | 2026-09-19 15:00 이후 변경 파일 + DB/백업 자산 목록 |
| `Temp/domain_probe.txt` | 도메인별 잔여 과제(진도 UI·가계부·뉴스·단어장·예외처리) 실측 |
| `Temp/ann_csv_probe.txt` | 기념일 시드 vs DB 실측, `word_creater/*.csv` 품질 |
| `Temp/ann_history.txt` | 초기 커밋(`5bd7968`) 대비 기념일 시드 비교 |
| `Temp/moji_probe.txt`, `Temp/q_lines.txt` | mojibake 정밀 스캔(오탐 분리) |

### 0-3. 재현 명령

```
python Temp\probe_state.py        -> Temp\probe_state.json
python Temp\recent_trace.py       -> Temp\recent_changes.txt
python Temp\domain_probe.py       -> Temp\domain_probe.txt
python Temp\ann_csv_probe.py      -> Temp\ann_csv_probe.txt
python Temp\ann_history.py        -> Temp\ann_history.txt
python Temp\moji_probe.py         -> Temp\moji_probe.txt
python -m unittest discover -s tests -t . -v
python -c "import glob,py_compile;fs=[f for f in glob.glob('*.py')+glob.glob('core/*.py')+glob.glob('ui/*.py')+glob.glob('tests/*.py') if '__pycache__' not in f];[py_compile.compile(f,doraise=True) for f in fs];print('COMPILE_OK',len(fs))"
```

---

## 1. 오늘의 결론 (Executive Summary)

| # | 결론 | 등급 | 근거 |
|---|---|---|---|
| 1 | **사용자 데이터가 0건이다.** 09-18 실측(schedules 5, transactions 3, study_words 89 …)이 지금은 전부 0. `scheduler.db`가 **2026-09-19 20:08:49에 재생성**된 흔적(mtime) + `config.json`(20:08:44) 동시 변경 + `backup/` 폴더 부재 | 🔴 **P0 사고** | §3 |
| 2 | **설정(⚙️) 탭이 열리지 않는다.** `setup_settings_view → refresh_task_list → get_tasks`가 `sqlite3.OperationalError: no such table: tasks`로 중단. **소스에 `CREATE TABLE tasks` DDL이 아예 없다**(초기 커밋부터 부재, docstring에만 흔적) | 🔴 **P0** | §2-3, §5-D |
| 3 | **회귀 게이트가 빨간불이다.** `unittest` 48건 중 **1 ERROR** → 실패 상태로 09-19에 커밋·푸시됨(커밋 메시지는 "48 OK"로 기록) | 🔴 **P0** | §2-1 |
| 4 | 09-19 저녁 미커밋 변경(`wordbook.item_type`, `init_db`, `add_word_with_item`)은 **앱에서 호출되지 않는 죽은 코드**이며 기존 UNIQUE 제약을 사실상 무력화(중복 단어 허용) | 🟠 **P1** | §2-2, §5-D |
| 5 | `word_creater/`의 1000단어 확장은 **미완**(English 1000만 완성, Japanese 708, Spanish 101, Chinese/French/German 21~22) + 생성물에 **mojibake 27셀**, `ui/daily_editor.py` 중복 import 1줄 | 🟠 **P1** | §2-5, §5-B |
| 6 | 기념일 시드 명칭 5건이 실체와 불일치(`만일홍보절`5/5, `어린이날`6/6, `개척절`10/3, `서방`10/9, `근화절`10/26) — 초기 커밋부터 존재한 **선행 손상** | 🟠 **P1** | §5-D |
| 7 | Day 1~4(엑셀 왕복·증권 P0 복구·스케줄러 정리·스모크 승격)는 **코드에 반영 확인**. Day 5~9(학습·뉴스·가계부·인프라·릴리스)는 **미착수** | 🟢 / ⚪ | §4 |

> **한 줄 요약**: "코드는 전진했지만 **데이터를 잃었고**, **설정 탭이 깨졌고**, **테스트가 빨간불**이다."
> **2026-09-20 결정**: 데이터 복구는 시도하지 않고 **현 DB를 새 베이스라인으로 동결**한 뒤, 스키마 확정 → 안전장치 → 재입력 순서로 새로 진행한다(**§12**).

---

## 2. 실측 스냅샷 (2026-09-20 13:32)

### 2-1. 실행·품질

| 항목 | 실측 | 판정 |
|---|---|---|
| Python | **3.14.7** (`C:\Python314`) | ✅ |
| `py_compile` | **25/25 OK** (`10yp_2.py` + `core/*` + `ui/*` + `tests/*`) | ✅ |
| `unittest` | **Ran 48 tests — FAILED (errors=1)** | 🔴 |
| 실패 테스트 | `tests.test_ui_smoke.TestUISmoke.test_all_views_switch_without_exception` | 🔴 |
| 실패 경로 | `switch_view("settings")` → `setup_settings_view`(3496행) → `refresh_task_list`(3566행) → `get_tasks`(518행) → **no such table: tasks** | 🔴 |
| 통과(증권 스모크) | `test_market_widgets_present`, `test_market_search_rows_iids_and_format`, `test_market_stale_token_discarded`, `test_market_select_summary` (4/5) | ✅ |
| `core/db_manager.py` mojibake | **2건** — 665행 `# --- 목록??DB`, 756행 `# --- 생활용어?⑹뼱 DB` (주석 전용, 실행 영향 0) | 🟡 |
| `10yp_2.py` mojibake | **0건** (스캔에서 잡힌 13건은 정상 문장의 물음표 → 오탐) | ✅ |
| `ui/daily_editor.py` | **11행·12행 완전 중복 import** (`from ttkbootstrap.constants import BOTH, YES, HORIZONTAL`) | 🟠 |

### 2-2. Git

| 항목 | 실측 |
|---|---|
| HEAD | `440b494` (2026-09-19 14:47, Day-4) |
| 브랜치 | `main` only / `origin/main`과 **미푸시 0** |
| 태그 | **없음** |
| 09-18 이후 커밋 | `5f7f80a`(증권 P0/P1) → `4bab4b8`(엑셀 왕복·mojibake 교정) → `ac2c961`(S-4/S-5/S-6) → `440b494`(스모크 승격) + 문서 4건 |
| **미커밋 변경** | `M core/db_manager.py`(09-19 15:53), `M ui/daily_editor.py`(09-19 17:20) |
| 미추적 | `word_creater/`(CSV 6종 + 생성기), `.vscode/` |
| DB 이력 | **없음** (`git log --all -- "*.db"` 빈 결과 / `.gitignore`에 `*.db`) → **Git으로 DB 복구 불가** |
| 커밋 메시지 | `440b494` 메시지가 `[\uC13C\uC678\uBA74…]` **리터럴 이스케이프**로 저장(한글 아님) 🟡 |

### 2-3. DB 실측 (`scheduler.db`)

- 크기 204,800 bytes / mtime **2026-09-19 20:08:49** / `PRAGMA integrity_check = ok` / `user_version = 0`
- 테이블 **15개**, **`tasks` 없음**

| 테이블 | 09-18 실측 | **09-20 실측** | 판정 |
|---|---|---|---|
| schedules | 5 | **0** | 🔴 소실 |
| transactions | 3 | **0** | 🔴 소실 |
| investment_journal | 1 | **0** | 🔴 소실 |
| saved_markets | 4 | **0** | 🔴 소실 |
| saved_news | 4 | **0** | 🔴 소실 |
| study_words | 89 | **0** | 🔴 소실 |
| study_notes | 12 | **0** | 🔴 소실 |
| ddays | 2 | **0** | 🔴 소실 |
| study_progress | 0 | 0 | ⚪ |
| study_subject_data | 0 | 0 | ⚪ (미사용) |
| favorite_quotes | 0 | 0 | ⚪ |
| categories | 16 | 15 | 🟡 재시드 결과 |
| anniversaries | 11 | 11 | ✅ (시드) |
| phrases | 340 | 340 | ✅ (시드) |
| wordbook | 340 | 340 | ✅ (시드) |
| **tasks** | **0 (테이블 존재)** | **테이블 없음** | 🔴 **P0 원인** |

- `wordbook` 컬럼: `id, language, rank, word, pron_en, pron_ko, pos, meaning, example, example_ko, item_type, reviewed_at, ease`
  - 언어별 **영어 300 / 일본어 20 / 중국어 20**, `item_type IS NULL` 0건, 인덱스는 `sqlite_autoindex_wordbook_1`만(=`UNIQUE(language, word, item_type)`)
- `data/images/`에 **`2026-09-19_2025 fc SKY.jpg`, `…_1.jpg` 생존** → 이미지 파일은 남았고, **그날의 일정/일지 텍스트는 소실**

### 2-4. 설정·환경

| 키 | 상태 |
|---|---|
| `api_keys.fss_stock` | `SET(len=64)` ✅ 실동작 |
| `api_keys.fss_product / fss_index / fss_company` | `EMPTY` (data.go.kr 서비스 종료 → 재신청 필요) |
| `theme` / `show_reminder` | `darkly` / `true` |
| `config.json` mtime | **2026-09-19 20:08:44** (DB 재생성 13초 전) |
| `backup/` 폴더 | **없음** — 자동/수동 백업이 한 번도 실행되지 않음 |
| `archive/logs/app.log` | 마지막 앱 사용 흔적 **2026-09-19 20:06:01**, 이후 기록 없음 |

### 2-5. 자산

| 경로 | 내용 |
|---|---|
| `word_creater/` (미추적) | `word_create_g.py`(207행, OpenAI 호출), `English_..._1000.csv`(1000행, mojibake 23셀), `Japanese_...`(708행, 1), `Spanish_...`(101행, 3), `Chinese/French/German_...`(21~22행) — 모두 UTF-8 **BOM** |
| `Temp/` | 오늘 재생성한 실측 산출물 (09-18 산출물은 전부 소실) |
| `archive/logs/app.log` | 40KB, 로테이션 없음 |
| `data/quotes_data.json` | 77KB (명언 시드) |

---

## 3. 🔴 사고 보고: 사용자 데이터 소실 (2026-09-19 20:08 추정)

### 3-1. 사실(실측)

1. `scheduler.db` mtime = **2026-09-19 20:08:49**, 같은 시각대에 `config.json`도 재작성(20:08:44). 두 파일 모두 **"초기 시드 상태의 새 DB"** 로 판정된다.
   - 근거: 사용자 데이터 전부 0건, 시드(anniversaries 11 / categories 15 / phrases 340 / wordbook 340)만 존재, `wordbook.item_type`이 전건 NOT NULL → **09-19 15:53 이후의 수정된 코드로 생성**된 DB.
2. 직전까지 앱은 정상 사용 중이었다.
   - `archive/logs/app.log` 마지막 기록 **20:06:01** (삼성 검색 totalCount=546)
   - `data/images/2026-09-19_2025 fc SKY.jpg` 등 **09-19 날짜 이미지 2건 생존** → 09-19에 일정 이미지 첨부 기능을 실제로 사용
3. 09-18 문서의 정량 기록(그때는 존재했음)과 대조하면 사라진 항목은 다음과 같다.

| 도메인 | 소실 항목 | 09-18 수량 |
|---|---|---|
| 일정 | `schedules` (일정/일지/이미지 참조) | 5 |
| 가계부 | `transactions` | 3 |
| 증권 | `investment_journal` / `saved_markets` / `saved_news` | 1 / 4 / 4 |
| 학습 | `study_words` / `study_notes` | 89 / 12 |
| 목표 | `ddays` | 2 |

### 3-2. 복구 가능성 (냉정한 평가)

| 경로 | 가능성 | 확인 방법 |
|---|---|---|
| Git 이력 | ❌ 불가 | `git log --all -- "*.db"` 결과 없음, `.gitignore`에 `*.db` |
| `backup/` 폴더 | ❌ 불가 | 폴더 자체가 없음(백업 기능 미실행) |
| Windows 휴지통 | ⚠️ **먼저 확인 필요** | 휴지통에서 `scheduler.db` / `scheduler.db-journal` 검색 |
| 파일 탐색기 → 이전 버전 / 파일 히스토리 / 복원 지점 | ⚠️ **확인 권장** | `scheduler.db` 우클릭 → 속성 → 이전 버전 |
| DB 파일 조각 복구(undelete 도구) | ⚠️ 낮음 | 삭제가 아니라 덮어쓰기(replace)면 회수 불가 |
| `data/images/*` | ✅ 생존 | 파일 2건 확인됨(참조 레코드만 소실) |
| 문서 기록 | 참고만 | 09-18 문서에 행수만 있음 → 내용 복원 불가 |

> **결론 및 결정(2026-09-20)**: 데이터 **복구 시도를 하지 않고**, 현재의 시드 DB를 **새 베이스라인**으로 삼는다.
> 복구를 포기하면 **마이그레이션 부담이 사라진다**(기념일 시드 정정·`wordbook` 제약 확정·1000단어 임포트가 모두 "교정"이 아니라 "확정" 작업이 된다).
> 대신 과거 기록은 재입력이며, 재입력은 **"과거 복원"이 아니라 앞으로 쓰면서 채우는 방식**으로 진행한다. → 상세 경로: **§12**

### 3-3. 재발 방지 요구사항 (설계 수준)

| ID | 요구사항 | 구현 지점(예정) |
|---|---|---|
| R-1 | **앱 시작 시 자동 백업**(일 1회, 7개 보관, `backup/scheduler_YYYYMMDD_HHMM.db`) + 마지막 백업 시각을 설정 화면에 표시 | `SchedulerApp.__init__` / `_backup_data` |
| R-2 | **사용자 DB 경로 보호**: 스크립트/테스트는 반드시 임시 경로(`tempfile`)만 사용하고, 실행 인자로 DB 경로를 받는다 | `DBManager(db_name=…)` + 테스트 픽스처 |
| R-3 | **초기화 기능은 명시적 확인 2단계**로만 수행(현재 코드에는 초기화 기능 자체가 없음 → 즉, 재생성은 외부 스크립트에서 발생) | 설정 화면 "데이터 초기화" 신설 시 |
| R-4 | `PRAGMA user_version` + `integrity_check` 게이트: 시작 시 무결성 실패면 **쓰기 금지 + 경고** | `core/db_manager.py` |
| R-5 | DB 파일 백업본이 없으면 앱이 **"백업 없음" 경고**를 설정 화면에 상시 표시 | 설정 화면 |
| R-6 | 파괴적 스크립트는 `Temp/`에서 돌리되 **대상 경로를 출력**하고, `scheduler.db` 문자열이 들어가면 실행 거부 | 스크립트 규약 |

---

## 4. 09-18 계획 대비 진척 (Day 1~9)

| Day | 계획(09-18 문서) | 상태 | 실측 증거 |
|---|---|---|---|
| Day 1 (09-18/19) | P0-3 엑셀 왕복, P0-4 mojibake 37줄 교정 | 🟢 **완료** | 커밋 `4bab4b8`, `tests/test_core.py`에 `TestScheduleExcelRoundTrip` 5건, `set_schedule(images=None)` 유지 |
| Day 2 (09-19) | P0-1/P0-2/P0-5 증권 Treeview·CRUD·`market_widget` 제거 | 🟢 **완료** | 커밋 `5f7f80a`, `_market_tree = ttk.Treeview(...)` 1789행 단일 생성, `market_widget` 참조 0건, 스모크 4/5 통과 |
| Day 3 (09-20 계획, 실제 09-19) | S-4/S-5/S-6 + P1-1/P1-2 | 🟢 **완료** | 커밋 `ac2c961`+`5f7f80a`, `def set_schedule` **1곳**(380행), `investment_journal` DDL **1곳**(219행), `_fmt_*` 헬퍼·`_market_pending`·Mock 경고 반영 |
| Day 4 (09-21 계획, 실제 09-19) | P1-8 스모크 테스트 승격 | 🟡 **부분** | `tests/test_ui_smoke.py` 추가 ✅ / 미사용 코드 정리 ✅ / **테스트는 실패 상태로 커밋** ❌ / 커밋·푸시 ✅ |
| Day 5 (09-22) | P1-5 학습(`study_progress`, `study_subject_data`, 진도 위젯) | ⚪ **미착수** | 진도 UI는 존재(`tree_progress`, 3025~3068행)하나 **진도율 위젯 없음**, `study_subject_data` API **앱 호출 0건** |
| Day 6 (09-23) | P1-3/P1-4 뉴스 소스 4건 교정 + 성공/실패 표시 | ⚪ **미착수** | 소스 오류 4건 그대로(`news_fetcher.py` 57/59/63/68행), UI엔 `수집 N건`만 표시 |
| Day 7 (09-24) | P1-6 가계부 카테고리 마스터 + 예산 경고 | ⚪ **미착수** | 카테고리는 **하드코딩 Combobox 11종**(2278~2280행), `get_category_summary` **앱 호출 0건**, `예산`/`budget` 문자열 **0건** |
| Day 8 (09-25) | P1-7 자동 백업 + P2-5 `user_version`/`integrity_check` | ⚪ **미착수** | 수동 백업만 존재, `user_version = 0`, `integrity_check` 게이트 없음, `backup/` 없음 |
| Day 9 (09-26) | 전체 회귀 + 문서 갱신 + 릴리스 태그 | ⚪ **미착수** | 태그 없음, 회귀는 현재 **레드** |

### 4-1. 새로 드러난 사실(계획에 없던 항목)

- **N-0(사고)**: 사용자 데이터 소실 → §3
- **N-1**: `tasks` DDL 부재 → 설정 탭 예외(§5-D)
- **N-2**: `wordbook.item_type` 미커밋 변경이 **죽은 코드 + 제약 약화**(§5-D)
- **N-3**: `word_creater/` 1000단어 확장 미완 + 품질 이슈(§5-B)
- **N-4**: 기념일 시드 명칭 5건 손상(§5-D)
- **N-5**: `ui/daily_editor.py` 중복 import(§5-E)

---

## 5. 분야별 전문가 진단 (2026-09-20)

> 표기: 🔴 P0(즉시) / 🟠 P1(이번 주) / 🟡 P2(다음 사이클) / ✅ 정상 / ⚪ 판단 보류

### 5-A. 일정·생산성 도메인 (일정관리/생산성 앱 전문가)

**현황**: 월간/주간/일간/전체 4뷰 + 시작 리마인더 + 이미지 첨부 + 엑셀 입출력 + D-Day/기념일 연동. 구조는 안정적이다.

| ID | 문제 | 근거 | 등급 |
|---|---|---|---|
| S-1(해결) | 엑셀 왕복 불가 | `df.columns` 정정 + `import_schedules_from_df` 키 정정 완료 | ✅ |
| S-2(해결) | 가져오기 전 행 무음 스킵 | `{imported, skipped}` 반환 + 테스트 5건 | ✅ |
| S-4(해결) | `set_schedule` 이중 정의 | 정의 1곳(380행), `def get_schedule` 1곳(407행) | ✅ |
| S-5(해결) | `investment_journal` DDL 중복 | `create_tables` 1곳(219행) | ✅ |
| **S-7** | **가져오기 실패 행 보고가 토스트에만 존재** — 스킵 N건/이유를 화면에서 확인 불가(로그 의존) | 10yp_2.py 1235행 부근 `가져오기 성공` 토스트 | 🟡 P2 |
| **S-8** | 주간 요약(W-키) 편집 창은 일지 위젯이 없어 저장 시 `journal=""`로 기록된다. 원래 설계 의도(W-키는 일지 미사용)이나, **W-키에 일지를 쓴 적이 있으면 소실**된다 | `ui/daily_editor.py` 54·83·84행 | 🟡 P2 |
| **S-9** | 일정 데이터가 0건이 되어 **실사용 검증 불가** → 스모크는 "예외 0"만 보증 | §3 | 🟠 P1 |

**해야 할 일**
1. (S-8) W-키 저장 시 일지는 건드리지 않도록 `journal=None` 유지 시맨틱 추가 여부를 결정(현재는 이미지에만 유지 시맨틱이 있음).
2. 가져오기 결과에 `imported/skipped/실패 사유 상위 3건`을 **UI표**로 노출.
3. 복원 후 **실사용 시나리오 5종**(일정 저장→주간 집계→엑셀 왕복→이미지 첨부→리마인더 표시)을 수동 점검하고 `Temp/dayN_check.json`으로 기록.

---

### 5-B. 학습 데이터 아키텍트 (학습/노트 도메인)

**현황**: 공부 탭 `Notebook` 13탭 + 별도 진도 탭(`tree_progress`). 시드 = 단어장 340 / 생활용어 340 / 공식 160 / 용어 100+ / 한자 380 / 명언 345.

| ID | 문제 | 근거 | 등급 |
|---|---|---|---|
| N-1 | `study_progress` **0행** — UI(3025~3068행)는 있으나 사용 이력 없음. **진도율 위젯 없음** | DB 실측 0, `진도` 문자열은 UI 라벨뿐 | 🟠 P1 |
| N-2 | `study_subject_data` **앱 호출 0건** = 죽은 테이블/죽은 API 3종(`get/set/search_subject_data`) | `10yp_2.py`에 해당 API 참조 없음 | 🟠 P1 |
| N-3 | 시드 하드코딩(단어 340행 규모) → 데이터 수정에 코드 배포 필요 | `core/word_data.py`, `phrase_data.py` | 🟡 P2 |
| N-4 | 복습 알고리즘(ease 0→1→3→7→14→30일)은 구현됨(`get_words_due_for_review`)하나 **진도·오답 통계와 미연결** | 1081~1105행 | 🟡 P2 |
| **N-6** | 1000단어 확장 산출물이 **미완·미검증·미이관**: English 1000행(mojibake 23셀), Japanese 708, Spanish 101, Chinese/French/German 21~22 | `Temp/ann_csv_probe.txt` | 🟠 P1 |
| **N-7** | 확장 데이터를 DB에 넣을 **경로가 없음**: CSV→DB 임포터 부재, `add_word_with_item`는 앱에서 미사용 | `10yp_2.py` 호출 0건 | 🟠 P1 |

**해야 할 일(권고)**
1. **진도율 위젯**: 과목별 `완료/전체`(study_progress 기준) + 오늘 복습 대상 수를 공부 탭 상단에 배치 → 데이터가 이미 있으므로 표시만으로 가치 발생.
2. `study_subject_data`는 **UI 연결(과학/IT/사회 메모 저장)** 또는 **테이블·API 제거** 중 하나로 결정(죽은 기능 방치 금지).
3. 1000단어 트랙은 **별도 티켓**으로 분리: ①CSV 품질 게이트(행수·중복·mojibake·빈칸 0), ②`Temp/import_words.py`(임시 DB 검증) → ③검증 통과 시 사용자 DB 반영(백업 후), ④미완 언어는 "부분 수록" 표기.
4. 시드/CSV 출처를 `data/`로 이관하는 P2 트랙은 유지(지금은 하지 않음).

---

### 5-C. 금융 데이터 엔지니어 (증권 도메인)

**현황**: 라이브 API 정상. `GetStockSecuritiesInfoService_V2/getStockPriceInfo_V2`, `삼성` totalCount=546~572, 30일 창. 7열 Treeview·ZWSP 종목코드 보존·비동기 검색·Mock 경고까지 Day-2/3에서 복구되었다.

| ID | 문제 | 근거 | 등급 |
|---|---|---|---|
| M-1/M-2/M-3(해결) | Treeview 부재/`_market_tree` 미생성/CRUD `AttributeError` | 1789행 단일 생성, 스모크 4건 통과 | ✅ |
| M-4(해결) | UI 스레드 동기 HTTP | 워커 + `after` 폴링(`_market_pending`) | ✅ |
| M-5(부분) | Mock 폴백 | 경고 표시는 구현, **기본 비활성 여부는 미확인**(API 키가 있으므로 실사용 영향 낮음) | 🟡 P2 |
| **M-9** | **저장목록 0건** — `saved_markets`가 재생성으로 소실되어 저장/수정/삭제 회귀를 다시 확인해야 함 | §2-3 | 🟠 P1 |
| **M-10** | 차트는 여전히 **Mock 추세선**(2081행 주석) → 시각적으로 "가짜"임을 표기하지 않으면 오인 위험 | 2081행 | 🟡 P2 |
| M-7(외부) | 지수/상품/기업 API는 data.go.kr 서비스 종료 | config `EMPTY` | ⚪ (재신청 필요) |

**해야 할 일**
1. 복구 후 **CRUD 실측 4단계**(검색→저장→수정→삭제) + 저장목록 재구축.
2. Mock 사용 시 **상태 라벨·차트 캡션 모두에 "샘플" 표기**(색상 + 텍스트) 규약 고정.
3. 지수/상품/기업 탭은 **재신청 전까지 숨김 처리**(오류 노출 방지) 결정.

---

### 5-D. 데이터 엔지니어링·무결성 (신규 배정)

이 영역이 **오늘 사고의 진앙**이다. 스키마 자기치유(self-healing)가 부분적으로만 되어 있다.

| ID | 문제 | 근거 | 등급 |
|---|---|---|---|
| **D-1** | **사용자 DB 재생성 사고** — 스크립트/세션에서 실 DB를 새로 만든 것으로 추정. 백업·차단 장치가 없었음 | §3 | 🔴 P0 |
| **D-2** | **`tasks` 테이블 DDL 부재** — `get_tasks/add_task/delete_task`(516~533행)는 있으나 `create_tables`(42~233행)에 DDL이 없고 docstring에만 `tasks(...)` 흔적. 09-18 DB에는 테이블이 있었으므로 **선행 앱 버전의 테이블이 사라진 뒤 코드가 그대로 남은 상태** | `findstr "CREATE TABLE" core\db_manager.py` → 14개, tasks 없음 | 🔴 P0 |
| **D-3** | `ensure_schedule_tables`는 `schedules.schedule_images`, `wordbook.reviewed_at/ease`, `phrases.*`, `saved_news.read_flag`, `investment_journal.created_at` 등만 자기치유 → **누락 테이블 자동 생성 로직 없음** | 287~330행 | 🟠 P1 |
| **D-4** | `wordbook` UNIQUE 제약이 `UNIQUE(language, word, item_type)`로 바뀜 + UI `add_word`는 `item_type`을 NULL로 삽입 → **SQLite는 NULL을 서로 다르게 취급하므로 중복 단어가 들어갈 수 있다**(09-18 이전 제약 `UNIQUE(language,word,pos)`보다 약화) | `db_manager.py` 142·710~720행, DB 인덱스 실측 | 🟠 P1 |
| **D-5** | `init_default_words`의 재시드 조건이 `WHERE language=? AND item_type IS NOT NULL` → **기존 정상 행(과거 버전이 넣은 행)을 "없음"으로 오판**해 재삽입 시도 | 674~680행 | 🟠 P1 |
| **D-6** | `init_db()`가 `DBManager` 정의 **이전**에 배치되어 있고, `conn`을 열어두었다 바로 닫는 무의미 코드. 앱 호출 0건(죽은 함수) | 21~29행 | 🟡 P2 |
| **D-7** | DDL에 `PRAGMA user_version` 관리가 없어 **스키마 버전 추적 불가** | DB 실측 `user_version=0` | 🟠 P1 |
| **D-8** | 기념일 시드 명칭 5건이 실체와 불일치: 5/5 `만일홍보절`(→어린이날), 6/6 `어린이날`(→현충일), 10/3 `개척절`(→개천절), 10/9 `서방`(→한글날), 10/26 `근화절`(→독도의 날). 초기 커밋부터 존재하므로 **선행 세션의 문자열 손상**이며, 시드는 이미 DB에 들어가 있어 **UPDATE 마이그레이션이 필요** | `ann_history.txt`, DB 실측 | 🟠 P1 |
| **D-9** | mojibake 잔존 2건(주석) | 665·756행 | 🟡 P2 |
| D-10 | `saved_news.link` UNIQUE, `favorite_quotes.item_id` UNIQUE 등 제약은 정상 | 스키마 확인 | ✅ |

**해야 할 일(순서 엄수)**
1. **(D-2)** `create_tables`에 `CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY AUTOINCREMENT, item TEXT, period TEXT, goal TEXT, content TEXT, remark TEXT)` 추가 + `ensure_schedule_tables`에서도 누락 테이블 보정(멱등).
2. **(D-1)** 자동 백업(R-1)을 **설정 뷰 수정과 같은 커밋**에서 함께 넣어, 이후 모든 실험 전에 백업이 존재하도록 만든다.
3. **(D-4/D-5)** `wordbook` 정책 확정:
   - 채택안: `item_type` **NOT NULL DEFAULT '단어'**, UI `add_word`도 `item_type`을 항상 기록, 재시드 조건은 `WHERE language=? AND item_type='단어'`(또는 `COUNT(*)=0`), 기존 데이터는 `UPDATE wordbook SET item_type='단어' WHERE item_type IS NULL`.
   - 폐기안: `item_type` 변경 전부 되돌리고(미커밋이므로 revert) 1000단어 트랙에서 다시 설계.
4. **(D-7)** `PRAGMA user_version=1` + 시작 시 `integrity_check != 'ok'` 면 경고 모드.
5. **(D-8)** 기념일 명칭 교정 마이그레이션(`Temp/fix_anniversaries.py`로 임시 DB 검증 후 실 DB 적용, 사전 백업 필수).

---

### 5-E. 아키텍처·품질 (소프트웨어 아키텍트)

**현황**: `10yp_2.py` **3,700행**(09-13 시점 3,042행 → **+658행**, 대부분 증권 뷰 재작성. 참고로 증권 커밋 `5f7f80a` 단독 변경은 +462/−226) 단일 파일 + `core/` 20모듈 + `ui/` 1모듈 + `tests/` 2파일.

| ID | 문제 | 근거 | 등급 |
|---|---|---|---|
| **A-1** | **`switch_view`에 예외 격리가 전혀 없다** — 한 뷰의 오류가 그 뷰 전체를 백지로 만들고, 원인은 콘솔에만 남는다 | 409~433행, 실제로 설정 탭에서 발생 | 🔴 P0 |
| **A-2** | `ui/daily_editor.py` **중복 import 1줄**(11·12행 동일) | 정적 분석에서 즉시 적발되는 수준 | 🟠 P1 |
| **A-3** | **테스트가 빨간 상태로 커밋**되었고, 커밋 메시지는 "48 OK"라고 기록 → 커밋 시점 검증 절차 부재 | `440b494` | 🔴 P0 |
| **A-4** | 뷰 단위 분리 2단계 미착수(09-14 계획 대기) — 3,700행 단일 파일이 손상·중복의 온상 | 09-14/09-18 문서 | 🟡 P2 |
| **A-5** | 커밋 메시지에 `\uXXXX` 리터럴이 저장됨(인코딩 도구 문제 재발) | `440b494` | 🟡 P2 |
| **A-6** | 죽은 코드 잔존: `init_db`, `add_word_with_item`, `get_subject_data/set_subject_data/search_subject_data`, `_render_market_ui` 계열 잔재 여부 | grep 호출 0건 | 🟠 P1 |
| A-7 | `except` 광범위 사용은 09-14에 정리됨(경계 4곳 `noqa` 문서화) | 코드 확인 | ✅ |

**해야 할 일**
1. **(A-1)** `switch_view`를 `try/except Exception` + `log.exception` + **사용자 안내 라벨**("이 화면을 여는 중 오류가 발생했습니다. 로그: …")로 감싸고, 스모크 테스트에 "각 뷰 진입 시 오류 라벨 미표시" 단언 추가.
2. **(A-3)** 커밋 전 **`python -m unittest discover …` 통과 + 스모크 통과**를 DoD로 고정(§8).
3. **(A-2/A-6)** 중복 import·죽은 함수를 한 커밋에서 정리(단, `init_db`/`add_word_with_item`은 D-4 결정과 함께).
4. 커밋 메시지는 **ASCII 파일명 + UTF-8 텍스트** 규약 유지, 메시지에 결함 ID 필수(`[D-2] tasks DDL …`).

---

### 5-F. UX·접근성 (프로덕트 디자이너)

| ID | 문제 | 근거 | 등급 |
|---|---|---|---|
| U-1 | 뷰 진입 실패 시 **사용자에게 아무 설명이 없다**(백지 화면) | A-1과 동일 원인 | 🔴 P0 |
| U-2 | 수집/백업/가져오기 결과가 **토스트·메시지박스에만** 존재 → 사후 확인 불가 | 뉴스 `수집 N건`(3254행), 백업 메시지 | 🟠 P1 |
| U-3 | 학습 **진도율 위젯 없음** → "얼마나 했는지" 볼 수 없음 | N-1 | 🟠 P1 |
| U-4 | 샘플(Mock) 데이터와 실데이터 구분이 **색상만** | 증권 상태 라벨 | 🟡 P2 |
| U-5 | 창 크기/폰트가 고정값(`800x600`, Malgun Gothic 하드코딩) → DPI 배율·접근성 미지원 | `ui/daily_editor.py` 35행 외 | 🟡 P2 |
| U-6 | 파괴적 동작(삭제/복원)에 **되돌리기(Undo) 없음** | 삭제 핸들러 전반 | 🟡 P2 |

**해야 할 일**: 모든 파괴적 동작 옆에 **직전 백업 시각**을 표시하고, 백업이 없으면 경고 배너를 띄운다(데이터 사고 재발 방지와 UX를 동시에 해결).

---

### 5-G. DevOps·릴리스 (릴리스 엔지니어)

| ID | 문제 | 근거 | 등급 |
|---|---|---|---|
| **G-1** | **회귀 게이트가 사람 손에 의존** — 이번 커밋처럼 실패 상태로 푸시 가능 | `440b494` | 🔴 P0 |
| G-2 | 릴리스 태그/버전 규약 없음(`v1.0` 초기 커밋만 텍스트로 존재) | `git tag` 빈 결과 | 🟡 P2 |
| G-3 | 검증 산출물이 `Temp/`(휘발)에만 존재 → 폴더 삭제 시 근거 소실 | 이번 사건의 직접 원인 | 🟠 P1 |
| G-4 | `archive/logs/app.log` 로테이션 없음(단일 40KB+) | 파일 실측 | 🟡 P2 |
| G-5 | `word_creater/`가 미추적 → 도구를 다른 PC에서 재현 불가 | `git status` | 🟠 P1 |
| G-6 | venv/잠금 파일 없음(`requirements.txt` 버전 범위만) — Python 3.14.7에서만 검증 | 폴더 실측 | 🟡 P2 |

**해야 할 일**
1. **(G-1)** 커밋 규약: `py_compile` + `unittest` + `test_ui_smoke` 통과 로그를 **커밋 본문에 붙인다**(§8). `440b494`의 "48 OK" 같은 주장 금지.
2. **(G-3)** 검증 결과는 **`Temp/`(재생성 가능) + 문서 요약(`*.md`)** 두 곳에 남긴다. 문서에는 **재현 명령**을 항상 함께 적는다.
3. **(G-5)** `word_creater/`는 **도구로 저장소에 포함**할지 결정(포함 시 CSV는 생성물이므로 `.gitignore` 검토).

---

### 5-H. 보안·개인정보·문서 (보안/테크니컬 라이터)

| ID | 문제 | 근거 | 등급 |
|---|---|---|---|
| P-1 | API 키가 **평문 `config.json`** (gitignore로 커밋은 차단됨) | `.gitignore` 2행 | 🟡 P2 |
| P-2 | `app.log`에 **API 키가 쿼리스트링 평문**으로 기록됨(`serviceKey=6b57…`) | `archive/logs/app.log` 4행 등 다수 | 🟠 P1 |
| P-3 | 백업 파일에 DB+config(키 포함)를 함께 복사 → 백업 폴더 유출 시 키 노출 | `_backup_data` 3642행 부근 | 🟠 P1 |
| P-4 | 문서가 **한글 파일명**과 ASCII 파일명이 혼재 | 루트 MD 목록 | 🟡 P2 |
| **P-5** | 커밋/문서의 검증 기록이 **환경(DB 스키마 버전)에 의존**한다: `440b494`의 "48 OK"는 당시 `tasks` 테이블이 있던 DB에서는 사실이었고, DB 재생성 후에는 거짓이 된다 → 검증 기록에 **DB 경로·스키마 버전·시각**을 함께 남겨야 한다 | §2-1, §2-3, §3 | 🟠 P1 |

**해야 할 일**: 로그에서 `serviceKey`를 **마스킹**(`serviceKey=***`)하고, 백업은 `config.json`을 선택적으로 제외하거나 `backup/` 접근 안내를 추가한다.

---

## 6. 결함 우선순위 총괄 및 완료 기준(DoD)

### 6-1. P0 — 즉시 (데이터 손실·기능 무력화·검증 불능)

| ID | 영역 | 내용 | 완료 기준(측정 가능) |
|---|---|---|---|
| **P0-1** | 데이터 | 복구 시도(휴지통/이전 버전) + 자동 백업 도입 | `backup/scheduler_*.db` ≥ 1개 생성, 설정 화면에 마지막 백업 시각 표시 |
| **P0-2** | 데이터 | `tasks` DDL 복원(멱등 자기치유) | `PRAGMA table_info(tasks)` 6컬럼, `get_tasks()` 예외 0 |
| **P0-3** | 품질 | 테스트 레드 해소 | `Ran 48 tests — OK` (스모크 포함) |
| **P0-4** | 아키텍처 | `switch_view` 예외 격리 + 사용자 안내 | 각 뷰 진입 시 오류 라벨 미표시 + `log.exception` 기록 |
| **P0-5** | 증권 | 저장목록 CRUD 재검증 | 저장/수정/삭제 3동작 예외 0, 재실행 후 목록 유지 |
| **P0-6** | 보안 | 로그 API 키 마스킹 | `app.log`에 `serviceKey=***`만 기록 |

### 6-2. P1 — 이번 주 (신뢰성·데이터 품질)

| ID | 영역 | 내용 |
|---|---|---|
| **P1-1** | 데이터 | `wordbook.item_type` 정책 확정(채택/폐기) + UNIQUE 제약 정상화 |
| **P1-2** | 데이터 | 기념일 명칭 5건 교정 마이그레이션(사전 백업) |
| **P1-3** | 학습 | 진도율 위젯 + `study_progress` 실사용 경로 확보 |
| **P1-4** | 학습 | `study_subject_data` 연결 또는 제거 결정 |
| **P1-5** | 학습 | 1000단어 CSV 품질 게이트 + 임포터(임시 DB 검증 → 실 DB 반영) |
| **P1-6** | 뉴스 | 소스 4건 교정 + 성공/실패 집계 UI |
| **P1-7** | 가계부 | 카테고리 마스터 + 예산 경고 + 카테고리 통계 뷰(`get_category_summary` 연결) |
| **P1-8** | 품질 | 커밋 전 검증 게이트 고정(§8) + `word_creater/` 저장소 정책 결정 |
| **P1-9** | 인프라 | `user_version`/`integrity_check` 게이트 |

### 6-3. P2 — 다음 사이클

| ID | 내용 |
|---|---|
| P2-1 | 뷰 분리 2단계(`ui/`로 뷰 이관) — 증권 뷰부터 |
| P2-2 | 뉴스/증권 샘플 데이터 표기 강화, 차트 실데이터(P2-2 연계) |
| P2-3 | 지수/상품/기업 API 재신청(data.go.kr) |
| P2-4 | 백업 회전 7개·로그 로테이션·`requirements` 잠금 |
| P2-5 | mojibake 잔존 2건 정리, 커밋 메시지 인코딩 규약 |
| P2-6 | 접근성(DPI/폰트 배율), Undo/재실행 |

### 6-4. 모든 변경에 공통 적용하는 DoD (커밋 전 필수)

1. `py_compile` 25/25 OK
2. `python -m unittest discover -s tests -t .` → **OK (48+ 신규)**
3. 뷰 스모크 9/9 예외 0 (`tests/test_ui_smoke.py`)
4. mojibake 신규 증가 0 (`Temp/moji_probe.py`)
5. **실 DB 백업 존재 확인**(`backup/` 최신본 시각 < 작업 시작 시각)
6. 검증 로그와 명령을 커밋 본문에 기재(환경 포함: Python 3.14.7, DB 경로, `user_version`)

---

## 7. 실행 계획 (2026-09-20 시작, 7일)

> ⚠️ **2026-09-20 결정 반영**: 데이터 복구를 포기함에 따라 **이 표는 §12-3(Fresh-Start 실행 계획)으로 대체**되었다.
> 아래 표는 09-18 기준 원안으로 **기록 보존**용이다(진척 증거와 함께 유지).

> 전제: 하루 1~2시간. **각 Day는 "검증 커맨드 통과 + 커밋" 으로 닫는다.**

### Day 1 — 2026-09-20 (일) : 🔴 사고 수습 + 기능 복구 (P0-1, P0-2, P0-3)
- [ ] **(복구 시도 30분)** 휴지통 / `scheduler.db` 우클릭 → 속성 → 이전 버전 / 파일 히스토리 확인 → 결과를 `Temp/recovery_report.md`에 기록
- [ ] **수동 백업 1회 즉시 실행**: `scheduler.db`·`config.json` → `backup/`(폴더가 없으므로 `mkdir backup` 후 복사)
- [ ] `create_tables`에 `tasks` DDL 추가 + `ensure_schedule_tables`에 누락 테이블 보정(멱등)
- [ ] `tests/test_core.py`에 회귀 테스트 2건 추가: ①`tasks` 스키마 존재(PRAGMA 6컬럼) ②`add_task → get_tasks → delete_task` 왕복
- [ ] `ui/daily_editor.py` 중복 import 제거
- **검증**: `python -m unittest discover -s tests -t . -v` → **49+ OK(ERROR 0)** / `python Temp\probe_state.py` → `tables`에 `tasks` 포함
- **커밋**: `[D-2] tasks DDL 복원 + 설정 뷰 예외 해소 (P0-2/P0-3)`

### Day 2 — 2026-09-21 (월) : 안전장치 (P0-1, P0-4, P0-6, P1-9)
- [ ] **앱 시작 자동 백업**: 일 1회, `backup/scheduler_YYYYMMDD.db`, 7개 회전, 시작 시 로그 1줄
- [ ] 설정 화면에 **"마지막 백업: YYYY-MM-DD HH:MM"** 라벨 + "백업 없음" 경고 배너
- [ ] `switch_view` 예외 격리(try/except + `log.exception` + 오류 라벨)
- [ ] `core/market_fetcher.py` 로그의 `serviceKey` 마스킹
- [ ] `PRAGMA user_version=1`, 시작 시 `integrity_check` 실패 시 경고 모드
- **검증**: 앱 실행 → `backup/` 파일 생성 확인, `PRAGMA user_version`=1, `app.log`에 `serviceKey=***`, 스모크 9/9
- **커밋**: `[P0] 자동 백업·뷰 예외 격리·키 마스킹 (P0-1/P0-4/P0-6)`

### Day 3 — 2026-09-22 (화) : 데이터 정합성 (P1-1, P1-2)
- [ ] `wordbook.item_type` **정책 결정**(§5-D 3항) → 채택 시: `NOT NULL` + UI 기록 + `UPDATE … WHERE item_type IS NULL` 마이그레이션, 폐기 시: 미커밋 revert
- [ ] `Temp/fix_anniversaries.py`로 기념일 5건 교정(임시 DB 검증 → 백업 후 실 DB 적용)
- [ ] `Temp/moji_probe.py` 잔존 2건 정리(주석)
- [ ] 회귀 테스트: 기념일 이름 5건 정확성, `wordbook` 중복 방지(동일 단어 2회 삽입 → 1건)
- **검증**: `unittest` OK / `probe_state.json`의 `anniversaries` 이름과 수량 확인 / 중복 0
- **커밋**: `[D-4/D-8] wordbook 정책 확정 + 기념일 명칭 교정 (P1-1/P1-2)`

### Day 4 — 2026-09-23 (수) : 학습 (P1-3, P1-4)
- [ ] 공부 탭 상단에 **진도율 위젯**(과목별 `완료/전체`, 오늘 복습 대상 수)
- [ ] `study_progress` 입력/토글 흐름 실사용 점검(날짜 기본값=오늘, 과목 Combobox)
- [ ] `study_subject_data`: **연결(과학/IT/사회 메모 저장)** 또는 **제거** 결정 후 실행
- **검증**: 진도 1건 입력 → 앱 재시작 → 값 유지, 진도율 %가 DB 집계와 일치
- **커밋**: `[학습] 진도율 위젯 + subject_data 정리 (P1-3/P1-4)`

### Day 5 — 2026-09-24 (목) : 뉴스 (P1-6)
- [ ] 소스 4건 교정: `오마이데일리`(이탈리아 사이트 URL), `한겨레(교육)`(health URL), `조선일보 스포츠`(HTML), `Google 여행`(비인코딩 한글)
- [ ] 수집 결과에 **성공/실패 소스 수** 표시(예: `수집 42건 · 성공 12/17 · 실패 5`)
- [ ] `Temp/news_probe.py`로 소스별 응답 코드 집계(오프라인 테스트)
- **검증**: 카테고리별 소스 정합(교육 탭에 건강 기사 0), 실패 소스 목록 확인 가능
- **커밋**: `[뉴스] 소스 4건 교정 + 성공/실패 집계 (P1-6)`

### Day 6 — 2026-09-25 (금) : 가계부 + 단어 확장 (P1-5, P1-7)
- [ ] 카테고리 **마스터화**(`categories` 재사용 또는 `ledger_categories` 신설) + Combobox 고정
- [ ] **예산 설정 + 초과 경고**, `get_category_summary` 연결한 **카테고리별 요약 표**
- [ ] 1000단어 CSV 품질 게이트 스크립트(`Temp/check_words_csv.py`) + 임포터 초안
- **검증**: 동일 범주 통계 합계 일치, 예산 초과 시 경고 표시, 임시 DB에서 단어 임포트 후 중복 0
- **커밋**: `[가계부] 카테고리 마스터·예산 경고 (P1-7)` / (별도) `[학습] 단어 CSV 게이트·임포터 (P1-5)`

### Day 7 — 2026-09-26 (토) : 회귀·문서·릴리스 (P1-8, G-1, G-2)
- [ ] 전체 `unittest` + `test_ui_smoke` + `Temp/moji_probe.py` + `Temp/probe_state.py` 실행 → 결과를 `Temp/regression_0926.json`으로 저장
- [ ] 수동 시나리오: 일정 5종·증권 CRUD·학습 진도·뉴스·가계부·백업/복원
- [ ] 이 문서 갱신(P0/P1 체크) + `git tag v1.1` + 푸시
- **커밋**: `[QA] 회귀 7종 통과 + v1.1 릴리스`

---

## 8. 검증 체계(회귀 게이트) 구축 방안

### 8-1. 테스트 계층

| 계층 | 파일 | 검증 대상 | 실행 |
|---|---|---|---|
| 단위 | `tests/test_core.py` (428행) | DB CRUD·엑셀 왕복·이미지·복습·예외/재시도·i18n | `python -m unittest tests.test_core -v` |
| UI 스모크 | `tests/test_ui_smoke.py` (148행) | 9뷰 전환·증권 위젯/검색/토큰/요약 | `python -m unittest tests.test_ui_smoke -v` |
| **신규 제안** | `tests/test_schema.py` | ①15+1 테이블 존재 ②`tasks` 스키마 ③`user_version` ④마이그레이션 멱등성(2회 호출 시 스키마 동일) | 동일 명령 |
| **신규 제안** | `tests/test_data_guard.py` | ①`DBManager`가 **임시 경로 밖에서는 생성 금지**(환경변수/인자 강제) ②`integrity_check` 게이트 | 동일 명령 |
| 스크립트 실측 | `Temp/*.py` (오늘 6종) | DB 행수/스키마, 최근 변경 파일, 도메인 마커, CSV 품질, 기념일 시드, mojibake | §0-3 |

### 8-2. 커밋 게이트(사람 절차 → 문서화)

```
1) python -c "import glob,py_compile; ..."            # 25/25 OK
2) python -m unittest discover -s tests -t . -v       # OK (ERROR 0)
3) python Temp\probe_state.py                          # tables/행수/무결성 JSON 갱신
4) python Temp\moji_probe.py                           # 신규 손상 0
5) dir backup                                            # 백업 최신본 존재
→ 통과 로그를 커밋 본문에 붙이고 커밋
```

### 8-3. 금지 규약 (이번 사고에서 도출)

| 금지 | 이유 |
|---|---|
| `scheduler.db`·`config.json` 경로를 스크립트에 직접 하드코딩 | 실 DB 재생성 사고 |
| 사용자 DB에 대한 `DROP`/`DELETE FROM`/파일 삭제 | 데이터 파괴 |
| 마이그레이션 없이 시드 로직만 수정 | 기존 DB에서 결과 불일치(D-8과 동일 유형) |
| 검증 스크립트 없이 "완료" 체크 | 09-19 "48 OK" 사례 |
| `Temp/`만을 근거로 남기기 | 폴더 삭제로 근거 소실 |

### 8-4. Temp 산출물 규약 (재수립)

- 파일명: `probe_state.json`, `regression_YYYYMMDD.json`, `fix_<대상>.py`(ASCII)
- 각 산출물 첫 줄에 **실행 시각 + 입력 경로 + 코드 커밋 해시** 기록
- 스크립트는 **읽기 전용을 기본**으로 하고, 쓰기가 필요한 경우 `--apply` 플래그 + 사전 백업 필수

---

## 9. 리스크 및 결정 필요 사항

| ID | 항목 | 선택지 | 권고 |
|---|---|---|---|
| **D-1** | 사용자 데이터 복구 | (A)휴지통/이전 버전 탐색 (B)포기하고 재입력 (C)부분 복원(이미지·문서 기반) | **A 먼저 → 없으면 C(이미지 2건 활용) → B** |
| **D-2** | `tasks`(To-Do) 기능 유지 | (A)DDL 복원해 유지 (B)설정 화면에서 제거 | **A** (사용 이력은 없지만 UI·핸들러가 완성돼 있고 비용이 작다) |
| **D-3** | `wordbook.item_type` | (A)채택·정상화 (B)미커밋 revert 후 1000단어 트랙에서 재설계 | **(A)** — 이미 DB가 이 스키마로 재생성됨(채택이 현재 상태와 일치) |
| **D-4** | `study_subject_data` | (A)UI 연결 (B)테이블·API 제거 | **(A 조건부)** — 과학/IT/사회 과목에 메모 폼이 이미 유사 기능을 가지면 (B) |
| **D-5** | 1000단어 데이터 | (A)전 언어 완성 후 일괄 반영 (B)완성된 언어만 부분 반영 | **(B) → 이후 (A)** — 미완 CSV(21행)를 섞으면 품질 저하 |
| **D-6** | 자동 백업 위치/보관 | (A)`backup/` 7개 (B)외부 드라이브/클라우드 동기화 | **A + 사용자 선택 B** |
| **D-7** | 지수/상품/기업 탭 | (A)재신청 후 연동 (B)임시 숨김 | **B → A** |
| **D-8** | `word_creater/` 저장소 포함 | (A)도구+CSV 포함 (B)도구만 포함 (C)제외 | **(B)** — CSV는 생성물, 스크립트는 재현 자산 |
| **D-9** | 문서 파일명 | (A)한글 유지 (B)ASCII | **(B)** (09-18 결정 유지: `2026-09-20_progress_and_plan.md`) |
| **D-10** | 뷰 분리 범위 | (A)증권 뷰만 (B)9개 뷰 전체 | **(A)** 단계적 |

### 9-1. 잔여 리스크(모니터링)

| 리스크 | 신호 | 대응 |
|---|---|---|
| DB 재생성 재발 | `scheduler.db` mtime이 앱 사용 없이 변경 | 자동 백업 + R-2(임시 경로 강제) |
| 미커밋 변경 방치 | `git status`에 `M` 지속 | Day 3에서 반드시 커밋/되돌림 |
| 검증 산출물 소실 | `Temp/` 비어 있음 | §8-4 규약 + 문서에 결과 요약 병기 |
| 외부 API 종료 | `NO_OPENAPI_SERVICE_ERROR` | 소스 상태 표시 + 대체 소스(Google News 검색) 유지 |
| 손상(문자열/파일명) 재발 | mojibake 스캔 신규 히트 | 커밋 게이트 4단계 |

---

## 10. 오늘(2026-09-20) 즉시 할 일 — **복구 없이 새 출발 1일차**

- [x] 1. **베이스라인 동결(완료·2026-09-20 13:5x)**: `backup/scheduler_baseline_20260920.db`(204,800B, sha256 `5fac0539…`), `backup/config_baseline_20260920.json`(229B) — **원본과 해시 동일 확인**. 이후 모든 변경의 되돌림 지점 확보
- [x] 2. **`tasks` DDL 복원 + 자기치유(멱등) — 완료**: `DDL_TASKS` 단일 정의(create_tables ↔ ensure_schedule_tables 공유), 설정 탭 진입 복구
- [x] 3. **`ui/daily_editor.py` 중복 import 제거 — 완료**
- [x] 4. **회귀 테스트 5건 추가 — 완료**(`TestSchemaHealth`: tasks 6컬럼 / CRUD 왕복 / 테이블 삭제 후 자기치유 / 마이그레이션 멱등 / wordbook 기본값·중복 차단)
- [x] 5. **검증 완료**: `py_compile 25/25 OK`, `Ran 53 tests — OK`(직전 ERROR 1건 해소), 실 DB에 `tasks` 6컬럼 생성 확인
- [x] 6. 커밋·푸시 + 이 문서 §12-3 Day 1 갱신(완료)

> **Day 1 결과**: "설정 탭 정상 + 테스트 초록불(53/53) + 되돌림 지점 확보" 달성. 다음은 §12-3 Day 2(자동 백업·뷰 예외 격리·키 마스킹·`user_version`).

---

## 11. 부록

### 11-A. 모듈·파일 책임 지도 (2026-09-20 실측)

| 파일 | 행수 | 책임 | 상태 |
|---|---|---|---|
| `10yp_2.py` | 3,700 | 진입점 `SchedulerApp`, 사이드바, 9개 뷰(월간/주간/일간/전체/공부/뉴스/증권/가계부/설정) | 🟠 단일 파일 비대(증권 뷰 +658행) |
| `core/db_manager.py` | 1,173 | 스키마·CRUD·엑셀 입출력·마이그레이션 | 🔴 `tasks` DDL 부재, mojibake 2건 |
| `core/market_fetcher.py` | 404 | 금융위원회 OpenAPI·정규화·Mock | ✅ (로그 키 마스킹 필요) |
| `core/news_fetcher.py` | 241 | RSS 수집·소스 목록 | 🟠 소스 4건 오류 |
| `core/word_data.py` / `phrase_data.py` | 361 / 362 | 단어 340·생활용어 340 시드 | ⚪ 하드코딩 |
| `core/{formulas,glossary,hanja_data,idiom_data,science_data,history_data,quote_data}.py` | 124~410 | 공부 탭 13종 시드 | ✅ |
| `core/{logger,exceptions,i18n,config_manager,solar_terms}.py` | 27~95 | 로깅·예외·i18n·설정·절기 | ✅ |
| `core/news_summarizer.py` | 166 | 뉴스 요약 | ✅ |
| `ui/daily_editor.py` | 101 | 일정 편집 팝업(일간/주간 공용) | 🟠 중복 import |
| `tests/test_core.py` | 428 | 단위 테스트 43건 | ✅ |
| `tests/test_ui_smoke.py` | 148 | UI 스모크 5건 | 🔴 1건 실패 |
| `word_creater/word_create_g.py` | 207 | 단어 데이터 생성기(OpenAI) | ⚪ 미추적 |
| `Temp/*.py` | 6종 | 오늘 재생성한 실측 스크립트 | 🟢 |

### 11-B. 재현 명령 모음

```powershell
# 1. 현재 상태 실측
python Temp\probe_state.py ; type Temp\probe_state.json
python Temp\recent_trace.py ; type Temp\recent_changes.txt
python Temp\domain_probe.py ; type Temp\domain_probe.txt
python Temp\moji_probe.py ; type Temp\moji_probe.txt

# 2. 테스트/컴파일
python -m unittest discover -s tests -t . -v
python -c "import glob,py_compile;fs=[f for f in glob.glob('*.py')+glob.glob('core/*.py')+glob.glob('ui/*.py')+glob.glob('tests/*.py') if '__pycache__' not in f];[py_compile.compile(f,doraise=True) for f in fs];print('COMPILE_OK',len(fs))"

# 3. DB 직접 확인(읽기 전용)
python -c "import sqlite3;c=sqlite3.connect('scheduler.db');print([r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")]);print(c.execute('PRAGMA user_version').fetchone(), c.execute('PRAGMA integrity_check').fetchone())"

# 4. Git 확인
git --no-pager log --pretty=format:"%h %ad %s" --date=short -8
git status --short ; git log --all --oneline -- "*.db"
```

### 11-C. 실측 vs 추정 (문서 신뢰도 구분)

| 구분 | 항목 |
|---|---|
| **실측(반증 불가)** | 테이블 목록/행수, `tasks` DDL 부재, 테스트 1건 ERROR, 미커밋 2파일, `backup/` 없음, `data/images` 생존, CSV 행수, mojibake 2건, `user_version=0`, Git 상태 |
| **추정(증거 기반)** | DB 재생성 시각(09-19 20:08:49)과 원인(외부 스크립트/세션), 소실 시점(20:06 이후), 구 UI의 `tasks` 테이블 출처(초기 커밋 이전 버전) |
| **미확인(추가 조사 필요)** | `word_creater/*.csv` 생성 실패 원인(쿼터/중단), 휴지통·이전 버전 복구 가능성, Mock 폴백 기본값, `study_progress` 미사용 이유(사용자 습관 vs 도달 불가) |

### 11-D. 결함 ID 색인 (09-18 → 09-20)

| 09-18 ID | 내용 | 09-20 상태 |
|---|---|---|
| P0-1/P0-2/P0-5 | 증권 Treeview·CRUD·widget 제거 | ✅ 해결(`5f7f80a`) |
| P0-3 | 엑셀 왕복 | ✅ 해결(`4bab4b8`) |
| P0-4 | `db_manager` mojibake 37줄 | ✅ 해결(잔존 2건 → D-9) |
| S-4/S-5/S-6 | 단일 정의·DDL 중복·이미지 왕복 | ✅ 해결(`ac2c961`) |
| P1-1/P1-2 | 증권 스레드·Mock 경고 | ✅ 해결(`5f7f80a`) |
| P1-8 | 스모크 승격 | 🟡 부분(Day 4) |
| P1-3~P1-7 | 뉴스·학습·가계부·백업 | ⚪ 미착수 → 오늘 P1-3~P1-9로 재편 |
| — | **신규** D-1(데이터 소실), D-2(tasks), D-4/D-5(wordbook), D-8(기념일), A-1(뷰 예외 격리), P-2(로그 키) | 🔴/🟠 |

### 11-E. 이 문서의 사용 방법

1. §10의 6개를 오늘 끝내고 §7 Day 1 체크박스를 채운다.
2. 각 Day 종료 시 **이 문서의 해당 섹션을 갱신**(체크 + 실측 수치)하고 커밋에 포함한다.
3. 완료 주장에는 반드시 **검증 명령 + 결과 출력**을 붙인다(§8-2).

---

## 12. 복구 없이 새로 시작하는 경로 (Fresh-Start Track) — 2026-09-20 결정

### 12-1. 결정의 효과: "교정"이 "확정"으로 바뀐다

| 09-18 계획 항목 | 복구를 하는 경우(원안) | **복구 없이(현 결정)** |
|---|---|---|
| 기념일 명칭 5건 | `UPDATE` 마이그레이션 + 사용자 추가분 보존 판단 필요 | **시드 리스트를 정정하고 `check_default_anniversaries`를 재실행**(사용자 추가 0건 → 삭제 후 재시드가 안전) |
| `wordbook.item_type` 제약 | 기존 340행의 NULL 처리 + 제약 재구성 | **DDL 확정**(`NOT NULL DEFAULT '단어'`) + 시드 재실행 + 중복 방지 테스트 |
| 1000단어 CSV | 기존 단어와의 중복/충돌 조정 | **임포트 1회**(임시 DB 검증 → 확정) |
| `saved_markets`/`saved_news`/`investment_journal` | 데이터 복구 후 정합성 확인 | 재입력만 하면 됨(정합성 이슈 없음) |
| `study_progress`/`study_subject_data` | 기존 사용 이력 확인 필요 | **0행이므로 자유롭게 UI 연결 또는 제거 결정** |

즉, **잃은 것은 "기록"뿐이고, 얻은 것은 "스키마를 깨끗하게 다시 세울 기회"**다. 이 기회는 한 번뿐이므로 §12-5의 3가지를 반드시 함께 처리한다.

### 12-2. 새 출발 5원칙

1. **동결 먼저(Freeze)**: 현재 DB·config를 `backup/`에 베이스라인으로 복사한다. 이것이 "되돌림 지점"이다.
2. **스키마 먼저, 기능 나중(Schema first)**: `tasks` DDL, 제약, `user_version`, 시드 로직을 먼저 확정한다. 화면 개선은 그 다음이다.
3. **안전장치 없이는 실험 금지(Safety first)**: 자동 백업 + 테스트는 **임시 DB 경로 강제**. 실 DB를 건드리는 스크립트는 실행 전 백업 확인을 코드로 강제한다.
4. **재입력은 도구로(Re-enter with tools)**: 일정=엑셀 템플릿 가져오기, 단어=CSV 임포터, 나머지는 앱에서 직접. 손으로 반복 입력하지 않는다.
5. **각 단계는 테스트로 닫는다(Verify always)**: §8-2 커밋 게이트 5단계를 매일 실행한다.

### 12-3. Fresh-Start 실행 계획 (2026-09-20 ~ 09-26)

| Day | 목표 | 작업(체크리스트 요약) | 검증 |
|---|---|---|---|
| **Day 1**<br>09-20(일)<br>✅ **완료** | 기반 복구<br>(P0-2/P0-3) | ①베이스라인 백업 ②`tasks` DDL 단일 정의 + 누락 테이블 자기치유 ③중복 import 제거 ④회귀 테스트 5건 | **`Ran 53 tests — OK`**, `py_compile 25/25`, 실 DB에 `tasks` 6컬럼 확인 |
| **Day 2**<br>09-20(일)<br>✅ **완료** | 안전장치<br>(P0-1/P0-4/P0-6/P1-9) | ①시작 시 자동 백업(일 1회, 7개 회전)+설정 화면 "마지막 백업" 라벨·경고 ②`switch_view` 예외 격리(오류 라벨+`log.exception`) ③로그 인증키 마스킹(`SecretMaskingFilter` — 모든 핸들러) ④`user_version=1`+`integrity_check` 실패 시 읽기 전용 게이트 | 실측: `backup/scheduler_20260920.db` 자동 생성, `user_version=1`, app.log에 `serviceKey=***`(`61 tests OK`) |
| **Day 3**<br>09-22(화) | 스키마 확정<br>(P1-1/P1-2) | ①기념일 시드 정정(12건) 후 재시드 ②(✅09-20 선반영) `wordbook` DDL·`add_word`·시드 조건 교정 → **남은 것: 기존 340행 `item_type` 정규화**(실측: `동사` 338 + `명사` 2 → `'단어'`) ③시드/마이그레이션 멱등 테스트 | 기념일 12건·공휴일 플래그 정확, 단어 중복 0, 2회 실행 시 변화 0 |
| **Day 4**<br>09-23(수) | 재입력 도구<br>(P0-5 연계) | ①`Temp/make_schedule_template.py`(엑셀 템플릿) ②고아 이미지 2건 재연결 ③재입력 1차(일정·D-Day) ④증권 CRUD 재검증 | 템플릿→가져오기 왕복 건수 일치, 저장목록 CRUD 예외 0 |
| **Day 5**<br>09-24(목) | 학습<br>(P1-3/P1-4) | ①진도율 위젯 ②`study_progress` 실사용 경로 ③`study_subject_data` 연결/제거 결정 | 진도 입력→재시작 후 유지, 진도율 % = DB 집계 |
| **Day 6**<br>09-25(금) | 뉴스 + 단어<br>(P1-5/P1-6/P1-7) | ①뉴스 소스 4건 교정 ②성공/실패 집계 ③완성 언어 CSV만 임포트 ④(가능 시) 가계부 카테고리·예산 | 교육 카테고리 정합, 임포트 후 단어 중복 0, 미완 언어 제외 확인 |
| **Day 7**<br>09-26(토) | 회귀·릴리스<br>(P1-8/G-1/G-2) | ①`unittest`+스모크+`probe_state`+`moji_probe` ②수동 시나리오 6종 ③문서 갱신 ④`git tag v1.1` | `Temp/regression_0926.json`, 태그 푸시 완료 |

> Day 6까지 P1을 다 못 끝내면 **가계부(P1-7)와 1000단어 완성(P1-5 확장)은 다음 사이클로 넘긴다.** 릴리스(Day 7)는 미루지 않는다.

> **Day 1~2 실측 결과(2026-09-20)**: 테스트 48 → **61건 전부 OK**, `py_compile 25/25 OK`, 실 DB에 `tasks` 6컬럼 + `user_version=1`, `backup/`에 자동 백업(`scheduler_20260920.db`)+베이스라인 동결본, app.log 마스킹 실기록 확인. 다음 착수는 **Day 3(스키마 확정)**.

### 12-4. 데이터 재입력 로드맵 (과거 수치를 목표로 삼지 않는다)

| 우선 | 도메인 | 방법 | 예상 |
|---|---|---|---|
| 1 | 기념일 | **코드 시드(정정본)로 자동** — 손으로 넣지 않는다 | 0분 |
| 1 | 2026-09-19 일정 | 살아 있는 `data/images` 2건을 일간 탭에서 **다시 첨부**(레코드 생성) | 5분 |
| 1 | 일정(과거) | **엑셀 템플릿**(`날짜/일정/저널/이미지`) 채워서 앱에서 가져오기 (이미 왕복 기능 검증 완료) | 30분 |
| 2 | D-Day | 설정 탭에서 직접(2건 수준) | 5분 |
| 2 | 가계부 | 가계부 탭에서 월 1회 입력 습관으로 채움 | 10분/월 |
| 3 | 증권 저장목록·투자일기 | 증권 탭에서 저장(+투자일기 1건) | 10분 |
| 3 | 학습 노트·단어 | 공부 탭에서 직접(필요한 것만) | 상황별 |
| 4 | 단어 대량(1000) | CSV 임포터 신설 후 **완성 언어만**(English 1000 / Japanese 708 / Spanish 101) | 1회 |

> **핵심**: 잃은 5/3/89 같은 "숫자"를 복원하려 애쓰지 않는다. 필요한 것만 다시 쓰고, 나머지는 앞으로의 사용으로 채운다.

### 12-5. 이 기회에 반드시 함께 처리하는 3가지 (재발 방지 겸 리팩터링)

1. **`tasks` DDL + 자기치유 마이그레이션**: 테이블 누락을 코드가 스스로 복구(멱등)하도록 바꾼다. 이번 사고의 직접 원인 제거.
2. **기념일 시드 정정(12건)**: 신정 1/1, 삼일절 3/1, 어린이날 5/5, 현충일 6/6, 광복절 8/15, 개천절 10/3, 한글날 10/9, 기독탄신일 12/25(=공휴일, `is_holiday=1`) + 설날·추석(`type=1`, 1/1·8/15) + 독도의 날 10/26(`is_holiday=0`). 현재 시드는 이름 5건이 손상되고 `is_holiday`가 전건 1이라 달력·리마인더가 틀린 정보를 보여준다.
3. **`user_version=1` + `integrity_check` 게이트 + 시작 자동 백업 + 로그 키 마스킹**: "잃지 않는 앱"으로 만드는 최소 장치.

---

> 문서 상태: **2026-09-20 실측 확정 / 데이터 복구 포기 결정 / Fresh-Start Day 1 착수 대기**
