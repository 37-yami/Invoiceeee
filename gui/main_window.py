# -*- coding: utf-8 -*-
"""主窗口壳:无边框自绘标题栏 + 玻璃分区 + 全景壁纸 + 页面容器。

- 整窗无系统边框,标题栏与壁纸融为一体(壁纸缺失时回退深色)
- 顶栏/侧栏/状态栏 = 壁纸对应区域加深后的"玻璃",与内容区分明
- 支持拖动移动、双击最大化、右下角与边缘缩放
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
LEGACY_WS_NAME = "工作区"

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
NAV_ICONS = {"overview": "◉", "invoices": "▤", "stats": "▥", "settings": "⚙"}
HEADER_H = 58
NAV_W = 178
STATUS_H = 30
CHROME_DARK = "#14161f"  # 无壁纸时的玻璃兜底色


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
        self._active_page = None
        self._wallpaper_labels: list[tk.Label] = []
        self._cards: list = []
        self._wallpaper_photo = None
        self._glass_photos: dict[str, object] = {}
        self._wallpaper_job = None

        apply_theme(self)
        self.title("学生报销管家")
        self.geometry("1180x720")
        self.minsize(980, 620)
        self.configure(bg=T["dark"])
        self.report_callback_exception = self._report_callback_exception

        self._go_frameless()
        self._build_titlebar()
        self._build_body()
        self._build_resize_grips()

        self.show_page("overview")
        self.after(200, self._poll)
        self.after(120, self._redraw_wallpaper)
        self.bind("<Configure>", self._on_resize_wallpaper)
        if HAS_DND:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)

    # ---------- 无边框窗口 ----------
    def _go_frameless(self):
        try:
            self.overrideredirect(True)
        except Exception:
            pass

    def _window_buttons(self, parent):
        """自绘 最小化/最大化/关闭。"""
        specs = [("✕", self.destroy, "btn_close"),
                 ("▢", self._toggle_max, "btn_max"),
                 ("—", self.iconify, "btn_min")]  # 逆序 pack(side=right)
        for text, cmd, key in specs:
            b = tk.Label(parent, text=text, bg=T["dark"],
                         fg=T["text_muted"], font=("Segoe UI", 10),
                         width=4, cursor="hand2")
            b.pack(side="right", fill="y")
            b.bind("<Button-1>", lambda e, c=cmd: c())
            enter_fg = "#ff6b6b" if key == "btn_close" else "#ffffff"
            b.bind("<Enter>", lambda e, w=b: w.config(fg=enter_fg))
            b.bind("<Leave>", lambda e, w=b: w.config(fg=T["text_muted"]))

    def _toggle_max(self):
        try:
            if self.state() == "zoomed":
                self.state("normal")
            else:
                self.state("zoomed")
        except Exception:
            pass

    def _drag_start(self, event):
        self._drag_pos = (event.x_root, event.y_root,
                          self.winfo_x(), self.winfo_y())

    def _drag_move(self, event):
        if not getattr(self, "_drag_pos", None):
            return
        px, py, wx, wy = self._drag_pos
        dx, dy = event.x_root - px, event.y_root - py
        try:
            self.geometry(f"+{wx + dx}+{wy + dy}")
        except Exception:
            pass

    def _drag_end(self, _event):
        self._drag_pos = None

    def _build_titlebar(self):
        bar = tk.Frame(self, bg=T["dark"], height=HEADER_H)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        # 玻璃底层(壁纸裁剪)
        self._titlebar_glass = tk.Label(bar, bg=T["dark"])
        self._titlebar_glass.place(x=0, y=0, relwidth=1, relheight=1)

        drag = tk.Frame(bar, bg="")
        drag.place(x=0, y=0, relwidth=1, relheight=1)
        for ev in ("<Button-1>",):
            drag.bind(ev, self._drag_start)
        drag.bind("<B1-Motion>", self._drag_move)
        drag.bind("<ButtonRelease-1>", self._drag_end)
        drag.bind("<Double-Button-1>", lambda _e: self._toggle_max())

        logo = tk.Label(drag, text="报", bg=T["accent"], fg="#ffffff",
                        font=("Microsoft YaHei", 11, "bold"), width=2,
                        pady=3, cursor="fleur")
        logo.pack(side="left", padx=(16, 8), pady=10)
        title = tk.Label(drag, text="学生报销管家", bg=T["dark"],
                         fg=T["text_on_dark"],
                         font=("Microsoft YaHei", 13, "bold"), cursor="fleur")
        title.pack(side="left", pady=10)

        self.ws_combo = ttk.Combobox(bar, state="readonly", width=30,
                                     font=("Microsoft YaHei", 9))
        self.ws_combo.place(x=300, rely=0.5, anchor="w")
        self.ws_combo.bind("<<ComboboxSelected>>", self._on_ws_selected)
        self._fill_ws_combo()

        self._window_buttons(bar)

    def _build_resize_grips(self):
        """边缘缩放手柄:右/下/右下。"""
        size = 6
        grip_opts = dict(bg=T["dark"])
        right = tk.Frame(self, width=size, cursor="sb_h_double_arrow",
                         **grip_opts)
        right.place(relx=1.0, y=HEADER_H, anchor="ne",
                    relheight=1, height=-HEADER_H)
        bottom = tk.Frame(self, height=size, cursor="sb_v_double_arrow",
                          **grip_opts)
        bottom.place(relx=0.0, rely=1.0, y=-size, relwidth=1.0,
                     x=int(size), anchor="sw")
        corner = tk.Frame(self, width=size * 2, height=size * 2,
                          cursor="size_nw_se", **grip_opts)
        corner.place(relx=1.0, rely=1.0, anchor="se")

        for widget, mode in ((right, "x"), (bottom, "y"), (corner, "xy")):
            widget.bind("<Button-1>", lambda e, m=mode: self._rz_start(e, m))
            widget.bind("<B1-Motion>", self._rz_move)

    def _rz_start(self, event, mode):
        self._rz = {"mode": mode, "x": event.x_root, "y": event.y_root,
                    "w": self.winfo_width(), "h": self.winfo_height()}

    def _rz_move(self, event):
        info = getattr(self, "_rz", None)
        if not info:
            return
        dx = event.x_root - info["x"]
        dy = event.y_root - info["y"]
        w = max(980, info["w"] + dx) if "x" in info["mode"] else info["w"]
        h = max(620, info["h"] + dy) if "y" in info["mode"] else info["h"]
        try:
            self.geometry(f"{w}x{h}")
        except Exception:
            pass

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
        self._status(f"Workspace 已切换:{new_ws.root}")
        self.pages["invoices"].refresh()
        self.pages["overview"].show()
        self.pages["settings"].show()

    def _build_body(self):
        body = tk.Frame(self, bg=T["dark"])
        body.pack(fill="both", expand=True)

        # 左侧导航(玻璃)
        nav = tk.Frame(body, bg=T["dark"], width=NAV_W)
        nav.pack(side="left", fill="y")
        nav.pack_propagate(False)
        self._nav_glass = tk.Label(nav, bg=T["dark"])
        self._nav_glass.place(x=0, y=0, relwidth=1, relheight=1)

        tk.Frame(nav, bg=T["dark"], height=18).pack()
        tk.Label(nav, text="菜  单", bg=T["dark"], fg="#5c6178",
                 font=("Microsoft YaHei", 8), anchor="w").pack(
            fill="x", padx=22, pady=(4, 4))
        self.nav_buttons: dict[str, tk.Button] = {}
        for key in PAGES:
            btn = tk.Button(nav, text=f"{NAV_ICONS[key]}  {NAV_LABELS[key]}",
                            anchor="w", bg=T["dark"],
                            fg=T["text_on_dark"],
                            activebackground=T["dark_active"],
                            activeforeground="#ffffff", relief="flat", bd=0,
                            pady=10, padx=18, font=("Microsoft YaHei", 11),
                            cursor="hand2",
                            command=lambda k=key: self.show_page(k))

            def on_enter(_e, k=key):
                if self._active_page != k:
                    self.nav_buttons[k].config(bg=T["dark_hover"])

            def on_leave(_e, k=key):
                if self._active_page != k:
                    self.nav_buttons[k].config(bg=T["dark"])

            btn.bind("<Enter>", on_enter)
            btn.bind("<Leave>", on_leave)
            btn.pack(fill="x", padx=10, pady=3)
            self.nav_buttons[key] = btn

        # 内容区容器
        container = tk.Frame(body, bg=T["bg"])
        container.pack(side="left", fill="both", expand=True)

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

        # 状态栏(玻璃)
        status = tk.Frame(self, bg=T["dark"], height=STATUS_H)
        status.pack(fill="x", side="bottom")
        status.pack_propagate(False)
        self._status_glass = tk.Label(status, bg=T["dark"])
        self._status_glass.place(x=0, y=0, relwidth=1, relheight=1)
        self.status_var = tk.StringVar(value="就绪")
        tk.Label(status, textvariable=self.status_var, bg=T["dark"],
                 fg="#7c8296", font=("Microsoft YaHei", 9)).pack(
            side="left", padx=12, pady=4)

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
        self._redraw_wallpaper()

    # ---------- 全景壁纸与玻璃 ----------
    def attach_wallpaper(self, page) -> tk.Label:
        """给页面垫壁纸层(必须在该页创建其他子元素之前调用)。"""
        label = tk.Label(page, bg=T["bg"])
        label.place(x=0, y=0, relwidth=1, relheight=1)
        self._wallpaper_labels.append(label)
        return label

    def register_card(self, card) -> None:
        self._cards.append(card)

    def _on_resize_wallpaper(self, _event):
        if self._wallpaper_job:
            self.after_cancel(self._wallpaper_job)
        self._wallpaper_job = self.after(300, self._redraw_wallpaper)

    def _wallpaper_source(self) -> Path | None:
        custom = self.db.get_setting("background_image")
        if custom and Path(custom).exists():
            return Path(custom)
        built_in = APP_DIR / "assets" / "default_bg.png"
        return built_in if built_in.exists() else None

    def _redraw_wallpaper(self):
        w = max(self.winfo_width(), 980)
        h = max(self.winfo_height(), 620)
        source = self._wallpaper_source()
        if not (source and self.has_pil):
            self._apply_no_wallpaper()
            return
        try:
            img = Image.open(source).convert("RGB")
            ratio = max(w / img.width, h / img.height)
            img = img.resize((int(img.width * ratio) + 1,
                              int(img.height * ratio) + 1))
            # 居中裁到窗口尺寸
            x0 = max(0, (img.width - w) // 2)
            y0 = max(0, (img.height - h) // 2)
            img = img.crop((x0, y0, x0 + w, y0 + h))

            self._wallpaper_photo = self._mk_photo(img, 0.32)
            for label in self._wallpaper_labels:
                label.config(image=self._wallpaper_photo)
            # 玻璃区:标题栏/侧栏/状态栏(更深,保证可读与分区感)
            self._glass_photos["titlebar"] = self._mk_photo(
                img.crop((0, 0, w, HEADER_H)), 0.74)
            self._titlebar_glass.config(
                image=self._glass_photos["titlebar"])
            self._glass_photos["nav"] = self._mk_photo(
                img.crop((0, HEADER_H, NAV_W, h - STATUS_H)), 0.68)
            self._nav_glass.config(image=self._glass_photos["nav"])
            self._glass_photos["status"] = self._mk_photo(
                img.crop((0, h - STATUS_H, w, h)), 0.78)
            self._status_glass.config(image=self._glass_photos["status"])
            self.after_idle(self._refresh_cards)
        except Exception:
            self._apply_no_wallpaper()

    @staticmethod
    def _mk_photo(img: "Image.Image", dim: float):
        overlay = Image.new("RGB", img.size, "#14161f")
        return ImageTk.PhotoImage(Image.blend(img, overlay, dim))

    def _apply_no_wallpaper(self):
        self._wallpaper_photo = None
        for label in self._wallpaper_labels:
            label.config(image="", bg=T["bg"])
        for glass in (self._titlebar_glass, self._nav_glass,
                      self._status_glass):
            glass.config(image="", bg=CHROME_DARK)
        self.after_idle(self._refresh_cards)

    def _refresh_cards(self):
        for card in self._cards:
            try:
                card.refresh_wallpaper(self._wallpaper_photo)
            except Exception:
                pass

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
