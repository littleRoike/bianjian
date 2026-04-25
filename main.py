# -*- coding: utf-8 -*-
"""
极简悬浮便笺 Sticky Note
纯 Python + Tkinter 实现，无第三方依赖，可打包为独立 EXE。
"""

import os
import re
import sys
import socket
import json
import base64
import shutil
import threading
import time
import ctypes
from ctypes import wintypes
from datetime import datetime
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, colorchooser, filedialog, messagebox

# 系统托盘（可选；未安装时自动降级为直接退出）
try:
    import pystray
    from PIL import Image, ImageDraw
    _HAS_TRAY = True
except Exception:
    _HAS_TRAY = False

# Pillow 图像 → Tk 位图（用于悬浮球）。与托盘不同，未装 PIL 时悬浮球降级为纯画布。
try:
    from PIL import Image as _PILImage
    _HAS_PIL_TK = True
except Exception:
    _HAS_PIL_TK = False


def resource_path(rel: str) -> str:
    """兼容 PyInstaller：冻结后读 `_MEIPASS`，否则读源码目录。"""
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, rel)

# ------------------------------------------------------------
# 常量
# ------------------------------------------------------------
UNCHECKED = "\u2610"  # ☐
CHECKED = "\u2611"    # ☑
# 任务行前缀：复选框 + 零宽词连接符 + 不换行空格（共 3 个索引单位）。
# Text 使用 wrap=char，避免 word 在符号与正文间断行；U+2060+NBSP 进一步保证前缀成段。旧版 2 字符前缀仍兼容。
TASK_JOINER = "\u2060"  # WORD JOINER，零宽
TASK_GAP = "\u00a0"  # NBSP

# 单实例：本机回环端口（第二次启动向该端口发 1 字节以唤醒已有实例）
SINGLE_INSTANCE_PORT = 49673

# 字体族
FONT_FAMILY = "Microsoft YaHei UI"
FONT_SIZE = 11

# ------------------------------------------------------------
# 主题（配色）
# ------------------------------------------------------------
# 每套主题定义一组颜色；模块级 COLOR_xxx 常量由 apply_theme(name) 动态赋值。
# - simple_white 保留原来的极简白风格（默认）
# - 其余几套是"浅亮"取向的备选，可在"更多 → 主题颜色…"中切换
THEMES = {
    "simple_white": {
        "label": "简约白 · 默认",
        "BG": "#ffffff",
        "FG": "#3c3c3c",
        "SUBTLE": "#8a8a8a",
        "MUTED": "#b5b5b5",
        "BORDER": "#e6e6e6",
        "TOP_BG": "#ffffff",
        "TOOLBAR_BG": "#fafafa",
        "BTN_HOVER": "#eef1f5",
        "HIGHLIGHT": "#fff2a8",
        "SELECT": "#d8d8d8",
        "MENU_SEP": "#ececec",
        "TOOLTIP_BG": "#2b2b2b",
        "TOOLTIP_FG": "#ffffff",
    },
    "warm_cream": {
        "label": "奶油米 · 温润",
        "BG": "#fffdf6",
        "FG": "#3c3a34",
        "SUBTLE": "#8f8a7d",
        "MUTED": "#bdb6a6",
        "BORDER": "#ecd9b8",
        "TOP_BG": "#fff7dd",
        "TOOLBAR_BG": "#fff4cc",
        "BTN_HOVER": "#f3e7c1",
        "HIGHLIGHT": "#ffeb99",
        "SELECT": "#e5d6ae",
        "MENU_SEP": "#efe3c3",
        "TOOLTIP_BG": "#3c3a34",
        "TOOLTIP_FG": "#fffdf6",
    },
    "sky_mint": {
        "label": "天青薄荷 · 清爽",
        "BG": "#fafdff",
        "FG": "#2f4256",
        "SUBTLE": "#7e94a7",
        "MUTED": "#b2c3d2",
        "BORDER": "#d4e2f0",
        "TOP_BG": "#eef7fd",
        "TOOLBAR_BG": "#e6f3fb",
        "BTN_HOVER": "#d5ebf8",
        "HIGHLIGHT": "#cdf5e4",
        "SELECT": "#c7dcee",
        "MENU_SEP": "#dbe7f2",
        "TOOLTIP_BG": "#2f4256",
        "TOOLTIP_FG": "#fafdff",
    },
    "dusk_rose": {
        "label": "暮光粉 · 柔和",
        "BG": "#fffafc",
        "FG": "#4a3440",
        "SUBTLE": "#9d7a8b",
        "MUTED": "#c8b4bf",
        "BORDER": "#e6d3dc",
        "TOP_BG": "#fdeef3",
        "TOOLBAR_BG": "#fbe3eb",
        "BTN_HOVER": "#f2d4df",
        "HIGHLIGHT": "#ffd9ea",
        "SELECT": "#e9cddc",
        "MENU_SEP": "#eed5df",
        "TOOLTIP_BG": "#4a3440",
        "TOOLTIP_FG": "#fffafc",
    },
    "sage_paper": {
        "label": "草本米 · 护眼",
        "BG": "#f6f7f1",
        "FG": "#3a4138",
        "SUBTLE": "#85917e",
        "MUTED": "#b4bcae",
        "BORDER": "#d9ded0",
        "TOP_BG": "#edefe3",
        "TOOLBAR_BG": "#e7ebdd",
        "BTN_HOVER": "#dce2cd",
        "HIGHLIGHT": "#ecf2b4",
        "SELECT": "#d7ddc7",
        "MENU_SEP": "#dde2d2",
        "TOOLTIP_BG": "#3a4138",
        "TOOLTIP_FG": "#f6f7f1",
    },
}
DEFAULT_THEME = "simple_white"

# 模块级颜色常量（被整份代码引用）；由 apply_theme 动态覆盖。
COLOR_BG = COLOR_FG = COLOR_SUBTLE = COLOR_MUTED = COLOR_BORDER = ""
COLOR_TOP_BG = COLOR_TOOLBAR_BG = COLOR_BTN_HOVER = COLOR_HIGHLIGHT = ""
COLOR_SELECT = COLOR_MENU_SEP = COLOR_TOOLTIP_BG = COLOR_TOOLTIP_FG = ""
CURRENT_THEME = DEFAULT_THEME


def apply_theme(name: str):
    """把指定主题写入模块级 COLOR_xxx 常量。不重绘任何窗口；
    调用方需要自行刷新/重建 UI 才能看到效果。"""
    global COLOR_BG, COLOR_FG, COLOR_SUBTLE, COLOR_MUTED, COLOR_BORDER
    global COLOR_TOP_BG, COLOR_TOOLBAR_BG, COLOR_BTN_HOVER, COLOR_HIGHLIGHT
    global COLOR_SELECT, COLOR_MENU_SEP, COLOR_TOOLTIP_BG, COLOR_TOOLTIP_FG
    global CURRENT_THEME
    theme = THEMES.get(name) or THEMES[DEFAULT_THEME]
    CURRENT_THEME = name if name in THEMES else DEFAULT_THEME
    COLOR_BG = theme["BG"]
    COLOR_FG = theme["FG"]
    COLOR_SUBTLE = theme["SUBTLE"]
    COLOR_MUTED = theme["MUTED"]
    COLOR_BORDER = theme["BORDER"]
    COLOR_TOP_BG = theme["TOP_BG"]
    COLOR_TOOLBAR_BG = theme["TOOLBAR_BG"]
    COLOR_BTN_HOVER = theme["BTN_HOVER"]
    COLOR_HIGHLIGHT = theme["HIGHLIGHT"]
    COLOR_SELECT = theme["SELECT"]
    COLOR_MENU_SEP = theme["MENU_SEP"]
    COLOR_TOOLTIP_BG = theme["TOOLTIP_BG"]
    COLOR_TOOLTIP_FG = theme["TOOLTIP_FG"]


# 先用默认主题初始化一次，模块其它位置才能安全引用 COLOR_xxx
apply_theme(DEFAULT_THEME)

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


# 多便笺：每张便笺单独一个文件，放在 notes/ 子目录
NOTES_DIR = os.path.join(get_data_dir(), "notes")

# 老版本单便笺文件（仅在迁移时读取；迁移后会被重命名为 .migrated）
LEGACY_MD = os.path.join(get_data_dir(), "notes.md")
LEGACY_JSON = os.path.join(get_data_dir(), "notes.json")
LEGACY_CONFIG = os.path.join(get_data_dir(), "config.json")

# 应用全局偏好（与具体便笺无关的开关，如"永不显示悬浮球"）
APP_PREFS_PATH = os.path.join(get_data_dir(), "app.json")

# 悬浮球图标路径（打包时通过 --add-data 带上 static 目录）
BALL_IMAGE_PATH = resource_path(os.path.join("static", "便笺.png"))
# Windows 窗口/任务栏图标路径（打包时通过 --add-data 带上 static 目录）
APP_ICON_PATH = resource_path(os.path.join("static", "app.ico"))
APP_USER_MODEL_ID = "bianjian.stickynote.app"
BALL_SIZE = 40
BALL_PEEK = 16
BALL_AUTO_HIDE_MS = 3000
BALL_EDGE_TOLERANCE = 3

# Win32 layered window constants (Windows only)
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
BI_RGB = 0
DIB_RGB_COLORS = 0
LR_LOADFROMFILE = 0x00000010
IMAGE_ICON = 1
WM_SETICON = 0x0080
ICON_SMALL = 0
ICON_BIG = 1


class _POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class _SIZE(ctypes.Structure):
    _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]


class _BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_ubyte),
        ("BlendFlags", ctypes.c_ubyte),
        ("SourceConstantAlpha", ctypes.c_ubyte),
        ("AlphaFormat", ctypes.c_ubyte),
    ]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


def _rgba_to_premultiplied_bgra_bytes(img):
    rgba = img.convert("RGBA").tobytes()
    src = memoryview(rgba)
    out = bytearray(len(rgba))
    for i in range(0, len(src), 4):
        r = src[i]
        g = src[i + 1]
        b = src[i + 2]
        a = src[i + 3]
        out[i] = (b * a) // 255
        out[i + 1] = (g * a) // 255
        out[i + 2] = (r * a) // 255
        out[i + 3] = a
    return bytes(out)


