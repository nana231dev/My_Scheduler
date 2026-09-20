# -*- coding: utf-8 -*-
"""일정 편집 팝업 — 10yp_2.py 뷰 분리 1단계로 추출 (2026-09-14).

10yp_2.py의 SchedulerApp이 import해 사용한다. 동작은 추출 전과 동일하다.
"""
import tkinter as tk
import tkinter.ttk as tk_ttk
from tkinter import messagebox

import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, YES, HORIZONTAL
from tkinter.constants import X, Y, LEFT, RIGHT, TOP, BOTTOM


try:
    from ttkbootstrap.widgets import ToastNotification
except ImportError:
    from ttkbootstrap.toast import ToastNotification

try:
    from ttkbootstrap.widgets.scrolled import ScrolledText
except ImportError:
    from ttkbootstrap.scrolled import ScrolledText


class DailyEditor(ttk.Toplevel):
    def __init__(self, parent, date_key, title_str, db, refresh_callback, auto_summary=""):
        super().__init__(parent)
        self.date_key = str(date_key)
        self.db = db
        self.refresh_callback = refresh_callback
        
        self.title(title_str)
        self.geometry("800x600")
        self.place_window_center() 

        frame = ttk.Frame(self, padding=20)
        frame.pack(fill=BOTH, expand=YES)

        saved = self.db.get_schedule(self.date_key)

        if "W-" in self.date_key: 
            ttk.Label(frame, text="주간 일정 요약 (자동 집계)", bootstyle="primary", font=("Malgun Gothic", 12, "bold")).pack(anchor="w", pady=(0, 5))
            txt_auto = ScrolledText(frame, height=10, font=("Malgun Gothic", 10), bootstyle="secondary")
            txt_auto.pack(fill=X, pady=(0, 20))
            txt_auto.insert("1.0", auto_summary)
            txt_auto.text.configure(state="disabled")

            ttk.Label(frame, text="주간 목표 및 메모 (직접 입력)", bootstyle="success", font=("Malgun Gothic", 12, "bold")).pack(anchor="w", pady=(0, 5))
            self.txt_sch = ScrolledText(frame, height=10, font=("Malgun Gothic", 10), bootstyle="success")
            self.txt_sch.pack(fill=BOTH, expand=YES)
            self.txt_sch.insert("1.0", saved["schedule"])
            self.txt_jnl = None
            
        else:
            paned = tk_ttk.PanedWindow(frame, orient=HORIZONTAL)
            paned.pack(fill=BOTH, expand=YES, pady=(0, 10))

            frame_left = ttk.Labelframe(paned, text=" 📝 일정 (Schedule) ", padding=10, bootstyle="info")
            paned.add(frame_left, weight=1)
            
            self.txt_sch = ScrolledText(frame_left, font=("Malgun Gothic", 11), height=15, bootstyle="info")
            self.txt_sch.pack(fill=BOTH, expand=YES)
            self.txt_sch.insert("1.0", saved["schedule"])

            frame_right = ttk.Labelframe(paned, text=" 📖 일지/비고 (Journal) ", padding=10, bootstyle="secondary")
            paned.add(frame_right, weight=1)
            
            self.txt_jnl = ScrolledText(frame_right, font=("Malgun Gothic", 11), height=15, bootstyle="secondary")
            self.txt_jnl.pack(fill=BOTH, expand=YES)
            self.txt_jnl.insert("1.0", saved["journal"])

        btn_box = ttk.Frame(frame)
        btn_box.pack(fill=X, pady=10)
        
        ttk.Button(btn_box, text="저장 (Save)", bootstyle="success", command=self.save).pack(side=RIGHT, padx=5)
        ttk.Button(btn_box, text="삭제 (Delete)", bootstyle="danger-outline", command=self.delete).pack(side=RIGHT, padx=5)
        ttk.Button(btn_box, text="닫기 (Close)", bootstyle="secondary-outline", command=self.destroy).pack(side=RIGHT, padx=5)

    def save(self):
        sch_text = self.txt_sch.get("1.0", "end-1c")
        jnl_text = self.txt_jnl.get("1.0", "end-1c") if self.txt_jnl else ""
        self.db.set_schedule(self.date_key, sch_text, jnl_text)
        
        toast = ToastNotification(
            title="저장 완료",
            message=f"{self.date_key} 데이터가 저장되었습니다.",
            duration=2000,
            bootstyle="success",
            position=(50, 50, "ne")
        )
        toast.show_toast()
        self.refresh_callback()
        self.destroy()

    def delete(self):
        if messagebox.askyesno("삭제 확인", "정말 삭제하시겠습니까?"):
            self.db.delete_schedule(self.date_key)
            self.refresh_callback()
            self.destroy()
