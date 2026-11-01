"""
Game Launcher v2.0 — a premium three-pane gaming dashboard.

Layout:  sidebar  |  library (featured banner + cards)  |  system + details panel

Features: real hardware monitoring (CPU/RAM/GPU/storage), Steam library import,
auto-detect of main executables, artwork with icon fallback, favourites, play
tracking + session playtime, search, sorting, filters, multi-select removal,
theme accents. Built on customtkinter; all monitoring data is real.
"""

import os
import sys
import json
import hashlib
import subprocess
import threading
from datetime import datetime
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog, messagebox, Menu
from PIL import Image, ImageDraw, ImageFont, ImageOps

try:
    import win32gui
    import win32ui
    import win32con
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

try:
    import monitoring
except Exception:
    monitoring = None

try:
    import steam_import
except Exception:
    steam_import = None

try:
    import psutil
    HAS_PSUTIL = True
except Exception:
    HAS_PSUTIL = False

APP_TITLE = "GAME LAUNCHER"
APP_VERSION = "v2.0"
CONFIG_DIR = Path.home() / ".game_launcher"
CONFIG_FILE = CONFIG_DIR / "games.json"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
ICON_DIR = CONFIG_DIR / "icons"

ICON_SIZE = 256
CARD_W, CARD_H = 140, 180       # card artwork area
HERO_W, HERO_H = 300, 170       # featured artwork area

# ---------------- Design tokens (purple gaming palette) ----------------
BG = "#080B14"
SIDEBAR_BG = "#0B0D19"
PANEL = "#111525"
PANEL2 = "#171C2C"
CARD = "#151A29"
PURPLE = "#9333EA"
PURPLE2 = "#A855F7"
PURPLE_LIGHT = "#C084FC"
BLUE = "#38BDF8"
TEXT = "#F1F5F9"
MUTED = "#94A3B8"
BORDER = "#293247"
SUCCESS = "#22C55E"
WARNING = "#F59E0B"
ERROR = "#EF4444"
STAR_GOLD = "#FBBF24"

SORT_OPTIONS = ["A - Z", "Z - A", "Recently added", "Recently played", "Most played", "Least played"]
VIEWS = ["library", "favourites", "recent"]

THEMES = {
    "Violet": ("#9333EA", "#7C3AED", "#C084FC"),
    "Blue":   ("#2563EB", "#1D4ED8", "#93C5FD"),
    "Emerald": ("#10B981", "#059669", "#6EE7B7"),
    "Crimson": ("#EF4444", "#DC2626", "#FCA5A5"),
    "Amber":  ("#F59E0B", "#D97706", "#FCD34D"),
    "Cyan":   ("#06B6D4", "#0891B2", "#67E8F9"),
}

SKIP_SUBSTRINGS = [
    "unins", "uninstall", "setup", "install", "redist", "vcredist", "vc_redist",
    "dxsetup", "directx", "dxwebsetup", "crash", "report", "updater", "verify",
    "cleanup", "ue4prereq", "dotnet", "openal", "physx", "launcher_update",
    "uninstaller", "_commonredist", "settings", "config",
]
STRUCTURE_DIRS = {"bin", "binaries", "bin64", "win64", "win32", "x64", "x86",
                  "build", "game", "dist", "release", "launcher", "content"}
NAME_PALETTE = [
    (76, 175, 80), (33, 150, 243), (156, 39, 176), (255, 152, 0),
    (233, 30, 99), (0, 150, 136), (63, 81, 181), (255, 87, 34),
]


# ---------------- Storage helpers ----------------
def resource_path(name):
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, name)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), name)


def ensure_dirs():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    ICON_DIR.mkdir(parents=True, exist_ok=True)


def _load_json(path, default):
    ensure_dirs()
    if os.path.exists(path):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            return data
        except Exception:
            pass
    return default


def load_games():
    d = _load_json(CONFIG_FILE, [])
    return d if isinstance(d, list) else []


def save_games(games):
    ensure_dirs()
    CONFIG_FILE.write_text(json.dumps(games, indent=2, ensure_ascii=False), encoding="utf-8")


def load_settings():
    d = _load_json(SETTINGS_FILE, {})
    return d if isinstance(d, dict) else {}


def save_settings(s):
    ensure_dirs()
    SETTINGS_FILE.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")


def name_from_exe(path):
    folder = os.path.basename(os.path.dirname(path))
    if folder and not folder.endswith(":"):
        return folder
    return os.path.splitext(os.path.basename(path))[0]


# ---------------- Icon extraction ----------------
def _hicon_to_pil(hicon, size):
    hdc_screen = win32gui.GetDC(0)
    hdc = win32ui.CreateDCFromHandle(hdc_screen)
    hbmp = win32ui.CreateBitmap()
    hbmp.CreateCompatibleBitmap(hdc, size, size)
    hdc_mem = hdc.CreateCompatibleDC()
    hdc_mem.SelectObject(hbmp)
    win32gui.DrawIconEx(hdc_mem.GetSafeHdc(), 0, 0, hicon, size, size, 0, None, win32con.DI_NORMAL)
    info = hbmp.GetInfo()
    bits = hbmp.GetBitmapBits(True)
    img = Image.frombuffer("RGBA", (info["bmWidth"], info["bmHeight"]), bits, "raw", "BGRA", 0, 1)
    hdc_mem.DeleteDC(); hdc.DeleteDC(); win32gui.ReleaseDC(0, hdc_screen)
    return img