def _update_layered_window_rgba(hwnd, pil_img, x, y):
    """Windows per-pixel alpha 绘制。失败抛异常由调用方兜底。"""
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    w, h = pil_img.size
    bgra = _rgba_to_premultiplied_bgra_bytes(pil_img)

    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if not (style & WS_EX_LAYERED):
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)

    bmi = _BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = -h  # top-down DIB
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = BI_RGB
    bmi.bmiHeader.biSizeImage = w * h * 4

    bits = ctypes.c_void_p()
    hdc_screen = user32.GetDC(None)
    if not hdc_screen:
        raise RuntimeError("GetDC failed")
    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
    if not hdc_mem:
        user32.ReleaseDC(None, hdc_screen)
        raise RuntimeError("CreateCompatibleDC failed")

    hbitmap = gdi32.CreateDIBSection(
        hdc_mem, ctypes.byref(bmi), DIB_RGB_COLORS, ctypes.byref(bits), None, 0
    )
    if not hbitmap or not bits:
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(None, hdc_screen)
        raise RuntimeError("CreateDIBSection failed")

    old_obj = gdi32.SelectObject(hdc_mem, hbitmap)
    ctypes.memmove(bits, bgra, len(bgra))

    pt_dst = _POINT(int(x), int(y))
    size = _SIZE(int(w), int(h))
    pt_src = _POINT(0, 0)
    blend = _BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)

    ok = user32.UpdateLayeredWindow(
        hwnd,
        hdc_screen,
        ctypes.byref(pt_dst),
        ctypes.byref(size),
        hdc_mem,
        ctypes.byref(pt_src),
        0,
        ctypes.byref(blend),
        ULW_ALPHA,
    )

    gdi32.SelectObject(hdc_mem, old_obj)
    gdi32.DeleteObject(hbitmap)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(None, hdc_screen)

    if not ok:
        raise RuntimeError("UpdateLayeredWindow failed")


def new_note_id() -> str:
    """生成新便笺 ID：YYYYMMDD-HHMMSS，必要时加后缀避免同秒内冲突。"""
    base = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = base
    suffix = 1
    while os.path.exists(os.path.join(NOTES_DIR, f"{candidate}.json")):
        suffix += 1
        candidate = f"{base}-{suffix}"
    return candidate


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
        self._last_close_at = 0.0

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
        self._last_close_at = time.monotonic()

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


