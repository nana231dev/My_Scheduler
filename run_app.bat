@echo off
rem ── My_Scheduler 실행 (2026-09-14) ──
rem 콘솔 한글 깨짐 방지: 코드페이지 UTF-8 + 파이썬 I/O 인코딩 고정
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d %~dp0
python 10yp_2.py
