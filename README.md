# 🎮 Game Launcher

A premium, purple-themed **desktop gaming dashboard** for Windows. Browse your library as artwork cards, see a cinematic featured game, monitor live CPU / RAM / GPU / storage, and import your whole **Steam** library in one click — all from a single portable `.exe`.

![Game Launcher icon](icon_preview.png)

## v2.0 — Premium dashboard

- **Three-pane layout** — navigation sidebar · game library · live system panel.
- **Featured game banner** — big artwork, install status, play stats and Play button for the selected game.
- **Artwork cards** — Steam cover art (centre-cropped) or the game's own icon, with favourite star and play count.
- **Live hardware monitoring** — real CPU utilisation/clock/cores, RAM usage, GPU model (+ utilisation/temp/VRAM on NVIDIA), and per-drive storage. Never simulated.
- **Steam library import** — reads Steam's library folders and manifests (works offline), detects each game's main executable, fetches cover + hero artwork, and de-dupes.
- **Views** — Library, Favourites, Recently Played.
- **Session playtime** — tracks time played per launch and totals it.

## Features

- **One launcher for every game** — add a game's `.exe`, auto-detect it from a folder, or import Steam.
- **Auto-detect** — finds the *main* game executable in a folder (skips uninstallers, launchers, settings tools, redistributables).
- **Real game icons** — high-resolution icon extracted straight from each executable.
- **Auto-naming** — games are named after their folder (e.g. `Dave the Diver`).
- **Launch** — double-click a card or press Play; the game runs in its own folder.
- **Search** — filters by title, executable filename and path.
- **Favourites**, **sorting** (A–Z / Z–A / recently added / recently played / most / least played), **multi-select removal** (game files are never deleted), **right-click menu**.
- **Themes** — 6 accent palettes (Violet, Blue, Emerald, Crimson, Amber, Cyan); purple by default.
- **Portable & offline-first** — one `.exe`, no install; everything works without internet (artwork falls back to icons when offline).

## Download & Run (Windows)

1. Go to the [**Releases**](../../releases) page.
2. Download **`GameLauncher.exe`**.
3. Put it anywhere you like — it's **portable**, no install needed.
4. Double-click to run.

> **Windows SmartScreen:** because the app is unsigned, the first launch may show a "Windows protected your PC" prompt. Click **More info → Run anyway**.

Your games, icons, artwork and settings live in `%USERPROFILE%\.game_launcher\`, so they survive updates and moving the `.exe`.

## Using it

1. **Add games** with `+ Add Game` (pick an `.exe`), `Auto Detect` (pick a game folder), or `Steam Import` (import everything installed in Steam).
2. **Single-click** a card to select it (it becomes the featured game); **double-click** or press **▶ Play** to launch.
3. Use the sidebar to switch between **Library**, **Favourites** and **Recently Played**.
4. Watch live **CPU / RAM / GPU / storage** in the right-hand panel.
5. Star a game to favourite it. Right-click any card for Launch / Favourite / Rename / Change path / Open folder / Remove.
6. To remove several: sidebar → **Select / Remove** → click games → **Remove (N)**.

## Requirements

- Windows 10 or 11
- Nothing else — it's a single self-contained `.exe`.

## Hardware monitoring notes

- **CPU / RAM / storage** — always available (via `psutil`).
- **GPU model** — via WMI, all brands.
- **GPU utilisation / temperature / VRAM** — only on **NVIDIA** GPUs (via NVML). On AMD / Intel these show **unavailable** rather than a fabricated number. CPU temperature is likewise unavailable without a driver.

## Building from source

```bash
# 1. Install Python 3.10+ and dependencies
pip install customtkinter Pillow pywin32 pyinstaller psutil nvidia-ml-py

# 2. (Optional) Regenerate the app icon
python make_icon.py

# 3. Build the .exe
pyinstaller --noconfirm --clean --onefile --windowed --name GameLauncher \
  --icon icon.ico --add-data "icon.ico;." --collect-all customtkinter \
  --hidden-import psutil --hidden-import pynvml \
  --hidden-import win32com --hidden-import win32com.client \
  --hidden-import win32api --hidden-import win32gui \
  --hidden-import win32ui --hidden-import win32con game_launcher.py

# Output: dist/GameLauncher.exe
```

## Project structure

| Path | Purpose |
|------|---------|
| `game_launcher.py` | App shell, three-pane UI, library, featured banner, details, launch |
| `monitoring.py` | Hardware monitoring service (CPU / RAM / GPU / storage) |
| `steam_import.py` | Steam VDF parsing, game discovery, artwork fetch/cache |
| `make_icon.py` | Generates `icon.ico` from scratch |
| `icon.ico` / `icon_preview.png` | App icon + preview |
| `GAME_LAUNCHER_AUDIT.md` | Architecture audit of the pre-redesign app |
| `GAME_LAUNCHER_IMPLEMENTATION.md` | v2.0 implementation report (done / partial / limited) |

## Roadmap

- [ ] Epic / GOG library import
- [ ] Categories & tags
- [ ] List view + custom artwork picker
- [ ] Settings screen (scan directories, refresh interval, startup)
- [ ] Circular gauges and card hover animations

## License

[MIT](LICENSE)