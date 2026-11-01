"""
Game Launcher — a single-window launcher for all your games.
Add a game by pointing at its .exe (or auto-detect the main executable in a
folder); the launcher names it after its folder, pulls the game's icon,
colours each tile from its artwork, and shows a hero panel for the selected
game. Click to select, double-click (or Play) to launch.
Favourites, play tracking, sorting, search, multi-select removal, and
themes included.
"""

import os
import sys
import json
import hashlib
import subprocess
from datetime import datetime
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog, messagebox, Menu
from PIL import Image, ImageDraw, ImageFont

try:
    import win32gui
    import win32ui
    import win32con
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

APP_TITLE = "Game Launcher"
APP_TAGLINE = "Your games, one click away"
CONFIG_DIR = Path.home() / ".game_launcher"
CONFIG_FILE = CONFIG_DIR / "games.json"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
ICON_DIR = CONFIG_DIR / "icons"

ICON_SIZE = 256         # cached icon resolution (high-res extraction)
CARD_ICON_SIZE = 100    # rendered tile size
HERO_ICON_SIZE = 128    # hero panel picture size

CARD_BASE = (35, 38, 46)    # dark base for card-tint blending
CARD_SELECTED_BG = "#3b2f55"
DANGER = "#dc2626"
DANGER_HOVER = "#b91c1c"
STAR_GOLD = "#fbbf24"
STAR_MUTED = "#8b8f98"

SORT_OPTIONS = ["A - Z", "Most played", "Last played", "Recently added"]

THEMES = {
    "Violet":     ("#7C3AED", "#6D28D9", "#c4b5fd"),
    "Crimson":    ("#dc2626", "#b91c1c", "#fca5a5"),
    "Ocean Blue": ("#2563eb", "#1d4ed8", "#93c5fd"),
    "Emerald":    ("#10b981", "#059669", "#6ee7b7"),
    "Sunset":     ("#f97316", "#ea580c", "#fdba74"),
    "Rose":       ("#ec4899", "#db2777", "#f9a8d4"),
    "Gold":       ("#d97706", "#b45309", "#fcd34d"),
    "Teal":       ("#0d9488", "#0f766e", "#5eead4"),
}
DEFAULT_THEME = "Violet"

NAME_PALETTE = [
    (76, 175, 80), (33, 150, 243), (156, 39, 176), (255, 152, 0),
    (233, 30, 99), (0, 150, 136), (63, 81, 181), (255, 87, 34),
]

# Substrings that mark a non-game executable (uninstallers, redist, etc.)
SKIP_SUBSTRINGS = [
    "unins", "uninstall", "setup", "install", "redist", "vcredist", "vc_redist",
    "dxsetup", "directx", "dxwebsetup", "crash", "report", "updater", "verify",
    "cleanup", "ue4prereq", "dotnet", "openal", "physx", "launcher_update",
    "uninstaller", "_commonredist",
]
# Folder names that sit under a game root but don't identify a game themselves.
STRUCTURE_DIRS = {"bin", "binaries", "bin64", "win64", "win32", "x64", "x86",
                  "build", "game", "dist", "release", "launcher", "content"}


def resource_path(name):
    """Path to a bundled file, working both as source and frozen exe."""
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, name)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), name)


def ensure_dirs():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    ICON_DIR.mkdir(parents=True, exist_ok=True)


def load_games():
    ensure_dirs()
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []


