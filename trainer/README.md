# Carmageddon 2 Trainer

A Frida-based runtime trainer for Carmageddon 2 (Steam build, `CARMA2_HW.EXE`).
**Re-enables the dev/edit mode that's broken on the Steam edition** via runtime
memory hooking — no binary patching, no save-file editing, no typed cheat codes.

The dev features themselves (damage cycler, credits ops, fly mode, edit mode,
camera cycler, etc.) are publicly documented in the [Carmashit cheat executable
article](https://razor.cwaboard.co.uk/2022/06/20/carmageddon-2-carmashit-cheat-executable-functions/)
and the [Carmageddon wiki](https://wiki.cwaboard.co.uk/wiki/Cheats). This trainer
just makes them accessible on Steam where the typed-code dispatcher is broken.

## What it does

- **Auto-start race** — skips menus, drops you straight into a race
- **One-click cheat firing** — fires any of the 94 cheat strings via hash
  injection (hooks `GetCheatInputHash` and overrides the hash buffer before
  `CheatDetect` reads it). No typing required.
- **21 dev cheat functions** wired to buttons, organized into 9 groups
  (cheat/advantage focused only — no debug, no visual settings):
  instant repair, damage cycler (god mode), timer freeze, teleport, credit
  ops (+/-2k/5k/set/max/drain), spawn any powerup, gravity toggle, gonad
  of death, unlock all 9 cameras (including unused Ped Cam / Drone Cam),
  HUD mode cycler, unlock all cars & races (menu cheat), force race end.
  All runtime-verified on the retail Steam binary.
- **Alt+Tab works normally** — game behaves like a standard Windows app (minimize on focus loss, restore on click, etc.)
- **Windowed mode** — dgVoodoo 2 starts the game windowed; press Alt+Enter in-game to toggle fullscreen
- **Pinnable favorites** — right-click any powerup to pin it to the Race tab
- **Friendly status text** — bottom of window shows "In Main menu" / "In race" etc.
- **Disabled-when-detached** — buttons grey out when the game isn't attached
- **Auto-detects game path** — searches Steam registry, running processes, common install paths
- **Bundles dgVoodoo 2** — auto-installs the Glide + DDraw wrapper for windowed mode and Alt+Tab support

## Run

```
py -3 trainer.py
```

Requires Python 3.10+, `frida`, `PySide6`. The game must be the Steam build
(`CARMA2_HW.EXE`, 2,680,320 bytes).

## Tabs

- **Race**
  - **RACE FLOW**: Auto-start race · Finish race · Enable cheat mode
  - **SPECIAL CHEATS**: Fly mode · Gonad of death (non-powerup actions)
  - **FAVORITES**: dynamic group of user-pinned powerups. Right-click any powerup in the Powerups tab to pin/unpin.
- **Dev cheats** — 21 cheat-focused features dispatched by setting `cheat_mode = 0xa11ee75d` at `[0x68b8e0]` and calling polled-table functions directly (bypassing the broken typed-code path on Steam). Groups: dev mode · player · credits · powerups · physics · cameras · display · main menu · utility. Live state for credits, damage, gravity, HUD mode. **Enable Dev Mode first** or nothing else fires.
- **Powerups** — grid of all 89 spawn-powerup cheats with search filter. Right-click for the pin/unpin context menu. Pinned powerups get a Carma-red border.
- **Status** — connection state, game path, dgVoodoo status, force-reattach button, and About text.

The top bar holds: connection state · Attach/Spawn · Detach.

## How it works under the hood

1. Frida attaches to `carma2_hw.exe` (or spawns it).
2. The agent installs an `Interceptor.attach` on `GetCheatInputHash` (`0x482f10`).
3. When the trainer fires a cheat, it arms a one-shot override: the next call to
   `GetCheatInputHash` returns our chosen `(h1, h2)` instead of the typed buffer.
4. The game's `CheatDetect` (`0x443c90`) sees a match against its 94-entry table at
   `0x590970` and dispatches the matching handler — exactly as if the user had
   typed the cheat string.

For menu navigation, the agent reimplements the click handler natively using
`NativeFunction` calls into the engine's `menu_cleanup`/`init`/`finalize`/`postfx`
chain — no `SendInput`, no fake mouse cursor.

To make Alt+Tab work, the agent blocks DirectInput from installing its
`WH_KEYBOARD_LL` low-level keyboard hook (which eats system keys like
Alt+Tab and Win before Windows can process them). It intercepts
`SetWindowsHookEx`, and when DINPUT.dll requests hook type 13
(`WH_KEYBOARD_LL`), it rewrites the hook type to an invalid value so the
real call fails, then overrides the NULL return with a fake handle so
DINPUT thinks the install succeeded. The game's keyboard still works via
the regular Windows message queue.

For windowed mode, the trainer bundles dgVoodoo 2, a modern Glide/DDraw
wrapper that translates the game's 3Dfx Glide and DirectDraw calls to
Direct3D 11. dgVoodoo handles Alt+Enter (fullscreen toggle), windowed
rendering, and focus-loss events natively. Its DDraw.dll wrapper also
prevents the game from entering exclusive display mode, which would
otherwise suppress system hotkeys.

## Files

```
trainer/
├── trainer.py             entry point
├── deps/
│   └── dgvoodoo/          bundled dgVoodoo 2 v2.87.1
│       ├── Glide.dll      Glide → D3D11 wrapper
│       ├── Glide2x.dll    Glide → D3D11 wrapper
│       ├── Glide3x.dll    Glide → D3D11 wrapper
│       ├── DDraw.dll      DDraw → D3D11 wrapper (prevents exclusive mode)
│       ├── dgVoodoo.conf  pre-tuned config (windowed, no watermark)
│       └── dgVoodooCpl.exe control panel for runtime configuration
├── backend/
│   ├── agent.js           Frida script: cursor release, WH_KEYBOARD_LL
│   │                      blocker (alt-tab fix), dinput non-exclusive,
│   │                      cheat hash injection, menu click reimpl,
│   │                      dev cheat RPCs (21)
│   ├── frida_core.py      Carma2Backend (spawn/attach/detach, _rpc() wrapper,
│   │                      auto_start_race, EXE verify, ensure_dgvoodoo)
│   ├── cheat_db.py        94-entry cheat table (embedded, no binary needed)
│   ├── dev_actions.py     Declarative registry of all 21 dev cheat actions
│   │                      with metadata (group, kind, requires, state_key)
│   ├── diag_focus.py      (diagnostic template, not used at runtime)
│   └── diag_messages.py   (diagnostic template, not used at runtime)
└── ui/
    ├── main_window.py     QMainWindow, tabs, top bar, snap poller
    ├── bridge.py          Qt<->Frida thread bridge, named signals, worker thread,
    │                      _safe_call helper, dev_call dispatcher
    ├── style.py           Dark Carma-red QSS theme
    ├── tab_race.py        Race control buttons + pinnable favorites
    ├── tab_dev.py         Dev cheats tab — generic widget factory driven by
    │                      dev_actions registry; live state from snap_updated
    ├── tab_powerups.py    89-button grid w/ search filter
    └── tab_status.py      Connection + game path + wrapper status + about
```

## Adding new cheats

When new cheat strings get reverse-engineered, just add them to
`carma2_tools/hash_function.py:KNOWN_CHEATS`. The trainer picks them up
automatically — `cheat_db.py` joins on `(h1, h2)`.

## Persistent settings

Stored via `QSettings('carma2_tools', 'trainer')` (Windows registry):
- `geometry` — window position/size
- `favorites` — list of pinned cheat names
- `game_exe` — auto-detected game path

## Adding a new dev cheat

1. Add the function VA to `agent.js` `DEV` constants block
2. Add an RPC export in `agent.js` `rpc.exports`
3. Add a thin Python wrapper in `frida_core.py` (one liner via `_rpc()`)
4. Add an `Action(...)` row to `dev_actions.py`
5. Restart the trainer — the DevTab picks it up automatically (no UI code)

## Credits & sources

The dev/edit mode features exposed by this trainer are documented publicly:

- [Carmashit cheat executable functions](https://razor.cwaboard.co.uk/2022/06/20/carmageddon-2-carmashit-cheat-executable-functions/) — razor.cwaboard.co.uk — the definitive documentation of Carma2's dev mode (Carmashit was a mid-development build with all edit modes pre-enabled).
- [Carmageddon wiki (cwaboard)](https://wiki.cwaboard.co.uk/wiki/Cheats) — cheat strings, effects, controls.
- [Carmageddon fandom wiki](https://carmageddon.fandom.com/) — features, camera modes, Wrecks Gallery, unused content.
- [Unused content from Carmageddon II](https://wiki.cwaboard.co.uk/wiki/Unused_content_from_Carmageddon_II:_Carpocalypse_Now) — Ped Cam / Drone Cam references.

**What this project adds on top:**
- Re-enables the dev mode on the retail Steam edition (where the typed-code
  path is broken per community reports — GOG edition works normally).
- Runtime-verified memory addresses for the Steam binary
  (MD5 `66a9c49483ff4415b518bb7df01385bd`).
- Hash injection technique for one-click cheat firing without typing.
- Bundles dgVoodoo 2 for proper windowed mode, Alt+Tab, and Alt+Enter support.
- PySide6 GUI organized into 9 dev cheat groups with live state display.
