# Carmageddon 2 Trainer

A Frida-based runtime trainer for Carmageddon 2 (Steam build, `CARMA2_HW.EXE`).
Hooks the live game and calls its internal cheat dispatcher directly — no key
simulation, no save-file editing, no game-file modification.

## What it does

- **Auto-start race** — skips menus, drops you straight into a race
- **Fire any cheat** — all 94 cheat strings are known. Every powerup effect
  is documented (0 unknowns remaining).
- **46 hidden dev cheats** (2026-04-10) — discovered via static analysis +
  autonomous Frida probing. Includes instant repair, damage cycler (god mode),
  credit ops (+/- 2k/5k or set arbitrary), teleport, gravity toggle, timer
  freeze, HUD/MiniMap toggles, spectator camera, lock-on targeting, checkpoint
  finder, upgrade purchases, camera mode unlock (9 modes including Ped Cam
  and Drone Cam), powerup spawner, and more. See "Dev cheats" tab.
- **No minimize on alt-tab** — game stays visible when you switch windows
- **Windowed-mode toggle** — Ctrl+Shift+W global hotkey, in-bar button, or auto-on-spawn checkbox
- **Pinnable favorites** — right-click any powerup to pin it to the Race tab
- **Friendly status text** — bottom of window shows "In Main menu" / "In race" etc.
- **Disabled-when-detached** — buttons grey out when the game isn't attached
- **Advanced/Developer mode** — opt-in toggle to expose the full cheat table + live debug state

## Run

```
py -3 trainer.py
```

Requires Python 3.10+, `frida`, `PySide6`. Game must be the Steam build at the
canonical path (`C:\Program Files (x86)\Steam\steamapps\common\Carmageddon2`).

For debug logs, run from a terminal — every action is mirrored to stderr.

**Global hotkey:** `Ctrl+Shift+W` toggles nGlide windowed/fullscreen mode at any
time, regardless of which window has focus.

## Tabs

- **Race**
  - **RACE FLOW**: Auto-start race · Finish race · Enable cheat mode
  - **SPECIAL CHEATS**: Fly mode · Gonad of death (non-powerup actions, can't be reached from the Powerups tab)
  - **FAVORITES**: dynamic group of user-pinned powerups. First-run defaults: Turbo, Instant repair, Credit bonus, Solid granite car, Lunar gravity. Right-click any powerup in the Powerups tab to pin/unpin.
- **Dev cheats** *(2026-04-10)* — 46 hidden developer features dispatched by setting `cheat_mode = 0xa11ee75d` and calling polled-table functions directly. Groups: dev mode toggle · player actions · credits ops · powerups spawner · movement · opponents cycler · spectator camera · HUD/display · sound · misc · experimental. Live state for credits, damage state, gravity, HUD mode, spectator state. **Enable Dev Mode first** or nothing else fires. Some features need true in-race state.
- **Powerups** — grid of all 89 spawn-powerup cheats with search filter. Right-click for the pin/unpin context menu. Pinned powerups get a Carma-red border.
- **Status** — connection state, force-reattach, About text, and an **Advanced / developer mode** toggle.
- **All cheats** *(only visible in Advanced mode)* — full 94-entry table view with handler/arg columns. Click a row + FIRE button, or double-click any row to fire instantly.

The top bar holds: connection state · Attach/Spawn · Detach · "Start in windowed" checkbox · "Windowed ⇄" runtime toggle button.

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

To stop the game minimizing on alt-tab, the agent hooks `RegisterClass[Ex]A/W`
at startup, captures the game's `lpfnWndProc`, and `Interceptor.attach`es it.
On every WndProc call it inspects the message; deactivation messages
(`WM_ACTIVATEAPP wParam=FALSE`, `WM_ACTIVATE WA_INACTIVE`, `WM_NCACTIVATE
wParam=FALSE`, `WM_KILLFOCUS`) get rewritten to `WM_NULL` so the game's switch
falls through and never triggers its display-mode tear-down.

For the windowed-mode toggle, the agent captures nGlide's `WH_KEYBOARD` hook
proc address (installed via `SetWindowsHookExA` from `glide2x.dll`) and
disassembles it to extract the two memory addresses nGlide flips to request a
mode switch (`TOGGLE_PENDING` and `TOGGLE_FLAG`). At toggle time the trainer
just writes those addresses directly — bypassing every guard check inside the
hook proc and avoiding any synthetic input. nGlide's render thread picks up
the flipped flag next frame and performs the actual mode switch.

## Files

```
trainer/
├── trainer.py             entry point (PySide6 app)
├── backend/
│   ├── agent.js           Frida script: input release, dinput non-exclusive,
│   │                      no-minimize WndProc subclass, nGlide windowed toggle,
│   │                      cheat hash injection, menu click reimpl,
│   │                      dev cheat RPCs (46)
│   ├── frida_core.py      Carma2Backend (spawn/attach/detach, RPC wrappers,
│   │                      adaptive auto_start_race, dev cheat methods)
│   ├── cheat_db.py        Loads the 94-entry cheat table from carma2hw.bin
│   ├── dev_actions.py     Declarative registry of all 46 dev cheat actions
│   │                      with metadata (group, kind, requires, state_key)
│   ├── diag_focus.py      Diagnostic template: log window-state Win32 calls
│   └── diag_messages.py   Diagnostic template: log activation messages + WndProc
└── ui/
    ├── main_window.py     QMainWindow, tabs, top bar, hotkey, snap poller
    ├── bridge.py          Qt<->Frida thread bridge, named signals, worker thread,
    │                      _safe_call helper, dev_call dispatcher
    ├── style.py           Dark Carma-red QSS theme
    ├── tab_race.py        Race control buttons
    ├── tab_dev.py         Dev cheats tab — generic widget factory driven by
    │                      dev_actions registry; live state from snap_updated
    ├── tab_powerups.py    89-button grid w/ search filter
    ├── tab_cheats.py      Full table view, click row + FIRE to trigger
    └── tab_status.py      Connection + live state + about
```

## Adding new cheats

When new cheat strings get reverse-engineered, just add them to
`carma2_tools/hash_function.py:KNOWN_CHEATS`. The trainer picks them up
automatically — `cheat_db.py` joins on `(h1, h2)`.

If a powerup's effect description is missing from `POWERUP.TXT` (shows up as
`'n/a'`), add a friendly override to `cheat_db.py:KNOWN_EFFECTS` keyed by
powerup id. Example: `0: 'Credit bonus'` (for the WETWET cheat).

## Persistent settings

Stored via `QSettings('carma2_tools', 'trainer')` (Windows registry):
- `geometry` — window position/size
- `advanced` — Advanced/Developer mode toggle
- `favorites` — list of pinned cheat names

## Adding a new dev cheat

1. Add the function VA to `agent.js` `DEV` constants block
2. Add an RPC export in `agent.js` `rpc.exports`
3. Add a thin Python wrapper in `frida_core.py` (one liner)
4. Add an `Action(...)` row to `dev_actions.py`
5. Restart the trainer — the DevTab picks it up automatically (no UI code)

For features that read/write a state variable, also add the field to the
compound `snap()` in `agent.js` so the live label updates.
