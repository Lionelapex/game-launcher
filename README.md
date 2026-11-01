# 🎮 Game Launcher

A single-window launcher for all your PC games. Point it at a game's `.exe` — or auto-detect the main executable in a folder — and it shows up as a colourful, icon-labelled tile. Select a game to see its big picture, then Play. No more digging through folder trees.

![Game Launcher icon](icon_preview.png)

## Features

- **One launcher for every game** — add any game's `.exe` and it shows up in a tidy grid.
- **Auto-detect** — point at a folder and it finds the *main* game executable (skipping uninstallers, launchers and redistributables), so a whole game or a whole library can be added in one click.
- **Hero showcase** — single-click a game to select it and see its big picture, play stats, and a Play button.
- **Real game icons** — each tile pulls the game's actual icon (high-resolution, extracted straight from the executable).
- **Auto-naming** — games are named after their folder (e.g. `Dave the Diver`), not a raw filename.
- **Click to launch** — double-click a tile or press **Play** to run the game in its own folder.
- **Search** — filter your library instantly.
- **Favourites** — star your favourites; they're pinned to the top of the grid.
- **Play tracking** — see how many times you've played each game and when you last played it.
- **Sorting** — A–Z, most played, last played, or recently added.
- **Themes** — 8 colour palettes (Violet, Crimson, Ocean Blue, Emerald, Sunset, Rose, Gold, Teal).
- **Multi-select removal** — enter Select mode, tick several games, remove them in one go.
- **Right-click menu** — Launch, Favourite, Rename, Change path, or Remove any game.
- **Vibrant UI** — every tile is coloured from its game's own artwork.

## Download & Run (Windows)

1. Go to the [**Releases**](../../releases) page.
2. Download **`GameLauncher.exe`**.
3. Put it anywhere you like — it's **portable**, no install needed.
4. Double-click to run.

> **Windows SmartScreen:** because the app is unsigned, the first launch may show a "Windows protected your PC" prompt. Click **More info → Run anyway**. (Building it yourself from source below avoids this entirely.)

Your games list, icons and settings are saved in `%USERPROFILE%\.game_launcher\`, so they survive updates and moving the `.exe` around.

## Using it

1. Click **+ Add Game** and pick the game's `.exe` — or click **Auto Detect** and choose a game folder to add its main executable automatically.
2. Each game appears as a tile named after its folder, complete with its icon.
3. **Single-click** a tile to select it (shows its big picture in the hero panel); **double-click** or press **▶ Play** to launch.
4. Star a game (★ in the top-right of its tile) to pin it to the top of your library.
5. Use the dropdowns to change the **sort order** and the **theme color palette**.
6. To remove several at once: click **Select** → click the games to highlight them → **Remove Selected (N)**.

## Requirements

- Windows 10 or 11
- Nothing else — it's a single self-contained `.exe`.

## Building from source

```bash
# 1. Install Python 3.10+ and dependencies
pip install customtkinter Pillow pywin32 pyinstaller

# 2. (Optional) Regenerate the app icon
python make_icon.py

# 3. Build the .exe
pyinstaller --noconfirm --clean --onefile --windowed \
  --name GameLauncher --icon icon.ico --add-data "icon.ico;." \
  --collect-all customtkinter game_launcher.py

# Output: dist/GameLauncher.exe
```

## Project structure

| Path | Purpose |
|------|---------|
| `game_launcher.py` | The app — GUI, game management, icon extraction, auto-detect |
| `make_icon.py` | Generates `icon.ico` from scratch |
| `icon.ico` | App icon (violet gradient + gamepad) |
| `icon_preview.png` | Icon preview used in this README |

## Roadmap

- [ ] Import libraries from Steam / Epic / GOG
- [ ] Categories & tags
- [ ] Custom game art / covers (fetch box art from the web)

## License

[MIT](LICENSE)