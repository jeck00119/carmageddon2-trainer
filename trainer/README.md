# Carmageddon 2 Trainer

A GUI trainer for Carmageddon 2 (Steam edition) that re-enables the built-in
developer mode which is broken on the Steam build.

Built as an **educational project** exploring runtime game modding with
[Frida](https://frida.re/) (dynamic instrumentation) and
[PySide6](https://doc.qt.io/qtforpython-6/) (Qt GUI).

## Features

- **21 dev cheats** in a click-friendly GUI — instant repair, god mode, timer freeze,
  teleport, credit editing, spawn any powerup, gravity toggle, unlock all cameras,
  HUD cycler, unlock all cars & races, and more
- **One-click cheat firing** — all 94 known cheat codes available without typing
- **Windowed mode + Alt+Tab** — game runs as a normal Windows app
  (press Alt+Enter to toggle fullscreen)
- **Auto-start race** — skip menus, jump straight into gameplay
- **Pinnable favorites** — right-click any powerup to pin it for quick access
- **Auto-detects game path** from Steam

## Quick start

```bash
pip install frida frida-tools PySide6
py -3 trainer.py
```

Click **Attach / Spawn game** to launch Carmageddon 2. The trainer
auto-installs [dgVoodoo 2](https://github.com/dege-diosg/dgVoodoo2) as
the graphics wrapper on first run (backs up original files).

Requires the Steam build of `CARMA2_HW.EXE`.

## How it works

The trainer uses [Frida](https://frida.re/) to attach to the running game
and apply runtime hooks — no files are modified on disk.

- **Cheats** are fired by injecting hash values into the game's own cheat
  dispatcher, so they execute on the game's thread exactly like typed codes
- **Windowed mode** is provided by [dgVoodoo 2](https://github.com/dege-diosg/dgVoodoo2),
  which translates the game's 3Dfx Glide calls to Direct3D 11
- **Alt+Tab** works because the trainer prevents DirectInput from installing
  a low-level keyboard hook that would eat system hotkeys

## Tabs

| Tab | What's in it |
|-----|-------------|
| **Race** | Auto-start race, finish race, enable cheat mode, fly mode, pinned favorites |
| **Dev cheats** | 26 buttons across 10 groups with live state display. Enable Dev Mode first. |
| **Powerups** | Grid of all 89 powerups with search. Right-click to pin/unpin. |
| **Game Settings** | 31 configurable options across 4 groups (Display, Graphics, Gameplay, Audio). Writes to dgVoodoo.conf + OPTIONS.TXT. Changes take effect on next launch. |
| **Status** | Connection info, game path, graphics wrapper status, force reattach |

## Credits

The dev mode features are publicly documented by the Carmageddon community:

- [Carmashit cheat executable article](https://razor.cwaboard.co.uk/2022/06/20/carmageddon-2-carmashit-cheat-executable-functions/) — comprehensive dev mode documentation
- [Carmageddon wiki](https://wiki.cwaboard.co.uk/wiki/Cheats) — cheat strings and effects
- [dgVoodoo 2](https://github.com/dege-diosg/dgVoodoo2) by Dege — Glide/DDraw wrapper (bundled, freeware)

This project adds runtime-verified addresses for the Steam binary and a
GUI to make the existing community-documented features accessible.

## License

Educational project. dgVoodoo 2 is freeware by Dege, bundled under its
[distribution terms](https://dege.freeweb.hu/dgVoodoo2/).
