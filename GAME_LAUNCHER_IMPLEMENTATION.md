# GAME_LAUNCHER_IMPLEMENTATION.md

Implementation report for the **v2.0 premium redesign**. This document is
deliberately blunt about what is fully done, partially done, depends on
hardware, or is known-limited — nothing is claimed as working unless tested.

## 1. Summary

The launcher was rebuilt from a single-pane grid into a **three-pane gaming
dashboard** with live hardware monitoring, Steam library import, artwork-based
cards, a featured banner, Favourites / Recently Played views, and a purple
design system — while preserving existing games, storage format, detection and
launching.

## 2. Modified / new files

| File | Status | Purpose |
|---|---|---|
| `game_launcher.py` | Rewritten (v2.0) | App shell, 3-pane UI, library, featured banner, details, launch, session tracking |
| `monitoring.py` | **New** | Hardware monitoring service (CPU/RAM/GPU/storage) |
| `steam_import.py` | **New** | Steam VDF parsing, installed-game discovery, artwork fetch/cache |
| `GAME_LAUNCHER_AUDIT.md` | **New** | Pre-redesign audit |
| `GAME_LAUNCHER_IMPLEMENTATION.md` | **New** | This report |
| `README.md` | Updated | Documents v2.0 features |
| `requirements.txt` | Updated | Adds `psutil`, `nvidia-ml-py` |
| `game_launcher_v1_backup.py` | Removed before commit | v1.2 retained in git history (`1eac774`) |

## 3. Fully implemented & tested

- **Three-pane shell** — sidebar (220 px) + central library + right system/details panel (300 px). Verified the app boots and renders all panels.
- **Design system** — centralised purple/navy colour tokens; consistent panels, rounded cards, borders.
- **Featured banner** — shows the selected game with hero artwork (if imported from Steam) or a centred icon on a colour backdrop, plus title, install status, play count, last-played, Play / Open Folder / Remove.
- **Artwork-based cards** — Steam cover art centre-cropped; otherwise the extracted exe icon centred on a deterministic colour; letter fallback. Favourite star, play count, double-click to launch, right-click context menu.
- **Live hardware monitoring (real data)** — verified against this host:
  - CPU: `Intel(R) Core(TM) i5-9600KF @ 3.70GHz`, live utilisation, clock, 6 cores / 6 threads.
  - RAM: live used/total/percent (24 GB total observed).
  - GPU: model via WMI (`AMD Radeon RX 6800`), utilisation/temp/VRAM via NVML when NVIDIA.
  - Storage: per-volume drive letter, label, free/total, usage (6 volumes detected; EFI/DVD partitions < 1 GB filtered out).
- **Steam library import** — parses `libraryfolders.vdf` + `appmanifest_*.acf`, detects the main exe per install, de-dupes, then fetches cover + hero artwork (cached). Verified against this machine: found **eFootball™, The Forest, Crimson Desert Enhanced** and correctly resolved each main exe (e.g. `Crimson Desert\bin64\CrimsonDesert.exe`).
- **Main-executable detection fix** — a whole-tree `find_main_exe()` now picks the real game (e.g. `eFootball.exe`, 353 MB) over tools (`Settings.exe`, 0.5 MB) by penalising settings/config/launcher names.
- **Views / filters** — Library, Favourites, Recently Played; verified counts.
- **Sorting** — A–Z, Z–A, Recently added, Recently played, Most played, Least played; verified.
- **Search** — filters by name, executable filename and folder.
- **Favourites**, **multi-select removal** (with confirmation; game files untouched), **right-click menu** (Launch/Favourite/Rename/Change path/Open folder/Remove).
- **Session playtime** — launch records the child PID; a 5 s poll adds elapsed time to `total_seconds` when the process exits; persisted.
- **Theme accents** — 6 palettes; changing recolours accents and persists.
- **Data preservation** — reads v1 `games.json` unchanged (defaults via `.get`).

## 4. Partially implemented

- **Animations** — CustomTkinter provides hover/fade on buttons, but there is **no** card hover-scaling, skeleton loaders, animated progress or slide transitions. Not implemented.
- **Circular gauges** — CPU/RAM/GPU use horizontal progress bars, not circular gauges (CustomTkinter has no native arc widget). Storage uses horizontal bars as specified.
- **List view** — grid only; list mode not implemented.
- **Settings panel** — theme selector only; no full settings screen for scan dirs / refresh interval / startup.
- **Game directories manager** — Auto Detect scans a chosen folder on demand; there is no persistent watched-directory list UI yet.
- **Artwork** — automatic Steam CDN artwork only; no manual "set custom artwork" action. Non-Steam games fall back to the exe icon.
- **Toasts** — uses modal message boxes instead of non-blocking toast notifications.
- **Typography** — Inter / Rajdhani are specified, but are only used if installed on the host; otherwise Tk falls back to system fonts (Segoe UI).

## 5. Requires additional hardware / driver support

- **CPU temperature** — not available without a low-level driver; shown as unavailable.
- **GPU utilisation / temperature / VRAM** — available only on **NVIDIA** GPUs via NVML. On **AMD / Intel** these read **unavailable** (this host is an AMD RX 6800). The GPU *model* is always shown via WMI. AdapterRAM from WMI proved unreliable on this host and is not displayed.

## 6. Known limitations

- Session playtime tracks the **direct child process**. If a game re-launches itself through a launcher that exits early, playtime can be under-counted.
- Steam import relies on `appmanifest` + `installdir`; games with unusual layouts may need "Change path…".
- Artwork requires internet on first import; offline imports fall back to icons and still work.
- Rendering was **not visually verified against the reference image**: this environment has no vision model configured, so a pixel-level comparison could not be performed. Functional verification was done programmatically (panel construction, state changes, real hardware readouts).
- No unit-test suite; verification was via scripted smoke tests + launching the built `.exe`.

## 7. New dependencies

- `psutil` — CPU / RAM / disk metrics.
- `nvidia-ml-py` (`pynvml`) — NVIDIA GPU utilisation / temperature / VRAM (optional at runtime).
- Existing: `customtkinter`, `Pillow`, `pywin32`, `pyinstaller`.

## 8. Tests performed

| Test | Result |
|---|---|
| App builds (PyInstaller onefile windowed) | ✅ |
| Built `.exe` launches and stays running | ✅ (two processes, ~67 MB) |
| Three-pane GUI instantiates; featured + details render | ✅ |
| Cards render from injected games | ✅ |
| Views: favourites=1, recent=2 | ✅ |
| Sort "Most played" → top = Hades (50) | ✅ |
| Theme switch → accent changes | ✅ |
| Selection mode → "Remove (1)" → exit clears | ✅ |
| `find_main_exe(eFootball)` → `eFootball.exe` | ✅ |
| `detect_games(eFootball folder)` → `eFootball.exe` | ✅ |
| Steam discovery → 3 games, correct exes | ✅ |
| Monitoring: CPU `/` RAM `/` GPU model / 6 storage volumes | ✅ real values |

## 9. Build

```bash
pip install customtkinter Pillow pywin32 pyinstaller psutil nvidia-ml-py
pyinstaller --noconfirm --clean --onefile --windowed --name GameLauncher \
  --icon icon.ico --add-data "icon.ico;." --collect-all customtkinter \
  --hidden-import psutil --hidden-import pynvml \
  --hidden-import win32com --hidden-import win32com.client \
  --hidden-import win32api --hidden-import win32gui \
  --hidden-import win32ui --hidden-import win32con game_launcher.py
```
