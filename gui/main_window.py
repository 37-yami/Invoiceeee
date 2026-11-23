# -*- coding: utf-8 -*-
"""主窗口壳:顶栏(标题+工作区切换)、左侧导航、内容页容器。

打开即用:工作区默认放在项目目录下的「工作区」文件夹,自动创建,
不再有首启选择弹窗;想换工作区在「设置」页或顶部下拉里操作。
"""
from __future__ import annotations

import json
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from core.db import Database
from core.workspace import Workspace
from gui.importer import Importer
from gui.theme import COLORS as T
from gui.theme import apply as apply_theme

APP_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path.home() / ".student_invoice_gui.json"
DEFAULT_WS_NAME = "workspace"
LEGACY_WS_NAME = "工作区"  # 旧版默认目录,存在则继续沿用

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False

PAGES = ("overview", "invoices", "stats", "settings")
NAV_LABELS = {"overview": "概 览", "invoices": "票据库", "stats": "统 计",
              "settings": "设 置"}


def _load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_config(cfg: dict) -> None:
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False),
                               encoding="utf-8")
    except OSError:
        pass


def _resolve_workspace(explicit: str | None) -> Path:
    """参数 > 记忆 > 项目根下默认工作区(自动创建,不弹窗)。"""
    if explicit and Path(explicit).exists():
        return Path(explicit)
    remembered = _load_config().get("workspace")
    if remembered and Path(remembered).exists():
        return Path(remembered)
    legacy = APP_DIR / LEGACY_WS_NAME
    if legacy.exists():
        return legacy
    ws = APP_DIR / DEFAULT_WS_NAME
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def launch(workspace: str | None = None) -> None:
    ws_path = _resolve_workspace(workspace)
    _save_config({"workspace": str(ws_path)})
    ws = Workspace(ws_path)
    ws.ensure()
    db = Database(str(ws.db_path))
    db.init_schema()
    app = App(ws, db)
    app.mainloop()
    db.close()


