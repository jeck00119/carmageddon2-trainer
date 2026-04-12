# dgVoodoo 2 bundle

This folder bundles the **32-bit Glide wrapper** + control panel from
[dgVoodoo 2](https://github.com/dege-diosg/dgVoodoo2) v2.87.1 by Dege.

## What's here

| File | Purpose |
|---|---|
| `Glide.dll`, `Glide2x.dll`, `Glide3x.dll` | Glide → D3D11 wrappers for the 32-bit Carmageddon 2 Glide renderer. Replaces nGlide. |
| `dgVoodoo.conf` | Config pre-tuned for Carma2: `FullScreenMode = false` (start windowed), `3DfxWatermark = false`, `dgVoodooWatermark = false`. |
| `dgVoodooCpl.exe` | Control panel for runtime re-configuration (optional but handy). |

**Note:** dgVoodoo's `DDraw.dll` is intentionally NOT included. When both
the Glide and DDraw wrappers are in the game folder, dgVoodoo's windowed
Glide rendering breaks (the window is created but nothing is drawn). The
trainer's Frida agent handles the DDraw-exclusive-mode problem separately
by installing its own WH_KEYBOARD_LL hook and blocking DInput's.

## Why dgVoodoo instead of nGlide

dgVoodoo 2 is a modern D3D11 backend that correctly handles Alt+Enter (fullscreen
toggle), Alt+Tab (focus loss), and click-outside-window events. nGlide's windowed
support is a retrofit over a fullscreen-only Glide API and causes the game to
force itself back to fullscreen on focus loss, which is a well-known community
complaint for Carmageddon 2 on Windows 10.

When a user runs the trainer for the first time, `ensure_dgvoodoo()` in
`backend/frida_core.py` copies these files into the game folder (backing up any
existing `glide*.dll` to `glide*.dll.bak_nglide` so their original setup is not
destroyed). The trainer's `_is_dgvoodoo_glide()` detector verifies the install
succeeded before launching the game.

## License

dgVoodoo 2 is freeware (not open source). Bundling is allowed under Dege's
distribution terms. See the official readme at
<https://dege.freeweb.hu/dgVoodoo2/> for full terms.

Upstream source: <https://github.com/dege-diosg/dgVoodoo2>