def save_games(games):
    ensure_dirs()
    CONFIG_FILE.write_text(
        json.dumps(games, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_settings():
    ensure_dirs()
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def save_settings(settings):
    ensure_dirs()
    SETTINGS_FILE.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def name_from_exe(path):
    """Use the game's folder name (e.g. 'Dave the Diver')."""
    folder = os.path.basename(os.path.dirname(path))
    if folder and not folder.endswith(":"):
        return folder
    return os.path.splitext(os.path.basename(path))[0]


def _hicon_to_pil(hicon, size):
    """Draw a Windows HICON into a PIL RGBA image of the given size."""
    hdc_screen = win32gui.GetDC(0)
    hdc = win32ui.CreateDCFromHandle(hdc_screen)
    hbmp = win32ui.CreateBitmap()
    hbmp.CreateCompatibleBitmap(hdc, size, size)
    hdc_mem = hdc.CreateCompatibleDC()
    hdc_mem.SelectObject(hbmp)
    win32gui.DrawIconEx(
        hdc_mem.GetSafeHdc(), 0, 0, hicon, size, size, 0, None, win32con.DI_NORMAL
    )
    bmpinfo = hbmp.GetInfo()
    bmpstr = hbmp.GetBitmapBits(True)
    img = Image.frombuffer(
        "RGBA", (bmpinfo["bmWidth"], bmpinfo["bmHeight"]), bmpstr, "raw", "BGRA", 0, 1
    )
    hdc_mem.DeleteDC()
    hdc.DeleteDC()
    win32gui.ReleaseDC(0, hdc_screen)
    return img


def extract_icon(exe_path, size=256):
    """Pull the executable's icon as a PIL Image, preferring high resolution."""
    if not HAS_WIN32:
        return None
    hicon = None

    try:
        import ctypes
        from ctypes import wintypes
        shell32 = ctypes.windll.shell32
        hlarge = wintypes.HICON()
        hsmall = wintypes.HICON()
        hr = shell32.SHDefExtractIconW(
            os.path.abspath(exe_path), 0, 0,
            ctypes.byref(hlarge), ctypes.byref(hsmall), size,
        )
        if hr == 0 and hlarge.value:
            hicon = hlarge.value
            if hsmall.value:
                win32gui.DestroyIcon(hsmall.value)
    except Exception:
        hicon = None

    if not hicon:
        try:
            ico_large, ico_small = win32gui.ExtractIconEx(exe_path, 0)
            if ico_large:
                hicon = ico_large[0]
            elif ico_small:
                hicon = ico_small[0]
            for ic in ico_large[1:]:
                win32gui.DestroyIcon(ic)
            for ic in ico_small[1:]:
                win32gui.DestroyIcon(ic)
        except Exception:
            hicon = None

    if not hicon:
        return None

    try:
        img = _hicon_to_pil(hicon, size)
        return img
    except Exception:
        return None
    finally:
        try:
            win32gui.DestroyIcon(hicon)
        except Exception:
            pass


def placeholder_icon(name, size=128):
    """Coloured letter tile used when no icon can be extracted."""
    letter = (name.strip()[:1] or "?").upper()
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    color = name_color(name)
    d.rounded_rectangle([6, 6, size - 6, size - 6], radius=22, fill=color)
    try:
        font = ImageFont.truetype("segoeuib.ttf", int(size * 0.5))
    except Exception:
        font = ImageFont.load_default()
    bbox = d.textbbox((0, 0), letter, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((size - w) / 2 - bbox[0], (size - h) / 2 - bbox[1]), letter, fill="white", font=font)
    return img


def get_game_icon(game, size=128):
    """Return a cached icon file path for a game, generating it if needed."""
    exe = game.get("exe", "")
    if not exe or not os.path.exists(exe):
        return None

    cache_name = hashlib.md5(exe.encode("utf-8")).hexdigest() + ".png"
    cache_path = ICON_DIR / cache_name
    if cache_path.exists():
        game["icon"] = str(cache_path)
        return str(cache_path)

    img = extract_icon(exe, size)
    if img is None:
        img = placeholder_icon(game.get("name", "?"), size)
    try:
        img.save(cache_path)
        game["icon"] = str(cache_path)
        return str(cache_path)
    except Exception:
        return None


# ---------------- Colour helpers ----------------
def name_color(name):
    """A deterministic, vivid colour for a game name."""
    return NAME_PALETTE[sum(ord(c) for c in name) % len(NAME_PALETTE)]


def icon_dominant(icon_path):
    """Vivid average colour of an icon's opaque pixels, or None."""
    try:
        img = Image.open(icon_path).convert("RGBA").resize((16, 16))
        r = g = b = n = 0
        for pr, pg, pb, pa in img.getdata():
            if pa > 40:
                r += pr; g += pg; b += pb; n += 1
        if not n:
            return None
        r //= n; g //= n; b //= n
        mx = max(r, g, b)
        if mx < 90:
            return (139, 92, 246)
        scale = 225 / mx
        return (min(255, int(r * scale)), min(255, int(g * scale)), min(255, int(b * scale)))
    except Exception:
        return None


def blend(c1, c2, t):
    return tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3))


