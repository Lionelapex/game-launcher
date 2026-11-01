"""
Game Launcher — a single-window launcher for all your games.
Add a game by pointing at its .exe; the launcher names it after its folder,
pulls the game's own icon, colours each tile from its artwork, and shows
everything in a lively grid. Click to play. Favourites, play tracking,
sorting, search, and multi-select removal included.
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
ICON_DIR = CONFIG_DIR / "icons"

ICON_SIZE = 256         # cached icon resolution (high-res extraction)
CARD_ICON_SIZE = 100    # rendered tile size

ACCENT = "#7C3AED"          # violet accent (matches the app icon)
ACCENT_HOVER = "#6D28D9"
ACCENT_SOFT = "#c4b5fd"
CARD_BASE = (35, 38, 46)    # dark base for card-tint blending
CARD_SELECTED_BG = "#3b2f55"
DANGER = "#dc2626"
DANGER_HOVER = "#b91c1c"
STAR_GOLD = "#fbbf24"
STAR_MUTED = "#8b8f98"

SORT_OPTIONS = ["A - Z", "Most played", "Last played", "Recently added"]

NAME_PALETTE = [
    (76, 175, 80), (33, 150, 243), (156, 39, 176), (255, 152, 0),
    (233, 30, 99), (0, 150, 136), (63, 81, 181), (255, 87, 34),
]


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

    # 1) High-resolution shell icon (SHDefExtractIconW) — up to 256px.
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

    # 2) Fallback: classic ExtractIconEx.
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
            return (139, 92, 246)   # too dark -> fall back to accent violet
        scale = 225 / mx            # brighten so the colour pops
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


class GameLauncherApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1120x720")
        self.minsize(760, 520)

        self._apply_window_icon()

        self.games = load_games()
        self._ctk_images = {}
        self._cards = {}
        self._card_widgets = {}   # exe_key -> card frame
        self._card_vivids = {}    # exe_key -> (r, g, b) accent colour
        self._filter = ""
        self._sort_mode = SORT_OPTIONS[0]
        self._selection_mode = False
        self._selected = set()    # lowercase exe paths

        self._build_ui()
        self.refresh_grid()

    def _apply_window_icon(self):
        try:
            ico = resource_path("icon.ico")
            if os.path.exists(ico):
                self.iconbitmap(ico)
        except Exception:
            pass

    # ---------------- UI construction ----------------
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Top bar
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 6))
        top.grid_columnconfigure(1, weight=1)

        title_frame = ctk.CTkFrame(top, fg_color="transparent")
        title_frame.grid(row=0, column=0, sticky="w", padx=(0, 12))
        title = ctk.CTkLabel(
            title_frame, text=APP_TITLE, font=ctk.CTkFont(size=22, weight="bold")
        )
        title.grid(row=0, column=0, sticky="w")
        subtitle = ctk.CTkLabel(
            title_frame, text=APP_TAGLINE, font=ctk.CTkFont(size=12), text_color=ACCENT_SOFT
        )
        subtitle.grid(row=1, column=0, sticky="w")

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.on_search())
        search = ctk.CTkEntry(
            top, placeholder_text="Search games...", textvariable=self.search_var, width=200
        )
        search.grid(row=0, column=1, sticky="e", padx=(0, 8))

        self.sort_var = ctk.StringVar(value=SORT_OPTIONS[0])
        sort_menu = ctk.CTkOptionMenu(
            top, values=SORT_OPTIONS, variable=self.sort_var, command=self.on_sort,
            width=130, height=36, fg_color="#2a2d34", button_color="#3a3f47",
            button_hover_color="#4a5059",
        )
        sort_menu.grid(row=0, column=2, padx=(0, 8))

        # Remove-selected button (shown only in selection mode)
        self.btn_remove_sel = ctk.CTkButton(
            top, text="Remove Selected (0)", width=160, height=36,
            fg_color=DANGER, hover_color=DANGER_HOVER, command=self.remove_selected,
        )
        self.btn_remove_sel.grid(row=0, column=3, padx=(0, 8))
        self.btn_remove_sel.grid_remove()

        # Select toggle
        self.btn_select = ctk.CTkButton(
            top, text="Select", width=90, height=36,
            fg_color="transparent", border_width=1, border_color="#4a5059",
            hover_color="#3a3f47", text_color="#d1d5db", command=self.toggle_selection_mode,
        )
        self.btn_select.grid(row=0, column=4, padx=(0, 8))

        # Add game
        btn_add = ctk.CTkButton(
            top, text="+ Add Game", width=130, height=36,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, command=self.add_game,
        )
        btn_add.grid(row=0, column=5)

        # Grid area
        self.grid_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.grid_frame.grid(row=1, column=0, sticky="nsew", padx=16, pady=(4, 12))
        self.grid_frame.grid_columnconfigure(tuple(range(6)), weight=1, uniform="col")

        # Status bar
        self.status = ctk.CTkLabel(self, text="", anchor="w", font=ctk.CTkFont(size=12))
        self.status.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 8))

        # Context menu
        self.menu = Menu(self, tearoff=0)
        self.menu.add_command(label="Launch", command=self.menu_launch)
        self.menu.add_command(label="Toggle favourite", command=self.menu_favorite)
        self.menu.add_command(label="Rename", command=self.menu_rename)
        self.menu.add_command(label="Change path...", command=self.menu_change_path)
        self.menu.add_separator()
        self.menu.add_command(label="Remove", command=self.menu_remove)

    # ---------------- Grid rendering ----------------
    def _sorted_games(self, games):
        mode = self._sort_mode
        if mode == "Most played":
            key = lambda g: g.get("plays", 0)
            rev = True
        elif mode == "Last played":
            key = lambda g: g.get("last_played") or ""
            rev = True
        elif mode == "Recently added":
            key = lambda g: g.get("added") or ""
            rev = True
        else:  # "A - Z"
            key = lambda g: g.get("name", "").lower()
            rev = False
        favs = sorted([g for g in games if g.get("favorite")], key=key, reverse=rev)
        rest = sorted([g for g in games if not g.get("favorite")], key=key, reverse=rev)
        return favs + rest

    def refresh_grid(self):
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
            if query:
                text = "No games match your search."
            else:
                text = "No games yet\nClick \"+ Add Game\" to add your first game"
            empty = ctk.CTkLabel(
                self.grid_frame, text=text, font=ctk.CTkFont(size=16),
                text_color="#9ca3af", justify="center",
            )
            empty.grid(row=0, column=0, columnspan=6, pady=90)
            self._update_status()
            return

        cols = 6
        for i, game in enumerate(games):
            row, col = divmod(i, cols)
            card = self._make_card(game, i)
            card.grid(row=row, column=col, padx=6, pady=6, sticky="n")

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

        card = ctk.CTkFrame(
            self.grid_frame, corner_radius=14, fg_color=tint,
            border_width=2, border_color=tint,
        )
        card.grid_columnconfigure(0, weight=1)

        # Icon (real icon or letter tile)
        ctk_img = None
        if icon_path and os.path.exists(icon_path):
            try:
                pil = Image.open(icon_path).resize(
                    (CARD_ICON_SIZE, CARD_ICON_SIZE), Image.LANCZOS
                )
                ctk_img = ctk.CTkImage(
                    light_image=pil, dark_image=pil, size=(CARD_ICON_SIZE, CARD_ICON_SIZE)
                )
                self._ctk_images[index] = ctk_img
            except Exception:
                ctk_img = None

        if ctk_img:
            tile = ctk.CTkButton(
                card, image=ctk_img, text="", width=CARD_ICON_SIZE,
                height=CARD_ICON_SIZE, fg_color=plate, hover_color=tint_bright,
                corner_radius=12, command=lambda g=game: self._card_click(g),
            )
        else:
            letter = (name[:1] or "?").upper()
            tile = ctk.CTkButton(
                card, text=letter, width=CARD_ICON_SIZE, height=CARD_ICON_SIZE,
                font=ctk.CTkFont(size=42, weight="bold"),
                fg_color=rgb_hex(vivid), hover_color=tint_bright,
                text_color="white", command=lambda g=game: self._card_click(g),
            )
        tile.grid(row=0, column=0, padx=12, pady=(14, 6))

        # Name
        label = ctk.CTkLabel(
            card, text=name, width=CARD_ICON_SIZE + 24,
            font=ctk.CTkFont(size=13, weight="bold"), wraplength=CARD_ICON_SIZE + 20,
        )
        label.grid(row=1, column=0, padx=8, pady=(0, 4))
        label.bind("<Button-1>", lambda e, g=game: self._card_click(g))

        # Coloured accent underline
        underline = ctk.CTkFrame(card, width=44, height=3, corner_radius=2, fg_color=rgb_hex(vivid))
        underline.grid(row=2, column=0, pady=(0, 4))

        # Play count / last played
        plays = game.get("plays", 0)
        if plays:
            sub = f"\u25b6 {plays}"
            ago = time_ago(game.get("last_played"))
            if ago:
                sub += f"  \u00b7  {ago}"
        else:
            sub = "New"
        sublabel = ctk.CTkLabel(
            card, text=sub, width=CARD_ICON_SIZE + 24,
            font=ctk.CTkFont(size=11), text_color="#c7cad1",
        )
        sublabel.grid(row=3, column=0, padx=8, pady=(0, 12))

        # Favourite star (top-right badge)
        fav = bool(game.get("favorite"))
        star = ctk.CTkButton(
            card, text="\u2605" if fav else "\u2606", width=26, height=26,
            corner_radius=13, font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#20232b", hover_color=tint_bright,
            text_color=STAR_GOLD if fav else STAR_MUTED,
            command=lambda g=game: self.toggle_favorite(g),
        )
        star.place(relx=1.0, rely=0.0, anchor="ne", x=-4, y=4)

        for w in (tile, label, sublabel, card):
            w.bind("<Button-3>", lambda e, idx=index: self._show_menu(e, idx))

        self._card_widgets[exe_key] = card
        self._card_vivids[exe_key] = vivid
        self._cards[index] = card

        if exe_key in self._selected:
            self._set_card_selected(exe_key, True)
        return card

    # ---------------- Selection ----------------
    def _card_click(self, game):
        if self._selection_mode:
            self.toggle_select(game)
        else:
            self.launch_game(game)

    def toggle_selection_mode(self):
        self._selection_mode = not self._selection_mode
        if not self._selection_mode:
            self._selected.clear()
            for key in list(self._card_widgets):
                self._set_card_selected(key, False)
        self._update_action_bar()

    def toggle_select(self, game):
        key = game.get("exe", "").lower()
        if key in self._selected:
            self._selected.discard(key)
        else:
            self._selected.add(key)
        self._set_card_selected(key, key in self._selected)
        self._update_action_bar()

    def _set_card_selected(self, key, selected):
        card = self._card_widgets.get(key)
        if not card:
            return
        vivid = self._card_vivids.get(key, (124, 58, 237))
        tint = rgb_hex(blend(CARD_BASE, vivid, 0.30))
        if selected:
            card.configure(fg_color=CARD_SELECTED_BG, border_color=ACCENT)
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
            self.btn_select.configure(text="Done", border_color=ACCENT, text_color=ACCENT_SOFT)
            self.btn_remove_sel.configure(
                text=f"Remove Selected ({n})", state="normal" if n else "disabled"
            )
            self.btn_remove_sel.grid()
        else:
            self.btn_select.configure(text="Select", border_color="#4a5059", text_color="#d1d5db")
            self.btn_remove_sel.grid_remove()
        self._update_status()

    def _update_status(self):
        query = self._filter.strip().lower()
        if self._selection_mode:
            self.status.configure(
                text=f"Selection mode \u2014 {len(self._selected)} selected. Click games to toggle, then remove."
            )
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
            title="Select game executable", filetypes=[("Executable", "*.exe"), ("All files", "*.*")]
        )
        if path:
            g["exe"] = path
            g["icon"] = ""
            if not g.get("name"):
                g["name"] = name_from_exe(path)
            save_games(self.games)
            self.refresh_grid()

    def menu_remove(self):
        g = self._menu_game()
        if not g:
            return
        if messagebox.askyesno("Remove game", f'Remove "{g.get("name")}" from the launcher?'):
            self.games.pop(self._menu_index)
            save_games(self.games)
            self.refresh_grid()

    # ---------------- Search / sort ----------------
    def on_search(self):
        self._filter = self.search_var.get()
        self.refresh_grid()

    def on_sort(self, value):
        self._sort_mode = value
        self.refresh_grid()

    # ---------------- Favourites ----------------
    def toggle_favorite(self, game):
        game["favorite"] = not bool(game.get("favorite"))
        save_games(self.games)
        self.refresh_grid()

    # ---------------- Adding games ----------------
    def add_game(self):
        path = filedialog.askopenfilename(
            title="Select game executable", filetypes=[("Executable", "*.exe"), ("All files", "*.*")]
        )
        if not path:
            return
        if any(g.get("exe", "").lower() == path.lower() for g in self.games):
            messagebox.showinfo("Already added", f'"{path}" is already in the launcher.')
            return
        game = {
            "name": name_from_exe(path), "exe": path, "icon": "",
            "plays": 0, "last_played": None, "favorite": False,
            "added": datetime.now().isoformat(),
        }
        self.games.append(game)
        save_games(self.games)
        self.refresh_grid()

    # ---------------- Launching ----------------
    def launch_game(self, game):
        exe = game.get("exe", "")
        if not exe or not os.path.exists(exe):
            messagebox.showerror(
                "Not found",
                f"The executable could not be found:\n{exe}\n\nUse right-click \u2192 Change path to fix it.",
            )
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