def extract_icon(exe_path, size=256):
    if not HAS_WIN32:
        return None
    hicon = None
    try:
        import ctypes
        from ctypes import wintypes
        shell32 = ctypes.windll.shell32
        hl, hs = wintypes.HICON(), wintypes.HICON()
        hr = shell32.SHDefExtractIconW(os.path.abspath(exe_path), 0, 0,
                                       ctypes.byref(hl), ctypes.byref(hs), size)
        if hr == 0 and hl.value:
            hicon = hl.value
            if hs.value:
                win32gui.DestroyIcon(hs.value)
    except Exception:
        hicon = None
    if not hicon:
        try:
            la, sa = win32gui.ExtractIconEx(exe_path, 0)
            if la:
                hicon = la[0]
            elif sa:
                hicon = sa[0]
            for ic in la[1:]:
                win32gui.DestroyIcon(ic)
            for ic in sa[1:]:
                win32gui.DestroyIcon(ic)
        except Exception:
            hicon = None
    if not hicon:
        return None
    try:
        return _hicon_to_pil(hicon, size)
    except Exception:
        return None
    finally:
        try:
            win32gui.DestroyIcon(hicon)
        except Exception:
            pass


def name_color(name):
    return NAME_PALETTE[sum(ord(c) for c in name) % len(NAME_PALETTE)]


def get_game_icon(game, size=ICON_SIZE):
    exe = game.get("exe", "")
    if not exe or not os.path.exists(exe):
        return None
    cache = ICON_DIR / (hashlib.md5(exe.encode("utf-8")).hexdigest() + ".png")
    if cache.exists():
        game["icon"] = str(cache)
        return str(cache)
    img = extract_icon(exe, size)
    if img is None:
        letter = (game.get("name", "?")[:1] or "?").upper()
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([6, 6, size - 6, size - 6], radius=22, fill=name_color(game.get("name", "?")))
        try:
            f = ImageFont.truetype("segoeuib.ttf", int(size * 0.5))
        except Exception:
            f = ImageFont.load_default()
        bb = d.textbbox((0, 0), letter, font=f)
        d.text(((size - (bb[2] - bb[0])) / 2 - bb[0], (size - (bb[3] - bb[1])) / 2 - bb[1]),
               letter, fill="white", font=f)
    try:
        img.save(cache)
        game["icon"] = str(cache)
        return str(cache)
    except Exception:
        return None


