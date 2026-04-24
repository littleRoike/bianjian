# -*- coding: utf-8 -*-
"""
极简悬浮便笺 Sticky Note
纯 Python + Tkinter 实现，无第三方依赖，可打包为独立 EXE。
"""

import os
import re
import sys
import json
import base64
import threading
import tkinter as tk
from tkinter import ttk, colorchooser, filedialog, messagebox

# 系统托盘（可选；未安装时自动降级为直接退出）
try:
    import pystray
    from PIL import Image, ImageDraw
    _HAS_TRAY = True
except Exception:
    _HAS_TRAY = False

# ------------------------------------------------------------
# 常量
# ------------------------------------------------------------
UNCHECKED = "\u2610"  # ☐
CHECKED = "\u2611"    # ☑

# 字体族
FONT_FAMILY = "Microsoft YaHei UI"
FONT_SIZE = 11

# 配色（极简清爽）
COLOR_BG = "#ffffff"
COLOR_FG = "#3c3c3c"
COLOR_SUBTLE = "#8a8a8a"
COLOR_MUTED = "#b5b5b5"
COLOR_BORDER = "#e6e6e6"
COLOR_TOOLBAR_BG = "#fafafa"
COLOR_BTN_HOVER = "#eef1f5"
COLOR_HIGHLIGHT = "#fff2a8"
COLOR_SELECT = "#d8d8d8"          # 统一为柔和灰色选中
COLOR_MENU_SEP = "#ececec"
COLOR_TOOLTIP_BG = "#2b2b2b"
COLOR_TOOLTIP_FG = "#ffffff"

# 任务优先级：背景色 (淡色用于整行)、点色 (深色用于菜单圆点标记)
PRIORITY_ORDER = ("urgent", "high", "normal", "low")
PRIORITY_LABELS = {
    "urgent": "紧急",
    "high": "较高",
    "normal": "普通",
    "low": "较低",
}
PRIORITY_BG = {
    "urgent": "#ffd9d9",
    "high":   "#ffe5c2",
    "normal": "#dbe7ff",
    "low":    "#ececec",
}
PRIORITY_DOT = {
    "urgent": "#e05858",
    "high":   "#e89548",
    "normal": "#5b83de",
    "low":    "#9a9a9a",
}
DEFAULT_PRIORITY = "none"         # 未选优先级 = 无色
# 排序权重（数字越小越靠前）；未选优先级排在最末尾
PRIORITY_RANK = {"urgent": 0, "high": 1, "normal": 2, "low": 3, "none": 4}

# 窗口初始尺寸
INIT_W, INIT_H = 360, 500
MIN_W, MIN_H = 260, 280

# 贴边隐藏
HIDE_STRIP = 4  # 隐藏后露出的像素