def _try_ping_existing_instance():
    """若已有实例在监听 SINGLE_INSTANCE_PORT，向其发送唤醒信号。成功返回 True。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect(("127.0.0.1", SINGLE_INSTANCE_PORT))
        s.sendall(b"\x01")
        return True
    except OSError:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


# ------------------------------------------------------------
# 主类
# ------------------------------------------------------------
class StickyNote:
    """单张便笺窗口。

    不直接持有 tk.Tk()；由 NotesApp 管理生命周期，自身是一个 Toplevel。
    所有数据根据 note_id 派生到 notes/<id>.md / notes/<id>.json。
    """

    def __init__(self, app, note_id, is_new=False):
        self.app = app
        self.note_id = note_id
        self.md_path = os.path.join(NOTES_DIR, f"{note_id}.md")
        self.json_path = os.path.join(NOTES_DIR, f"{note_id}.json")

        self.root = tk.Toplevel(app.root)
        self.root.overrideredirect(True)
        self.root.configure(bg=COLOR_BORDER)

        # 读取配置（从 json 内嵌的 window 段）
        self.config = self._load_window_config()

        if self.config.get("geometry"):
            geo = self.config["geometry"]
        else:
            # 新便笺：按现有便笺数做堆叠偏移，避免全部重叠
            idx = len(app.notes)
            off = idx * 28
            geo = f"{INIT_W}x{INIT_H}+{240 + off}+{160 + off}"
        self.root.geometry(geo)
        self.root.minsize(MIN_W, MIN_H)

        self.pinned = self.config.get("pinned", True)
        self.transparency = float(self.config.get("transparency", 1.0))
        self.highlight_color = self.config.get("highlight_color", COLOR_HIGHLIGHT)
        # 便笺标题：默认 note-<id>；用户可点击顶栏中央编辑
        self.title_text = self.config.get("title") or f"note-{note_id}"
        try:
            self.root.title(self.title_text)
        except Exception:
            pass

        self.root.attributes("-topmost", self.pinned)
        self.root.attributes("-alpha", self.transparency)

        # 让无边框 Toplevel 也出现在任务栏
        self.root.after(10, self._register_taskbar)

        # 状态变量
        self._drag_data = {"x": 0, "y": 0}
        self._resize_data = {"x": 0, "y": 0, "w": 0, "h": 0}
        self._saving_job = None
        self._reorder_job = None
        self._reordering = False
        self._click_lock = False
        self._press_info = None
        self._select_all_active = False
        self._minimize_pending_restore = False
        self._hide_state = "visible"
        self._hide_edge = None
        self._edge_check_job = None
        self._visible = True
        self._destroyed = False

        self._build_ui()
        self._bind_events()
        self._load_notes()

        # 定时检查贴边
        self._schedule_edge_check()

        # 窗口关闭协议：按用户设置执行“隐藏到托盘 / 退出程序”
        self.root.protocol("WM_DELETE_WINDOW", self.request_close)

        # 新便笺：立刻落盘一次，确保文件存在
        if is_new:
            try:
                self._save_notes(force=False)
            except Exception:
                pass

    # --------------------------------------------------------
    # 配置（内嵌在 <id>.json 的 window 段）
    # --------------------------------------------------------
    def _load_window_config(self):
        """从本便笺的 json 里读取窗口配置；读不到返回 {}。"""
        if os.path.exists(self.json_path):
            try:
                with open(self.json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                win = data.get("window", {})
                if isinstance(win, dict):
                    return win
            except Exception:
                pass
        return {}

    def _save_config(self):
        """仅更新 json 的 window 段，不重序列化 lines（频繁调用的轻量路径）。"""
        if self._destroyed:
            return
        try:
            os.makedirs(NOTES_DIR, exist_ok=True)
            if os.path.exists(self.json_path):
                try:
                    with open(self.json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    data = {"version": 2, "lines": []}
            else:
                data = {"version": 2, "lines": []}
            data["id"] = self.note_id
            data["title"] = self.title_text
            data["window"] = {
                "geometry": self.root.geometry(),
                "pinned": self.pinned,
                "transparency": self.transparency,
                "highlight_color": self.highlight_color,
                "title": self.title_text,
            }
            with open(self.json_path, "w", encoding="utf-8") as f:
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
            self._apply_window_icon(hwnd)
            self.root.after(10, self.root.deiconify)
        except Exception:
            pass

    def _apply_window_icon(self, hwnd=None):
        """设置窗口图标：优先 app.ico，并显式推送大小图标给 Win32。"""
        if not os.path.exists(APP_ICON_PATH):
            return
        try:
            self.root.iconbitmap(APP_ICON_PATH)
        except Exception:
            pass
        try:
            import ctypes

            if hwnd is None:
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            if not hwnd:
                return

            # 32/48 像素分别覆盖小图标与大图标，任务栏与 Alt+Tab 显示更清晰。
            small_icon = ctypes.windll.user32.LoadImageW(
                None, APP_ICON_PATH, IMAGE_ICON, 32, 32, LR_LOADFROMFILE
            )
            big_icon = ctypes.windll.user32.LoadImageW(
                None, APP_ICON_PATH, IMAGE_ICON, 48, 48, LR_LOADFROMFILE
            )
            if small_icon:
                ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, small_icon)
                self._hicon_small = small_icon
            if big_icon:
                ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, big_icon)
                self._hicon_big = big_icon
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
        self.top_bar = tk.Frame(container, bg=COLOR_TOP_BG, height=40)
        self.top_bar.pack(fill="x", side="top")
        self.top_bar.pack_propagate(False)

        # 重要：pack 顺序决定空间分配——必须先 pack 左/右按钮组（固定宽度），
        # 再 pack 中间标题（expand=True 占剩余）。否则标题会把右侧按钮挤出窗口外，
        # 出现"关闭按钮不见了"的 bug。
        left = tk.Frame(self.top_bar, bg=COLOR_TOP_BG)
        left.pack(side="left", padx=6)
        self._icon_btn(left, "\u002B", self.app.new_note,
                       tip="新建便笺", size=18,
                       bg_override=COLOR_TOP_BG).pack(side="left", padx=1)
        self._icon_btn(left, "\u22EF", self.show_more_menu,
                       tip="更多", size=18,
                       bg_override=COLOR_TOP_BG).pack(side="left", padx=1)

        right = tk.Frame(self.top_bar, bg=COLOR_TOP_BG)
        right.pack(side="right", padx=6)
        self.pin_btn = self._icon_btn(
            right, self._pin_icon(), self.toggle_pin, tip="置顶", size=13,
            bg_override=COLOR_TOP_BG,
        )
        self.pin_btn.pack(side="left", padx=1)
        self._icon_btn(right, "\u2013", self.minimize_window,
                       tip="最小化为悬浮球（右侧）", size=14,
                       bg_override=COLOR_TOP_BG).pack(side="left", padx=1)
        self._icon_btn(right, "\u2715", self.request_close,
                       tip="隐藏到托盘 (右下角角标)",
                       size=14, hover=COLOR_BTN_HOVER,
                       bg_override=COLOR_TOP_BG).pack(side="left", padx=1)

        # 中间：便笺标题（双击可编辑，单击拖动窗口）。
        # 放最后 pack，只占 left/right 之外的剩余空间。
        self.title_frame = tk.Frame(self.top_bar, bg=COLOR_TOP_BG)
        self.title_frame.pack(side="left", fill="x", expand=True, padx=2)
        self.title_label = tk.Label(
            self.title_frame,
            text=self.title_text,
            bg=COLOR_TOP_BG,
            fg=COLOR_SUBTLE,
            font=(FONT_FAMILY, 10),
            cursor="hand2",
            anchor="center",
        )
        # width=0 + fill="x"：跟随父容器宽度；父容器宽度受 left/right 占位约束，
        # 文本过长时由 Tk 自动截断绘制，不会反向撑开父 frame 挤掉右侧按钮。
        self.title_label.pack(fill="x")
        self.title_label.bind("<ButtonPress-1>", self._start_move)
        self.title_label.bind("<B1-Motion>", self._do_move)
        self.title_label.bind("<Double-Button-1>", self._begin_edit_title)
        self.title_entry = None  # lazy-create

        # 顶栏（除标题区）用作拖动
        for w in (self.top_bar, left, right):
            w.bind("<ButtonPress-1>", self._start_move)
            w.bind("<B1-Motion>", self._do_move)
            w.bind("<Double-Button-1>", lambda e: None)

        # 顶栏与内容区之间的分隔线（与底栏分隔线呼应）
        sep_top = tk.Frame(container, bg=COLOR_BORDER, height=1)
        sep_top.pack(fill="x", side="top")

        # 编辑区
        text_frame = tk.Frame(container, bg=COLOR_BG)
        text_frame.pack(fill="both", expand=True)

        self.text = tk.Text(
            text_frame,
            # char：避免 word 在「☐」与正文间断行（复选框独占一行）；中文按字换行观感可接受
            wrap="char",
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
        # 任务行换行悬挂缩进（续行与「☐」后正文首字对齐）
        self._configure_task_hang_tag()

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
        self.more_menu.add_command("新建便笺", self.app.new_note)
        self.more_menu.add_command("打开便笺\u2026", lambda: self.app.show_note_picker(self.root))
        self.more_menu.add_command("新建任务", self.new_task_top)
        self.more_menu.add_command("切换任务 / 增删复选框", self.toggle_task_lines, "Ctrl+L")
        self.more_menu.add_separator()
        self.more_menu.add_command("切换置顶", self.toggle_pin)
        self.more_menu.add_command("窗口尺寸\u2026", self.show_size_dialog)
        self.more_menu.add_command("透明度调节\u2026", self.show_transparency_dialog)
        self.more_menu.add_command("高亮颜色\u2026", self.choose_highlight_color)
        self.more_menu.add_command("主题颜色\u2026", self.show_theme_dialog)
        self.more_menu.add_separator()
        self.more_menu.add_command("手动保存", lambda: self._save_notes(force=True), "Ctrl+S")
        self.more_menu.add_command("清空所有任务", self.clear_all)
        self.more_menu.add_command("打开存储目录", self.open_save_dir)
        self.more_menu.add_separator()
        self.more_menu.add_command("最小化", self.minimize_window)
        self.more_menu.add_command("隐藏到托盘", self.hide_to_tray)
        self.more_menu.add_command("关闭模式…", self.show_close_mode_dialog)
        self.more_menu.add_command("删除此便笺", self.delete_this_note)
        self.more_menu.add_command("关于", self.show_about)
        self.more_menu.add_command("退出程序", self.real_quit)

    # --------------------------------------------------------
    # 按钮工厂
    # --------------------------------------------------------
    def _icon_btn(self, parent, text, cmd, tip="", size=14,
                  hover=None, bg_override=None):
        # 默认参数若直接写 COLOR_xxx 会被 def 时求值，切主题就失效——这里延迟到调用时再取
        base_bg = bg_override if bg_override else COLOR_BG
        hover_bg = hover if hover else COLOR_BTN_HOVER
        btn = tk.Label(parent, text=text, bg=base_bg, fg=COLOR_SUBTLE,
                       font=(FONT_FAMILY, size), padx=8, pady=2, cursor="hand2")
        btn.bind("<Button-1>", lambda e: cmd())
        btn.bind("<Enter>", lambda e: btn.configure(bg=hover_bg, fg=COLOR_FG))
        btn.bind("<Leave>", lambda e: btn.configure(bg=base_bg, fg=COLOR_SUBTLE))
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
        # 左右方向键后纠正光标：任务行不允许落在 checkbox 左侧/内部
        self.text.bind("<Left>", self._on_left_right, add="+")
        self.text.bind("<Right>", self._on_left_right, add="+")
        # 上下方向键后纠正光标（仅普通移动；Shift+上下扩选不介入）
        self.text.bind("<Up>", self._on_up_down, add="+")
        self.text.bind("<Down>", self._on_up_down, add="+")
        # 顶部边界：抑制 Shift+Up 重复触发导致的选区闪烁
        self.text.bind("<Shift-Up>", self._on_shift_up, add="+")
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
        """返回 (is_task, checked, prefix_len)。规范前缀 3 字符；旧数据可为 2 字符。"""
        line_start = f"{line_no}.0"
        line_end = f"{line_no}.end"
        content = self.text.get(line_start, line_end)
        if not content:
            return False, False, 0
        if len(content) >= 3:
            c0, c1, c2 = content[0], content[1], content[2]
            if c0 == UNCHECKED and c1 == TASK_JOINER and c2 in (" ", TASK_GAP):
                return True, False, 3
            if c0 == CHECKED and c1 == TASK_JOINER and c2 in (" ", TASK_GAP):
                return True, True, 3
        if len(content) >= 2:
            c0, c1 = content[0], content[1]
            if c0 == UNCHECKED and c1 in (" ", TASK_GAP):
                return True, False, 2
            if c0 == CHECKED and c1 in (" ", TASK_GAP):
                return True, True, 2
        return False, False, 0

    def _current_line_no(self) -> int:
        return int(self.text.index("insert").split(".")[0])

    def _insert_task_at_line_start(self, line_no: int, checked=False,
                                   priority=DEFAULT_PRIORITY):
        ch = CHECKED if checked else UNCHECKED
        prefix = f"{ch}{TASK_JOINER}{TASK_GAP}"
        line_start = f"{line_no}.0"
        self.text.insert(line_start, prefix)
        self.text.tag_add("checkbox_done" if checked else "checkbox",
                          line_start, f"{line_no}.1")
        if checked:
            self._apply_done_style(line_no, True)
        # 应用默认优先级背景（整行至换行符，保证色块贯穿整行宽度）
        self._apply_priority(line_no, priority)

    def _apply_done_style(self, line_no: int, done: bool):
        is_task, _c, plen = self._line_prefix_info(line_no)
        if not is_task:
            return
        text_start = f"{line_no}.{plen}"
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

    def _configure_task_hang_tag(self):
        """按当前 Text 字体测量「复选框+空格」宽度，配置 task_hang 的 lmargin2。"""
        try:
            fn = tkfont.Font(self.root, font=self.text.cget("font"))
            w = max(
                fn.measure(UNCHECKED + TASK_JOINER + TASK_GAP),
                fn.measure(CHECKED + TASK_JOINER + TASK_GAP),
                fn.measure(UNCHECKED + TASK_GAP),
                fn.measure(CHECKED + TASK_GAP),
                fn.measure(UNCHECKED + " "),
                fn.measure(CHECKED + " "),
            )
            self.text.tag_configure("task_hang", lmargin1=0, lmargin2=w)
        except Exception:
            self.text.tag_configure("task_hang", lmargin1=0, lmargin2=22)

    def _sync_task_hang_indents(self):
        """为任务逻辑行挂上 task_hang（悬挂缩进），非任务行移除。"""
        if getattr(self, "_destroyed", False):
            return
        try:
            self._configure_task_hang_tag()
        except Exception:
            pass
        try:
            last_line = int(self.text.index("end-1c").split(".")[0])
        except Exception:
            return
        for ln in range(1, last_line + 1):
            start, end = self._line_range_with_newline(ln)
            is_task, _, _ = self._line_prefix_info(ln)
            if is_task:
                self.text.tag_add("task_hang", start, end)
            else:
                self.text.tag_remove("task_hang", start, end)

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
            _t, _c, _plen = self._line_prefix_info(new_line_no)
            self.text.mark_set("insert", f"{new_line_no}.{_plen}")
        self._sync_task_hang_indents()
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
            ch = CHECKED if checked else UNCHECKED
            empty_task_only = line_text in (
                ch + TASK_JOINER + TASK_GAP,
                ch + TASK_JOINER + " ",
                ch + TASK_GAP,
                ch + " ",
            )
            # 空任务行：直接删除整行（合并到上一行），不再只是卡在 prefix
            if empty_task_only:
                if line_no > 1:
                    self.text.delete(f"{line_no - 1}.end", f"{line_no}.end")
                    self._sync_task_hang_indents()
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
        """Home：任务行落到 prefix 之后；Shift+Home 扩展选区。"""
        idx = self.text.index("insert")
        line_no = int(idx.split(".")[0])
        is_task, _, prefix_len = self._line_prefix_info(line_no)
        target = f"{line_no}.{prefix_len if is_task else 0}"
        # Shift+Home：保留并扩展选区（不走默认 Tk，避免任务行落到 prefix 之前）
        if event.state & 0x0001:
            # 仅当目标命中锚点时才折叠选区，避免连续 Shift+Home 误清空选区
            if self._selection_exists():
                try:
                    sel_first = self.text.index("sel.first")
                    sel_last = self.text.index("sel.last")
                    anchor = self.text.index("anchor")
                except tk.TclError:
                    sel_first = sel_last = anchor = None
                if sel_first and self.text.compare(target, "==", anchor):
                    self.text.mark_set("insert", target)
                    self.text.mark_set("anchor", target)
                    self.text.tag_remove("sel", "1.0", "end")
                    return "break"

            if not self._selection_exists():
                self.text.mark_set("anchor", "insert")
            self.text.mark_set("insert", target)
            anchor = self.text.index("anchor")
            cur = self.text.index("insert")
            self.text.tag_remove("sel", "1.0", "end")
            if self.text.compare(anchor, "<", cur):
                self.text.tag_add("sel", anchor, cur)
            elif self.text.compare(anchor, ">", cur):
                self.text.tag_add("sel", cur, anchor)
            # 复用现有规则：选区自动避开 checkbox prefix
            self._on_selection_changed()
            return "break"

        self.text.mark_set("insert", target)
        # 普通 Home：清除可能的选区
        self.text.tag_remove("sel", "1.0", "end")
        return "break"

    def _on_left_right(self, _event):
        """左右键后纠正插入点：任务行光标不得进入 checkbox prefix。"""
        self.root.after_idle(self._clamp_insert_after_prefix)
        return None

    def _on_up_down(self, event):
        """上下键后纠正插入点（含 Shift+上下扩选场景）。"""
        self.root.after_idle(self._clamp_insert_after_prefix)
        return None

    def _on_shift_up(self, _event):
        """到达首行前缀边界后，吞掉重复 Shift+Up，避免选区闪烁。"""
        try:
            idx = self.text.index("insert")
            line_no = int(idx.split(".")[0])
            col = int(idx.split(".")[1])
        except Exception:
            return None
        if line_no != 1:
            return None
        is_task, _checked, prefix_len = self._line_prefix_info(1)
        if is_task and col <= prefix_len and self._selection_exists():
            self.text.mark_set("insert", f"1.{prefix_len}")
            return "break"
        return None

    def _clamp_insert_after_prefix(self):
        try:
            idx = self.text.index("insert")
            line_no = int(idx.split(".")[0])
            col = int(idx.split(".")[1])
        except Exception:
            return
        is_task, _checked, prefix_len = self._line_prefix_info(line_no)
        if is_task and col < prefix_len:
            self.text.mark_set("insert", f"{line_no}.{prefix_len}")

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
            _t, _c, _plen = self._line_prefix_info(1)
            self.text.mark_set("insert", f"1.{_plen}")
            self._sync_task_hang_indents()

    def _normalize_checkbox_prefixes(self):
        """归一化行首复选框前缀，避免出现 '☐ ☐ ' / '☑ ☐ ' 这类重复前缀。"""
        try:
            last_line = int(self.text.index("end-1c").split(".")[0])
        except Exception:
            return
        for ln in range(1, last_line + 1):
            line_start = f"{ln}.0"
            line_end = f"{ln}.end"
            content = self.text.get(line_start, line_end)
            if not content:
                continue
            is_task, checked, plen = self._line_prefix_info(ln)
            if not is_task:
                continue
            ch0 = CHECKED if checked else UNCHECKED
            rest = content[plen:]
            while True:
                if (
                    len(rest) >= 3
                    and rest[0] in (UNCHECKED, CHECKED)
                    and rest[1] == TASK_JOINER
                    and rest[2] in (" ", TASK_GAP)
                ):
                    rest = rest[3:]
                    continue
                if len(rest) >= 2 and rest[0] in (UNCHECKED, CHECKED) and rest[1] in (
                    " ",
                    TASK_GAP,
                ):
                    rest = rest[2:]
                    continue
                break
            new_line = ch0 + TASK_JOINER + TASK_GAP + rest
            if new_line != content:
                self.text.delete(line_start, line_end)
                self.text.insert(line_start, new_line)
                checked = ch0 == CHECKED
                self.text.tag_remove("checkbox", f"{ln}.0", f"{ln}.1")
                self.text.tag_remove("checkbox_done", f"{ln}.0", f"{ln}.1")
                self.text.tag_add("checkbox_done" if checked else "checkbox",
                                  f"{ln}.0", f"{ln}.1")
                self._apply_done_style(ln, checked)
        self._sync_task_hang_indents()

    def new_task_top(self):
        """在开头新增一个任务。"""
        self.text.insert("1.0", f"{UNCHECKED}{TASK_JOINER}{TASK_GAP}\n")
        self.text.tag_add("checkbox", "1.0", "1.1")
        self._apply_priority(1, DEFAULT_PRIORITY)
        _t, _c, _pl = self._line_prefix_info(1)
        self.text.mark_set("insert", f"1.{_pl}")
        self.text.focus_set()
        self._sync_task_hang_indents()
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
        self._sync_task_hang_indents()
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
        menu_win = getattr(self.more_menu, "_win", None)
        if menu_win is not None:
            try:
                if menu_win.winfo_exists():
                    self.more_menu.close()
                    return
            except Exception:
                # 菜单窗口状态异常时，继续走弹出逻辑。
                pass
        # 点击“更多”按钮时，菜单会先 FocusOut 关闭，再触发按钮回调；
        # 在一个很短窗口内抑制重开，避免出现“第二次点击又弹出”。
        if (time.monotonic() - getattr(self.more_menu, "_last_close_at", 0.0)) < 0.18:
            return
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
            os.makedirs(NOTES_DIR, exist_ok=True)
            os.startfile(NOTES_DIR)
        except Exception:
            pass

    # --------------------------------------------------------
    # 窗口尺寸（预设 + 自定义）
    # --------------------------------------------------------
    # 预设尺寸：(宽, 高, 标签)
    SIZE_PRESETS = (
        (280, 380, "紧凑"),
        (360, 500, "标准"),
        (440, 620, "宽松"),
        (560, 720, "超大"),
    )

    def show_size_dialog(self):
        dlg = FlatDialog(self.root, title="窗口尺寸", width=320)
        tk.Label(
            dlg.body,
            text="选择预设尺寸，或在下方自定义宽高（像素）。",
            bg=COLOR_BG, fg=COLOR_SUBTLE,
            font=(FONT_FAMILY, 10), justify="left",
        ).pack(anchor="w", pady=(0, 10))

        # 预设行
        preset_row = tk.Frame(dlg.body, bg=COLOR_BG)
        preset_row.pack(fill="x", pady=(0, 12))
        for w, h, label in self.SIZE_PRESETS:
            def apply_size(wv=w, hv=h):
                dlg.close()
                self.apply_window_size(wv, hv)
            flat_button(preset_row, f"{label}\n{w}×{h}", apply_size).pack(
                side="left", padx=(0, 6))

        # 自定义
        tk.Frame(dlg.body, bg=COLOR_MENU_SEP, height=1).pack(fill="x", pady=6)
        form = tk.Frame(dlg.body, bg=COLOR_BG)
        form.pack(fill="x", pady=(4, 8))

        cur_w = self.root.winfo_width()
        cur_h = self.root.winfo_height()
        tk.Label(form, text="宽度：", bg=COLOR_BG, fg=COLOR_FG,
                 font=(FONT_FAMILY, 10)).grid(row=0, column=0, sticky="w", padx=(0, 4), pady=3)
        w_var = tk.StringVar(value=str(cur_w))
        w_entry = tk.Entry(form, textvariable=w_var, bg="#ffffff", fg=COLOR_FG,
                           relief="flat", highlightthickness=1,
                           highlightbackground=COLOR_BORDER,
                           highlightcolor=COLOR_BORDER, width=8)
        w_entry.grid(row=0, column=1, sticky="w", pady=3)
        tk.Label(form, text=f"  (最小 {MIN_W})", bg=COLOR_BG, fg=COLOR_MUTED,
                 font=(FONT_FAMILY, 9)).grid(row=0, column=2, sticky="w")

        tk.Label(form, text="高度：", bg=COLOR_BG, fg=COLOR_FG,
                 font=(FONT_FAMILY, 10)).grid(row=1, column=0, sticky="w", padx=(0, 4), pady=3)
        h_var = tk.StringVar(value=str(cur_h))
        h_entry = tk.Entry(form, textvariable=h_var, bg="#ffffff", fg=COLOR_FG,
                           relief="flat", highlightthickness=1,
                           highlightbackground=COLOR_BORDER,
                           highlightcolor=COLOR_BORDER, width=8)
        h_entry.grid(row=1, column=1, sticky="w", pady=3)
        tk.Label(form, text=f"  (最小 {MIN_H})", bg=COLOR_BG, fg=COLOR_MUTED,
                 font=(FONT_FAMILY, 9)).grid(row=1, column=2, sticky="w")

        # 按钮
        btn_row = tk.Frame(dlg.body, bg=COLOR_BG)
        btn_row.pack(fill="x", pady=(10, 0))

        def on_ok():
            try:
                ww = int(w_var.get())
                hh = int(h_var.get())
            except ValueError:
                return
            dlg.close()
            self.apply_window_size(ww, hh)

        flat_button(btn_row, "取消", dlg.close).pack(side="right", padx=(6, 0))
        flat_button(btn_row, "应用", on_ok, primary=True).pack(side="right")
        w_entry.bind("<Return>", lambda _e: on_ok())
        h_entry.bind("<Return>", lambda _e: on_ok())

        dlg.place_near(self.root)
        dlg.focus_force()

    def apply_window_size(self, w, h):
        """把当前便笺调整到给定宽高。强制在 MIN 与屏幕之间夹逼。"""
        try:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            w = max(MIN_W, min(int(w), sw))
            h = max(MIN_H, min(int(h), sh - 40))
            # 保持左上角不变
            x = self.root.winfo_x()
            y = self.root.winfo_y()
            self.root.geometry(f"{w}x{h}+{x}+{y}")
            self._schedule_save()
        except Exception:
            pass

    # --------------------------------------------------------
    # 主题颜色（切换后重建所有便笺）
    # --------------------------------------------------------
    def show_theme_dialog(self):
        """弹出主题选择器：每项一行，点击即应用并持久化。"""
        dlg = FlatDialog(self.root, title="主题颜色", width=320)
        tk.Label(
            dlg.body,
            text="选择一个配色主题，所有便笺会一起切换。",
            bg=COLOR_BG,
            fg=COLOR_SUBTLE,
            font=(FONT_FAMILY, 10),
            justify="left",
            wraplength=320,
        ).pack(anchor="w", pady=(0, 10))

        list_frame = tk.Frame(dlg.body, bg=COLOR_BG)
        list_frame.pack(fill="both", expand=True)

        def apply_and_close(name):
            dlg.close()
            try:
                self.app.set_theme(name)
            except Exception:
                pass

        for key, theme in THEMES.items():
            is_current = (key == CURRENT_THEME)
            row = tk.Frame(list_frame, bg=COLOR_BG, cursor="hand2")
            row.pack(fill="x", pady=2)
            # 色卡（主色 + 顶栏 + 工具栏 3 小块）
            swatch = tk.Canvas(
                row, width=58, height=24,
                bg=COLOR_BG, highlightthickness=0, bd=0,
            )
            swatch.create_rectangle(0, 0, 20, 24, fill=theme["BG"], outline=theme["BORDER"])
            swatch.create_rectangle(20, 0, 40, 24, fill=theme["TOP_BG"], outline=theme["BORDER"])
            swatch.create_rectangle(40, 0, 58, 24, fill=theme["TOOLBAR_BG"], outline=theme["BORDER"])
            swatch.pack(side="left", padx=(4, 10), pady=4)

            lbl_text = theme["label"] + ("   （当前）" if is_current else "")
            lbl = tk.Label(
                row, text=lbl_text,
                bg=COLOR_BG,
                fg=COLOR_FG if is_current else COLOR_SUBTLE,
                anchor="w",
                font=(FONT_FAMILY, 10, "bold" if is_current else "normal"),
                padx=2, pady=4,
            )
            lbl.pack(side="left", fill="x", expand=True)

            for w in (row, swatch, lbl):
                w.bind("<Enter>", lambda _e, wgs=(row, lbl): (
                    wgs[0].configure(bg=COLOR_BTN_HOVER),
                    wgs[1].configure(bg=COLOR_BTN_HOVER),
                ))
                w.bind("<Leave>", lambda _e, wgs=(row, lbl): (
                    wgs[0].configure(bg=COLOR_BG),
                    wgs[1].configure(bg=COLOR_BG),
                ))
                w.bind("<Button-1>", lambda _e, k=key: apply_and_close(k))

        btn_row = tk.Frame(dlg.body, bg=COLOR_BG)
        btn_row.pack(fill="x", pady=(10, 0))
        flat_button(btn_row, "关闭", dlg.close).pack(side="right")

        dlg.place_near(self.root)
        dlg.focus_force()

    # --------------------------------------------------------
    # 便笺标题编辑
    # --------------------------------------------------------
    def _begin_edit_title(self, _event=None):
        """点击标题 → 切换为 Entry，可修改。"""
        if self.title_entry is not None:
            try:
                self.title_entry.focus_set()
            except Exception:
                pass
            return
        # 隐藏 label，用 Entry 覆盖
        var = tk.StringVar(value=self.title_text)
        entry = tk.Entry(
            self.title_frame,
            textvariable=var,
            bg="#ffffff",
            fg=COLOR_FG,
            font=(FONT_FAMILY, 10),
            relief="flat",
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
            highlightcolor=COLOR_BORDER,
            justify="center",
        )
        self.title_label.pack_forget()
        entry.pack(fill="x", expand=True, padx=2, pady=4)
        entry.focus_set()
        entry.select_range(0, "end")
        self.title_entry = entry

        def commit(_e=None):
            new_name = var.get().strip()
            if not new_name:
                new_name = f"note-{self.note_id}"
            self.title_text = new_name
            self.title_label.configure(text=new_name)
            try:
                entry.destroy()
            except Exception:
                pass
            self.title_entry = None
            self.title_label.pack(fill="x", expand=True)
            try:
                self.root.title(new_name)
            except Exception:
                pass
            self._schedule_save()
            try:
                self._save_config()
            except Exception:
                pass

        def cancel(_e=None):
            try:
                entry.destroy()
            except Exception:
                pass
            self.title_entry = None
            self.title_label.pack(fill="x", expand=True)

        entry.bind("<Return>", commit)
        entry.bind("<FocusOut>", commit)
        entry.bind("<Escape>", cancel)

    def show_about(self):
        flat_messagebox(
            self.root,
            "关于",
            "极简悬浮便笺 v1.1\n\n纯 Python + Tkinter 实现\n支持多窗口便笺 · 每张便笺独立文件\n\n数据保存目录：\nnotes/<id>.md + notes/<id>.json",
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
            try:
                ins_line = int(self.text.index("insert").split(".")[0])
                last_line = int(self.text.index("end-1c").split(".")[0])
                if ins_line == last_line:
                    self.text.see("insert")
            except tk.TclError:
                pass

    def _schedule_save(self):
        if self._saving_job:
            self.root.after_cancel(self._saving_job)
        self._saving_job = self.root.after(400, self._save_notes)

    def _save_notes(self, force=False):
        if self._destroyed:
            return
        try:
            md_lines, data = self._serialize()
            # 内嵌 window 配置 + id
            data["id"] = self.note_id
            data["title"] = self.title_text
            data["window"] = {
                "geometry": self.root.geometry(),
                "pinned": self.pinned,
                "transparency": self.transparency,
                "highlight_color": self.highlight_color,
                "title": self.title_text,
            }
            os.makedirs(NOTES_DIR, exist_ok=True)
            with open(self.md_path, "w", encoding="utf-8") as f:
                f.write("\n".join(md_lines))
            with open(self.json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
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
        if os.path.exists(self.json_path):
            try:
                with open(self.json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._load_from_json(data)
                loaded = True
            except Exception:
                loaded = False

        if not loaded and os.path.exists(self.md_path):
            try:
                with open(self.md_path, "r", encoding="utf-8") as f:
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
                self.text.insert("end", f"{ch}{TASK_JOINER}{TASK_GAP}")
                self.text.tag_add("checkbox_done" if checked else "checkbox",
                                  f"{line_no}.0", f"{line_no}.1")
                self._insert_segments(line_no, 3, line.get("segments", []))
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
        self._sync_task_hang_indents()

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
                self.text.insert("end", f"{ch}{TASK_JOINER}{TASK_GAP}")
                self.text.tag_add("checkbox_done" if checked else "checkbox",
                                  f"{line_no}.0", f"{line_no}.1")
                segments = self._parse_md_inline(m.group(2))
                self._insert_segments(line_no, 3, segments)
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
        self._sync_task_hang_indents()

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
            self._select_all_active = False
            return

        doc_end = self.text.index("end-1c")
        first_is_task, _c, first_plen = self._line_prefix_info(1)
        full_start = f"1.{first_plen if first_is_task else 0}"
        # Ctrl+A 全选场景：保持连续选区，不做逐行重建，避免大文本卡顿。
        if self.text.compare(start, "==", full_start) and self.text.compare(end, "==", doc_end):
            self._select_all_active = True
            return
        self._select_all_active = False

        start_line = int(start.split(".")[0])
        start_col = int(start.split(".")[1])
        end_line = int(end.split(".")[0])

        # 超大跨度选区不做逐行重建，避免 UI 偶发卡死。
        if end_line - start_line > 1200:
            return

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
            self.text.mark_set("anchor", start)
            self.text.mark_set("insert", "end-1c")
            self._select_all_active = True
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
            if (
                len(ln) >= 3
                and ln[0] == UNCHECKED
                and ln[1] == TASK_JOINER
                and ln[2] in (" ", TASK_GAP)
            ):
                out.append(ln[3:])
            elif len(ln) >= 2 and ln[0] == UNCHECKED and ln[1] in (" ", TASK_GAP):
                out.append(ln[2:])
            elif (
                len(ln) >= 3
                and ln[0] == CHECKED
                and ln[1] == TASK_JOINER
                and ln[2] in (" ", TASK_GAP)
            ):
                out.append(ln[3:])
            elif len(ln) >= 2 and ln[0] == CHECKED and ln[1] in (" ", TASK_GAP):
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

        # 防御：即便极端键盘时序使 start 偶发落到 prefix 左侧，也先夹紧到 prefix 后。
        s_line = int(start.split(".")[0])
        s_col = int(start.split(".")[1])
        s_is_task, _s_checked, s_plen = self._line_prefix_info(s_line)
        if s_is_task and s_col < s_plen:
            start = f"{s_line}.{s_plen}"

        # 全选（Ctrl+A）快速路径：直接清空并保留一个初始任务行。
        # 避免大选区跨行删除导致的残留 checkbox 与偶发卡顿。
        doc_end = self.text.index("end-1c")
        first_is_task, _c1, first_plen = self._line_prefix_info(1)
        full_start = f"1.{first_plen if first_is_task else 0}"
        is_full_doc_selection = (
            self.text.compare(start, "==", full_start)
            and self.text.compare(end, "==", doc_end)
        )
        if self._select_all_active or is_full_doc_selection:
            self._updating_sel = True
            try:
                self.text.delete("1.0", "end")
                self._ensure_first_task()
                self._normalize_checkbox_prefixes()
                self.text.tag_remove("sel", "1.0", "end")
            finally:
                self._updating_sel = False
                self._select_all_active = False
            self._sync_task_hang_indents()
            self._schedule_save()
            return

        sel_ranges = self.text.tag_ranges("sel")
        # 多段选区（由 _on_selection_changed 构造）必须按分段删除；
        # 若用 sel.first->sel.last 连续删除，会把中间被跳过的 checkbox prefix 也吞掉。
        if len(sel_ranges) > 2:
            insert_pos = str(sel_ranges[0])
            for i in range(len(sel_ranges) - 2, -1, -2):
                s = str(sel_ranges[i])
                e = str(sel_ranges[i + 1])
                if self.text.compare(s, "<", e):
                    self.text.delete(s, e)
            self._normalize_checkbox_prefixes()
            self.text.mark_set("insert", insert_pos)
            self.text.tag_remove("sel", "1.0", "end")
            self._select_all_active = False
            self._sync_task_hang_indents()
            self._schedule_save()
            return

        start_line = int(start.split(".")[0])
        start_col = int(start.split(".")[1])
        end_line = int(end.split(".")[0])

        if start_line == end_line:
            # 单行：选区已由 _on_selection_changed 避开 prefix
            self.text.delete(start, end)
            self._normalize_checkbox_prefixes()
            self.text.mark_set("insert", start)
            self._select_all_active = False
            self._sync_task_hang_indents()
            self._schedule_save()
            return

        # --- 多行：一次性跨行删除 ---
        # 选区 start 在首行 prefix 之后，end 在末行某位置。直接 delete(start, end)
        # 会把中间所有行（含 checkbox、换行）合并吃掉，末行剩余文字被拼到首行 prefix 之后。
        # 这是用户对"跨行选中后按退格"的自然预期。首行的 checkbox 永远被保留，因为
        # _on_selection_changed 已经把 start_col 卡在 prefix 之后。
        try:
            self.text.delete(start, end)
        except tk.TclError:
            return
        self._normalize_checkbox_prefixes()
        self.text.mark_set("insert", start)
        # 清除选区
        self.text.tag_remove("sel", "1.0", "end")
        self._select_all_active = False

        self._sync_task_hang_indents()
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
            self._sync_task_hang_indents()
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
    # 最小化 / 隐藏 / 退出（统一由 NotesApp 协调）
    # --------------------------------------------------------
    def minimize_window(self):
        """最小化。默认变成一个可拖拽的悬浮球；

        若用户在悬浮球右键菜单里选过"永不显示悬浮球"，则回退为传统任务栏 iconify。
        """
        try:
            self._save_config()
        except Exception:
            pass

        if not self.app.prefs.get("never_ball") and _HAS_PIL_TK:
            # 悬浮球模式：隐藏便笺 + 显示悬浮球
            try:
                self.root.withdraw()
            except Exception:
                pass
            self._visible = False
            try:
                ball = self.app.show_floating_ball(self)
                if ball is None:
                    # 图片不可用或悬浮球创建失败：回退传统最小化
                    try:
                        self.root.deiconify()
                    except Exception:
                        pass
                    self._legacy_minimize()
            except Exception:
                # 悬浮球创建失败时回退传统最小化
                self._legacy_minimize()
            return

        self._legacy_minimize()

    def _legacy_minimize(self):
        """传统最小化到任务栏。overrideredirect(True) 的窗口不能直接 iconify，
        需要先临时关闭无边框模式；用户从任务栏点回来时 `<Map>` 事件负责恢复样式。
        """
        self._minimize_pending_restore = True
        try:
            self.root.overrideredirect(False)
            self.root.iconify()
        except Exception:
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

    def delete_this_note(self):
        """永久删除当前便笺（弹确认框）。"""
        ok = flat_messagebox(
            self.root, "删除便笺",
            f"确定要永久删除这张便笺吗？\n内容无法恢复。\n\nID: {self.note_id}",
            kind="yesno",
        )
        if ok:
            try:
                self.app.delete_note(self)
            except Exception:
                pass

    def hide_to_tray(self):
        """关闭按钮：把本便笺隐藏到托盘。委托给 NotesApp 决定是否真正退出。"""
        self.app.hide_note(self)

    def _ask_close_mode(self, initial_mode="tray", initial_remember=False):
        """关闭确认：选择“最小化到托盘 / 关闭程序”，可勾选永久保存。"""
        dlg = FlatDialog(self.root, title="关闭选项", width=360)

        tk.Label(
            dlg.body,
            text="点击关闭按钮时，你希望执行哪种操作？",
            bg=COLOR_BG, fg=COLOR_SUBTLE,
            font=(FONT_FAMILY, 10), justify="left",
        ).pack(anchor="w", pady=(0, 10))

        mode_var = tk.StringVar(value=initial_mode if initial_mode in ("tray", "quit") else "tray")
        remember_var = tk.BooleanVar(value=bool(initial_remember))
        option_bg = COLOR_BG
        option_hover = COLOR_BTN_HOVER

        tk.Frame(dlg.body, bg=COLOR_MENU_SEP, height=1).pack(fill="x", pady=(0, 8))

        def _radio_row(text, value, desc):
            row = tk.Frame(dlg.body, bg=option_bg, cursor="hand2")
            row.pack(fill="x", pady=2)
            icon = tk.Label(
                row,
                text="",
                bg=option_bg,
                fg=COLOR_FG,
                font=(FONT_FAMILY, 11),
                padx=6,
                pady=2,
            )
            icon.pack(side="left", anchor="n")
            text_wrap = tk.Frame(row, bg=option_bg)
            text_wrap.pack(side="left", fill="x", expand=True)
            title = tk.Label(
                text_wrap,
                text=text,
                bg=option_bg,
                fg=COLOR_FG,
                anchor="w",
                justify="left",
                font=(FONT_FAMILY, 10),
                padx=0,
                pady=2,
            )
            title.pack(fill="x")
            tip = tk.Label(
                text_wrap,
                text=desc,
                bg=option_bg,
                fg=COLOR_MUTED,
                font=(FONT_FAMILY, 9),
                anchor="w",
                justify="left",
                padx=0,
                pady=0,
            )
            tip.pack(fill="x", pady=(0, 4))

            def refresh_icon():
                icon.configure(text="◉" if mode_var.get() == value else "○")

            def choose(_e=None):
                mode_var.set(value)
                refresh_icon()

            def on_enter(_e=None):
                row.configure(bg=option_hover)
                icon.configure(bg=option_hover)
                text_wrap.configure(bg=option_hover)
                title.configure(bg=option_hover)
                tip.configure(bg=option_hover)

            def on_leave(_e=None):
                row.configure(bg=option_bg)
                icon.configure(bg=option_bg)
                text_wrap.configure(bg=option_bg)
                title.configure(bg=option_bg)
                tip.configure(bg=option_bg)

            for w in (row, icon, text_wrap, title, tip):
                w.bind("<Button-1>", choose)
                w.bind("<Enter>", on_enter)
                w.bind("<Leave>", on_leave)
            mode_var.trace_add("write", lambda *_: refresh_icon())
            refresh_icon()
            return row

        _radio_row("最小化到托盘（默认推荐）", "tray", "关闭窗口后仍常驻后台，可从右下角图标快速恢复。")
        _radio_row("关闭程序", "quit", "退出整个便笺应用，所有窗口都会关闭。")

        tk.Frame(dlg.body, bg=COLOR_MENU_SEP, height=1).pack(fill="x", pady=(8, 8))

        remember_row = tk.Frame(dlg.body, bg=option_bg, cursor="hand2")
        remember_row.pack(fill="x")
        remember_icon = tk.Label(
            remember_row,
            text="",
            bg=option_bg,
            fg=COLOR_FG,
            font=(FONT_FAMILY, 11),
            padx=6,
            pady=2,
        )
        remember_icon.pack(side="left")
        remember_text = tk.Label(
            remember_row,
            text="永久保存此选项",
            bg=option_bg,
            fg=COLOR_FG,
            font=(FONT_FAMILY, 10),
            anchor="w",
            justify="left",
            padx=0,
            pady=2,
        )
        remember_text.pack(side="left", fill="x", expand=True)

        def refresh_remember_icon():
            remember_icon.configure(text="☑" if remember_var.get() else "☐")

        def toggle_remember(_e=None):
            remember_var.set(not remember_var.get())
            refresh_remember_icon()

        def remember_enter(_e=None):
            remember_row.configure(bg=option_hover)
            remember_icon.configure(bg=option_hover)
            remember_text.configure(bg=option_hover)

        def remember_leave(_e=None):
            remember_row.configure(bg=option_bg)
            remember_icon.configure(bg=option_bg)
            remember_text.configure(bg=option_bg)

        for w in (remember_row, remember_icon, remember_text):
            w.bind("<Button-1>", toggle_remember)
            w.bind("<Enter>", remember_enter)
            w.bind("<Leave>", remember_leave)
        refresh_remember_icon()

        result = {"ok": False}

        def confirm():
            result["ok"] = True
            dlg.result = (mode_var.get(), bool(remember_var.get()))
            dlg.close()

        btn_row = tk.Frame(dlg.body, bg=COLOR_BG)
        btn_row.pack(fill="x", pady=(12, 0))
        flat_button(btn_row, "取消", dlg.close).pack(side="right", padx=(6, 0))
        flat_button(btn_row, "确定", confirm, primary=True).pack(side="right")

        dlg.place_near(self.root)
        dlg.focus_force()
        dlg.grab_set()
        self.root.wait_window(dlg)

        if not result["ok"]:
            return None
        return dlg.result

    def request_close(self):
        """统一处理关闭动作：按用户配置决定托盘隐藏或退出程序。"""
        saved_mode = self.app.prefs.get("close_mode", "tray")
        saved_mode = saved_mode if saved_mode in ("tray", "quit") else "tray"
        locked = bool(self.app.prefs.get("close_mode_locked", False))

        mode = saved_mode
        if not locked:
            picked = self._ask_close_mode(initial_mode=saved_mode, initial_remember=False)
            if picked is None:
                return
            mode, remember = picked
            if remember:
                self.app.set_pref("close_mode", mode)
                self.app.set_pref("close_mode_locked", True)

        if mode == "quit":
            self.real_quit()
        else:
            self.hide_to_tray()

    def show_close_mode_dialog(self):
        """在设置中修改关闭模式与“是否永久保存”开关。"""
        saved_mode = self.app.prefs.get("close_mode", "tray")
        saved_mode = saved_mode if saved_mode in ("tray", "quit") else "tray"
        locked = bool(self.app.prefs.get("close_mode_locked", False))
        picked = self._ask_close_mode(initial_mode=saved_mode, initial_remember=locked)
        if picked is None:
            return
        mode, remember = picked
        self.app.set_pref("close_mode", mode)
        self.app.set_pref("close_mode_locked", remember)

    def show_from_tray(self):
        """从托盘/隐藏状态恢复。"""
        self.app.show_note(self)

    def real_quit(self):
        """兼容老引用：由 app 统一退出整个程序。"""
        self.app.real_quit()

    # 兼容旧引用
    def close_app(self):
        self.hide_to_tray()

    def destroy(self):
        """永久销毁当前便笺窗口（不删文件；仅在 NotesApp 调用时使用）。"""
        self._destroyed = True
        # 顺手撤掉对应悬浮球
        try:
            self.app.destroy_floating_ball(self.note_id)
        except Exception:
            pass
        # 停掉可能的延时任务，避免悬挂回调
        for job_attr in ("_saving_job", "_reorder_job", "_edge_check_job"):
            j = getattr(self, job_attr, None)
            if j:
                try:
                    self.root.after_cancel(j)
                except Exception:
                    pass
                setattr(self, job_attr, None)
        try:
            self.root.destroy()
        except Exception:
            pass


# ------------------------------------------------------------
# 悬浮球：最小化时代替任务栏图标，支持拖拽、右键菜单
# ------------------------------------------------------------
def _load_ball_image(size=BALL_SIZE):
    """加载 static/便笺.png，缩放到 size。失败返回 None。"""
    if not _HAS_PIL_TK:
        return None
    if not os.path.exists(BALL_IMAGE_PATH):
        return None
    try:
        img = _PILImage.open(BALL_IMAGE_PATH).convert("RGBA")
        img = img.resize((size, size), _PILImage.LANCZOS)
        return img
    except Exception:
        return None


class FloatingBall:
    """最小化后的悬浮球：圆形、可拖动、双击/单击恢复便笺、右键菜单。

    每张便笺最多对应一个悬浮球实例，由 NotesApp 统一管理。
    """

    def __init__(self, app, note):
        self.app = app
        self.note = note
        self.topmost = True
        self._auto_hide_job = None
        self._is_edge_hidden = False
        self._is_dragging = False
        self._last_interaction_dragged = False

        self.win = tk.Toplevel(app.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", self.topmost)

        raw_img = _load_ball_image(BALL_SIZE)
        if raw_img is None:
            raise RuntimeError("floating ball image unavailable")
        self._render_w, self._render_h = raw_img.size
        self.win.configure(cursor="hand2")

        # 初始位置：默认贴屏幕最右侧；y 尽量沿用便笺位置
        try:
            ny = note.root.winfo_y()
            if ny > -2000:
                y = ny + 8
            else:
                raise ValueError
        except Exception:
            sh = self.win.winfo_screenheight()
            y = sh - self._render_h - 120
        sw = self.win.winfo_screenwidth()
        x = sw - self._render_w
        self.win.geometry(f"{self._render_w}x{self._render_h}+{int(x)}+{int(y)}")
        self.win.update_idletasks()

        # 使用 Win32 分层窗口做按像素透明渲染（无色键）
        try:
            hwnd = ctypes.windll.user32.GetParent(self.win.winfo_id())
            if not hwnd:
                hwnd = self.win.winfo_id()
            _update_layered_window_rgba(hwnd, raw_img, x, y)
        except Exception as e:
            raise RuntimeError(f"layered window init failed: {e}") from e

        # 拖拽 / 单击 / 右键
        self._drag = {"x": 0, "y": 0, "moved": False}
        self.win.bind("<ButtonPress-1>", self._on_press)
        self.win.bind("<B1-Motion>", self._on_drag)
        self.win.bind("<ButtonRelease-1>", self._on_release)
        self.win.bind("<Double-Button-1>", lambda e: self.open_note())
        self.win.bind("<Button-3>", self._on_right)
        self.win.bind("<Enter>", self._on_mouse_enter)
        self.win.bind("<Leave>", self._on_mouse_leave)
        self._schedule_right_edge_hide()

    # ------- 交互 -------
    def _cancel_right_edge_hide(self):
        if self._auto_hide_job:
            try:
                self.win.after_cancel(self._auto_hide_job)
            except Exception:
                pass
            self._auto_hide_job = None

    def _at_right_edge(self):
        sw = self.win.winfo_screenwidth()
        x = self.win.winfo_x()
        right_edge = x + self._render_w
        return abs(sw - right_edge) <= BALL_EDGE_TOLERANCE

    def _schedule_right_edge_hide(self):
        self._cancel_right_edge_hide()
        if self._is_edge_hidden:
            return
        if not self._at_right_edge():
            return
        self._auto_hide_job = self.win.after(BALL_AUTO_HIDE_MS, self._hide_to_right_edge)

    def _hide_to_right_edge(self):
        self._auto_hide_job = None
        if self._is_edge_hidden:
            return
        if not self._at_right_edge():
            return
        sw = self.win.winfo_screenwidth()
        x = sw - BALL_PEEK
        y = self.win.winfo_y()
        self.win.geometry(f"+{int(x)}+{int(y)}")
        self._is_edge_hidden = True

    def _reveal_from_right_edge(self):
        if not self._is_edge_hidden:
            return
        sw = self.win.winfo_screenwidth()
        x = sw - self._render_w
        y = self.win.winfo_y()
        self.win.geometry(f"+{int(x)}+{int(y)}")
        self._is_edge_hidden = False

    def _on_press(self, e):
        self._cancel_right_edge_hide()
        self._reveal_from_right_edge()
        self._is_dragging = True
        self._last_interaction_dragged = False
        self._drag["x"] = e.x_root - self.win.winfo_x()
        self._drag["y"] = e.y_root - self.win.winfo_y()
        self._drag["moved"] = False

    def _on_drag(self, e):
        self._cancel_right_edge_hide()
        dx = abs(e.x_root - self.win.winfo_x() - self._drag["x"])
        dy = abs(e.y_root - self.win.winfo_y() - self._drag["y"])
        if dx + dy > 3:
            self._drag["moved"] = True
        x = e.x_root - self._drag["x"]
        y = e.y_root - self._drag["y"]
        self.win.geometry(f"+{int(x)}+{int(y)}")

    def _on_release(self, _e):
        self._is_dragging = False
        self._last_interaction_dragged = self._drag["moved"]
        self._schedule_right_edge_hide()
        if not self._drag["moved"]:
            # 单击：打开便笺
            self.open_note()

    def _on_mouse_enter(self, _e):
        # 鼠标悬浮在露出的小角上时，自动展开完整悬浮球
        self._cancel_right_edge_hide()
        self._reveal_from_right_edge()
        self._last_interaction_dragged = False

    def _on_mouse_leave(self, _e):
        if self._is_dragging:
            return
        # 没有发生拖动：离开即隐藏；拖动过则继续按延时隐藏
        if not self._last_interaction_dragged:
            self._hide_to_right_edge()
        else:
            self._schedule_right_edge_hide()

    def _on_right(self, e):
        menu = FlatMenu(self.win, min_width=170)
        menu.add_command("打开便笺", self.open_note)
        menu.add_command("打开便笺列表…", self.app.show_note_picker)
        menu.add_command("关闭悬浮球", self.close_ball)
        menu.add_separator()
        menu.add_command("永不显示悬浮球", self.disable_ball_forever)
        menu.add_separator()
        label_pin = "取消置顶" if self.topmost else "置于顶层"
        menu.add_command(label_pin, self.toggle_pin)
        menu.popup(e.x_root, e.y_root)

    # ------- 动作 -------
    def toggle_pin(self):
        self.topmost = not self.topmost
        try:
            self.win.attributes("-topmost", self.topmost)
        except Exception:
            pass

    def open_note(self):
        # 恢复便笺窗口 + 销毁悬浮球
        self.destroy()
        try:
            self.app.show_note(self.note)
        except Exception:
            pass

    def close_ball(self):
        """关闭悬浮球：便笺保持隐藏，用户只能通过托盘恢复。"""
        self.destroy()

    def disable_ball_forever(self):
        """永不显示悬浮球：写入全局偏好；关闭当前悬浮球并把便笺隐藏到托盘。"""
        try:
            self.app.set_pref("never_ball", True)
        except Exception:
            pass
        self.destroy()

    def destroy(self):
        self._cancel_right_edge_hide()
        try:
            self.app._floating_balls.pop(self.note.note_id, None)
        except Exception:
            pass
        try:
            self.win.destroy()
        except Exception:
            pass


# ------------------------------------------------------------
# NotesApp：多便笺管理器（持有唯一的 tk.Tk() 与唯一的托盘图标）
# ------------------------------------------------------------
class NotesApp:
    def __init__(self):
        # 唯一的 Tk 根；自身不显示，只作为所有 Toplevel 便笺的父容器
        self.root = tk.Tk()
        self.root.title("便笺")
        self.root.withdraw()
        self._register_app_user_model_id()

        self._singleton_srv = None
        self._setup_single_instance_listener()

        self.notes = {}          # note_id -> StickyNote (仅已加载的窗口)
        self._tray_icon = None
        self._floating_balls = {}  # note_id -> FloatingBall
        self._all_note_ids = []    # 磁盘上所有已知便笺 id，按时间倒序（最新在前）

        # 确保目录存在
        os.makedirs(NOTES_DIR, exist_ok=True)

        # 读取应用级偏好（全局，非便笺内嵌）
        self.prefs = self._load_prefs()
        # 应用主题色（默认 simple_white）
        apply_theme(self.prefs.get("theme", DEFAULT_THEME))

        # 迁移老版本单便笺数据
        self._migrate_legacy()

        # 启动托盘（单例；失败不致命）
        self._setup_tray()

        # 扫描磁盘上所有便笺 id，只加载最新的一张
        self._scan_note_ids()
        if self._all_note_ids:
            self.load_note(self._all_note_ids[0])
        else:
            # 首次启动：新建一张空白便笺
            self.new_note()

    def _register_app_user_model_id(self):
        """固定应用 ID，避免任务栏图标分组异常或图标不刷新。"""
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        except Exception:
            pass

    # ------- 应用偏好 -------
    def _load_prefs(self):
        try:
            if os.path.exists(APP_PREFS_PATH):
                with open(APP_PREFS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
        return {}

    def set_pref(self, key, value):
        self.prefs[key] = value
        try:
            with open(APP_PREFS_PATH, "w", encoding="utf-8") as f:
                json.dump(self.prefs, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ------- 主题切换 -------
    def set_theme(self, name):
        """切换主题：写入偏好 + 重建所有便笺（保留文本与显隐状态）。"""
        if name not in THEMES or name == CURRENT_THEME:
            # 名字不合法或没变化：无事发生
            if name in THEMES:
                self.set_pref("theme", name)
            return
        self.set_pref("theme", name)
        apply_theme(name)
        self._rebuild_all_notes()

    def _rebuild_all_notes(self):
        """保存 → 销毁 → 重建所有便笺，用于主题切换等需要整体刷新 UI 的场景。"""
        visible_states = {}
        loaded_ids = []
        for nid, n in list(self.notes.items()):
            if n._destroyed:
                continue
            try:
                n._save_notes(force=False)
            except Exception:
                pass
            visible_states[nid] = n._visible
            loaded_ids.append(nid)

        # 销毁所有悬浮球（它们的颜色也由主题决定，但目前图标为图片，仅菜单颜色需要刷新）
        for nid in list(self._floating_balls.keys()):
            try:
                self.destroy_floating_ball(nid)
            except Exception:
                pass

        # 销毁所有便笺窗口
        for n in list(self.notes.values()):
            try:
                n.destroy()
            except Exception:
                pass
        self.notes.clear()

        # 仅重建「切换主题前已经加载过」的便笺，避免一次性把全部磁盘便笺都弹出来
        for nid in loaded_ids:
            self.load_note(nid)

        # 恢复显隐状态
        for nid, was_visible in visible_states.items():
            n = self.notes.get(nid)
            if n is None:
                continue
            if not was_visible:
                try:
                    n.root.withdraw()
                    n._visible = False
                except Exception:
                    pass

    # ------- 悬浮球 -------
    def show_floating_ball(self, note):
        """为指定便笺显示悬浮球（若已存在则直接 lift）。"""
        ball = self._floating_balls.get(note.note_id)
        if ball is not None:
            try:
                ball.win.deiconify()
                ball.win.lift()
            except Exception:
                pass
            return ball
        try:
            ball = FloatingBall(self, note)
        except Exception:
            return None
        self._floating_balls[note.note_id] = ball
        return ball

    def destroy_floating_ball(self, note_id):
        ball = self._floating_balls.pop(note_id, None)
        if ball is not None:
            try:
                ball.win.destroy()
            except Exception:
                pass

    # ------- 迁移 -------
    def _migrate_legacy(self):
        """把老版本 notes.md / notes.json / config.json 迁移为 notes/<ts>.*。

        迁移成功后，把老文件重命名为 .migrated，避免下次又被识别。
        """
        # 若 notes/ 下已经有 json，视为新布局，不再迁移
        try:
            existing = [f for f in os.listdir(NOTES_DIR) if f.endswith(".json")]
        except Exception:
            existing = []
        if existing:
            return
        if not (os.path.exists(LEGACY_JSON) or os.path.exists(LEGACY_MD)):
            return

        ts = new_note_id()
        legacy_config = {}
        if os.path.exists(LEGACY_CONFIG):
            try:
                with open(LEGACY_CONFIG, "r", encoding="utf-8") as f:
                    legacy_config = json.load(f)
            except Exception:
                legacy_config = {}

        data = None
        if os.path.exists(LEGACY_JSON):
            try:
                with open(LEGACY_JSON, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = None
        if data is None:
            data = {"version": 2, "lines": []}

        data["id"] = ts
        data["window"] = {
            "geometry": legacy_config.get("geometry",
                                          f"{INIT_W}x{INIT_H}+240+160"),
            "pinned": legacy_config.get("pinned", True),
            "transparency": float(legacy_config.get("transparency", 1.0)),
            "highlight_color": legacy_config.get("highlight_color", COLOR_HIGHLIGHT),
        }

        try:
            with open(os.path.join(NOTES_DIR, f"{ts}.json"),
                      "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            return  # 迁移失败则保留老文件

        # 复制 md（保留老数据的完整性）
        if os.path.exists(LEGACY_MD):
            try:
                shutil.copy2(LEGACY_MD, os.path.join(NOTES_DIR, f"{ts}.md"))
            except Exception:
                pass

        # 老文件改名，避免重复迁移
        for p in (LEGACY_JSON, LEGACY_MD, LEGACY_CONFIG):
            if os.path.exists(p):
                try:
                    os.replace(p, p + ".migrated")
                except Exception:
                    pass

    # ------- 扫描 / 按需加载 -------
    def _scan_note_ids(self):
        """把磁盘上所有 notes/<id>.json 的 id 读进 self._all_note_ids，按时间倒序。"""
        try:
            files = [f for f in os.listdir(NOTES_DIR) if f.endswith(".json")]
        except Exception:
            files = []
        ids = [f[:-5] for f in files]
        # id 形如 YYYYMMDD-HHMMSS(-n)，字典序倒排即时间倒排
        ids.sort(reverse=True)
        self._all_note_ids = ids

    def load_note(self, note_id):
        """打开指定便笺：若未加载则构造窗口；若已加载但隐藏则恢复显示。"""
        existing = self.notes.get(note_id)
        if existing is not None and not existing._destroyed:
            self.show_note(existing)
            return existing
        # 检查文件是否真的存在（防止磁盘上已被删除）
        if not os.path.exists(os.path.join(NOTES_DIR, f"{note_id}.json")):
            return None
        try:
            note = StickyNote(self, note_id, is_new=False)
        except Exception:
            return None
        self.notes[note_id] = note
        if note_id not in self._all_note_ids:
            self._all_note_ids.insert(0, note_id)
        try:
            note.root.lift()
            note.root.focus_force()
        except Exception:
            pass
        return note

    def _load_all_notes(self):
        """加载磁盘上所有便笺窗口。仅用于主题切换后的批量重建。"""
        self._scan_note_ids()
        for note_id in sorted(self._all_note_ids):
            try:
                self.notes[note_id] = StickyNote(self, note_id, is_new=False)
            except Exception:
                pass

    # ------- 便笺切换面板 -------
    def show_note_picker(self, parent_window=None):
        """弹出便笺选择器：列出所有便笺，点击即打开（未加载的会按需构造）。"""
        self._scan_note_ids()
        master = parent_window or self.root
        dlg = FlatDialog(master, title="打开便笺", width=360)

        tk.Label(
            dlg.body,
            text=f"共 {len(self._all_note_ids)} 张便笺，点击任意一张打开。",
            bg=COLOR_BG, fg=COLOR_SUBTLE,
            font=(FONT_FAMILY, 10), justify="left",
        ).pack(anchor="w", pady=(0, 8))

        # 工具条
        tool_row = tk.Frame(dlg.body, bg=COLOR_BG)
        tool_row.pack(fill="x", pady=(0, 6))
        flat_button(
            tool_row, "新建便笺",
            lambda: (dlg.close(), self.new_note()),
            primary=True,
        ).pack(side="left")
        flat_button(
            tool_row, "显示全部",
            lambda: (dlg.close(), self._open_all_notes()),
        ).pack(side="left", padx=(8, 0))

        # 列表区域（可滚动）
        list_wrap = tk.Frame(dlg.body, bg=COLOR_BG,
                             highlightthickness=1,
                             highlightbackground=COLOR_BORDER)
        list_wrap.pack(fill="both", expand=True, pady=(4, 10))

        canvas = tk.Canvas(list_wrap, bg=COLOR_BG, highlightthickness=0,
                           height=320)
        canvas.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(list_wrap, orient="vertical", command=canvas.yview)
        sb.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=sb.set)
        inner = tk.Frame(canvas, bg=COLOR_BG)
        canvas.create_window((0, 0), window=inner, anchor="nw")

        def on_configure(_e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            # 让 inner 的宽度跟 canvas 走（避免空白）
            canvas.itemconfig("all", width=canvas.winfo_width())
        inner.bind("<Configure>", on_configure)
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(
                        canvas.find_all()[0] if canvas.find_all() else "",
                        width=e.width))
        # 鼠标滚轮
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(
                            int(-1 * (e.delta / 120)), "units"))

        def pick(nid):
            dlg.close()
            self.load_note(nid)

        for nid in self._all_note_ids:
            # 读取标题（优先 json.title），落不到就用 id
            title = self._read_note_title(nid) or f"note-{nid}"
            loaded = nid in self.notes and not self.notes[nid]._destroyed
            visible = loaded and self.notes[nid]._visible
            status = "已打开" if visible else ("后台" if loaded else "未加载")
            row = tk.Frame(inner, bg=COLOR_BG, cursor="hand2")
            row.pack(fill="x")
            title_lbl = tk.Label(
                row, text=title, bg=COLOR_BG, fg=COLOR_FG,
                anchor="w", font=(FONT_FAMILY, 10),
                padx=10, pady=7,
            )
            title_lbl.pack(side="left", fill="x", expand=True)
            id_lbl = tk.Label(
                row, text=nid, bg=COLOR_BG, fg=COLOR_MUTED,
                anchor="e", font=(FONT_FAMILY, 9),
                padx=6, pady=7,
            )
            id_lbl.pack(side="right")
            status_lbl = tk.Label(
                row, text=status, bg=COLOR_BG, fg=COLOR_SUBTLE,
                anchor="e", font=(FONT_FAMILY, 9),
                padx=10, pady=7,
            )
            status_lbl.pack(side="right")

            for w in (row, title_lbl, id_lbl, status_lbl):
                w.bind("<Enter>",
                       lambda _e, r=(row, title_lbl, id_lbl, status_lbl): (
                           [x.configure(bg=COLOR_BTN_HOVER) for x in r]))
                w.bind("<Leave>",
                       lambda _e, r=(row, title_lbl, id_lbl, status_lbl): (
                           [x.configure(bg=COLOR_BG) for x in r]))
                w.bind("<Button-1>", lambda _e, k=nid: pick(k))

        # 解绑滚轮（对话框关闭时）
        def on_close():
            try:
                canvas.unbind_all("<MouseWheel>")
            except Exception:
                pass
        dlg.bind("<Destroy>", lambda _e: on_close())

        btn_row = tk.Frame(dlg.body, bg=COLOR_BG)
        btn_row.pack(fill="x")
        flat_button(btn_row, "关闭", dlg.close).pack(side="right")

        dlg.place_near(master)
        dlg.focus_force()

    def _read_note_title(self, note_id):
        """只读 title 字段，用于选择器。失败返回 None。"""
        path = os.path.join(NOTES_DIR, f"{note_id}.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("title") or data.get("window", {}).get("title")
        except Exception:
            return None

    def _open_all_notes(self):
        """一次性打开所有磁盘上的便笺（老行为）。供"显示全部"使用。"""
        self._scan_note_ids()
        for nid in self._all_note_ids:
            self.load_note(nid)

    # ------- 新建 / 隐藏 / 显示 -------
    def new_note(self):
        note_id = new_note_id()
        try:
            note = StickyNote(self, note_id, is_new=True)
        except Exception:
            return None
        self.notes[note_id] = note
        if note_id not in self._all_note_ids:
            self._all_note_ids.insert(0, note_id)
        try:
            note.root.lift()
            note.root.focus_force()
        except Exception:
            pass
        return note

    def delete_note(self, note):
        """永久删除一张便笺（文件 + 窗口）。若删完一张不剩，自动新建空白便笺。"""
        if note._destroyed:
            return
        note_id = note.note_id
        try:
            note.destroy()
        except Exception:
            pass
        self.notes.pop(note_id, None)
        for p in (os.path.join(NOTES_DIR, f"{note_id}.json"),
                  os.path.join(NOTES_DIR, f"{note_id}.md")):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass
        # 没剩下任何便笺时，自动新建一张，避免用户陷入"无入口"
        if not any((not n._destroyed) for n in self.notes.values()):
            self.new_note()

    def hide_note(self, note):
        if note._destroyed:
            return
        try:
            note._save_notes(force=False)
        except Exception:
            pass
        try:
            note.root.withdraw()
        except Exception:
            pass
        note._visible = False
        # 关闭（×）也把可能的悬浮球一起撤掉
        self.destroy_floating_ball(note.note_id)
        # 无托盘兜底：若用户把所有便笺都关掉又没有托盘入口，就直接退出程序
        if not _HAS_TRAY or self._tray_icon is None:
            if all((n._destroyed or not n._visible) for n in self.notes.values()):
                self.real_quit()

    def show_note(self, note):
        if note._destroyed:
            return
        # 若该便笺当前有悬浮球，一并销毁
        self.destroy_floating_ball(note.note_id)
        try:
            note.root.deiconify()
            note.root.overrideredirect(True)
            note.root.attributes("-topmost", note.pinned)
            note.root.attributes("-alpha", note.transparency)
            note.root.lift()
            note.root.focus_force()
        except Exception:
            pass
        note._visible = True

    def show_current_note(self):
        """托盘默认动作：恢复当前（最近）便笺，不触发新建。"""
        # 优先按时间倒序恢复已加载便笺；未加载则尝试先加载再显示。
        self._scan_note_ids()
        for nid in self._all_note_ids:
            note = self.notes.get(nid)
            if note is not None and not note._destroyed:
                self.show_note(note)
                return
        if self._all_note_ids:
            note = self.load_note(self._all_note_ids[0])
            if note is not None:
                self.show_note(note)

    def show_all(self):
        # 先把磁盘上未加载的便笺补上，再恢复所有隐藏的
        self._scan_note_ids()
        for nid in list(self._all_note_ids):
            if nid not in self.notes or self.notes[nid]._destroyed:
                self.load_note(nid)
        for n in list(self.notes.values()):
            if not n._destroyed and not n._visible:
                self.show_note(n)

    def hide_all(self):
        for n in list(self.notes.values()):
            if not n._destroyed and n._visible:
                self.hide_note(n)

    def toggle_all(self):
        if any((not n._destroyed and n._visible) for n in self.notes.values()):
            self.hide_all()
        else:
            self.show_all()

    # ------- 托盘 -------
    def _make_tray_image(self):
        # 高分辨率绘制后缩回 64，圆角/斜线边缘更顺滑（托盘实际仍用 64 位图）
        scale = 4
        out = 64
        hi = out * scale

        def z(v):
            return int(round(v * scale))

        # 相对 64×64 中心整体放大约 10%（边线坐标同步缩放）
        cx = cy = 32.0
        grow = 1.06

        def gx(x):
            v = cx + (x - cx) * grow
            return int(round(max(0.0, min(63.0, v))))

        def gy(y):
            v = cy + (y - cy) * grow
            return int(round(max(0.0, min(63.0, v))))

        lx = int(round(cx + (3 - cx) * grow))
        ly = int(round(cy + (2 - cy) * grow))
        rx = int(round(cx + (61 - cx) * grow))
        ry = int(round(cy + (62 - cy) * grow))
        lx, ly = max(0, lx), max(0, ly)
        rx, ry = min(64, rx), min(64, ry)

        img = Image.new("RGBA", (hi, hi), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        paper = (248, 248, 250, 255)
        edge = (200, 200, 208, 255)
        r = z(max(1, int(round(10 * grow))))
        box = [z(lx), z(ly), z(rx), z(ry)]
        w_outline = max(1, z(1))
        w_line = max(1, z(3))
        w_tick = max(1, z(5))
        try:
            draw.rounded_rectangle(
                box, radius=r, fill=paper, outline=edge, width=w_outline
            )
        except AttributeError:
            draw.rectangle(box, fill=paper, outline=edge, width=w_outline)
        draw.line([(z(gx(8)), z(gy(11))), (z(gx(56)), z(gy(11)))], fill=(90, 90, 98, 255), width=w_line)
        draw.line([(z(gx(8)), z(gy(20))), (z(gx(45)), z(gy(20)))], fill=(130, 130, 138, 255), width=w_line)
        draw.line([(z(gx(24)), z(gy(40))), (z(gx(31)), z(gy(48)))], fill=(32, 150, 72, 255), width=w_tick)
        draw.line([(z(gx(31)), z(gy(48))), (z(gx(54)), z(gy(30)))], fill=(32, 150, 72, 255), width=w_tick)
        try:
            resample = Image.Resampling.LANCZOS
        except AttributeError:
            resample = Image.LANCZOS
        return img.resize((out, out), resample)

    def _setup_single_instance_listener(self):
        """绑定本机端口；第二次启动在 main() 中已 ping 退出，此处处理竞态下双启动。"""
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            srv.bind(("127.0.0.1", SINGLE_INSTANCE_PORT))
        except OSError:
            try:
                srv.close()
            except Exception:
                pass
            if _try_ping_existing_instance():
                try:
                    self.root.destroy()
                except Exception:
                    pass
                raise SystemExit(0)
            return

        srv.listen(8)
        self._singleton_srv = srv
        app = self

        def listen_loop():
            while getattr(app, "_singleton_srv", None) is not None:
                try:
                    conn, _ = srv.accept()
                except OSError:
                    break
                try:
                    conn.settimeout(2.0)
                    conn.recv(64)
                except Exception:
                    pass
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass
                try:
                    app.root.after(0, app.show_current_note)
                except Exception:
                    break

        threading.Thread(target=listen_loop, daemon=True).start()

    def _setup_tray(self):
        if not _HAS_TRAY:
            return
        try:
            image = self._make_tray_image()

            def _cb(fn):
                return lambda icon, item: self.root.after(0, fn)

            menu = pystray.Menu(
                pystray.MenuItem("打开当前便笺", _cb(self.show_current_note), default=True),
                pystray.MenuItem("新建便笺", _cb(self.new_note)),
                pystray.MenuItem("打开便笺…", _cb(self.show_note_picker)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("显示全部", _cb(self.show_all)),
                pystray.MenuItem("隐藏全部", _cb(self.hide_all)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("退出便笺",
                                 lambda icon, item: self.root.after(0, self.real_quit)),
            )

            self._tray_icon = pystray.Icon("bianjian", image, "极简悬浮便笺", menu=menu)
            threading.Thread(target=self._tray_icon.run, daemon=True).start()
        except Exception:
            self._tray_icon = None

    # ------- 退出 -------
    def real_quit(self):
        for n in list(self.notes.values()):
            try:
                if not n._destroyed:
                    n._save_notes(force=False)
            except Exception:
                pass
        # 销毁所有悬浮球
        for nid in list(self._floating_balls.keys()):
            try:
                self.destroy_floating_ball(nid)
            except Exception:
                pass
        if self._tray_icon is not None:
            try:
                self._tray_icon.visible = False
                self._tray_icon.stop()
            except Exception:
                pass
            self._tray_icon = None
        srv = getattr(self, "_singleton_srv", None)
        if srv is not None:
            self._singleton_srv = None
            try:
                srv.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                srv.close()
            except OSError:
                pass
        for n in list(self.notes.values()):
            try:
                n.destroy()
            except Exception:
                pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def run(self):
        self.root.mainloop()


def main():
    if _try_ping_existing_instance():
        sys.exit(0)
    app = NotesApp()
    app.run()


if __name__ == "__main__":
    main()
