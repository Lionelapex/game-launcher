"""
Steam library import for Game Launcher.
Reads Steam's libraryfolders.vdf + appmanifest_*.acf files (no Steam API
required, works offline) to discover installed games, and (optionally) pulls
cover/banner artwork from Steam's public CDN, cached locally.
"""

import os
import urllib.request
from pathlib import Path

ARTWORK_DIR = Path.home() / ".game_launcher" / "artwork"
STEAM_IMG = "https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/{name}"

SKIP_NAME_PARTS = ("redistribut", "steamworks", "server", "workshop",
                   "common redist", "dedicated", "controller", "vr", "tool")


def default_steam_path():
    for p in (r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"):
        if os.path.isdir(p):
            return p
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")
        v, _ = winreg.QueryValueEx(k, "InstallPath")
        winreg.CloseKey(k)
        return v
    except Exception:
        return None


def parse_vdf(text):
    """Parse a Valve VDF document into nested dicts (string leaves only)."""
    i, n = 0, len(text)

    def skip_ws():
        nonlocal i
        while i < n and text[i] in " \t\r\n":
            i += 1

    def parse_value():
        nonlocal i
        skip_ws()
        if i >= n:
            return None
        c = text[i]
        if c == '"':
            i += 1
            buf = []
            while i < n and text[i] != '"':
                if text[i] == "\\" and i + 1 < n:
                    buf.append(text[i + 1]); i += 2
                else:
                    buf.append(text[i]); i += 1
            i += 1
            return "".join(buf)
        if c == "{":
            return parse_object()
        i += 1
        return parse_value()

    def parse_object():
        nonlocal i
        obj = {}
        skip_ws()
        if i < n and text[i] == "{":
            i += 1
        while True:
            skip_ws()
            if i >= n or text[i] == "}":
                if i < n:
                    i += 1
                break
            key = parse_value()
            if key is None:
                break
            val = parse_value()
            obj[key] = val
        return obj

    return parse_object()


def get_library_folders(steam_path=None):
    steam_path = steam_path or default_steam_path()
    if not steam_path:
        return []
    lf = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
    if not os.path.exists(lf):
        return []
    try:
        data = parse_vdf(open(lf, encoding="utf-8", errors="replace").read())
    except Exception:
        return []
    folders = (data or {}).get("libraryfolders", {})
    paths = []
    for key, entry in folders.items():
        if isinstance(entry, dict) and entry.get("path"):
            if entry["path"] not in paths:
                paths.append(entry["path"])
    return paths


def get_installed_games(steam_path=None):
    """Return list of {appid, name, install_path} for installed Steam games."""
    results = []
    for lib in get_library_folders(steam_path):
        apps_dir = os.path.join(lib, "steamapps")
        if not os.path.isdir(apps_dir):
            continue
        for f in os.listdir(apps_dir):
            if not (f.startswith("appmanifest_") and f.endswith(".acf")):
                continue
            try:
                data = parse_vdf(open(os.path.join(apps_dir, f), encoding="utf-8", errors="replace").read())
            except Exception:
                continue
            st = (data or {}).get("AppState", {})
            name = (st.get("name") or "").strip()
            installdir = (st.get("installdir") or "").strip()
            appid = st.get("appid") or ""
            low = name.lower()
            if any(s in low for s in SKIP_NAME_PARTS):
                continue
            if not installdir:
                continue
            install_path = os.path.join(lib, "steamapps", "common", installdir)
            results.append({"appid": appid, "name": name, "install_path": install_path})
    return results


def fetch_steam_artwork(appid):
    """Download Steam cover + hero art, cached. Returns {'cover': path, 'hero': path} or {}."""
    if not appid:
        return {}
    try:
        ARTWORK_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        return {}

    def _get(name, dest):
        url = STEAM_IMG.format(appid=appid, name=name)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "GameLauncher/2.0"})
            data = urllib.request.urlopen(req, timeout=8).read()
        except Exception:
            return None
        if len(data) < 4096:      # Steam returns a tiny placeholder for missing art
            return None
        path = ARTWORK_DIR / f"{appid}_{dest}"
        try:
            path.write_bytes(data)
            return str(path)
        except Exception:
            return None

    cover = _get("library_600x900_2x.jpg", "cover.jpg")
    hero = _get("library_hero.jpg", "hero.jpg") or _get("header.jpg", "header.jpg")
    return {"cover": cover, "hero": hero}