class App(TkinterDnD.Tk if HAS_DND else tk.Tk):
    def __init__(self, ws: Workspace, db: Database):
        super().__init__()
        self.ws = ws
        self.db = db
        self.theme = T
        self.has_pil = HAS_PIL
        self.importer = Importer(ws, db)
        self.queue: queue.Queue = queue.Queue()
        self._importing = False
        self.editing_id = None

        apply_theme(self)
        self.title("学生报销管家")
        self.geometry("1180x720")
        self.minsize(980, 620)
        self.configure(bg=T["dark"])
        self.report_callback_exception = self._report_callback_exception

        self._build_header()
        self._build_body()

        self.show_page("overview")
        self.after(200, self._poll)
        if HAS_DND:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)

    # ---------- 布局 ----------
    def _build_header(self):
        header = tk.Frame(self, bg=T["dark"], height=58)
        header.pack(fill="x")
        header.pack_propagate(False)
        logo = tk.Label(header, text="报", bg=T["accent"], fg="#ffffff",
                        font=("Microsoft YaHei", 11, "bold"), width=2,
                        pady=3)
        logo.pack(side="left", padx=(16, 8), pady=10)
        tk.Label(header, text="学生报销管家", bg=T["dark"],
                 fg=T["text_on_dark"],
                 font=("Microsoft YaHei", 13, "bold")).pack(
            side="left", pady=10)
        self.ws_combo = ttk.Combobox(header, state="readonly", width=30,
                                     font=("Microsoft YaHei", 9))
        self.ws_combo.pack(side="left", padx=18, pady=12)
        self.ws_combo.bind("<<ComboboxSelected>>", self._on_ws_selected)
        self._fill_ws_combo()

    def _fill_ws_combo(self):
        short = self.ws.root.name or str(self.ws.root)
        self._ws_values = [short, "切换 Workspace…", "打开 Workspace 文件夹"]
        self.ws_combo["values"] = self._ws_values
        self.ws_combo.current(0)

    def _on_ws_selected(self, _event=None):
        choice = self.ws_combo.get()
        if choice == "切换 Workspace…":
            folder = filedialog.askdirectory(
                title="选择(或新建)Workspace 文件夹")
            if folder:
                self.switch_workspace(folder)
            else:
                self.ws_combo.current(0)
        elif choice == "打开 Workspace 文件夹":
            from gui.report_dialog import open_folder

            open_folder(self.ws.root)
            self.ws_combo.current(0)

    def switch_workspace(self, folder: str):
        new_ws = Workspace(Path(folder))
        new_ws.ensure()
        self.ws = new_ws
        self.importer = Importer(new_ws, self.db)
        _save_config({"workspace": str(new_ws.root.resolve())})
        self._fill_ws_combo()
        self._status(f"工作区已切换:{new_ws.root}")
        self.pages["invoices"].refresh()
        self.pages["overview"].show()
        self.pages["settings"].show()

    def _build_body(self):
        body = tk.Frame(self, bg=T["dark"])
        body.pack(fill="both", expand=True)

        # 左侧导航
        nav = tk.Frame(body, bg=T["dark"], width=176)
        nav.pack(side="left", fill="y")
        nav.pack_propagate(False)
        tk.Frame(nav, bg=T["dark"], height=16).pack()
        tk.Label(nav, text="菜  单", bg=T["dark"], fg="#565d73",
                 font=("Microsoft YaHei", 8), anchor="w").pack(
            fill="x", padx=22, pady=(4, 2))
        NAV_ICONS = {"overview": "◉", "invoices": "▤", "stats": "▥",
                     "settings": "⚙"}
        self.nav_buttons: dict[str, tk.Button] = {}
        for key in PAGES:
            btn = tk.Button(nav, text=f"{NAV_ICONS[key]}  {NAV_LABELS[key]}",
                            anchor="w", bg=T["dark"],
                            fg=T["text_on_dark"],
                            activebackground=T["dark_active"],
                            activeforeground="#ffffff", relief="flat", bd=0,
                            pady=11, padx=20, font=("Microsoft YaHei", 11),
                            cursor="hand2",
                            command=lambda k=key: self.show_page(k))

            def on_enter(_e, k=key):
                if getattr(self, "_active_page", None) != k:
                    self.nav_buttons[k].config(bg=T["dark_hover"])

            def on_leave(_e, k=key):
                if getattr(self, "_active_page", None) != k:
                    self.nav_buttons[k].config(bg=T["dark"])

            btn.bind("<Enter>", on_enter)
            btn.bind("<Leave>", on_leave)
            btn.pack(fill="x")
            self.nav_buttons[key] = btn

        # 内容区容器
        container = tk.Frame(body, bg=T["bg"])
        container.pack(side="left", fill="both", expand=True)
        self.status_var = tk.StringVar(value="就绪")

        self.pages: dict[str, tk.Frame] = {}
        from gui.page_invoices import InvoicesPage
        from gui.page_overview import OverviewPage
        from gui.page_settings import SettingsPage
        from gui.page_stats import StatsPage

        pages = {
            "overview": OverviewPage(container, self),
            "invoices": InvoicesPage(container, self),
            "stats": StatsPage(container, self),
            "settings": SettingsPage(container, self),
        }
        for page in pages.values():
            page.place(in_=container, x=0, y=0, relwidth=1, relheight=1)
        self.pages = pages

        status = tk.Frame(self, bg=T["dark"], height=26)
        status.pack(fill="x", side="bottom")
        status.pack_propagate(False)
        tk.Label(status, textvariable=self.status_var, bg=T["dark"],
                 fg="#8a90a3", font=("Microsoft YaHei", 9)).pack(
            side="left", padx=12)

    def _status(self, text: str):
        self.status_var.set(text)

    def show_page(self, key: str):
        self._active_page = key
        for name, btn in self.nav_buttons.items():
            if name == key:
                btn.config(bg=T["dark_active"], fg="#ffffff")
            else:
                btn.config(bg=T["dark"], fg=T["text_on_dark"])
        page = self.pages[key]
        page.lift()
        if hasattr(page, "show"):
            page.show()

    def reload_engine(self):
        self.importer = Importer(self.ws, self.db)

    def refresh_background(self):
        self.pages["overview"].show()

    # ---------- 导入 ----------
    def add_files(self):
        from gui.page_invoices import FILETYPES

        paths = filedialog.askopenfilenames(
            title="选择票据图片或 PDF(可多选)", filetypes=FILETYPES)
        if paths:
            self._start_import([Path(p) for p in paths])

    def add_folder(self):
        folder = filedialog.askdirectory(title="选择票据文件夹(递归导入)")
        if not folder:
            return
        files = self.importer.scan_folder(Path(folder))
        if not files:
            self._status("该文件夹没有票据文件")
            return
        self._start_import(files)

    def _reimport(self):
        if self._importing:
            return
        self._importing = True
        self._status("重新识别中……")

        def work():
            try:
                rows = self.importer.reimport_unknown()
            finally:
                self._importing = False
            self.queue.put(("reimported", rows))

        threading.Thread(target=work, daemon=True).start()

    def _start_import(self, paths):
        if self._importing:
            self._status("正在导入,请稍候……")
            return
        self._importing = True
        self._status(f"导入中(共 {len(paths)} 个文件,含识别)……")

        def work():
            try:
                rows = self.importer.import_files(paths)
            finally:
                self._importing = False
            self.queue.put(("imported", rows))

        threading.Thread(target=work, daemon=True).start()

    def _poll(self):
        try:
            while True:
                kind, rows = self.queue.get_nowait()
                if kind == "imported":
                    dups = sum(1 for r in rows if r.dup_flag)
                    self._status(
                        f"已导入 {len(rows)} 张"
                        + (f",疑似重复 {dups} 张(可强制保留)"
                           if dups else ""))
                elif kind == "reimported":
                    self._status(f"重新识别 {len(rows)} 张")
                self.pages["invoices"].refresh()
                self.pages["overview"].show()
        except queue.Empty:
            pass
        self.after(200, self._poll)

    def _on_drop(self, event):
        files: list[Path] = []
        for raw in self.tk.splitlist(event.data):
            p = Path(raw)
            if p.is_dir():
                files.extend(self.importer.scan_folder(p))
            elif p.exists() and p.suffix.lower() in \
                    self.importer.ACCEPTED_EXTS:
                files.append(p)
        if files:
            self.show_page("invoices")
            self._start_import(files)

    # ---------- 异常兜底 ----------
    def _report_callback_exception(self, exc_type, exc_value, tb):
        import traceback

        detail = "".join(
            traceback.format_exception(exc_type, exc_value, tb))[-900:]
        self._status(f"出错了:{exc_value}")
        try:
            messagebox.showerror("出错了", detail, parent=self)
        except Exception:
            pass