def get_data_dir() -> str:
    """获取数据目录（exe/脚本所在目录）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


SAVE_MD = os.path.join(get_data_dir(), "notes.md")
SAVE_JSON = os.path.join(get_data_dir(), "notes.json")
CONFIG_FILE = os.path.join(get_data_dir(), "config.json")


# ------------------------------------------------------------
# 扁平菜单（替代 tk.Menu 以统一风格）
# ------------------------------------------------------------
class FlatMenu:
    """极简扁平菜单：无系统边框、纯白底、hover 灰色、1px 边线。

    支持每项带"主文案 + 快捷键提示"两栏对齐。
    """

    def __init__(self, master, min_width=220):
        self.master = master
        self.min_width = min_width
        self.items = []  # [("cmd", label, cmd, shortcut) | ("sep", None, None, None)]
        self._win = None

    def add_command(self, label, command, shortcut="", dot_color=None):
        self.items.append(("cmd", label, command, shortcut, dot_color))
        return self

    def add_separator(self):
        self.items.append(("sep", None, None, None, None))
        return self

    def clear(self):
        self.items = []

    def close(self):
        if self._win is not None:
            try:
                self._win.destroy()
            except Exception:
                pass
            self._win = None

    def popup(self, x, y):
        self.close()
        win = tk.Toplevel(self.master)
        win.wm_overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=COLOR_BORDER)

        inner = tk.Frame(win, bg=COLOR_BG)
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        tk.Frame(inner, bg=COLOR_BG, height=4).pack(fill="x")

        for item in self.items:
            kind = item[0]
            if kind == "sep":
                wrap = tk.Frame(inner, bg=COLOR_BG)
                wrap.pack(fill="x", pady=4)
                tk.Frame(wrap, bg=COLOR_MENU_SEP, height=1).pack(fill="x", padx=10)
                continue

            _k, label, cmd, shortcut, dot_color = item

            row = tk.Frame(inner, bg=COLOR_BG, cursor="hand2")
            row.pack(fill="x", padx=4)

            widgets = [row]

            # 可选彩色圆点前缀
            dot_lbl = None
            if dot_color:
                dot_lbl = tk.Label(
                    row,
                    text="\u25CF",
                    bg=COLOR_BG,
                    fg=dot_color,
                    font=(FONT_FAMILY, 10),
                    padx=14,
                    pady=6,
                )
                dot_lbl.pack(side="left")
                widgets.append(dot_lbl)

            main_lbl = tk.Label(
                row,
                text=label,
                bg=COLOR_BG,
                fg=COLOR_FG,
                anchor="w",
                font=(FONT_FAMILY, 10),
                padx=0 if dot_lbl else 16,
                pady=6,
            )
            main_lbl.pack(side="left", fill="x", expand=True)
            widgets.append(main_lbl)

            if shortcut:
                sc_lbl = tk.Label(
                    row,
                    text=shortcut,
                    bg=COLOR_BG,
                    fg=COLOR_MUTED,
                    anchor="e",
                    font=(FONT_FAMILY, 9),
                    padx=16,
                    pady=6,
                )
                sc_lbl.pack(side="right")
                widgets.append(sc_lbl)

            self._bind_row(widgets, cmd)

        tk.Frame(inner, bg=COLOR_BG, height=4).pack(fill="x")

        # 尺寸：至少 min_width
        win.update_idletasks()
        w = max(self.min_width, win.winfo_reqwidth())
        h = win.winfo_reqheight()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        x = min(x, sw - w - 4)
        y = min(y, sh - h - 4)
        win.geometry(f"{w}x{h}+{x}+{y}")

        self._win = win
        win.bind("<FocusOut>", lambda _e: self.close())
        win.bind("<Escape>", lambda _e: self.close())
        win.focus_force()

    def _bind_row(self, widgets, cmd):
        def enter(_e):
            for w in widgets:
                w.configure(bg=COLOR_BTN_HOVER)

        def leave(_e):
            for w in widgets:
                w.configure(bg=COLOR_BG)

        def click(_e):
            self.close()
            if cmd:
                cmd()

        for w in widgets:
            w.bind("<Enter>", enter)
            w.bind("<Leave>", leave)
            w.bind("<Button-1>", click)


# ------------------------------------------------------------
# 扁平对话框（替代系统对话框以统一风格）
# ------------------------------------------------------------
class FlatDialog(tk.Toplevel):
    """极简扁平对话框：无边框、单 1px 边线、统一字体与按钮。"""

    def __init__(self, master, title="", width=280):
        super().__init__(master)
        self.wm_overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=COLOR_BORDER)
        self.result = None
        self._drag = {"x": 0, "y": 0}

        outer = tk.Frame(self, bg=COLOR_BG)
        outer.pack(fill="both", expand=True, padx=1, pady=1)

        header = tk.Frame(outer, bg=COLOR_BG, height=34)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header,
            text=title,
            bg=COLOR_BG,
            fg=COLOR_FG,
            font=(FONT_FAMILY, 10),
            padx=14,
        ).pack(side="left")

        close_btn = tk.Label(
            header,
            text="\u2715",
            bg=COLOR_BG,
            fg=COLOR_SUBTLE,
            font=(FONT_FAMILY, 12),
            padx=10,
            cursor="hand2",
        )
        close_btn.pack(side="right")
        close_btn.bind("<Enter>", lambda _e: close_btn.configure(bg=COLOR_BTN_HOVER, fg=COLOR_FG))
        close_btn.bind("<Leave>", lambda _e: close_btn.configure(bg=COLOR_BG, fg=COLOR_SUBTLE))
        close_btn.bind("<Button-1>", lambda _e: self.close())

        for w in (header,):
            w.bind("<ButtonPress-1>", self._start_move)
            w.bind("<B1-Motion>", self._do_move)

        tk.Frame(outer, bg=COLOR_MENU_SEP, height=1).pack(fill="x")

        self.body = tk.Frame(outer, bg=COLOR_BG)
        self.body.pack(fill="both", expand=True, padx=16, pady=14)

        self._width_hint = width
        self.bind("<Escape>", lambda _e: self.close())

    def _start_move(self, event):
        self._drag["x"] = event.x_root - self.winfo_x()
        self._drag["y"] = event.y_root - self.winfo_y()

    def _do_move(self, event):
        x = event.x_root - self._drag["x"]
        y = event.y_root - self._drag["y"]
        self.geometry(f"+{x}+{y}")

    def place_near(self, master):
        self.update_idletasks()
        w = max(self._width_hint, self.winfo_reqwidth())
        h = self.winfo_reqheight()
        x = master.winfo_rootx() + 30
        y = master.winfo_rooty() + 60
        self.geometry(f"{w}x{h}+{x}+{y}")

    def close(self):
        try:
            self.destroy()
        except Exception:
            pass


def flat_button(parent, text, command, primary=False):
    """与风格一致的扁平按钮。"""
    bg = COLOR_FG if primary else COLOR_BTN_HOVER
    fg = "#ffffff" if primary else COLOR_FG
    hover = "#555555" if primary else "#dde1e7"
    btn = tk.Label(
        parent,
        text=text,
        bg=bg,
        fg=fg,
        font=(FONT_FAMILY, 10),
        padx=16,
        pady=5,
        cursor="hand2",
    )
    btn.bind("<Enter>", lambda _e: btn.configure(bg=hover))
    btn.bind("<Leave>", lambda _e: btn.configure(bg=bg))
    btn.bind("<Button-1>", lambda _e: command())
    return btn


def flat_messagebox(master, title, message, kind="info"):
    """替换 tkinter.messagebox.showinfo/askyesno 的极简版本。

    kind: info | yesno
    返回：yesno -> True/False；info -> None
    """
    dlg = FlatDialog(master, title=title, width=300)
    tk.Label(
        dlg.body,
        text=message,
        bg=COLOR_BG,
        fg=COLOR_FG,
        font=(FONT_FAMILY, 10),
        justify="left",
        wraplength=320,
    ).pack(anchor="w", pady=(0, 14))

    result = {"value": None}
    btn_row = tk.Frame(dlg.body, bg=COLOR_BG)
    btn_row.pack(fill="x")

    if kind == "yesno":
        def on_no():
            result["value"] = False
            dlg.close()

        def on_yes():
            result["value"] = True
            dlg.close()

        flat_button(btn_row, "取消", on_no).pack(side="right", padx=(6, 0))
        flat_button(btn_row, "确定", on_yes, primary=True).pack(side="right")
    else:
        flat_button(btn_row, "知道了", dlg.close, primary=True).pack(side="right")

    dlg.place_near(master)
    dlg.focus_force()
    dlg.grab_set()
    master.wait_window(dlg)
    return result["value"]


# ------------------------------------------------------------
# 主类
# ------------------------------------------------------------
class StickyNote:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("便笺")

        # 无边框
        self.root.overrideredirect(True)

        # 基础样式
        self.root.configure(bg=COLOR_BORDER)

        # 读取配置
        self.config = self._load_config()
        geo = self.config.get("geometry", f"{INIT_W}x{INIT_H}+240+160")
        self.root.geometry(geo)
        self.root.minsize(MIN_W, MIN_H)

        self.pinned = self.config.get("pinned", True)
        self.transparency = float(self.config.get("transparency", 1.0))
        self.highlight_color = self.config.get("highlight_color", COLOR_HIGHLIGHT)

        self.root.attributes("-topmost", self.pinned)
        self.root.attributes("-alpha", self.transparency)

        # 任务栏显示（可选：overrideredirect会让窗口不出现在任务栏，需特殊处理）
        self.root.after(10, self._register_taskbar)

        # 状态变量
        self._drag_data = {"x": 0, "y": 0}
        self._resize_data = {"x": 0, "y": 0, "w": 0, "h": 0}
        self._saving_job = None
        self._reorder_job = None
        self._reordering = False
        self._click_lock = False
        self._press_info = None  # {"x", "y", "line", "col", "dragged"}
        self._minimize_pending_restore = False
        self._hide_state = "visible"  # visible / hidden / animating
        self._hide_edge = None  # "left"
        self._edge_check_job = None
        self._visible = True
        self._tray_icon = None

        self._build_ui()
        self._bind_events()
        self._load_notes()

        # 定时检查贴边
        self._schedule_edge_check()

        # 窗口关闭协议：改为"隐藏到托盘"
        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)

        # 启动系统托盘图标（后台线程）
        self._setup_tray()

    # --------------------------------------------------------
    # 配置
    # --------------------------------------------------------
    def _load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_config(self):
        try:
            data = {
                "geometry": self.root.geometry(),
                "pinned": self.pinned,
                "transparency": self.transparency,
                "highlight_color": self.highlight_color,
            }
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _register_taskbar(self):
        """让无边框窗口仍能出现在任务栏（Windows）。"""
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            GWL_EXSTYLE = -20
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_TOOLWINDOW = 0x00000080
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style = style & ~WS_EX_TOOLWINDOW
            style = style | WS_EX_APPWINDOW
            self.root.withdraw()
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            self.root.after(10, self.root.deiconify)
        except Exception:
            pass

    # --------------------------------------------------------
    # UI 构建
    # --------------------------------------------------------
    def _build_ui(self):
        # 外层：1px 边框
        outer = tk.Frame(self.root, bg=COLOR_BORDER)
        outer.pack(fill="both", expand=True)
        container = tk.Frame(outer, bg=COLOR_BG)
        container.pack(fill="both", expand=True, padx=1, pady=1)
        self.container = container

        # 顶栏
        self.top_bar = tk.Frame(container, bg=COLOR_BG, height=38)
        self.top_bar.pack(fill="x", side="top")
        self.top_bar.pack_propagate(False)

        left = tk.Frame(self.top_bar, bg=COLOR_BG)
        left.pack(side="left", padx=6)
        self._icon_btn(left, "\u002B", self.new_task_top, tip="新建任务", size=18).pack(side="left", padx=1)
        self._icon_btn(left, "\u22EF", self.show_more_menu, tip="更多", size=18).pack(side="left", padx=1)

        right = tk.Frame(self.top_bar, bg=COLOR_BG)
        right.pack(side="right", padx=6)
        self.pin_btn = self._icon_btn(right, self._pin_icon(), self.toggle_pin, tip="置顶", size=13)
        self.pin_btn.pack(side="left", padx=1)
        self._icon_btn(right, "\u2013", self.minimize_window,
                       tip="最小化", size=14).pack(side="left", padx=1)
        self._icon_btn(right, "\u2715", self.hide_to_tray,
                       tip="隐藏到托盘 (右下角角标)",
                       size=14, hover=COLOR_BTN_HOVER).pack(side="left", padx=1)

        # 顶栏用作拖动
        for w in (self.top_bar,):
            w.bind("<ButtonPress-1>", self._start_move)
            w.bind("<B1-Motion>", self._do_move)
            w.bind("<Double-Button-1>", lambda e: None)

        # 编辑区
        text_frame = tk.Frame(container, bg=COLOR_BG)
        text_frame.pack(fill="both", expand=True)

        self.text = tk.Text(
            text_frame,
            wrap="word",
            bd=0,
            relief="flat",
            font=(FONT_FAMILY, FONT_SIZE),
            padx=18,
            pady=10,
            bg=COLOR_BG,
            fg=COLOR_FG,
            insertbackground=COLOR_FG,
            insertwidth=1,
            selectbackground=COLOR_SELECT,
            selectforeground=COLOR_FG,
            spacing1=2,
            spacing3=6,
            highlightthickness=0,
            cursor="xterm",
            undo=True,
        )
        self.text.pack(fill="both", expand=True, padx=0, pady=0)

        # tag 配置
        # 先配置优先级背景 tag —— 之后的 tag 优先级天然更高，可覆盖它的背景色
        for prio in PRIORITY_ORDER:
            self.text.tag_configure(
                f"prio_{prio}", background=PRIORITY_BG[prio]
            )

        self.text.tag_configure("bold", font=(FONT_FAMILY, FONT_SIZE, "bold"))
        self.text.tag_configure("italic", font=(FONT_FAMILY, FONT_SIZE, "italic"))
        self.text.tag_configure("underline", underline=True)
        self.text.tag_configure("strike", overstrike=True)
        self.text.tag_configure("highlight", background=self.highlight_color)
        self.text.tag_configure("done", overstrike=True, foreground=COLOR_MUTED)
        self.text.tag_configure("checkbox", foreground=COLOR_SUBTLE)
        self.text.tag_configure("checkbox_done", foreground=COLOR_MUTED)

        # 让选中（sel）优先级最高，覆盖 highlight / done 的背景/前景色
        # 否则高亮文字被选中时看不到选中效果
        self.text.tag_configure(
            "sel",
            background=COLOR_SELECT,
            foreground=COLOR_FG,
        )
        self.text.tag_raise("sel")

        # 底部工具栏
        self.bottom_bar = tk.Frame(container, bg=COLOR_TOOLBAR_BG, height=38)
        self.bottom_bar.pack(fill="x", side="bottom")
        self.bottom_bar.pack_propagate(False)

        sep = tk.Frame(self.bottom_bar, bg=COLOR_BORDER, height=1)
        sep.pack(fill="x", side="top")

        tools = tk.Frame(self.bottom_bar, bg=COLOR_TOOLBAR_BG)
        tools.pack(side="left", padx=6, pady=0)

        self._tool_btn(tools, "B", lambda: self.toggle_tag("bold"),
                       font=(FONT_FAMILY, FONT_SIZE, "bold"), tip="加粗 Ctrl+B").pack(side="left", padx=1)
        self._tool_btn(tools, "I", lambda: self.toggle_tag("italic"),
                       font=(FONT_FAMILY, FONT_SIZE, "italic"), tip="斜体 Ctrl+I").pack(side="left", padx=1)
        self._tool_btn(tools, "U", lambda: self.toggle_tag("underline"),
                       font=(FONT_FAMILY, FONT_SIZE, "underline"), tip="下划线 Ctrl+U").pack(side="left", padx=1)
        self._tool_btn(tools, "\u0053\u0336", lambda: self.toggle_tag("strike"),
                       tip="删除线").pack(side="left", padx=1)
        self._tool_btn(tools, "\u2630", self.toggle_task_lines,
                       tip="切换任务 Ctrl+L").pack(side="left", padx=1)
        self._tool_btn(tools, "\U0001F5BC", self.insert_image,
                       tip="插入图片").pack(side="left", padx=1)
        self._tool_btn(tools, "H", lambda: self.toggle_tag("highlight"),
                       tip="高亮 Ctrl+H",
                       bg_override=self.highlight_color).pack(side="left", padx=1)

        # 右下角 resize 手柄
        grip = tk.Canvas(self.bottom_bar, bg=COLOR_TOOLBAR_BG,
                         width=16, height=16, highlightthickness=0,
                         cursor="size_nw_se")
        for i in range(3):
            for j in range(3):
                if i + j >= 2:
                    grip.create_rectangle(3 + i * 4, 3 + j * 4,
                                          4 + i * 4, 4 + j * 4,
                                          fill=COLOR_MUTED, outline="")
        grip.pack(side="right", padx=4, pady=4)
        grip.bind("<ButtonPress-1>", self._start_resize)
        grip.bind("<B1-Motion>", self._do_resize)

        # 右键菜单（自定义扁平风格）—— 全部功能一次性展开
        self.ctx_menu = FlatMenu(self.root, min_width=240)
        # 优先级（带颜色圆点）
        self.ctx_menu.add_command(
            "紧急", lambda: self.set_current_priority("urgent"),
            dot_color=PRIORITY_DOT["urgent"])
        self.ctx_menu.add_command(
            "较高", lambda: self.set_current_priority("high"),
            dot_color=PRIORITY_DOT["high"])
        self.ctx_menu.add_command(
            "普通", lambda: self.set_current_priority("normal"),
            dot_color=PRIORITY_DOT["normal"])
        self.ctx_menu.add_command(
            "较低", lambda: self.set_current_priority("low"),
            dot_color=PRIORITY_DOT["low"])
        self.ctx_menu.add_command(
            "无 (默认)", lambda: self.set_current_priority("none"),
            dot_color=COLOR_MUTED)
        self.ctx_menu.add_separator()
        self.ctx_menu.add_command("切换任务 / 增删复选框", self.toggle_task_lines, "Ctrl+L")
        self.ctx_menu.add_command("删除此行", self.delete_current_line)
        self.ctx_menu.add_separator()
        self.ctx_menu.add_command("加粗", lambda: self.toggle_tag("bold"), "Ctrl+B")
        self.ctx_menu.add_command("斜体", lambda: self.toggle_tag("italic"), "Ctrl+I")
        self.ctx_menu.add_command("下划线", lambda: self.toggle_tag("underline"), "Ctrl+U")
        self.ctx_menu.add_command("删除线", lambda: self.toggle_tag("strike"))
        self.ctx_menu.add_command("高亮", lambda: self.toggle_tag("highlight"), "Ctrl+H")
        self.ctx_menu.add_separator()
        self.ctx_menu.add_command("剪切", self._do_cut, "Ctrl+X")
        self.ctx_menu.add_command("复制", self._do_copy, "Ctrl+C")
        self.ctx_menu.add_command("粘贴", lambda: self._safe_event("<<Paste>>"), "Ctrl+V")
        self.ctx_menu.add_command("全选", self._select_all, "Ctrl+A")

        # "更多" 菜单（自定义扁平风格）—— 所有偏好设置都直接展开
        self.more_menu = FlatMenu(self.root, min_width=240)
        self.more_menu.add_command("新建任务", self.new_task_top)
        self.more_menu.add_command("切换任务 / 增删复选框", self.toggle_task_lines, "Ctrl+L")
        self.more_menu.add_separator()
        self.more_menu.add_command("切换置顶", self.toggle_pin)
        self.more_menu.add_command("透明度调节\u2026", self.show_transparency_dialog)
        self.more_menu.add_command("高亮颜色\u2026", self.choose_highlight_color)
        self.more_menu.add_separator()
        self.more_menu.add_command("手动保存", lambda: self._save_notes(force=True), "Ctrl+S")
        self.more_menu.add_command("清空所有任务", self.clear_all)
        self.more_menu.add_command("打开存储目录", self.open_save_dir)
        self.more_menu.add_separator()
        self.more_menu.add_command("最小化", self.minimize_window)
        self.more_menu.add_command("隐藏到托盘", self.hide_to_tray)
        self.more_menu.add_command("关于", self.show_about)
        self.more_menu.add_command("退出程序", self.real_quit)

    # --------------------------------------------------------
    # 按钮工厂
    # --------------------------------------------------------
    def _icon_btn(self, parent, text, cmd, tip="", size=14, hover=COLOR_BTN_HOVER):
        btn = tk.Label(parent, text=text, bg=COLOR_BG, fg=COLOR_SUBTLE,
                       font=(FONT_FAMILY, size), padx=8, pady=2, cursor="hand2")
        btn.bind("<Button-1>", lambda e: cmd())
        btn.bind("<Enter>", lambda e: btn.configure(bg=hover, fg=COLOR_FG))
        btn.bind("<Leave>", lambda e: btn.configure(bg=COLOR_BG, fg=COLOR_SUBTLE))
        if tip:
            self._attach_tooltip(btn, tip)
        return btn

    def _tool_btn(self, parent, text, cmd, font=None, tip="", bg_override=None):
        if font is None:
            font = (FONT_FAMILY, FONT_SIZE)
        base_bg = bg_override if bg_override else COLOR_TOOLBAR_BG
        btn = tk.Label(parent, text=text, bg=base_bg, fg=COLOR_FG,
                       font=font, padx=8, pady=4, cursor="hand2", width=2)
        btn.bind("<Button-1>", lambda e: cmd())
        btn.bind("<Enter>", lambda e: btn.configure(bg=COLOR_BTN_HOVER))
        btn.bind("<Leave>", lambda e: btn.configure(bg=base_bg))
        if tip:
            self._attach_tooltip(btn, tip)
        return btn

    def _attach_tooltip(self, widget, text):
        tip = {"win": None}

        def enter(_e):
            if tip["win"]:
                return
            x = widget.winfo_rootx() + 10
            y = widget.winfo_rooty() + widget.winfo_height() + 6
            tw = tk.Toplevel(widget)
            tw.wm_overrideredirect(True)
            tw.wm_geometry(f"+{x}+{y}")
            tw.attributes("-topmost", True)
            lbl = tk.Label(tw, text=text, bg=COLOR_TOOLTIP_BG, fg=COLOR_TOOLTIP_FG,
                           font=(FONT_FAMILY, 9), padx=8, pady=3, bd=0)
            lbl.pack()
            tip["win"] = tw

        def leave(_e):
            if tip["win"]:
                tip["win"].destroy()
                tip["win"] = None

        widget.bind("<Enter>", enter, add="+")
        widget.bind("<Leave>", leave, add="+")

    # --------------------------------------------------------
    # 事件绑定
    # --------------------------------------------------------
    def _bind_events(self):
        # 回车：新任务
        self.text.bind("<Return>", self._on_return)
        # 退格 / 删除：保护复选框 prefix 不被键盘破坏
        self.text.bind("<BackSpace>", self._on_backspace)
        self.text.bind("<Delete>", self._on_delete)
        # 左键：按下只记录状态，拖拽走 Tk 默认；松开时判定是否单击 checkbox
        self.text.bind("<Button-1>", self._on_text_press)
        self.text.bind("<B1-Motion>", self._on_text_drag)
        self.text.bind("<ButtonRelease-1>", self._on_text_release)
        # Home 键：让光标落在复选框之后（任务行）
        self.text.bind("<Home>", self._on_home)
        # 拖选 / 键盘扩展选区之后：自动修正选区，跳过复选框
        self.text.bind("<<Selection>>", self._on_selection_changed)
        # 复制 / 剪切：过滤掉选区里的复选框前缀
        self.text.bind("<Control-c>", self._do_copy_event)
        self.text.bind("<Control-C>", self._do_copy_event)
        self.text.bind("<Control-x>", self._do_cut_event)
        self.text.bind("<Control-X>", self._do_cut_event)
        self.text.bind("<Control-a>", lambda e: (self._select_all(), "break")[1])
        self.text.bind("<Control-A>", lambda e: (self._select_all(), "break")[1])
        # 粘贴：先以保留 checkbox 的方式删除选区，再插入剪贴板
        self.text.bind("<Control-v>", self._on_paste)
        self.text.bind("<Control-V>", self._on_paste)
        self.text.bind("<<Paste>>", self._on_paste)
        # 普通按键输入：若有选区，必须以"保留 checkbox"方式处理覆盖
        self.text.bind("<KeyPress>", self._on_keypress)
        # 右键菜单
        self.text.bind("<Button-3>", self._on_text_right_click)
        # 快捷键
        self.text.bind("<Control-b>", lambda e: (self.toggle_tag("bold"), "break")[1])
        self.text.bind("<Control-B>", lambda e: (self.toggle_tag("bold"), "break")[1])
        self.text.bind("<Control-i>", lambda e: (self.toggle_tag("italic"), "break")[1])
        self.text.bind("<Control-I>", lambda e: (self.toggle_tag("italic"), "break")[1])
        self.text.bind("<Control-u>", lambda e: (self.toggle_tag("underline"), "break")[1])
        self.text.bind("<Control-U>", lambda e: (self.toggle_tag("underline"), "break")[1])
        self.text.bind("<Control-h>", lambda e: (self.toggle_tag("highlight"), "break")[1])
        self.text.bind("<Control-H>", lambda e: (self.toggle_tag("highlight"), "break")[1])
        self.text.bind("<Control-s>", lambda e: (self._save_notes(force=True), "break")[1])
        # Ctrl+L 一键把当前行/选区行 切换任务态（增删复选框）
        self.text.bind("<Control-l>", lambda e: (self.toggle_task_lines(), "break")[1])
        self.text.bind("<Control-L>", lambda e: (self.toggle_task_lines(), "break")[1])

        # 文本变化触发保存
        self.text.bind("<<Modified>>", self._on_modified)
        self.text.bind("<KeyRelease>", lambda e: self._schedule_save())

        # 焦点变化触发贴边
        self.root.bind("<FocusIn>", self._on_focus_in)
        self.root.bind("<FocusOut>", self._on_focus_out)
        # 最小化恢复：从任务栏点回来时，重新应用无边框样式
        self.root.bind("<Map>", self._on_window_map)

    # --------------------------------------------------------
    # 拖动 / 缩放
    # --------------------------------------------------------
    def _start_move(self, event):
        self._drag_data["x"] = event.x_root - self.root.winfo_x()
        self._drag_data["y"] = event.y_root - self.root.winfo_y()

    def _do_move(self, event):
        x = event.x_root - self._drag_data["x"]
        y = event.y_root - self._drag_data["y"]
        self.root.geometry(f"+{x}+{y}")
        self._schedule_save()

    def _start_resize(self, event):
        self._resize_data["x"] = event.x_root
        self._resize_data["y"] = event.y_root
        self._resize_data["w"] = self.root.winfo_width()
        self._resize_data["h"] = self.root.winfo_height()

    def _do_resize(self, event):
        dx = event.x_root - self._resize_data["x"]
        dy = event.y_root - self._resize_data["y"]
        new_w = max(MIN_W, self._resize_data["w"] + dx)
        new_h = max(MIN_H, self._resize_data["h"] + dy)
        self.root.geometry(f"{new_w}x{new_h}")
        self._schedule_save()

    # --------------------------------------------------------
    # 任务 / Checkbox 交互
    # --------------------------------------------------------
    def _line_prefix_info(self, line_no: int):
        """返回 (is_task, checked, prefix_len)。"""
        line_start = f"{line_no}.0"
        line_end = f"{line_no}.end"
        content = self.text.get(line_start, line_end)
        if not content:
            return False, False, 0
        if content.startswith(UNCHECKED + " "):
            return True, False, 2
        if content.startswith(CHECKED + " "):
            return True, True, 2
        return False, False, 0

    def _current_line_no(self) -> int:
        return int(self.text.index("insert").split(".")[0])

    def _insert_task_at_line_start(self, line_no: int, checked=False,
                                   priority=DEFAULT_PRIORITY):
        ch = CHECKED if checked else UNCHECKED
        prefix = f"{ch} "
        line_start = f"{line_no}.0"
        self.text.insert(line_start, prefix)
        self.text.tag_add("checkbox_done" if checked else "checkbox",
                          line_start, f"{line_no}.1")
        if checked:
            self._apply_done_style(line_no, True)
        # 应用默认优先级背景（整行至换行符，保证色块贯穿整行宽度）
        self._apply_priority(line_no, priority)

    def _apply_done_style(self, line_no: int, done: bool):
        text_start = f"{line_no}.2"
        text_end = f"{line_no}.end"
        if done:
            self.text.tag_add("done", text_start, text_end)
        else:
            self.text.tag_remove("done", text_start, text_end)

    # ------- 优先级 -------
    def _line_range_with_newline(self, line_no):
        """返回包含换行符的行区间，便于整行染色。
        使用 end+1c：若是最后一行，Tk 会自动裁剪到文档末尾，不会报错。"""
        return f"{line_no}.0", f"{line_no}.end+1c"

    def _apply_priority(self, line_no: int, priority: str):
        start, end = self._line_range_with_newline(line_no)
        # 先清除所有已知优先级 tag
        for p in PRIORITY_ORDER:
            self.text.tag_remove(f"prio_{p}", start, end)
        # "none" 或未知值 → 不加任何 tag（保持纯白）
        if priority in PRIORITY_BG:
            self.text.tag_add(f"prio_{priority}", start, end)

    def _get_line_priority(self, line_no: int) -> str:
        tags = self.text.tag_names(f"{line_no}.0")
        for p in PRIORITY_ORDER:
            if f"prio_{p}" in tags:
                return p
        return "none"

    def set_current_priority(self, priority: str):
        """右键菜单入口：设置光标所在行/选区各行的优先级。"""
        if self._reordering:
            return
        if priority != "none" and priority not in PRIORITY_BG:
            return
        try:
            try:
                sel_start = self.text.index("sel.first")
                sel_end = self.text.index("sel.last")
                start_line = int(sel_start.split(".")[0])
                end_line = int(sel_end.split(".")[0])
                if int(sel_end.split(".")[1]) == 0 and end_line > start_line:
                    end_line -= 1
            except tk.TclError:
                start_line = end_line = self._current_line_no()
            for ln in range(start_line, end_line + 1):
                self._apply_priority(ln, priority)
            self._schedule_save()
        except Exception:
            pass

    # ------- 排序：已完成沉底 -------
    def _schedule_reorder(self, delay=220):
        """防抖：短时间多次勾选只重建一次，避免卡顿。"""
        if self._reorder_job is not None:
            try:
                self.root.after_cancel(self._reorder_job)
            except Exception:
                pass
        self._reorder_job = self.root.after(delay, self._reorder_completed_to_bottom)

    def _reorder_completed_to_bottom(self):
        """重建文本：未完成任务保持原顺序 → 已完成任务按优先级排到末尾。"""
        self._reorder_job = None
        if self._reordering:
            return
        self._reordering = True
        try:
            _md, data = self._serialize()
            lines = data.get("lines", [])

            active = []
            completed = []
            for ln in lines:
                if ln.get("type") == "task" and ln.get("checked"):
                    completed.append(ln)
                else:
                    active.append(ln)

            # 已完成按优先级稳定排序（紧急 → 较低）
            completed.sort(key=lambda x: PRIORITY_RANK.get(
                x.get("priority", DEFAULT_PRIORITY), PRIORITY_RANK[DEFAULT_PRIORITY]))

            new_lines = active + completed
            if new_lines == lines:
                return
            data["lines"] = new_lines
            self.text.delete("1.0", "end")
            self._load_from_json(data)
        except Exception:
            # 任何异常静默，避免点击流程整体崩溃
            pass
        finally:
            self._reordering = False

    def _on_return(self, event):
        # 若存在选区，先以保留 checkbox 的方式删除选区
        if self._selection_exists():
            self._delete_selection_preserving_checkboxes()
        idx = self.text.index("insert")
        line_no = int(idx.split(".")[0])
        col = int(idx.split(".")[1])

        is_task, checked, prefix_len = self._line_prefix_info(line_no)

        # 正常插入换行 + 新任务 prefix
        # 如果光标在 prefix 中部，跳到 prefix 之后（避免分裂 prefix）
        if is_task and col < prefix_len:
            self.text.mark_set("insert", f"{line_no}.{prefix_len}")

        # 继承当前行优先级（没有则默认）
        inherited_priority = self._get_line_priority(line_no) if is_task else DEFAULT_PRIORITY
        self.text.insert("insert", "\n")
        new_line_no = line_no + 1
        # 如果新行已有 prefix（粘贴等），不重复插入
        is_task_new, _, _ = self._line_prefix_info(new_line_no)
        if not is_task_new:
            self._insert_task_at_line_start(new_line_no, checked=False,
                                            priority=inherited_priority)
            self.text.mark_set("insert", f"{new_line_no}.2")
        self._schedule_save()
        return "break"

    def _on_backspace(self, event):
        """退格：

        - 有选区：走自定义删除（保留中间行复选框）
        - 空任务行：允许删除整行（合并到上一行），让用户能"收回"多余的任务
        - 非空任务行的 prefix 内：光标跳到文字起点，静默不删除（保护复选框完整性）
        - 其它情形：走 Tk 默认行为
        """
        if self._selection_exists():
            self._delete_selection_preserving_checkboxes()
            return "break"

        idx = self.text.index("insert")
        line_no = int(idx.split(".")[0])
        col = int(idx.split(".")[1])
        is_task, checked, prefix_len = self._line_prefix_info(line_no)

        if is_task:
            line_text = self.text.get(f"{line_no}.0", f"{line_no}.end")
            empty_task_only = line_text == (CHECKED if checked else UNCHECKED) + " "
            # 空任务行：直接删除整行（合并到上一行），不再只是卡在 prefix
            if empty_task_only:
                if line_no > 1:
                    self.text.delete(f"{line_no - 1}.end", f"{line_no}.end")
                    self._schedule_save()
                    return "break"
                # 第一行空任务：保留（避免无内容），光标对齐文字起点
                self.text.mark_set("insert", f"{line_no}.{prefix_len}")
                return "break"
            # 非空任务：保护 prefix
            if 0 < col <= prefix_len:
                self.text.mark_set("insert", f"{line_no}.{prefix_len}")
                return "break"
        return None

    def _on_delete(self, event):
        """Delete 向后删除：保护复选框 prefix。"""
        if self._selection_exists():
            self._delete_selection_preserving_checkboxes()
            return "break"

        idx = self.text.index("insert")
        line_no = int(idx.split(".")[0])
        col = int(idx.split(".")[1])
        is_task, _checked, prefix_len = self._line_prefix_info(line_no)
        if is_task and col < prefix_len:
            # 静默：保护复选框不被单字符删除
            self.text.mark_set("insert", f"{line_no}.{prefix_len}")
            return "break"
        return None

    def _on_home(self, event):
        """Home：任务行落到 prefix 之后，普通行落到行首。"""
        idx = self.text.index("insert")
        line_no = int(idx.split(".")[0])
        is_task, _, prefix_len = self._line_prefix_info(line_no)
        target = f"{line_no}.{prefix_len if is_task else 0}"
        self.text.mark_set("insert", target)
        # 清除可能的选区（普通 Home 行为）
        self.text.tag_remove("sel", "1.0", "end")
        return "break"

    # -------- 鼠标按下 / 拖拽 / 松开 --------
    def _on_text_press(self, event):
        """仅记录按下信息；不在这里 toggle，避免打断用户拖选。"""
        if self._reordering:
            return "break"
        try:
            idx = self.text.index(f"@{event.x},{event.y}")
            line_no = int(idx.split(".")[0])
            col = int(idx.split(".")[1])
            self._press_info = {
                "x": event.x, "y": event.y,
                "line": line_no, "col": col,
                "dragged": False,
            }
        except Exception:
            self._press_info = None
        return None  # 放行默认行为（光标定位 / 开始选区）

    def _on_text_drag(self, event):
        if self._reordering:
            return "break"
        info = self._press_info
        if info is None:
            return None
        dx = abs(event.x - info["x"])
        dy = abs(event.y - info["y"])
        if dx > 3 or dy > 3:
            info["dragged"] = True
        return None  # 放行默认拖选

    def _on_text_release(self, event):
        """若这是一次"原地单击"并且命中 checkbox，才 toggle。"""
        info = self._press_info
        self._press_info = None
        if info is None or self._reordering or self._click_lock:
            return None
        # 拖动过 → 用户是在做选区/移动，不 toggle
        if info["dragged"]:
            return None
        # 若现在有选区 → 也视为选择操作，不 toggle
        try:
            self.text.index("sel.first")
            return None
        except tk.TclError:
            pass

        line_no = info["line"]
        col = info["col"]
        try:
            is_task, checked, _ = self._line_prefix_info(line_no)
        except Exception:
            return None
        if not (is_task and col == 0):
            return None

        self._click_lock = True
        try:
            new_char = UNCHECKED if checked else CHECKED
            priority = self._get_line_priority(line_no)
            self.text.delete(f"{line_no}.0", f"{line_no}.1")
            self.text.insert(f"{line_no}.0", new_char)
            self.text.tag_remove("checkbox", f"{line_no}.0", f"{line_no}.1")
            self.text.tag_remove("checkbox_done", f"{line_no}.0", f"{line_no}.1")
            self.text.tag_add("checkbox_done" if not checked else "checkbox",
                              f"{line_no}.0", f"{line_no}.1")
            self._apply_done_style(line_no, not checked)
            self._apply_priority(line_no, priority)
        except Exception:
            pass
        finally:
            self._click_lock = False

        self._schedule_reorder()
        self._schedule_save()
        return "break"

    def _on_text_right_click(self, event):
        # 将光标移到点击处，便于后续操作
        idx = self.text.index(f"@{event.x},{event.y}")
        self.text.mark_set("insert", idx)
        self.ctx_menu.popup(event.x_root, event.y_root)
        return "break"

    def delete_current_line(self):
        line_no = self._current_line_no()
        line_start = f"{line_no}.0"
        # 如果不是最后一行，删除到下一行行首（连同换行）
        last_line = int(self.text.index("end-1c").split(".")[0])
        if line_no < last_line:
            self.text.delete(line_start, f"{line_no + 1}.0")
        else:
            # 最后一行：删整行内容及其前的换行（若有）
            if line_no > 1:
                self.text.delete(f"{line_no - 1}.end", f"{line_no}.end")
            else:
                self.text.delete(line_start, f"{line_no}.end")
        self._schedule_save()

    def clear_all(self):
        if flat_messagebox(self.root, "清空", "确定清空所有任务？", kind="yesno"):
            self.text.delete("1.0", "end")
            self._ensure_first_task()
            self._schedule_save()

    def _ensure_first_task(self):
        """文件/文本为空时，保证至少有一个任务行。"""
        content = self.text.get("1.0", "end-1c")
        if not content:
            self._insert_task_at_line_start(1, checked=False)
            self.text.mark_set("insert", "1.2")

    def new_task_top(self):
        """在开头新增一个任务。"""
        self.text.insert("1.0", f"{UNCHECKED} \n")
        self.text.tag_add("checkbox", "1.0", "1.1")
        self._apply_priority(1, DEFAULT_PRIORITY)
        self.text.mark_set("insert", "1.2")
        self.text.focus_set()
        self._schedule_save()

    def toggle_task_lines(self):
        """切换当前行/选区涉及行 的任务态（批量添加或移除复选框）。

        规则：以首行为准——首行是任务则批量取消；否则批量添加。
        """
        # 确定行范围
        try:
            sel_start = self.text.index("sel.first")
            sel_end = self.text.index("sel.last")
            start_line = int(sel_start.split(".")[0])
            end_line = int(sel_end.split(".")[0])
            # 若选区恰好结束在行首，end_line 不计入
            if int(sel_end.split(".")[1]) == 0 and end_line > start_line:
                end_line -= 1
        except tk.TclError:
            start_line = end_line = self._current_line_no()

        first_is_task, _c, _p = self._line_prefix_info(start_line)
        mode_remove = first_is_task

        if mode_remove:
            # 批量移除 prefix
            for ln in range(start_line, end_line + 1):
                is_task, _, prefix_len = self._line_prefix_info(ln)
                if is_task:
                    self.text.delete(f"{ln}.0", f"{ln}.{prefix_len}")
                    # 清理可能残留的 done 样式
                    self.text.tag_remove("done", f"{ln}.0", f"{ln}.end")
        else:
            # 批量添加 prefix（跳过已是任务的行；空行也加）
            for ln in range(start_line, end_line + 1):
                is_task, _, _ = self._line_prefix_info(ln)
                if not is_task:
                    self._insert_task_at_line_start(ln, checked=False)

        # 聚焦光标（单行时定位到文字开头）
        if start_line == end_line:
            _it, _c2, plen = self._line_prefix_info(start_line)
            self.text.mark_set("insert", f"{start_line}.{plen}")

        self.text.focus_set()
        self._schedule_save()

    # 兼容旧别名
    insert_task_here = toggle_task_lines

    # --------------------------------------------------------
    # 格式化
    # --------------------------------------------------------
    def toggle_tag(self, tag_name: str):
        try:
            sel_start = self.text.index("sel.first")
            sel_end = self.text.index("sel.last")
        except tk.TclError:
            return
        # 若整个区间已带 tag，则移除；否则添加
        ranges = self.text.tag_ranges(tag_name)
        has_all = self._range_fully_tagged(tag_name, sel_start, sel_end)
        if has_all:
            self.text.tag_remove(tag_name, sel_start, sel_end)
        else:
            self.text.tag_add(tag_name, sel_start, sel_end)
        self._schedule_save()

    def _range_fully_tagged(self, tag_name, start, end):
        """简化判断：如果开头已经带该 tag 就视为已生效（再次点击取消）。"""
        tags_at_start = self.text.tag_names(start)
        return tag_name in tags_at_start

    # --------------------------------------------------------
    # 图片插入
    # --------------------------------------------------------
    def insert_image(self):
        path = filedialog.askopenfilename(
            parent=self.root,
            title="选择图片",
            filetypes=[("图片", "*.png;*.gif;*.jpg;*.jpeg;*.bmp"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            # Tk 原生支持 PNG/GIF；JPG 尝试 PIL，无 PIL 则提示
            img = None
            ext = os.path.splitext(path)[1].lower()
            if ext in (".png", ".gif"):
                img = tk.PhotoImage(file=path)
            else:
                try:
                    from PIL import Image, ImageTk  # 可选
                    pil = Image.open(path)
                    pil.thumbnail((320, 320))
                    img = ImageTk.PhotoImage(pil)
                except ImportError:
                    flat_messagebox(
                        self.root,
                        "提示",
                        "仅支持 PNG/GIF 原生插入。如需 JPG/JPEG 支持，请安装 Pillow：\n\npip install pillow",
                    )
                    return
            # 限制过大尺寸
            if hasattr(img, "width") and img.width() > 320:
                # PhotoImage 缩放
                try:
                    factor = max(1, img.width() // 320 + 1)
                    img = img.subsample(factor, factor)
                except Exception:
                    pass
            if not hasattr(self, "_images"):
                self._images = []
            self._images.append(img)  # 防止 GC
            self.text.image_create("insert", image=img, padx=4, pady=4)
            # 保存时以 [图片:<path>] 记录
            self.text.insert("insert", "")  # no-op
            # 记录当前 image 的 path，用于保存
            if not hasattr(self, "_image_paths"):
                self._image_paths = {}
            # tkinter 的 image item 没有直接 id，可通过 index 和 image 名关联
            # 简化：保存时把嵌入 image 行转为 ![](path)
            self._image_paths[str(img)] = path
            self._schedule_save()
        except Exception as e:
            flat_messagebox(self.root, "插入失败", str(e))

    # --------------------------------------------------------
    # 置顶 / 透明度 / 高亮色
    # --------------------------------------------------------
    def _pin_icon(self):
        return "\U0001F4CC" if self.pinned else "\u25CB"

    def toggle_pin(self):
        self.pinned = not self.pinned
        self.root.attributes("-topmost", self.pinned)
        self.pin_btn.configure(text=self._pin_icon(),
                               fg=COLOR_FG if self.pinned else COLOR_MUTED)
        self._save_config()

    def show_more_menu(self):
        x = self.root.winfo_rootx() + 44
        y = self.root.winfo_rooty() + 38
        self.more_menu.popup(x, y)

    def show_transparency_dialog(self):
        dlg = FlatDialog(self.root, title="透明度调节", width=300)

        tk.Label(
            dlg.body,
            text="拖动滑块调整窗口整体透明度",
            bg=COLOR_BG,
            fg=COLOR_SUBTLE,
            font=(FONT_FAMILY, 9),
        ).pack(anchor="w", pady=(0, 8))

        val_row = tk.Frame(dlg.body, bg=COLOR_BG)
        val_row.pack(fill="x", pady=(0, 6))

        val_lbl = tk.Label(
            val_row,
            text=f"{int(self.transparency * 100)}%",
            bg=COLOR_BG,
            fg=COLOR_FG,
            font=(FONT_FAMILY, 14, "bold"),
        )
        val_lbl.pack(side="left")

        var = tk.DoubleVar(value=self.transparency)

        def on_change(val):
            v = float(val)
            self.transparency = v
            self.root.attributes("-alpha", v)
            val_lbl.configure(text=f"{int(v * 100)}%")

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Flat.Horizontal.TScale",
            background=COLOR_BG,
            troughcolor=COLOR_BORDER,
            bordercolor=COLOR_BG,
            lightcolor=COLOR_BG,
            darkcolor=COLOR_BG,
        )
        s = ttk.Scale(
            dlg.body,
            from_=0.3,
            to=1.0,
            variable=var,
            orient="horizontal",
            length=260,
            command=on_change,
            style="Flat.Horizontal.TScale",
        )
        s.pack(fill="x", pady=(4, 14))

        btn_row = tk.Frame(dlg.body, bg=COLOR_BG)
        btn_row.pack(fill="x")
        flat_button(
            btn_row,
            "完成",
            lambda: (self._save_config(), dlg.close()),
            primary=True,
        ).pack(side="right")

        dlg.place_near(self.root)

    def choose_highlight_color(self):
        col = colorchooser.askcolor(color=self.highlight_color,
                                    title="选择高亮颜色", parent=self.root)
        if col and col[1]:
            self.highlight_color = col[1]
            self.text.tag_configure("highlight", background=self.highlight_color)
            self._save_config()

    def open_save_dir(self):
        try:
            os.startfile(get_data_dir())
        except Exception:
            pass

    def show_about(self):
        flat_messagebox(
            self.root,
            "关于",
            "极简悬浮便笺 v1.0\n\n纯 Python + Tkinter 实现\n\n数据以标准 Markdown 保存于程序目录：\nnotes.md",
        )

    # --------------------------------------------------------
    # 贴边自动隐藏
    # --------------------------------------------------------
    def _schedule_edge_check(self):
        if self._edge_check_job:
            self.root.after_cancel(self._edge_check_job)
        self._edge_check_job = self.root.after(600, self._edge_check_tick)

    def _edge_check_tick(self):
        try:
            if self._hide_state == "visible":
                x = self.root.winfo_x()
                if x <= 0 and not self._is_focused():
                    self._slide_hide("left")
            elif self._hide_state == "hidden":
                # 当鼠标进入可见区时弹出
                mx = self.root.winfo_pointerx()
                my = self.root.winfo_pointery()
                wx = self.root.winfo_x()
                wy = self.root.winfo_y()
                ww = self.root.winfo_width()
                wh = self.root.winfo_height()
                if wx <= mx <= wx + ww and wy <= my <= wy + wh:
                    self._slide_show()
        except Exception:
            pass
        self._edge_check_job = self.root.after(400, self._edge_check_tick)

    def _is_focused(self):
        try:
            return self.root.focus_displayof() is not None
        except Exception:
            return False

    def _slide_hide(self, edge):
        if edge != "left":
            return
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        y = self.root.winfo_y()
        target_x = -(w - HIDE_STRIP)
        self._animate_to(target_x, y, w, h)
        self._hide_state = "hidden"
        self._hide_edge = edge

    def _slide_show(self):
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        y = self.root.winfo_y()
        self._animate_to(0, y, w, h)
        self._hide_state = "visible"

    def _animate_to(self, x, y, w, h, steps=6):
        cur_x = self.root.winfo_x()
        dx = (x - cur_x) / steps

        def step(i):
            nx = int(cur_x + dx * i)
            self.root.geometry(f"{w}x{h}+{nx}+{y}")
            if i < steps:
                self.root.after(12, lambda: step(i + 1))
            else:
                self.root.geometry(f"{w}x{h}+{x}+{y}")

        step(1)

    def _on_focus_in(self, _e):
        if self._hide_state == "hidden":
            self._slide_show()

    def _on_focus_out(self, _e):
        # 失焦后，若位置在左边缘，交给定时器处理
        pass

    # --------------------------------------------------------
    # 保存 / 加载
    # --------------------------------------------------------
    def _on_modified(self, _e):
        if self.text.edit_modified():
            self.text.edit_modified(False)
            self._schedule_save()

    def _schedule_save(self):
        if self._saving_job:
            self.root.after_cancel(self._saving_job)
        self._saving_job = self.root.after(400, self._save_notes)

    def _save_notes(self, force=False):
        try:
            md_lines, data = self._serialize()
            with open(SAVE_MD, "w", encoding="utf-8") as f:
                f.write("\n".join(md_lines))
            with open(SAVE_JSON, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._save_config()
        except Exception as e:
            if force:
                flat_messagebox(self.root, "保存失败", str(e))

    def _serialize(self):
        """遍历每一行，生成 markdown + 带格式的 json。"""
        md_lines = []
        json_lines = []
        last_line = int(self.text.index("end-1c").split(".")[0])
        for i in range(1, last_line + 1):
            is_task, checked, prefix_len = self._line_prefix_info(i)
            line_end = f"{i}.end"
            text_start = f"{i}.{prefix_len}"
            text_content = self.text.get(text_start, line_end)

            # 带格式的段
            segments = self._get_line_segments(i, prefix_len)
            md_text = "".join(self._segment_to_md(seg) for seg in segments)

            priority = self._get_line_priority(i)

            if is_task:
                mark = "x" if checked else " "
                md_lines.append(f"- [{mark}] {md_text}")
                json_lines.append({
                    "type": "task",
                    "checked": checked,
                    "priority": priority,
                    "segments": segments,
                })
            else:
                if text_content == "":
                    md_lines.append("")
                    json_lines.append({"type": "empty"})
                else:
                    md_lines.append(md_text)
                    json_lines.append({
                        "type": "text",
                        "priority": priority,
                        "segments": segments,
                    })

        return md_lines, {"version": 1, "lines": json_lines}

    def _get_line_segments(self, line_no, prefix_len):
        """按 tag 变化切分该行文本。"""
        start = f"{line_no}.{prefix_len}"
        end = f"{line_no}.end"
        line_end_col = int(self.text.index(end).split(".")[1])
        start_col = prefix_len
        segments = []
        col = start_col
        while col < line_end_col:
            idx = f"{line_no}.{col}"
            ch = self.text.get(idx, f"{line_no}.{col + 1}")
            tags = [t for t in self.text.tag_names(idx)
                    if t in ("bold", "italic", "underline", "strike", "highlight")]
            tags.sort()
            if segments and segments[-1]["tags"] == tags:
                segments[-1]["text"] += ch
            else:
                segments.append({"text": ch, "tags": tags})
            col += 1
        return segments

    def _segment_to_md(self, seg):
        t = seg["text"]
        if not t:
            return ""
        tags = seg["tags"]
        # 转义 markdown 敏感字符？保持原字符，最大兼容性
        out = t
        if "strike" in tags:
            out = f"~~{out}~~"
        if "highlight" in tags:
            out = f"=={out}=="
        if "underline" in tags:
            out = f"<u>{out}</u>"
        if "italic" in tags:
            out = f"*{out}*"
        if "bold" in tags:
            out = f"**{out}**"
        return out

    def _load_notes(self):
        """优先从 JSON 还原（含格式），否则从 MD 解析。"""
        loaded = False
        if os.path.exists(SAVE_JSON):
            try:
                with open(SAVE_JSON, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._load_from_json(data)
                loaded = True
            except Exception:
                loaded = False

        if not loaded and os.path.exists(SAVE_MD):
            try:
                with open(SAVE_MD, "r", encoding="utf-8") as f:
                    content = f.read()
                self._load_from_md(content)
                loaded = True
            except Exception:
                loaded = False

        if not loaded:
            self._ensure_first_task()

        # 重置修改状态
        self.text.edit_modified(False)

    def _load_from_json(self, data):
        lines = data.get("lines", [])
        self.text.delete("1.0", "end")
        for i, line in enumerate(lines):
            line_no = i + 1
            if i > 0:
                self.text.insert("end", "\n")
            t = line.get("type")
            if t == "task":
                checked = line.get("checked", False)
                ch = CHECKED if checked else UNCHECKED
                self.text.insert("end", f"{ch} ")
                self.text.tag_add("checkbox_done" if checked else "checkbox",
                                  f"{line_no}.0", f"{line_no}.1")
                self._insert_segments(line_no, 2, line.get("segments", []))
                if checked:
                    self._apply_done_style(line_no, True)
                priority = line.get("priority", DEFAULT_PRIORITY)
                self._apply_priority(line_no, priority)
            elif t == "text":
                self._insert_segments(line_no, 0, line.get("segments", []))
                priority = line.get("priority")
                if priority:
                    self._apply_priority(line_no, priority)
            else:
                # empty
                pass
        if not lines:
            self._ensure_first_task()

    def _insert_segments(self, line_no, start_col, segments):
        col = start_col
        for seg in segments:
            text = seg.get("text", "")
            if not text:
                continue
            start_idx = f"{line_no}.{col}"
            self.text.insert(start_idx, text)
            end_idx = f"{line_no}.{col + len(text)}"
            for tag in seg.get("tags", []):
                self.text.tag_add(tag, start_idx, end_idx)
            col += len(text)

    def _load_from_md(self, content):
        """从 markdown 解析（基础支持）。"""
        self.text.delete("1.0", "end")
        lines = content.split("\n")
        if not lines:
            self._ensure_first_task()
            return
        for i, raw in enumerate(lines):
            line_no = i + 1
            if i > 0:
                self.text.insert("end", "\n")
            m = re.match(r"^- \[( |x|X)\] (.*)$", raw)
            if m:
                checked = m.group(1).lower() == "x"
                ch = CHECKED if checked else UNCHECKED
                self.text.insert("end", f"{ch} ")
                self.text.tag_add("checkbox_done" if checked else "checkbox",
                                  f"{line_no}.0", f"{line_no}.1")
                segments = self._parse_md_inline(m.group(2))
                self._insert_segments(line_no, 2, segments)
                if checked:
                    self._apply_done_style(line_no, True)
                # 从 md 加载的任务默认普通优先级
                self._apply_priority(line_no, DEFAULT_PRIORITY)
            else:
                if raw.strip() == "":
                    pass
                else:
                    segments = self._parse_md_inline(raw)
                    self._insert_segments(line_no, 0, segments)

    def _parse_md_inline(self, s: str):
        """粗略解析 markdown inline 为 segments。"""
        patterns = [
            (re.compile(r"\*\*(.+?)\*\*"), "bold"),
            (re.compile(r"\*(.+?)\*"), "italic"),
            (re.compile(r"<u>(.+?)</u>"), "underline"),
            (re.compile(r"~~(.+?)~~"), "strike"),
            (re.compile(r"==(.+?)=="), "highlight"),
        ]
        # 简化：逐字符扫描，记录当前生效的 tags
        # 先用占位标记展开：把 **..** 等替换为 (TAG_OPEN:tag)text(TAG_CLOSE:tag)
        tokens = []
        i = 0
        while i < len(s):
            matched = False
            for pat, tag in patterns:
                m = pat.match(s, i)
                if m:
                    # 递归处理内部
                    inner_segs = self._parse_md_inline(m.group(1))
                    for seg in inner_segs:
                        seg2 = dict(seg)
                        seg2["tags"] = list(set(seg["tags"] + [tag]))
                        seg2["tags"].sort()
                        tokens.append(seg2)
                    i = m.end()
                    matched = True
                    break
            if not matched:
                if tokens and tokens[-1].get("tags") == []:
                    tokens[-1]["text"] += s[i]
                else:
                    tokens.append({"text": s[i], "tags": []})
                i += 1
        # 合并相邻同 tag 段
        merged = []
        for t in tokens:
            if merged and merged[-1]["tags"] == t["tags"]:
                merged[-1]["text"] += t["text"]
            else:
                merged.append(t)
        return merged

    # --------------------------------------------------------
    # 复选框保护 / 选区修正 / 剪贴板
    # --------------------------------------------------------
    def _selection_exists(self):
        try:
            self.text.index("sel.first")
            return True
        except tk.TclError:
            return False

    def _on_selection_changed(self, event=None):
        """选区变化时，排除每一行的复选框 prefix，让 checkbox 永远不被视觉选中。

        使用 `_updating_sel` 标志位防止递归触发。
        """
        if getattr(self, "_updating_sel", False) or self._reordering:
            return
        try:
            start = self.text.index("sel.first")
            end = self.text.index("sel.last")
        except tk.TclError:
            return

        start_line = int(start.split(".")[0])
        start_col = int(start.split(".")[1])
        end_line = int(end.split(".")[0])

        # 按行构造要保留的子选区，跳过每行 checkbox prefix
        segments = []
        for ln in range(start_line, end_line + 1):
            is_task, _c, plen = self._line_prefix_info(ln)
            col_from = start_col if ln == start_line else 0
            if is_task:
                col_from = max(col_from, plen)
            if ln == end_line:
                seg_end = end
            else:
                seg_end = f"{ln + 1}.0"  # 含换行
            seg_start = f"{ln}.{col_from}"
            if self.text.compare(seg_start, "<", seg_end):
                segments.append((seg_start, seg_end))

        # 避免无意义的重建（防止递归和闪烁）
        cur_ranges = self.text.tag_ranges("sel")
        if len(cur_ranges) == 2 * len(segments):
            same = True
            for i, (s, e) in enumerate(segments):
                cs = str(cur_ranges[i * 2])
                ce = str(cur_ranges[i * 2 + 1])
                if not (self.text.compare(s, "==", cs) and self.text.compare(e, "==", ce)):
                    same = False
                    break
            if same:
                return

        self._updating_sel = True
        try:
            self.text.tag_remove("sel", "1.0", "end")
            for s, e in segments:
                self.text.tag_add("sel", s, e)
        finally:
            self._updating_sel = False

    def _select_all(self):
        """全选：跳过首行的复选框 prefix。"""
        self._updating_sel = True
        try:
            self.text.tag_remove("sel", "1.0", "end")
            is_task, _c, plen = self._line_prefix_info(1)
            start = f"1.{plen if is_task else 0}"
            self.text.tag_add("sel", start, "end-1c")
            self.text.mark_set("insert", "end-1c")
        finally:
            self._updating_sel = False

    def _filter_selection_text(self):
        """读取选区文本，按行过滤掉行首的复选框 prefix，返回纯文本。"""
        try:
            start = self.text.index("sel.first")
            end = self.text.index("sel.last")
        except tk.TclError:
            return None

        raw = self.text.get(start, end)
        # 选区起点已由 _on_selection_changed 修正为 prefix 之后（或非任务行）
        # 因此 raw 的第一行不会带 "☐ " / "☑ "
        # 后续每行若是完整任务行，会以 checkbox 开头，这里过滤它
        lines = raw.split("\n")
        out = []
        for i, ln in enumerate(lines):
            if i == 0:
                out.append(ln)
                continue
            if ln.startswith(UNCHECKED + " "):
                out.append(ln[2:])
            elif ln.startswith(CHECKED + " "):
                out.append(ln[2:])
            else:
                out.append(ln)
        return "\n".join(out)

    def _do_copy(self):
        text = self._filter_selection_text()
        if text is None:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def _do_cut(self):
        if not self._selection_exists():
            return
        text = self._filter_selection_text()
        if text is not None:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
        self._delete_selection_preserving_checkboxes()

    def _do_copy_event(self, _event):
        self._do_copy()
        return "break"

    def _do_cut_event(self, _event):
        self._do_cut()
        return "break"

    def _delete_selection_preserving_checkboxes(self):
        """删除选区内容但保留每行的复选框 prefix 与行结构。

        策略（自底向上处理，索引不会失效）：
        - 末行：从"选区末端"往前删到"该行 prefix 之后"（或行首）
        - 中间行：整行的文字部分删除（保留 prefix）
        - 首行：从"选区起点"删到行末
        - 行结构保留（不合并行）。这样每个 checkbox 都不被破坏。
        """
        try:
            start = self.text.index("sel.first")
            end = self.text.index("sel.last")
        except tk.TclError:
            return

        start_line = int(start.split(".")[0])
        start_col = int(start.split(".")[1])
        end_line = int(end.split(".")[0])

        if start_line == end_line:
            # 单行：选区已由 _on_selection_changed 避开 prefix
            self.text.delete(start, end)
            self._schedule_save()
            return

        # --- 多行：自底向上删除 ---
        # 末行：删除"选区末端"之前的文字部分
        is_task_end, _c, plen_end = self._line_prefix_info(end_line)
        keep_col_end = plen_end if is_task_end else 0
        if self.text.compare(f"{end_line}.{keep_col_end}", "<", end):
            self.text.delete(f"{end_line}.{keep_col_end}", end)

        # 中间行：删除文字部分（保留 prefix）
        for ln in range(end_line - 1, start_line, -1):
            is_task_mid, _c, plen_mid = self._line_prefix_info(ln)
            keep_col = plen_mid if is_task_mid else 0
            line_end_col = int(self.text.index(f"{ln}.end").split(".")[1])
            if keep_col < line_end_col:
                self.text.delete(f"{ln}.{keep_col}", f"{ln}.end")

        # 首行：从选区起点删到该行末
        first_line_end_col = int(self.text.index(f"{start_line}.end").split(".")[1])
        if start_col < first_line_end_col:
            self.text.delete(start, f"{start_line}.end")

        # 光标定位到首行选区起点
        self.text.mark_set("insert", f"{start_line}.{start_col}")
        # 清除选区
        self.text.tag_remove("sel", "1.0", "end")

        self._schedule_save()

    def _on_paste(self, event=None):
        """粘贴：先以保留 checkbox 的方式删除选区，再插入剪贴板文本。"""
        if self._selection_exists():
            self._delete_selection_preserving_checkboxes()
        try:
            data = self.root.clipboard_get()
        except tk.TclError:
            return "break"
        if data:
            self.text.insert("insert", data)
            self._schedule_save()
        return "break"

    def _on_keypress(self, event):
        """普通字符输入：若存在选区，确保覆盖时不破坏 checkbox。

        只在"可打印字符 + 非 Ctrl/Alt 组合键"时介入；其它按键（方向键、
        Backspace、Delete、Ctrl+X 等）交给专用 handler 或默认行为处理。
        """
        ch = event.char
        if not ch:
            return None
        # 排除控制字符（\x00-\x1f, \x7f）
        if ord(ch) < 0x20 or ord(ch) == 0x7f:
            return None
        # Ctrl / Alt 组合：state 位 0x4 = Ctrl, 0x20000 = Alt
        if event.state & 0x4 or event.state & 0x20000:
            return None
        if not self._selection_exists():
            return None
        # 自定义替换
        self._delete_selection_preserving_checkboxes()
        self.text.insert("insert", ch)
        self._schedule_save()
        return "break"

    # --------------------------------------------------------
    # 工具
    # --------------------------------------------------------
    def _safe_event(self, ev):
        try:
            self.text.event_generate(ev)
        except Exception:
            pass

    # --------------------------------------------------------
    # 系统托盘 / 后台运行
    # --------------------------------------------------------
    def _make_tray_image(self):
        """动态绘制托盘图标（64x64）：深灰圆角底 + 白色横线 + 绿色勾。"""
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # 便笺主体（圆角矩形）
        try:
            draw.rounded_rectangle([4, 6, 60, 60], radius=10,
                                   fill=(50, 50, 50, 255))
        except AttributeError:
            draw.rectangle([4, 6, 60, 60], fill=(50, 50, 50, 255))
        # 顶部两条"纸张"线
        draw.line([(14, 18), (50, 18)], fill=(230, 230, 230, 255), width=2)
        draw.line([(14, 26), (40, 26)], fill=(180, 180, 180, 255), width=2)
        # 绿色勾
        draw.line([(14, 42), (26, 52)], fill=(110, 206, 110, 255), width=4)
        draw.line([(26, 52), (50, 34)], fill=(110, 206, 110, 255), width=4)
        return img

    def _setup_tray(self):
        if not _HAS_TRAY:
            return
        try:
            image = self._make_tray_image()

            def _label_show_hide(_item):
                return "隐藏便笺" if self._visible else "显示便笺"

            def _label_pin(_item):
                return "取消置顶" if self.pinned else "置顶显示"

            def _cb(fn):
                return lambda icon, item: self.root.after(0, fn)

            menu = pystray.Menu(
                pystray.MenuItem(_label_show_hide,
                                 _cb(self.toggle_visible),
                                 default=True),
                pystray.MenuItem("新建任务",
                                 _cb(self._tray_new_task)),
                pystray.MenuItem(_label_pin,
                                 _cb(self._tray_toggle_pin)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("退出便笺",
                                 lambda icon, item: self.root.after(0, self.real_quit)),
            )

            self._tray_icon = pystray.Icon(
                "bianjian",
                image,
                "极简悬浮便笺",
                menu=menu,
            )

            t = threading.Thread(target=self._tray_icon.run, daemon=True)
            t.start()
        except Exception:
            # 托盘初始化失败不致命
            self._tray_icon = None

    def _tray_new_task(self):
        self.show_from_tray()
        self.new_task_top()

    def _tray_toggle_pin(self):
        self.toggle_pin()
        if self._tray_icon is not None:
            try:
                self._tray_icon.update_menu()
            except Exception:
                pass

    def _tray_refresh_menu(self):
        if self._tray_icon is not None:
            try:
                self._tray_icon.update_menu()
            except Exception:
                pass

    def minimize_window(self):
        """最小化到任务栏。

        overrideredirect(True) 的窗口无法直接 iconify（Windows 下无反应），
        需要先临时关闭无边框模式；当用户从任务栏点回来时再恢复。
        """
        try:
            self._save_config()
        except Exception:
            pass
        self._minimize_pending_restore = True
        try:
            self.root.overrideredirect(False)
            self.root.iconify()
        except Exception:
            # 兜底：若最小化失败，回退到"隐藏到托盘"
            self._minimize_pending_restore = False
            try:
                self.root.overrideredirect(True)
            except Exception:
                pass
            self.hide_to_tray()

    def _on_window_map(self, event):
        """窗口从最小化 / withdraw 状态恢复显示时触发。"""
        if event.widget is not self.root:
            return
        if self._minimize_pending_restore:
            self._minimize_pending_restore = False
            # 延迟一帧再切回无边框，避免与系统 map 动画竞态
            self.root.after(10, self._restore_borderless)

    def _restore_borderless(self):
        try:
            self.root.overrideredirect(True)
            self.root.attributes("-topmost", self.pinned)
            self.root.attributes("-alpha", self.transparency)
            self.root.lift()
        except Exception:
            pass

    def hide_to_tray(self):
        """关闭按钮：隐藏到托盘，程序继续在后台运行。"""
        # 无托盘时直接退出，避免用户找不到入口
        if not _HAS_TRAY or self._tray_icon is None:
            self.real_quit()
            return
        try:
            self._save_notes(force=False)
            self._save_config()
        except Exception:
            pass
        self.root.withdraw()
        self._visible = False
        self._tray_refresh_menu()

    def show_from_tray(self):
        """从托盘恢复主窗口。"""
        self.root.deiconify()
        # overrideredirect 窗口 withdraw/deiconify 后可能丢失样式，这里重新应用
        try:
            self.root.overrideredirect(True)
            self.root.attributes("-topmost", self.pinned)
            self.root.attributes("-alpha", self.transparency)
        except Exception:
            pass
        self.root.lift()
        try:
            self.root.focus_force()
        except Exception:
            pass
        self._visible = True
        self._tray_refresh_menu()

    def toggle_visible(self):
        if self._visible:
            self.hide_to_tray()
        else:
            self.show_from_tray()

    def real_quit(self):
        """真正退出程序（保存 + 停止托盘 + 销毁窗口）。"""
        try:
            self._save_notes(force=False)
            self._save_config()
        except Exception:
            pass
        if self._tray_icon is not None:
            try:
                self._tray_icon.visible = False
                self._tray_icon.stop()
            except Exception:
                pass
            self._tray_icon = None
        try:
            self.root.destroy()
        except Exception:
            pass

    # 兼容旧引用
    def close_app(self):
        self.hide_to_tray()

    def run(self):
        self.root.mainloop()


def main():
    app = StickyNote()
    app.run()


if __name__ == "__main__":
    main()
