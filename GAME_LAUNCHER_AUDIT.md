# GAME_LAUNCHER_AUDIT.md

Technical audit of the Game Launcher **before** the v2.0 redesign, plus the
redesign architecture and the compatibility risks considered.

## 1. Existing architecture (pre-redesign)

| Aspect | Detail |
|---|---|
| Language | Python 3.11 |
| UI framework | CustomTkinter (Tkinter wrapper) |
| Packaging | PyInstaller `--onefile --windowed`, single `GameLauncher.exe` |
| Platform | Windows 10/11 |
| Entry point | `game_launcher.py` → `main()` → `GameLauncherApp(ctk.CTk)` |
| Icon extraction | `pywin32` (`SHDefExtractIconW` → `ExtractIconEx` fallback), drawn to a PIL bitmap at 256 px |
| Imaging | Pillow (icon caching, letter-tile fallback, dominant-colour sampling) |
| Persistence | JSON files under `%USERPROFILE%\.game_launcher\` |

## 2. Existing modules (pre-redesign)

v1.x was a **single file** (`game_launcher.py`, ~725 lines) containing UI,
storage, icon extraction, colour helpers, detection and launching. v2.0 splits
this into:

- `game_launcher.py` — app shell, UI, library, featured banner, details, launch.
- `monitoring.py` — hardware monitoring service (NEW).
- `steam_import.py` — Steam discovery + artwork (NEW).

## 3. Existing game-detection workflow

- **Auto Detect** (`detect_games(folder)`): walks a folder tree, filters
  non-game executables by filename substrings (`unins`, `setup`, `redist`,
  `vcredist`, `crash`, `settings`, …), groups candidates by their game root
  (handling `bin/`, `bin64/`, `win64/` structure folders), and scores each exe
  by name-match with the game folder, depth and file size to pick one main exe
  per game.
- **Add Game**: manual file-picker to a specific `.exe`.
- No persistent scan-directory list; scanning is one-shot per invocation.

## 4. Existing game-launching workflow

`subprocess.Popen([exe], cwd=os.path.dirname(exe))` — launched in its own
folder so games that resolve assets relative to their working directory work.
Launching incremented `plays` and stamped `last_played`.

## 5. Existing data storage

- `games.json` — list of `{name, exe, icon, plays, last_played, favorite, added, total_seconds, appid?}`.
- `settings.json` — `{theme}`.
- `icons/<md5(exe)>.png` — cached 256 px icon.
- `artwork/<appid>_cover.jpg` / `_hero.jpg` — cached Steam artwork (v2.0).
- No database; JSON is human-editable and survives updates.

## 6. Current UI structure

- **v1.x:** single pane — top bar (search, sort, theme, add/detect/select),
  a hero panel for the selected game, and a 6-column grid of coloured game cards.
- **v2.0 (this redesign):** three-pane dashboard — left navigation sidebar,
  central library (featured banner + cards), right-hand system + details panel.

## 7. Identified limitations (pre-redesign)

1. No hardware/system monitoring of any kind.
2. No Steam integration; games had to be added individually or via folder scan.
3. Grid only — no list view.
4. No artwork beyond the exe icon; steam games had no cover art.
5. No true "recently played" view (only a sort).
6. No session playtime; only a launch counter.
7. No persistent scan-directory manager or settings screen.
8. Visual design was functional but not "premium"; limited colour depth.

## 8. Proposed redesign architecture

- **Design system** — centralised colour tokens (purple gaming palette),
  reusable card/panel builders.
- **Shell** — `CTk` window with a 3-column grid: sidebar (220 px) / centre
  (weight 1) / right panel (300 px).
- **Services** — `monitoring.collect()` (psutil + WMI + optional NVML) and
  `steam_import` (VDF parser + artwork). Both isolated from UI code.
- **Non-blocking** — hardware polling runs on `after()` ticks (2 s); Steam
  import + artwork download run on a worker thread and hand back to the UI thread.
- **Preserved** — `detect_games`, icon extraction, launching, JSON storage,
  favourites, sorting, search, multi-select removal.

## 9. Implementation plan

1. Design tokens + shell (sidebar / centre / right). ✅
2. Featured banner using hero artwork or icon fallback. ✅
3. Artwork-based cards (cover crop / icon on colour). ✅
4. Right panel: live CPU / RAM / GPU / storage. ✅
5. Selected-game details. ✅
6. Steam import + artwork caching. ✅
7. Session playtime tracking. ✅
8. Views (Library / Favourites / Recently Played) + filters + sorting. ✅
9. Remove v1 style, keep entry point + build command. ✅

## 10. Compatibility risks & mitigations

| Risk | Mitigation |
|---|---|
| Existing `games.json` records lack new fields | All reads use `.get(key, default)`, so v1 records load unchanged and are upgraded on next save. |
| GPU metrics unavailable on AMD/Intel | NVML is used only if an NVIDIA GPU initialises; otherwise util/temp/VRAM show **unavailable** (never faked). |
| NVML init failing repeatedly | Initialised once and memoised; never retried after failure. |
| Steam not installed / VDF format drift | VDF parser is tolerant; import reports zero games instead of crashing. |
| Artwork download offline | All downloads wrapped in try/except with short timeouts; falls back to the exe icon. |
| Blocking UI on hardware queries | psutil calls are milliseconds; reported on 2 s `after()` ticks. Steam import + artwork run off-thread. |
| PyInstaller missing new deps | Build adds `--hidden-import psutil/pynvml/win32com/win32api/win32gui/win32ui/win32con`. |
| Removing games deletes files | Removal only edits `games.json`; message box states game files are NOT deleted. |