# ---------------- Artwork helpers ----------------
def card_picture(game, w=CARD_W, h=CARD_H):
    """Cover art (center-cropped) or a centered icon on a coloured backdrop."""
    cover = game.get("artwork_cover")
    if cover and os.path.exists(cover):
        try:
            return ImageOps.fit(Image.open(cover).convert("RGB"), (w, h), Image.LANCZOS, centering=(0.5, 0.35))
        except Exception:
            pass
    icon = get_game_icon(game, ICON_SIZE)
    bg = Image.new("RGB", (w, h), name_color(game.get("name", "?")))
    if icon and os.path.exists(icon):
        try:
            im = Image.open(icon).convert("RGBA")
            thumb = ImageOps.contain(im, (w - 20, h - 20), Image.LANCZOS)
            bg.paste(thumb, ((w - thumb.width) // 2, (h - thumb.height) // 2), thumb)
            return bg
        except Exception:
            pass
    d = ImageDraw.Draw(bg)
    letter = (game.get("name", "?")[:1] or "?").upper()
    try:
        f = ImageFont.truetype("segoeuib.ttf", int(h * 0.4))
    except Exception:
        f = ImageFont.load_default()
    bb = d.textbbox((0, 0), letter, font=f)
    d.text(((w - (bb[2] - bb[0])) / 2 - bb[0], (h - (bb[3] - bb[1])) / 2 - bb[1]),
           letter, fill="white", font=f)
    return bg


def hero_picture(game, w=HERO_W, h=HERO_H):
    hero = game.get("artwork_hero")
    if hero and os.path.exists(hero):
        try:
            return ImageOps.fit(Image.open(hero).convert("RGB"), (w, h), Image.LANCZOS, centering=(0.5, 0.5))
        except Exception:
            pass
    return card_picture(game, w, h)


# ---------------- Detection ----------------
def _is_skip(fname):
    low = fname.lower()
    return any(s in low for s in SKIP_SUBSTRINGS)


BAD_WORDS = ("launcher", "client", "download", "updater", "store", "service",
             "patcher", "browser", "installer", "settings", "config", "crash")


def _score_exe(game_name, exe, depth):
    gn = "".join(c for c in game_name.lower() if c.isalnum())
    base = os.path.splitext(os.path.basename(exe))[0].lower()
    bn = "".join(c for c in base if c.isalnum())
    score = 0.0
    if bn and (bn == gn or bn in gn or gn in bn):
        score += 4
    score -= depth * 0.5
    if any(b in base for b in BAD_WORDS):
        score -= 4
    try:
        size = os.path.getsize(exe)
    except Exception:
        size = 0
    score += min(size / (2 * 1024 ** 3), 2.0)
    return score


def _pick_main_exe(game_name, candidates):
    best, best_score = None, -1e9
    for exe, depth in candidates:
        s = _score_exe(game_name, exe, depth)
        if s > best_score:
            best, best_score = exe, s
    return best


def find_main_exe(folder):
    """Pick one main executable from an entire game folder tree."""
    folder = os.path.abspath(folder)
    cands = []
    for root, dirs, files in os.walk(folder):
        rel = os.path.relpath(root, folder)
        depth = 0 if rel == "." else len(rel.split(os.sep))
        if any(p.lower() in {"redist", "_commonredist", "uninstall", "directx", "dotnet"} for p in rel.split(os.sep)):
            dirs[:] = []
            continue
        for f in files:
            if f.lower().endswith(".exe") and not _is_skip(f):
                cands.append((os.path.join(root, f), depth))
    return _pick_main_exe(os.path.basename(folder), cands)


def detect_games(folder):
    """One main executable per game folder under a library root."""
    folder = os.path.abspath(folder)
    root_name = os.path.basename(folder).lower()
    groups = {}
    for root, dirs, files in os.walk(folder):
        rel = os.path.relpath(root, folder)
        parts = [p for p in rel.split(os.sep) if p] if rel != "." else []
        if any(p.lower() in {"redist", "_commonredist", "uninstall", "directx", "dotnet"} for p in parts):
            dirs[:] = []
            continue
        if parts and (parts[0].lower() in STRUCTURE_DIRS or parts[0].lower() == root_name):
            game_root, name = folder, os.path.basename(folder)
        elif parts:
            game_root, name = os.path.join(folder, parts[0]), parts[0]
        else:
            game_root, name = folder, os.path.basename(folder)
        for f in files:
            if f.lower().endswith(".exe") and not _is_skip(f):
                groups.setdefault(game_root, [name, []])[1].append((os.path.join(root, f), len(parts)))
    out = []
    for game_root, (name, cands) in groups.items():
        exe = _pick_main_exe(name, cands)
        if exe:
            out.append({"name": name, "exe": exe})
    return out


def _fmt_gb(n):
    if n is None:
        return "—"
    return f"{n / 1024 ** 3:.1f} GB"


def time_ago(iso):
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso)
    except Exception:
        return ""
    d = datetime.now() - dt
    if d.days >= 365:
        return f"{d.days // 365}y ago"
    if d.days >= 1:
        return f"{d.days}d ago"
    if d.seconds >= 3600:
        return f"{d.seconds // 3600}h ago"
    if d.seconds >= 60:
        return f"{d.seconds // 60}m ago"
    return "just now"


# ============================== APP ==============================
class GameLauncherApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE} {APP_VERSION}")
        self.geometry("1420x860")
        self.minsize(1120, 640)
        self.configure(fg_color=BG)
        self._apply_window_icon()

        self.settings = load_settings()
        self.accent, self.accent_hover, self.accent_soft = THEMES.get(
            self.settings.get("theme"), THEMES["Violet"])

        self.games = load_games()
        self._view = "library"
        self._filter = ""
        self._sort_mode = "A - Z"
        self._selection_mode = False
        self._selected = set()
        self._hero = None
        self._card_widgets = {}
        self._card_names = {}
        self._ctk_images = {}
        self._drive_rows = {}
        self._running = {}          # exe_key -> {"pid", "start"}

        self._build_ui()
        self.refresh_library()
        self._tick_monitors()
        self._tick_running()
        if monitoring is not None:
            threading.Thread(target=monitoring.prime_cpu, daemon=True).start()

    def _apply_window_icon(self):
        try:
            ico = resource_path("icon.ico")
            if os.path.exists(ico):
                self.iconbitmap(ico)
        except Exception:
            pass

    # ---------------- shell ----------------
    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_center()
        self._build_right()

    def _nav(self, text, cmd, primary=False):
        b = ctk.CTkButton(self.nav_frame, text=text, anchor="w", height=38, corner_radius=10,
                          fg_color=self.accent if primary else "transparent",
                          hover_color=PANEL2 if not primary else self.accent_hover,
                          text_color=TEXT, font=ctk.CTkFont(size=14),
                          command=cmd)
        b.pack(fill="x", padx=10, pady=3)
        return b

    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color=SIDEBAR_BG)
        sb.grid(row=0, column=0, sticky="nsw")
        sb.grid_propagate(False)
        ctk.CTkLabel(sb, text=APP_TITLE, font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=TEXT).pack(anchor="w", padx=18, pady=(20, 0))
        ctk.CTkLabel(sb, text=APP_VERSION, font=ctk.CTkFont(size=11),
                     text_color=self.accent_soft).pack(anchor="w", padx=18, pady=(0, 16))

        self.nav_frame = ctk.CTkFrame(sb, fg_color="transparent")
        self.nav_frame.pack(fill="x")
        self._nav("Home / Library", lambda: self.set_view("library"))
        self._nav("Favourites", lambda: self.set_view("favourites"))
        self._nav("Recently Played", lambda: self.set_view("recent"))

        ctk.CTkFrame(sb, height=1, fg_color=BORDER).pack(fill="x", padx=14, pady=12)
        ctk.CTkLabel(sb, text="ADD GAMES", font=ctk.CTkFont(size=10), text_color=MUTED).pack(anchor="w", padx=18, pady=(0, 4))
        self._nav("+  Add Game", self.add_game)
        self._nav("Auto Detect", self.auto_detect)
        self._nav("Steam Import", self.steam_import_dialog)
        self._nav("Select / Remove", self.toggle_selection_mode)

        ctk.CTkFrame(sb, height=1, fg_color=BORDER).pack(fill="x", padx=14, pady=12)
        ctk.CTkLabel(sb, text="THEME", font=ctk.CTkFont(size=10), text_color=MUTED).pack(anchor="w", padx=18, pady=(0, 4))
        self.theme_var = ctk.StringVar(value=self.settings.get("theme", "Violet"))
        ctk.CTkOptionMenu(sb, values=list(THEMES.keys()), variable=self.theme_var,
                          command=self.on_theme, fg_color=PANEL2, button_color=PANEL2,
                          button_hover_color=BORDER, height=32).pack(fill="x", padx=14)

        ctk.CTkLabel(sb, text="Purple gaming dashboard", font=ctk.CTkFont(size=10),
                     text_color=MUTED).pack(side="bottom", anchor="w", padx=18, pady=14)

    def _build_center(self):
        center = ctk.CTkFrame(self, fg_color="transparent")
        center.grid(row=0, column=1, sticky="nsew", padx=(14, 8), pady=12)
        center.grid_columnconfigure(0, weight=1)
        center.grid_rowconfigure(3, weight=1)

        # top bar
        topbar = ctk.CTkFrame(center, fg_color="transparent")
        topbar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        topbar.grid_columnconfigure(0, weight=1)
        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.on_search())
        ctk.CTkEntry(topbar, placeholder_text="Search games, executables, paths...",
                     textvariable=self.search_var, height=38, fg_color=PANEL,
                     border_color=BORDER).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.sort_var = ctk.StringVar(value=self._sort_mode)
        ctk.CTkOptionMenu(topbar, values=SORT_OPTIONS, variable=self.sort_var,
                          command=self.on_sort, width=150, height=38, fg_color=PANEL,
                          button_color=PANEL2, button_hover_color=BORDER).grid(row=0, column=1)

        # featured banner
        self.featured = ctk.CTkFrame(center, height=200, corner_radius=16, fg_color=PANEL)
        self.featured.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        self.featured.grid_propagate(False)

        # library header
        head = ctk.CTkFrame(center, fg_color="transparent")
        head.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        self.lib_title = ctk.CTkLabel(head, text="My Library", font=ctk.CTkFont(size=18, weight="bold"))
        self.lib_title.pack(side="left")
        self.lib_count = ctk.CTkLabel(head, text="", font=ctk.CTkFont(size=12), text_color=MUTED)
        self.lib_count.pack(side="left", padx=(10, 0))
        self.sel_btn = ctk.CTkButton(head, text="Cancel select", width=110, height=30,
                                     fg_color=ERROR, hover_color="#B91C1C",
                                     command=self._on_sel_btn)
        self.sel_btn.pack(side="right")

        self.grid = ctk.CTkScrollableFrame(center, fg_color="transparent")
        self.grid.grid(row=3, column=0, sticky="nsew")
        self.grid.grid_columnconfigure(tuple(range(5)), weight=1, uniform="col")

    def _build_right(self):
        rp = ctk.CTkFrame(self, width=300, corner_radius=0, fg_color=SIDEBAR_BG)
        rp.grid(row=0, column=2, sticky="nse")
        rp.grid_propagate(False)
        self.right = ctk.CTkScrollableFrame(rp, fg_color="transparent", width=284)
        self.right.pack(fill="both", expand=True)

        ctk.CTkLabel(self.right, text="SYSTEM", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=MUTED, anchor="w").pack(fill="x", padx=14, pady=(16, 6))

        # CPU
        self.cpu_card, self.cpu_bar, self.cpu_pct, self.cpu_info = self._stat_card("CPU")
        # RAM
        self.ram_card, self.ram_bar, self.ram_pct, self.ram_info = self._stat_card("RAM")
        # GPU
        self.gpu_card, self.gpu_bar, self.gpu_pct, self.gpu_info = self._stat_card("GPU")

        # Storage
        ctk.CTkLabel(self.right, text="STORAGE", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=MUTED, anchor="w").pack(fill="x", padx=14, pady=(14, 4))
        self.storage_frame = ctk.CTkFrame(self.right, fg_color="transparent")
        self.storage_frame.pack(fill="x", padx=14)

        # Selected game
        ctk.CTkFrame(self.right, height=1, fg_color=BORDER).pack(fill="x", padx=14, pady=12)
        ctk.CTkLabel(self.right, text="SELECTED GAME", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=MUTED, anchor="w").pack(fill="x", padx=14, pady=(0, 4))
        self.details = ctk.CTkFrame(self.right, fg_color=PANEL, corner_radius=12)
        self.details.pack(fill="x", padx=14, pady=(0, 16))

    def _stat_card(self, title):
        card = ctk.CTkFrame(self.right, fg_color=PANEL, corner_radius=12)
        card.pack(fill="x", padx=14, pady=4)
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 0))
        ctk.CTkLabel(top, text=title, font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=self.accent_soft).pack(side="left")
        pct = ctk.CTkLabel(top, text="—", font=ctk.CTkFont(size=13, weight="bold"))
        pct.pack(side="right")
        bar = ctk.CTkProgressBar(card, height=8, corner_radius=4, progress_color=self.accent)
        bar.set(0)
        bar.pack(fill="x", padx=12, pady=(6, 4))
        info = ctk.CTkLabel(card, text="", font=ctk.CTkFont(size=11),
                            text_color=MUTED, anchor="w", justify="left", wraplength=250)
        info.pack(fill="x", padx=12, pady=(0, 10))
        return card, bar, pct, info

    # ---------------- monitoring tick ----------------
    def _tick_monitors(self):
        try:
            if monitoring is not None:
                snap = monitoring.collect()
                self._apply_monitors(snap)
        except Exception:
            pass
        self.after(2000, self._tick_monitors)

    def _apply_monitors(self, snap):
        cpu = snap["cpu"]
        if cpu.get("usage") is not None:
            self.cpu_bar.set(min(cpu["usage"] / 100, 1))
            self.cpu_pct.configure(text=f"{cpu['usage']:.0f}%")
        else:
            self.cpu_pct.configure(text="—")
        self.cpu_info.configure(
            text=f"{cpu.get('model') or 'Unknown CPU'}\n"
                 f"{cpu.get('clock_mhz') or '—'} MHz · {cpu.get('cores') or '—'} cores / "
                 f"{cpu.get('threads') or '—'} threads")

        ram = snap["ram"]
        if ram.get("percent") is not None:
            self.ram_bar.set(ram["percent"] / 100)
            self.ram_pct.configure(text=f"{ram['percent']:.0f}%")
            self.ram_info.configure(text=f"{_fmt_gb(ram['used'])} / {_fmt_gb(ram['total'])} used")
        else:
            self.ram_pct.configure(text="—")
            self.ram_info.configure(text="Unavailable")

        gpu = snap["gpu"]
        if gpu.get("util") is not None:
            self.gpu_bar.set(gpu["util"] / 100)
            self.gpu_pct.configure(text=f"{gpu['util']:.0f}%")
        else:
            self.gpu_bar.set(0)
            self.gpu_pct.configure(text="—")
        extra = []
        if gpu.get("temp") is not None:
            extra.append(f"{gpu['temp']}°C")
        if gpu.get("vram_total"):
            extra.append(f"VRAM {_fmt_gb(gpu['vram_used'])} / {_fmt_gb(gpu['vram_total'])}")
        if not extra:
            extra.append("util/temp/VRAM unavailable on this GPU")
        self.gpu_info.configure(text=f"{gpu.get('name') or 'Unknown GPU'}\n" + " · ".join(extra))

        # storage rows (build once)
        if not self._drive_rows:
            for vol in snap["storage"]:
                row = ctk.CTkFrame(self.storage_frame, fg_color=PANEL, corner_radius=10)
                row.pack(fill="x", pady=3)
                lbl = ctk.CTkLabel(row, text="", font=ctk.CTkFont(size=11), anchor="w")
                lbl.pack(fill="x", padx=10, pady=(6, 2))
                bar = ctk.CTkProgressBar(row, height=6, corner_radius=3, progress_color=self.accent)
                bar.set(0)
                bar.pack(fill="x", padx=10, pady=(0, 8))
                self._drive_rows[vol["drive"]] = (lbl, bar)
        for vol in snap["storage"]:
            if vol["drive"] in self._drive_rows:
                lbl, bar = self._drive_rows[vol["drive"]]
                name = f"{vol['drive'].rstrip(chr(92))} {vol.get('label') or ''}".strip()
                lbl.configure(text=f"{name}   {vol['percent']:.0f}%  ({_fmt_gb(vol['free'])} free)")
                bar.set(vol["percent"] / 100)

    # ---------------- session tracking ----------------
    def _tick_running(self):
        if HAS_PSUTIL:
            for key in list(self._running):
                info = self._running[key]
                try:
                    alive = psutil.pid_exists(info["pid"])
                except Exception:
                    alive = False
                if not alive:
                    dur = (datetime.now() - info["start"]).total_seconds()
                    g = next((x for x in self.games if x.get("exe", "").lower() == key), None)
                    if g:
                        g["total_seconds"] = int(g.get("total_seconds", 0) + dur)
                        save_games(self.games)
                    self._running.pop(key, None)
                    self.render_details()
        self.after(5000, self._tick_running)

    # ---------------- views / library ----------------
    def set_view(self, view):
        self._view = view
        self.lib_title.configure(text={"library": "My Library", "favourites": "Favourites",
                                       "recent": "Recently Played"}.get(view, "My Library"))
        self.refresh_library()

    def _visible_games(self):
        games = list(self.games)
        if self._view == "favourites":
            games = [g for g in games if g.get("favorite")]
        elif self._view == "recent":
            games = [g for g in games if g.get("plays", 0) > 0]
        q = self._filter.strip().lower()
        if q:
            games = [g for g in games
                     if q in g.get("name", "").lower()
                     or q in g.get("exe", "").lower()
                     or q in os.path.dirname(g.get("exe", "")).lower()]
        mode = self._sort_mode
        if mode == "Z - A":
            key, rev = (lambda g: g.get("name", "").lower()), True
        elif mode == "Recently added":
            key, rev = (lambda g: g.get("added") or ""), True
        elif mode == "Recently played":
            key, rev = (lambda g: g.get("last_played") or ""), True
        elif mode == "Most played":
            key, rev = (lambda g: g.get("plays", 0)), True
        elif mode == "Least played":
            key, rev = (lambda g: g.get("plays", 0)), False
        else:
            key, rev = (lambda g: g.get("name", "").lower()), False
        return sorted(games, key=key, reverse=rev)

    def refresh_library(self):
        for w in self.grid.winfo_children():
            w.destroy()
        self._card_widgets.clear()
        self._card_names.clear()
        self._ctk_images.clear()

        games = self._visible_games()
        self.lib_count.configure(text=f"{len(games)} of {len(self.games)} games")

        if not games:
            ctk.CTkLabel(self.grid, text="No games here yet.\nUse  + Add Game  /  Auto Detect  /  Steam Import",
                         font=ctk.CTkFont(size=14), text_color=MUTED, justify="center").grid(
                             row=0, column=0, columnspan=5, pady=80)
        else:
            for i, g in enumerate(games):
                self._make_card(g, i).grid(row=i // 5, column=i % 5, padx=6, pady=6, sticky="n")

        # keep hero valid
        if self._hero is not None and self._hero.get("exe", "").lower() not in {
                x.get("exe", "").lower() for x in self.games}:
            self._hero = None
        if self._hero is None and games:
            self._hero = games[0]
        self.render_featured()
        self.render_details()
        self.sel_btn.pack_forget() if not self._selection_mode else self.sel_btn.pack(side="right")

    def _make_card(self, game, index):
        key = game.get("exe", "").lower()
        card = ctk.CTkFrame(self.grid, fg_color=CARD, corner_radius=12,
                            border_width=2, border_color=CARD)
        pic = card_picture(game)
        cimg = ctk.CTkImage(light_image=pic, dark_image=pic, size=(CARD_W, CARD_H))
        self._ctk_images[key] = cimg

        img_btn = ctk.CTkButton(card, image=cimg, text="", width=CARD_W, height=CARD_H,
                                fg_color=CARD, hover_color=PANEL2, corner_radius=10,
                                command=lambda g=game: self._card_click(g))
        img_btn.pack(padx=6, pady=(6, 2))
        img_btn.bind("<Double-Button-1>", lambda e, g=game: self.launch_game(g))

        nm = ctk.CTkLabel(card, text=game.get("name", "Unnamed"), width=CARD_W,
                          font=ctk.CTkFont(size=12, weight="bold"), wraplength=CARD_W)
        nm.pack(padx=6)
        nm.bind("<Button-1>", lambda e, g=game: self._card_click(g))
        nm.bind("<Double-Button-1>", lambda e, g=game: self.launch_game(g))

        sub = f"▶ {game.get('plays', 0)}" if game.get("plays") else "New"
        ago = time_ago(game.get("last_played"))
        if game.get("plays") and ago:
            sub += f" · {ago}"
        ctk.CTkLabel(card, text=sub, font=ctk.CTkFont(size=10), text_color=MUTED).pack(pady=(0, 6))

        fav = bool(game.get("favorite"))
        star = ctk.CTkButton(card, text="★" if fav else "☆", width=24, height=24, corner_radius=12,
                             font=ctk.CTkFont(size=13, weight="bold"), fg_color="#0E1220",
                             hover_color=self.accent, text_color=STAR_GOLD if fav else MUTED,
                             command=lambda g=game: self.toggle_favorite(g))
        star.place(relx=1.0, rely=0.0, anchor="ne", x=-8, y=8)

        for w in (card, img_btn, nm):
            w.bind("<Button-3>", lambda e, idx=index: self._show_menu(e, idx))

        self._card_widgets[key] = card
        self._card_names[key] = nm
        self._apply_card_state(key)
        return card

    def _apply_card_state(self, key):
        card = self._card_widgets.get(key)
        if not card:
            return
        hero_key = self._hero.get("exe", "").lower() if self._hero else None
        if key in self._selected:
            card.configure(border_color=ERROR, fg_color=PANEL2)
        elif key == hero_key:
            card.configure(border_color=self.accent, fg_color=PANEL2)
        else:
            card.configure(border_color=CARD, fg_color=CARD)

    def _card_click(self, game):
        if self._selection_mode:
            key = game.get("exe", "").lower()
            if key in self._selected:
                self._selected.discard(key)
            else:
                self._selected.add(key)
            self._apply_card_state(key)
            self.lib_count.configure(text=f"{len(self._selected)} selected")
            self.sel_btn.configure(text=f"Remove ({len(self._selected)})")
        else:
            old = self._hero.get("exe", "").lower() if self._hero else None
            self._hero = game
            if old:
                self._apply_card_state(old)
            self._apply_card_state(game.get("exe", "").lower())
            self.render_featured()
            self.render_details()

    # ---------------- featured + details ----------------
    def render_featured(self):
        for w in self.featured.winfo_children():
            w.destroy()
        g = self._hero
        if not g:
            ctk.CTkLabel(self.featured, text="Select a game to see it featured here",
                         text_color=MUTED, font=ctk.CTkFont(size=14)).place(relx=0.5, rely=0.5, anchor="center")
            return
        pic = hero_picture(g, HERO_W, HERO_H)
        cimg = ctk.CTkImage(light_image=pic, dark_image=pic, size=(HERO_W, HERO_H))
        self._featured_img = cimg
        ctk.CTkLabel(self.featured, image=cimg, text="").pack(side="left", padx=(14, 16), pady=14)

        info = ctk.CTkFrame(self.featured, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True, pady=14, padx=(0, 16))
        ctk.CTkLabel(info, text=g.get("name", "Unnamed"), anchor="w",
                     font=ctk.CTkFont(size=26, weight="bold")).pack(anchor="w")
        installed = bool(g.get("exe")) and os.path.exists(g.get("exe", ""))
        status = "Installed" if installed else "Missing"
        meta = f"{status} · ▶ {g.get('plays', 0)} plays"
        if g.get("last_played"):
            meta += f" · last played {time_ago(g.get('last_played'))}"
        ctk.CTkLabel(info, text=meta, anchor="w", text_color=self.accent_soft,
                     font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(4, 0))
        ctk.CTkLabel(info, text=g.get("exe", ""), anchor="w", text_color=MUTED,
                     font=ctk.CTkFont(size=10), wraplength=560, justify="left").pack(anchor="w", pady=(2, 10))

        row = ctk.CTkFrame(info, fg_color="transparent")
        row.pack(anchor="w")
        ctk.CTkButton(row, text="▶  Play", width=120, height=38, font=ctk.CTkFont(size=14, weight="bold"),
                      fg_color=self.accent, hover_color=self.accent_hover,
                      command=lambda: self.launch_game(g)).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="Open Folder", width=110, height=38, fg_color=PANEL2,
                      hover_color=BORDER, command=lambda: self.open_folder(g)).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="Remove", width=90, height=38, fg_color=PANEL2,
                      hover_color=ERROR, text_color="#FCA5A5",
                      command=lambda: self._remove_game(g)).pack(side="left")

    def render_details(self):
        for w in self.details.winfo_children():
            w.destroy()
        g = self._hero
        if not g:
            ctk.CTkLabel(self.details, text="No game selected", text_color=MUTED,
                         font=ctk.CTkFont(size=12)).pack(padx=12, pady=16)
            return
        exe = g.get("exe", "")
        installed = bool(exe) and os.path.exists(exe)
        lines = [
            ("Status", "Installed" if installed else "Missing"),
            ("Genre", g.get("genre") or "—"),
            ("Executable", os.path.basename(exe) if exe else "—"),
            ("Folder", os.path.dirname(exe) if exe else "—"),
            ("Last played", time_ago(g.get("last_played")) or "Never"),
            ("Playtime", self._fmt_playtime(g)),
        ]
        ctk.CTkLabel(self.details, text=g.get("name", "Unnamed"), anchor="w",
                     font=ctk.CTkFont(size=14, weight="bold"), wraplength=250,
                     justify="left").pack(fill="x", padx=12, pady=(10, 6))
        for k, v in lines:
            row = ctk.CTkFrame(self.details, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=1)
            ctk.CTkLabel(row, text=k, width=74, anchor="w", font=ctk.CTkFont(size=10),
                         text_color=MUTED).pack(side="left")
            ctk.CTkLabel(row, text=str(v), anchor="w", font=ctk.CTkFont(size=11),
                         wraplength=160, justify="left").pack(side="left", fill="x", expand=True)
        row2 = ctk.CTkFrame(self.details, fg_color="transparent")
        row2.pack(fill="x", padx=12, pady=(8, 12))
        ctk.CTkButton(row2, text="Play", height=30, fg_color=self.accent, hover_color=self.accent_hover,
                      command=lambda: self.launch_game(g)).pack(side="left", padx=(0, 6))
        ctk.CTkButton(row2, text="Folder", height=30, fg_color=PANEL2, hover_color=BORDER,
                      command=lambda: self.open_folder(g)).pack(side="left", padx=(0, 6))
        ctk.CTkButton(row2, text="✕", width=32, height=30, fg_color=PANEL2, hover_color=ERROR,
                      command=lambda: self._remove_game(g)).pack(side="left")

    def _fmt_playtime(self, g):
        secs = int(g.get("total_seconds", 0))
        if secs <= 0:
            return "—"
        h, m = divmod(secs // 60, 60)
        return f"{h}h {m}m" if h else f"{m}m"

    # ---------------- search / sort / theme ----------------
    def on_search(self):
        self._filter = self.search_var.get()
        self.refresh_library()

    def on_sort(self, value):
        self._sort_mode = value
        self.refresh_library()

    def on_theme(self, value):
        self.accent, self.accent_hover, self.accent_soft = THEMES.get(value, THEMES["Violet"])
        self.settings["theme"] = value
        save_settings(self.settings)
        for _, bar, _, _ in ((self.cpu_card, self.cpu_bar, None, None),
                             (self.ram_card, self.ram_bar, None, None),
                             (self.gpu_card, self.gpu_bar, None, None)):
            bar.configure(progress_color=self.accent)
        self.refresh_library()

    # ---------------- favourites ----------------
    def toggle_favorite(self, game):
        game["favorite"] = not bool(game.get("favorite"))
        save_games(self.games)
        self.refresh_library()

    # ---------------- selection / removal ----------------
    def toggle_selection_mode(self):
        self._selection_mode = not self._selection_mode
        if not self._selection_mode:
            self._selected.clear()
        if self._selection_mode:
            self.sel_btn.configure(text=f"Remove ({len(self._selected)})")
            self.sel_btn.pack(side="right")
        else:
            self.sel_btn.pack_forget()
        for k in list(self._card_widgets):
            self._apply_card_state(k)
        self.refresh_library()

    def remove_selected(self):
        if not self._selected:
            return
        if not messagebox.askyesno("Remove games", f"Remove {len(self._selected)} selected game(s)?"):
            return
        self.games = [g for g in self.games if g.get("exe", "").lower() not in self._selected]
        self._selected.clear()
        self._selection_mode = False
        save_games(self.games)
        self.refresh_library()

    def _remove_game(self, g):
        if not messagebox.askyesno("Remove", f'Remove "{g.get("name")}" from the library?\n\n'
                                              "(Game files are NOT deleted.)"):
            return
        if g in self.games:
            self.games.remove(g)
        save_games(self.games)
        self.refresh_library()

    # ---------------- context menu ----------------
    def _show_menu(self, event, index):
        visible = self._visible_games()
        if index >= len(visible):
            return
        g = visible[index]
        m = Menu(self, tearoff=0)
        m.add_command(label="Launch", command=lambda: self.launch_game(g))
        m.add_command(label="Unfavourite" if g.get("favorite") else "Favourite",
                      command=lambda: self.toggle_favorite(g))
        m.add_command(label="Rename...", command=lambda: self._rename(g))
        m.add_command(label="Change path...", command=lambda: self._change_path(g))
        m.add_command(label="Open folder", command=lambda: self.open_folder(g))
        m.add_separator()
        m.add_command(label="Remove from library", command=lambda: self._remove_game(g))
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    def _on_sel_btn(self):
        if self._selection_mode:
            self.remove_selected()

    def _rename(self, g):
        d = ctk.CTkInputDialog(text="New name:", title="Rename game")
        v = d.get_input()
        if v and v.strip():
            g["name"] = v.strip()
            save_games(self.games)
            self.refresh_library()

    def _change_path(self, g):
        p = filedialog.askopenfilename(title="Select executable",
                                       filetypes=[("Executable", "*.exe"), ("All files", "*.*")])
        if p:
            g["exe"] = p
            g["icon"] = ""
            save_games(self.games)
            self.refresh_library()

    # ---------------- add / detect / steam ----------------
    def add_game(self):
        path = filedialog.askopenfilename(title="Select game executable",
                                          filetypes=[("Executable", "*.exe"), ("All files", "*.*")])
        if not path:
            return
        if any(g.get("exe", "").lower() == path.lower() for g in self.games):
            messagebox.showinfo("Already added", "That executable is already in the library.")
            return
        self.games.append({"name": name_from_exe(path), "exe": path, "icon": "",
                           "plays": 0, "last_played": None, "favorite": False,
                           "total_seconds": 0, "added": datetime.now().isoformat()})
        save_games(self.games)
        self.refresh_library()

    def auto_detect(self):
        folder = filedialog.askdirectory(title="Select a game folder (or your games folder)")
        if not folder:
            return
        found = detect_games(folder)
        if not found:
            messagebox.showinfo("Auto Detect", "No game executables found in that folder.")
            return
        existing = {g.get("exe", "").lower() for g in self.games}
        added = 0
        for it in found:
            if it["exe"].lower() in existing:
                continue
            self.games.append({"name": it["name"], "exe": it["exe"], "icon": "",
                               "plays": 0, "last_played": None, "favorite": False,
                               "total_seconds": 0, "added": datetime.now().isoformat()})
            added += 1
        save_games(self.games)
        self.refresh_library()
        messagebox.showinfo("Auto Detect", f"Found {len(found)} game(s), added {added} new.")

    def steam_import_dialog(self):
        if steam_import is None:
            messagebox.showerror("Steam Import", "Steam module unavailable.")
            return
        sf = steam_import.default_steam_path()
        if not sf:
            messagebox.showinfo("Steam Import", "Steam was not found on this PC.")
            return
        if not messagebox.askyesno("Steam Import",
                                   f"Import installed games from Steam?\n\n{sf}"):
            return
        threading.Thread(target=self._steam_import_worker, daemon=True).start()

    def _steam_import_worker(self):
        try:
            installed = steam_import.get_installed_games()
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Steam Import", str(e)))
            return
        existing = {g.get("exe", "").lower() for g in self.games}
        added = 0
        new_games = []
        for sg in installed:
            exe = find_main_exe(sg["install_path"])
            if not exe or exe.lower() in existing:
                continue
            rec = {"name": sg["name"], "exe": exe, "icon": "", "appid": sg["appid"],
                   "plays": 0, "last_played": None, "favorite": False,
                   "total_seconds": 0, "added": datetime.now().isoformat()}
            new_games.append(rec)
            existing.add(exe.lower())
            added += 1
        # fetch artwork (best effort) then hand back to UI thread
        for rec in new_games:
            if steam_import is not None and rec.get("appid"):
                try:
                    art = steam_import.fetch_steam_artwork(rec["appid"])
                    if art.get("cover"):
                        rec["artwork_cover"] = art["cover"]
                    if art.get("hero"):
                        rec["artwork_hero"] = art["hero"]
                except Exception:
                    pass

        def finish():
            self.games.extend(new_games)
            save_games(self.games)
            self.refresh_library()
            messagebox.showinfo("Steam Import",
                                f"Found {len(installed)} installed Steam game(s),\nadded {added} new.")
        self.after(0, finish)

    # ---------------- launch / open ----------------
    def launch_game(self, game):
        exe = game.get("exe", "")
        if not exe or not os.path.exists(exe):
            messagebox.showerror("Not found", f"The executable could not be found:\n{exe}")
            return
        try:
            proc = subprocess.Popen([exe], cwd=os.path.dirname(exe))
        except Exception as e:
            messagebox.showerror("Launch failed", str(e))
            return
        key = exe.lower()
        if HAS_PSUTIL:
            self._running[key] = {"pid": proc.pid, "start": datetime.now()}
        game["plays"] = game.get("plays", 0) + 1
        game["last_played"] = datetime.now().isoformat()
        if not game.get("added"):
            game["added"] = datetime.now().isoformat()
        save_games(self.games)
        self.refresh_library()

    def open_folder(self, game):
        exe = game.get("exe", "")
        if exe and os.path.exists(exe):
            try:
                os.startfile(os.path.dirname(exe))
            except Exception:
                pass


def main():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = GameLauncherApp()
    app.mainloop()


if __name__ == "__main__":
    main()