def rgb_hex(c):
    return "#%02x%02x%02x" % c


def time_ago(iso):
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso)
    except Exception:
        return ""
    delta = datetime.now() - dt
    days = delta.days
    if days >= 365:
        return f"{days // 365}y ago"
    if days >= 1:
        return f"{days}d ago"
    secs = delta.seconds
    if secs >= 3600:
        return f"{secs // 3600}h ago"
    if secs >= 60:
        return f"{secs // 60}m ago"
    return "just now"


# ---------------- Auto-detect ----------------
def _is_skip(fname):
    low = fname.lower()
    return any(s in low for s in SKIP_SUBSTRINGS)


def _pick_main_exe(game_name, candidates):
    """Pick the executable most likely to be the real game."""
    gn = game_name.lower()
    gn_norm = "".join(c for c in gn if c.isalnum())
    best, best_score = None, -1e9
    for exe, depth in candidates:
        base = os.path.splitext(os.path.basename(exe))[0].lower()
        base_norm = "".join(c for c in base if c.isalnum())
        score = 0
        if base_norm and (base_norm == gn_norm or base_norm in gn_norm or gn_norm in base_norm):
            score += 4
        score -= depth * 0.5
        for bad in ("launcher", "client", "download", "updater", "store", "service",
                    "patcher", "browser", "wow", "installer"):
            if bad in base:
                score -= 4
        try:
            size = os.path.getsize(exe)
        except Exception:
            size = 0
        score += min(size / (2 * 1024 * 1024 * 1024), 2.0)
        if score > best_score:
            best, best_score = exe, score
    return best


def detect_games(folder):
    """Find one main game executable per game folder under `folder`."""
    folder = os.path.abspath(folder)
    groups = {}
    for root, dirs, files in os.walk(folder):
        rel = os.path.relpath(root, folder)
        parts = [p for p in rel.split(os.sep) if p] if rel != "." else []
        if any(p.lower() in {"redist", "_commonredist", "uninstall", "directx", "dotnet", "__installer"} for p in parts):
            dirs[:] = []
            continue
        if parts and parts[0].lower() in STRUCTURE_DIRS:
            game_root, name = folder, os.path.basename(folder)
        elif parts:
            game_root = os.path.join(folder, parts[0])
            name = parts[0]
        else:
            game_root, name = folder, os.path.basename(folder)

        for f in files:
            if not f.lower().endswith(".exe") or _is_skip(f):
                continue
            groups.setdefault(game_root, [name, []])[1].append((os.path.join(root, f), len(parts)))

    results = []
    for game_root, (name, cands) in groups.items():
        exe = _pick_main_exe(name, cands)
        if exe:
            results.append({"name": name, "exe": exe})
    return results


class GameLauncherApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1200x760")
        self.minsize(1000, 560)

        self._apply_window_icon()

        self.accent, self.accent_hover, self.accent_soft = THEMES[DEFAULT_THEME]
        self.theme_name = DEFAULT_THEME
        settings = load_settings()
        if settings.get("theme") in THEMES:
            self._set_theme(settings["theme"])

        self.games = load_games()
        self._ctk_images = {}
        self._cards = {}
        self._card_widgets = {}
        self._card_vivids = {}
        self._filter = ""
        self._sort_mode = SORT_OPTIONS[0]
        self._selection_mode = False
        self._selected = set()      # lowercase exe paths (multi-remove)
        self._hero = None           # game dict shown in the hero panel
        self._hero_exe_key = None
        self._hero_img = None

        self._build_ui()
        self.refresh_grid()

    def _apply_window_icon(self):
        try:
            ico = resource_path("icon.ico")
            if os.path.exists(ico):
                self.iconbitmap(ico)
        except Exception:
            pass

    def _set_theme(self, name):
        self.accent, self.accent_hover, self.accent_soft = THEMES.get(name, THEMES[DEFAULT_THEME])
        self.theme_name = name

    # ---------------- UI construction ----------------
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Top bar
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 6))
        top.grid_columnconfigure(1, weight=1)

        title_frame = ctk.CTkFrame(top, fg_color="transparent")
        title_frame.grid(row=0, column=0, sticky="w", padx=(0, 10))
        ctk.CTkLabel(title_frame, text=APP_TITLE, font=ctk.CTkFont(size=20, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(title_frame, text=APP_TAGLINE, font=ctk.CTkFont(size=11), text_color=self.accent_soft).grid(row=1, column=0, sticky="w")

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.on_search())
        ctk.CTkEntry(top, placeholder_text="Search games...", textvariable=self.search_var, width=150).grid(row=0, column=1, sticky="e", padx=(0, 8))

        self.sort_var = ctk.StringVar(value=SORT_OPTIONS[0])
        ctk.CTkOptionMenu(top, values=SORT_OPTIONS, variable=self.sort_var, command=self.on_sort,
                          width=115, height=36, fg_color="#2a2d34", button_color="#3a3f47",
                          button_hover_color="#4a5059").grid(row=0, column=2, padx=(0, 8))

        self.theme_var = ctk.StringVar(value=self.theme_name)
        ctk.CTkOptionMenu(top, values=list(THEMES.keys()), variable=self.theme_var, command=self.on_theme,
                          width=110, height=36, fg_color="#2a2d34", button_color="#3a3f47",
                          button_hover_color="#4a5059").grid(row=0, column=3, padx=(0, 8))

        self.btn_remove_sel = ctk.CTkButton(
            top, text="Remove Selected (0)", width=160, height=36,
            fg_color=DANGER, hover_color=DANGER_HOVER, command=self.remove_selected)
        self.btn_remove_sel.grid(row=0, column=4, padx=(0, 8))
        self.btn_remove_sel.grid_remove()

        ctk.CTkButton(top, text="Auto Detect", width=104, height=36,
                      fg_color="#2a2d34", hover_color="#3a3f47", command=self.auto_detect).grid(row=0, column=5, padx=(0, 8))

        self.btn_select = ctk.CTkButton(
            top, text="Select", width=84, height=36, fg_color="transparent",
            border_width=1, border_color="#4a5059", hover_color="#3a3f47",
            text_color="#d1d5db", command=self.toggle_selection_mode)
        self.btn_select.grid(row=0, column=6, padx=(0, 8))

        self.btn_add = ctk.CTkButton(
            top, text="+ Add Game", width=116, height=36,
            fg_color=self.accent, hover_color=self.accent_hover, command=self.add_game)
        self.btn_add.grid(row=0, column=7)

        # Hero panel
        self.hero_frame = ctk.CTkFrame(self, corner_radius=16, fg_color="#23262e", height=150)
        self.hero_frame.grid(row=1, column=0, sticky="ew", padx=16, pady=(2, 6))
        self.hero_frame.grid_propagate(False)

        # Grid area
        self.grid_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.grid_frame.grid(row=2, column=0, sticky="nsew", padx=16, pady=(4, 12))
        self.grid_frame.grid_columnconfigure(tuple(range(6)), weight=1, uniform="col")

        # Status bar
        self.status = ctk.CTkLabel(self, text="", anchor="w", font=ctk.CTkFont(size=12))
        self.status.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 8))

        # Context menu
        self.menu = Menu(self, tearoff=0)
        self.menu.add_command(label="Launch", command=self.menu_launch)
        self.menu.add_command(label="Toggle favourite", command=self.menu_favorite)
        self.menu.add_command(label="Rename", command=self.menu_rename)
        self.menu.add_command(label="Change path...", command=self.menu_change_path)
        self.menu.add_separator()
        self.menu.add_command(label="Remove", command=self.menu_remove)

    # ---------------- Hero panel ----------------
    def _render_hero(self):
        for w in self.hero_frame.winfo_children():
            w.destroy()
        game = self._hero
        hf = self.hero_frame
        hf.grid_columnconfigure(1, weight=1)

        if game is None:
            ctk.CTkLabel(hf, text="Select a game to see it here",
                         font=ctk.CTkFont(size=15), text_color="#9ca3af").place(
                             relx=0.5, rely=0.5, anchor="center")
            return

        name = game.get("name", "Unnamed")
        icon_path = get_game_icon(game, ICON_SIZE)
        vivid = icon_dominant(icon_path) if (icon_path and os.path.exists(icon_path)) else name_color(name)
        vivid = vivid or name_color(name)
        hf.configure(fg_color=rgb_hex(blend(CARD_BASE, vivid, 0.22)))

        pil = None
        if icon_path and os.path.exists(icon_path):
            try:
                pil = Image.open(icon_path).resize((HERO_ICON_SIZE, HERO_ICON_SIZE), Image.LANCZOS)
            except Exception:
                pil = None
        if pil:
            self._hero_img = ctk.CTkImage(light_image=pil, dark_image=pil, size=(HERO_ICON_SIZE, HERO_ICON_SIZE))
            ctk.CTkLabel(hf, image=self._hero_img, text="").grid(
                row=0, column=0, rowspan=2, padx=(18, 12), pady=12, sticky="w")
        else:
            letter = (name[:1] or "?").upper()
            ctk.CTkButton(hf, text=letter, width=HERO_ICON_SIZE, height=HERO_ICON_SIZE,
                          font=ctk.CTkFont(size=52, weight="bold"), fg_color=rgb_hex(vivid),
                          hover_color=rgb_hex(vivid), text_color="white").grid(
                              row=0, column=0, rowspan=2, padx=(18, 12), pady=12, sticky="w")

        ctk.CTkLabel(hf, text=name, font=ctk.CTkFont(size=24, weight="bold"),
                     anchor="w", text_color="white").grid(row=0, column=1, sticky="sw", padx=(4, 16), pady=(16, 0))

        plays = game.get("plays", 0)
        meta = f"\u25b6 {plays} plays"
        ago = time_ago(game.get("last_played"))
        if ago:
            meta += f"  \u00b7  last played {ago}"
        ctk.CTkLabel(hf, text=meta, font=ctk.CTkFont(size=13),
                     text_color="#c7cad1", anchor="w").grid(row=1, column=1, sticky="nw", padx=(4, 16), pady=(6, 0))

        btn_row = ctk.CTkFrame(hf, fg_color="transparent")
        btn_row.grid(row=2, column=1, sticky="sw", padx=(4, 16), pady=(8, 16))
        ctk.CTkButton(btn_row, text="\u25b6  Play", width=120, height=40,
                      font=ctk.CTkFont(size=15, weight="bold"),
                      fg_color=self.accent, hover_color=self.accent_hover,
                      command=lambda g=game: self.launch_game(g)).pack(side="left", padx=(0, 8))
        fav = bool(game.get("favorite"))
        ctk.CTkButton(btn_row, text="\u2605" if fav else "\u2606", width=40, height=40,
                      font=ctk.CTkFont(size=20), fg_color="#20232b", hover_color="#3a3f47",
                      text_color=STAR_GOLD if fav else STAR_MUTED,
                      command=lambda g=game: self.toggle_favorite(g)).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="Remove", width=80, height=40,
                      fg_color="#20232b", hover_color=DANGER_HOVER, text_color="#fca5a5",
                      command=lambda g=game: self._remove_game(g)).pack(side="left")

    # ---------------- Grid rendering ----------------
    def _sorted_games(self, games):
        mode = self._sort_mode
        if mode == "Most played":
            key = lambda g: g.get("plays", 0); rev = True
        elif mode == "Last played":
            key = lambda g: g.get("last_played") or ""; rev = True
        elif mode == "Recently added":
            key = lambda g: g.get("added") or ""; rev = True
        else:
            key = lambda g: g.get("name", "").lower(); rev = False
        favs = sorted([g for g in games if g.get("favorite")], key=key, reverse=rev)
        rest = sorted([g for g in games if not g.get("favorite")], key=key, reverse=rev)
        return favs + rest

    def refresh_grid(self):
        if self._hero is not None:
            exes = {g.get("exe", "").lower() for g in self.games}
            if not exes or self._hero.get("exe", "").lower() not in exes:
                self._hero = None
                self._hero_exe_key = None

        for w in self.grid_frame.winfo_children():
            w.destroy()
        self._cards.clear()
        self._ctk_images.clear()
        self._card_widgets.clear()
        self._card_vivids.clear()

        query = self._filter.strip().lower()
        games = [g for g in self.games if query in g.get("name", "").lower()] if query else list(self.games)
        games = self._sorted_games(games)

        if not games:
            text = "No games match your search." if query else "No games yet\nClick \"+ Add Game\" or \"Auto Detect\" to add games"
            ctk.CTkLabel(self.grid_frame, text=text, font=ctk.CTkFont(size=16),
                         text_color="#9ca3af", justify="center").grid(
                             row=0, column=0, columnspan=6, pady=70)
            self._render_hero()
            self._update_status()
            return

        cols = 6
        for i, game in enumerate(games):
            row, col = divmod(i, cols)
            self._make_card(game, i).grid(row=row, column=col, padx=6, pady=6, sticky="n")

        self._render_hero()
        self._update_status()

    def _make_card(self, game, index):
        exe_key = game.get("exe", "").lower()
        name = game.get("name", "Unnamed")

        icon_path = get_game_icon(game, ICON_SIZE)
        vivid = icon_dominant(icon_path) if (icon_path and os.path.exists(icon_path)) else name_color(name)
        vivid = vivid or name_color(name)
        tint = rgb_hex(blend(CARD_BASE, vivid, 0.30))
        tint_bright = rgb_hex(blend(CARD_BASE, vivid, 0.55))
        plate = rgb_hex(blend(CARD_BASE, vivid, 0.16))

        card = ctk.CTkFrame(self.grid_frame, corner_radius=14, fg_color=tint,
                            border_width=2, border_color=tint)
        card.grid_columnconfigure(0, weight=1)

        ctk_img = None
        if icon_path and os.path.exists(icon_path):
            try:
                pil = Image.open(icon_path).resize((CARD_ICON_SIZE, CARD_ICON_SIZE), Image.LANCZOS)
                ctk_img = ctk.CTkImage(light_image=pil, dark_image=pil, size=(CARD_ICON_SIZE, CARD_ICON_SIZE))
                self._ctk_images[index] = ctk_img
            except Exception:
                ctk_img = None

        if ctk_img:
            tile = ctk.CTkButton(card, image=ctk_img, text="", width=CARD_ICON_SIZE,
                                 height=CARD_ICON_SIZE, fg_color=plate, hover_color=tint_bright,
                                 corner_radius=12, command=lambda g=game: self._card_click(g))
        else:
            letter = (name[:1] or "?").upper()
            tile = ctk.CTkButton(card, text=letter, width=CARD_ICON_SIZE, height=CARD_ICON_SIZE,
                                 font=ctk.CTkFont(size=42, weight="bold"), fg_color=rgb_hex(vivid),
                                 hover_color=tint_bright, text_color="white",
                                 command=lambda g=game: self._card_click(g))
        tile.grid(row=0, column=0, padx=12, pady=(14, 6))

        label = ctk.CTkLabel(card, text=name, width=CARD_ICON_SIZE + 24,
                             font=ctk.CTkFont(size=13, weight="bold"), wraplength=CARD_ICON_SIZE + 20)
        label.grid(row=1, column=0, padx=8, pady=(0, 4))

        ctk.CTkFrame(card, width=44, height=3, corner_radius=2, fg_color=rgb_hex(vivid)).grid(row=2, column=0, pady=(0, 4))

        plays = game.get("plays", 0)
        sub = f"\u25b6 {plays}" if plays else "New"
        ago = time_ago(game.get("last_played"))
        if plays and ago:
            sub += f"  \u00b7  {ago}"
        sublabel = ctk.CTkLabel(card, text=sub, width=CARD_ICON_SIZE + 24,
                                font=ctk.CTkFont(size=11), text_color="#c7cad1")
        sublabel.grid(row=3, column=0, padx=8, pady=(0, 12))

        fav = bool(game.get("favorite"))
        star = ctk.CTkButton(card, text="\u2605" if fav else "\u2606", width=26, height=26,
                             corner_radius=13, font=ctk.CTkFont(size=14, weight="bold"),
                             fg_color="#20232b", hover_color=tint_bright,
                             text_color=STAR_GOLD if fav else STAR_MUTED,
                             command=lambda g=game: self.toggle_favorite(g))
        star.place(relx=1.0, rely=0.0, anchor="ne", x=-4, y=4)

        label.bind("<Button-1>", lambda e, g=game: self._card_click(g))
        for w in (tile, label, sublabel, card):
            w.bind("<Button-3>", lambda e, idx=index: self._show_menu(e, idx))
            w.bind("<Double-Button-1>", lambda e, g=game: self._card_dclick(g))

        self._card_widgets[exe_key] = card
        self._card_vivids[exe_key] = vivid
        self._cards[index] = card
        self._apply_card_state(exe_key)
        return card

    # ---------------- Interaction ----------------
    def _card_click(self, game):
        if self._selection_mode:
            self.toggle_select(game)
        else:
            self.select_hero(game)

    def _card_dclick(self, game):
        if not self._selection_mode:
            self.launch_game(game)

    def select_hero(self, game):
        old = self._hero_exe_key
        self._hero = game
        self._hero_exe_key = game.get("exe", "").lower()
        if old and old != self._hero_exe_key:
            self._apply_card_state(old)
        self._apply_card_state(self._hero_exe_key)
        self._render_hero()

    def toggle_selection_mode(self):
        self._selection_mode = not self._selection_mode
        if not self._selection_mode:
            self._selected.clear()
        for key in list(self._card_widgets):
            self._apply_card_state(key)
        self._update_action_bar()

    def toggle_select(self, game):
        key = game.get("exe", "").lower()
        if key in self._selected:
            self._selected.discard(key)
        else:
            self._selected.add(key)
        self._apply_card_state(key)
        self._update_action_bar()

    def _apply_card_state(self, key):
        card = self._card_widgets.get(key)
        if not card:
            return
        vivid = self._card_vivids.get(key, (124, 58, 237))
        tint = rgb_hex(blend(CARD_BASE, vivid, 0.30))
        tint_bright = rgb_hex(blend(CARD_BASE, vivid, 0.55))
        if key in self._selected:
            card.configure(fg_color=CARD_SELECTED_BG, border_color=self.accent)
        elif key == self._hero_exe_key:
            card.configure(fg_color=tint_bright, border_color=self.accent)
        else:
            card.configure(fg_color=tint, border_color=tint)

    def remove_selected(self):
        if not self._selected:
            return
        n = len(self._selected)
        if not messagebox.askyesno("Remove games", f"Remove {n} selected game(s) from the launcher?"):
            return
        self.games = [g for g in self.games if g.get("exe", "").lower() not in self._selected]
        self._selected.clear()
        save_games(self.games)
        self._selection_mode = False
        self.refresh_grid()
        self._update_action_bar()

    def _update_action_bar(self):
        n = len(self._selected)
        if self._selection_mode:
            self.btn_select.configure(text="Done", border_color=self.accent, text_color=self.accent_soft)
            self.btn_remove_sel.configure(text=f"Remove Selected ({n})", state="normal" if n else "disabled")
            self.btn_remove_sel.grid()
        else:
            self.btn_select.configure(text="Select", border_color="#4a5059", text_color="#d1d5db")
            self.btn_remove_sel.grid_remove()
        self._update_status()

    def _update_status(self):
        query = self._filter.strip().lower()
        if self._selection_mode:
            self.status.configure(text=f"Selection mode \u2014 {len(self._selected)} selected. Click games to toggle, then remove.")
        else:
            favs = sum(1 for g in self.games if g.get("favorite"))
            shown = sum(1 for g in self.games if not query or query in g.get("name", "").lower())
            text = f"{len(self.games)} games"
            if favs:
                text += f"  \u00b7  {favs} favourites"
            if query:
                text += f"  \u00b7  showing {shown}"
            self.status.configure(text=text)

    # ---------------- Context menu ----------------
    def _show_menu(self, event, index):
        self._menu_index = index
        g = self._menu_game()
        if g is not None:
            self.menu.entryconfigure(1, label="Unfavourite" if g.get("favorite") else "Add to favourites")
        else:
            self.menu.entryconfigure(1, label="Toggle favourite")
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def _menu_game(self):
        return self.games[self._menu_index] if self._menu_index < len(self.games) else None

    def menu_launch(self):
        g = self._menu_game()
        if g:
            self.launch_game(g)

    def menu_favorite(self):
        g = self._menu_game()
        if g:
            self.toggle_favorite(g)

    def menu_rename(self):
        g = self._menu_game()
        if not g:
            return
        dialog = ctk.CTkInputDialog(text="New name:", title="Rename game")
        new_name = dialog.get_input()
        if new_name and new_name.strip():
            g["name"] = new_name.strip()
            save_games(self.games)
            self.refresh_grid()

    def menu_change_path(self):
        g = self._menu_game()
        if not g:
            return
        path = filedialog.askopenfilename(
            title="Select game executable", filetypes=[("Executable", "*.exe"), ("All files", "*.*")])
        if path:
            g["exe"] = path
            g["icon"] = ""
            if not g.get("name"):
                g["name"] = name_from_exe(path)
            save_games(self.games)
            self.refresh_grid()

    def menu_remove(self):
        g = self._menu_game()
        if g:
            self._remove_game(g)

    def _remove_game(self, g):
        if not messagebox.askyesno("Remove game", f'Remove "{g.get("name")}" from the launcher?'):
            return
        if g in self.games:
            self.games.remove(g)
        save_games(self.games)
        self.refresh_grid()

    # ---------------- Search / sort / theme ----------------
    def on_search(self):
        self._filter = self.search_var.get()
        self.refresh_grid()

    def on_sort(self, value):
        self._sort_mode = value
        self.refresh_grid()

    def on_theme(self, value):
        self._set_theme(value)
        save_settings({"theme": value})
        self.btn_add.configure(fg_color=self.accent, hover_color=self.accent_hover)
        self.btn_select.configure(border_color=self.accent, text_color=self.accent_soft)
        for key in list(self._card_widgets):
            self._apply_card_state(key)
        self._render_hero()

    # ---------------- Favourites ----------------
    def toggle_favorite(self, game):
        game["favorite"] = not bool(game.get("favorite"))
        save_games(self.games)
        self.refresh_grid()

    # ---------------- Adding games ----------------
    def add_game(self):
        path = filedialog.askopenfilename(
            title="Select game executable", filetypes=[("Executable", "*.exe"), ("All files", "*.*")])
        if not path:
            return
        self._add_exe(path)

    def auto_detect(self):
        folder = filedialog.askdirectory(title="Select a game folder to auto-detect")
        if not folder:
            return
        found = detect_games(folder)
        if not found:
            messagebox.showinfo("Auto-detect", "No game executables found in that folder.")
            return
        added = 0
        existing = {g.get("exe", "").lower() for g in self.games}
        for item in found:
            if item["exe"].lower() in existing:
                continue
            self.games.append({
                "name": item["name"], "exe": item["exe"], "icon": "",
                "plays": 0, "last_played": None, "favorite": False,
                "added": datetime.now().isoformat(),
            })
            added += 1
        save_games(self.games)
        self.refresh_grid()
        messagebox.showinfo("Auto-detect", f"Found {len(found)} game(s), added {added} new.")

    def _add_exe(self, path):
        if any(g.get("exe", "").lower() == path.lower() for g in self.games):
            messagebox.showinfo("Already added", f'"{path}" is already in the launcher.')
            return
        self.games.append({
            "name": name_from_exe(path), "exe": path, "icon": "",
            "plays": 0, "last_played": None, "favorite": False,
            "added": datetime.now().isoformat(),
        })
        save_games(self.games)
        self.refresh_grid()

    # ---------------- Launching ----------------
    def launch_game(self, game):
        exe = game.get("exe", "")
        if not exe or not os.path.exists(exe):
            messagebox.showerror(
                "Not found",
                f"The executable could not be found:\n{exe}\n\nUse right-click \u2192 Change path to fix it.")
            return
        try:
            cwd = os.path.dirname(exe)
            subprocess.Popen([exe], cwd=cwd)
        except Exception as e:
            messagebox.showerror("Launch failed", str(e))
            return

        game["plays"] = game.get("plays", 0) + 1
        game["last_played"] = datetime.now().isoformat()
        if not game.get("added"):
            game["added"] = datetime.now().isoformat()
        save_games(self.games)
        self.refresh_grid()


def main():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = GameLauncherApp()
    app.mainloop()


if __name__ == "__main__":
    main()