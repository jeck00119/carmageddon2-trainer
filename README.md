# Carmageddon 2 Tools

Reverse engineering / runtime patching tools for **Carmageddon 2: Carpocalypse Now** (1998, Stainless Software / SCi).

Targets the Steam build's hardware-accelerated executable: `CARMA2_HW.EXE` (PE32 Win95, ImageBase `0x00400000`, ~2.6 MB).

---

## Quick start

```
py -3 trainer/trainer.py
```

The **trainer** is the user-facing app. It spawns the game, hooks input release / no-minimize / cheat injection / nGlide windowed toggle, and provides a PySide6 GUI with 4 tabs (Race, Dev cheats, Powerups, Status) plus a hidden "All cheats" tab in Advanced mode. See `trainer/README.md` for full details.

**Project status (2026-04-10):** The cheat system is 100% reverse-engineered. All 94 cheat table strings are known. The hidden cheat string is known. 46 hidden dev features discovered and wired into the trainer. 9 camera modes unlockable (including Ped Cam and Drone Cam). The wiki says dev mode is "broken on Steam" — the trainer bypasses this via Frida.

---

## Cheat system — verified facts

### How the game's cheat code system works

1. The game maintains a small ring buffer of typed letters per frame.
2. Each frame, **`GetCheatInputHash`** at VA `0x00482f10` computes a 64-bit hash `(h1, h2)` from the buffer and stores it at `[0x68c1e0]` / `[0x68c1e4]`.
3. **`CheatDetect`** at VA `0x00443c90` walks the table at VA `0x00590970` (file offset `0x18eb70`) — **94 entries × 16 bytes**, struct `{u32 h1, u32 h2, void* handler, u32 arg}` — looking for a match.
4. On match, it `call`s `handler(arg)` (effectively).

### The 5 unique handlers seen in the table

| Handler VA | What it does | How `arg` is used |
|---|---|---|
| `0x00441580` | `set_cheat_mode` — writes the cheat-mode flag at `[0x68b8e0]` | Cheat-mode value (e.g. `0x564e78b9` for LAPMYLOVEPUMP, `0xa11ee75d` for cheat 0) |
| `0x004415c0` | `finish_race` — instant win | unused |
| `0x00442e80` | `spawn_powerup` — actually a 7-byte trampoline `mov edx, ecx; mov ecx, 0x75bc2c; jmp 0x4d8d30`. **Real fn at `0x4d8d30`** (or `0x4d8d40` for dev-menu entry). Crashes outside true in-race (game_state==0). | Powerup id (0..97) |
| `0x00444350` | `fly_toggle` — toggle free-fly camera | unused |
| `0x00444f10` | `gonad_of_death` — Steel Gonad O' Death | unused |

Of the 94 entries: 89× `spawn_powerup`, 2× `set_cheat_mode`, 1× each of the other three.

### Verified cheat strings

**94 of 94 pinned** (100% complete, 2026-04-10). Full list lives in `hash_function.py:KNOWN_CHEATS`. Run `py -3 hash_function.py` to self-test all of them.

56 strings were found via brute force (lengths 4–8) + pattern attacks. The remaining 38 were solved by cross-referencing the [CWA Wiki](https://wiki.cwaboard.co.uk/wiki/Power_Ups_in_Carmageddon_II) cheat lists against our hash table — all matched instantly.

The **hidden cheat** string is also known: `MWUCUZYSFUYHTQWXEPVU` (unlocks car carousel + toggles sound).

### Entry 0 — multiplayer dev mode

Table entry 0: string `XZSUYYUCWZZZZZWYVYOZVWVXPVQWJZ` (30 chars), handler `set_cheat_mode`, arg `0xa11ee75d`. Sets cheat_mode to a value that enables dev cheats even in multiplayer (the LAPMYLOVEPUMP mode is equivalent in single-player). Found via CWA Wiki cross-reference.

### Dev menu (discovered 2026-04-10)

Setting `cheat_mode = 0xa11ee75d` unlocks an entire hidden dev cheat system dispatched by a polled-table at `0x442e90`. Each dev feature is bound to a function key (F1-F12) or letter key via `data/Keymap_0.txt`. Confirmed working features:

| Key | Effect |
|---|---|
| **F1** | Dev menu cycler (Edit mode: Options ↔ Cheat) |
| **F2** | Instant repair |
| **F3** | Damage cycler — NO DAMAGE / NO CRUSHAGE / NO WASTAGE / combinations / FULLY VULNERABLE |
| **F4** | Item / opponent cycler |
| **F5** | Timer freeze toggle |
| **F7** | +2000 credits |
| **F8** | +5000 credits |
| **F12** | HUD mode cycler — Full HUD / No HUD / Minimal HUD (also writes lighting profiler stats to `litopstat.TIF`/`.PIX`) |
| **'j'** | MiniMap toggle |
| **'o'** | Recovery cost editor |
| **L-Shift, L-Ctrl, '0'..'7'** | Powerup spawner family — each spawns `base + 10*Σ(modifier_keys)`. Calls real spawn_powerup at `0x4d8d40` (fastcall: ecx=0x75bc2c, edx=id, push 1, push 1). Bails when game_state==0. |

The dispatcher uses `is_action_pressed (0x4833a0)` not low-level `is_key_pressed`. To fake a dev key from Frida, hook `0x4833a0`. See `dev_probe.py` for the complete autonomous mapper.

### The HIDDEN cheat — NOT in the table

Function `0x00443c50` (called from inside the menu screen handler `0x0046a0e0` at offset `+0x70d`) does its OWN inline check, not via the table:

```asm
0x00443c50  call   0x00482f10           ; GetCheatInputHash
0x00443c55  cmp    [eax],   0x616fb8e4  ; check h1
0x00443c5b  jne    exit
0x00443c5d  cmp    [eax+4], 0x7c6100a8  ; check h2
0x00443c64  jne    exit
0x00443c66  call   0x00455a50           ; toggle sound master flag
0x00443c6b  mov    ecx, [0x6845fc]
0x00443c71  mov    [0x75bc04], 1        ; mystery side-effect flag
0x00443c7b  mov    edx, 0x1519          ; sound id 5401 (FlaskGone.WAV)
0x00443c80  jmp    0x00455690           ; PlaySound
```

**Effect (verified at runtime by patching the JNE checks to NOPs and calling the function directly):** toggles the sound subsystem master flag at `[0x762328]` and the CD audio flag at `[0x7a06c0]`, plays the FlaskGone sound, and sets `[0x75bc04] = 1`. That last flag has 7 readers in the binary across rendering / opponent state / race iteration code; **its full effect was never traced**.

**The cheat string is `MWUCUZYSFUYHTQWXEPVU`** (solved 2026-04-10 via CWA Wiki cross-reference). It unlocks the car carousel in the main menu + toggles sound.

---

## Tools in this folder

### User-facing app

| Path | What it does |
|---|---|
| **trainer/** | PySide6 trainer GUI. The user-facing product — see `trainer/README.md`. Run with `py -3 trainer/trainer.py`. |

### Cheat-system core (used by the trainer + RE work)

| File | What it does |
|---|---|
| **hash_function.py** | Reversed `carma2_hash(s)` + `KNOWN_CHEATS` dict (**94/94 pinned** — 100% complete). Run directly to self-test. |
| **powerup_names.py** | Auto-generated from `data/DATA.TWT/POWERUP.TXT` — maps powerup id (0..97) to its on-screen description. |
| **fast_hash.py** | Numba-accelerated brute-force kernel (~300M/s on a modern CPU). |

### Cheat-system core

| File | What it does |
|---|---|
| **fast_hash.py** | Numba-accelerated brute-force kernel (~300M/s). Kept for potential future use. |

### Dev menu probe (autonomous Frida mapping)

| File | What it does |
|---|---|
| **dev_probe.py** | Autonomous probe runner. Spawns the game, attaches `dev_probe_agent.js` alongside the trainer's agent.js, walks the polled-table at `0x5900a0`, fakes each action via `is_action_pressed` hook, captures resulting events. Outputs `dev_probe.log` + `dev_action_map.json`. |
| **dev_probe_agent.js** | Frida agent loaded as a second script. RPCs: `setCheatMode`, `setSelection`, `installTrace`, `setFakeAction`, `callDevMenu`, `callNumKey`, `dumpOptionTable`, `getActionKey`, `pokeKeyState`, `readU32Range`. Hooks: dev menu fn, num_key handlers, sprintf, print_text, PlaySound, all 5 cheat handlers. |
| **dev_probe.log** | Last run trace |
| **dev_action_map.json** | Structured action_id → effects map |

### Analysis / RE helpers

| File | What it does |
|---|---|
| **analyze.py** | Offline analyzer for `carma2hw.bin`. Subcommands: `disasm <VA> [LEN]`, `callers <VA>`, `xrefs <VA>`. |
| **dump_cheat_table.py** | Parses the 94-entry cheat table at VA 0x590970 and writes `cheats.md` with each entry's handler, arg, pinned string, and effect. |
| **parse_powerups.py** | Regenerates `powerup_names.py` from `powerup.txt`. |

### Data

| File | What it does |
|---|---|
| **carma2hw.bin** | Local copy of `CARMA2_HW.EXE` for offline analysis (don't run it — no Steam DRM context). |
| **powerup.txt** | Extracted from `data/DATA.TWT`. Full definition of all 98 powerups (names, icons, timing, params). |
| **cheats.md** | Generated 94-entry catalog of the cheat table. |
| **README.md** | This file. |

---

## Verified memory addresses (CARMA2_HW.EXE, ImageBase 0x00400000)

### Code

| VA | Symbol | Verified by |
|---|---|---|
| `0x00482f10` | `GetCheatInputHash` (fastcall) — returns ptr to `(h1, h2)` struct | Frida hook fired during runtime cheat injection |
| `0x00443c90` | `CheatDetect` — walks the cheat table | Static analysis (table xref) |
| `0x00443c50` | **HIDDEN cheat** — inline hash check + sound toggle | Frida hook + direct call after JNE patch |
| `0x00482550` | `is_key_pressed(ecx = key_idx)` — DirectInput-backed key state, key_idx is the line number in `data/KEYNAMES.TXT` | Hook fired during menu key probe; faking the return value drove the menu cursor |
| `0x00441580` | `set_cheat_mode(eax = mode)` | Table handler; verified via injection |
| `0x00442e80` | spawn_powerup TRAMPOLINE — `mov edx, ecx; mov ecx, 0x75bc2c; jmp 0x4d8d30` | Disasm; not the real fn |
| `0x004d8d30` | **Real `spawn_powerup`** — fastcall (`ecx=0x75bc2c`, `edx=powerup_id`, `push 1; push 1`). Validates against `[0x6a0ad0]`, indexes `[0x6a0a54]` w/ stride 172. Bails when `game_state==0` (loading screen — must be true in-race). | Disasm + dispatcher trace |
| `0x00444f10` | `gonad_of_death` | Table handler |
| `0x00442e90` | **Polled-table dispatcher** — walks records at `0x5900a0..0x5904c0` and fires fn at `[esi+0x14]` when `is_action_pressed(record.id)` transitions to true. Called every frame from `0x492156`/`0x49227b`/`0x492bc4`. | Runtime trace via dev_probe |
| `0x004833a0` | `is_action_pressed(ecx = action_id)` — looks up keybinding via `[0x74b5e0]` then state via `[0x68bee0]`. THIS is what the polled-table dispatcher uses, NOT the low-level `is_key_pressed`. | Disasm + dev_probe |
| `0x004414b0` | Dev menu cycler function (Edit mode: Options ↔ Cheat). Gated by `cheat_mode == 0xa11ee75d` or `0x564e78b9`. Triggered by F1 via dispatcher. | dev_probe |
| `0x004dbdb0..0x004dc110` | Powerup spawner family (10 fns at +0x60 stride). Each computes `id = base + 10*Σ(modifier_keys)` and calls real spawn_powerup. Bound to L-Sh, L-Ctl, '0'..'7'. | Disasm + dev_probe |
| `0x00455a50` | `toggle_sound_subsystem` | Direct call from `0x00443c50` |
| `0x00455690` | `PlaySound(ecx = channel, edx = sound_id)` (fastcall) | Direct call from `0x00443c50` |
| `0x00503c50` | `DoGame` — main race state machine. Switch on `[0x75bc24]`, jump table at `0x00504154`. State 4 (jump target `0x00503daa`) is the actual race body. | Disassembly + caller search; called from main game loop at `0x0049252f` |
| `0x005039e0` | "Show race start screen" function (called from `DoGame` state 4) | Static analysis |
| `0x0046a0e0` | Main menu / Options screen update — called per-frame. Polls 7 keys (`51, 52, 63, 72, 73, 83, 89`). Contains the call to the hidden cheat at offset `+0x70d`. | Hook fired at ~50 Hz during menu |
| `0x0046ccb0` | `menu_cleanup(this = menu)` — thiscall. Releases assets of the old menu before a transition. | Runtime verified (start_race.py) |
| `0x0046c970` | `menu_init(this = menu)` — thiscall. Loads assets of the new menu. | Runtime verified |
| `0x00470a90` | `menu_finalize(ecx = old_menu, edx = new_menu)` — fastcall. Updates item-state carry-over between two menus. | Runtime verified |
| `0x00467a70` | `menu_postfx(this = new_menu)` — thiscall. Final setup after a transition. | Runtime verified |
| `0x00500760` | DirectDraw setup dispatcher — branches on `[0x6aa9e0]`. The `je 0x00500795` at `0x0050077b` is the windowed-vs-fullscreen branch. | Discovered via `LocalWindowedDDSetup` string xref |
| `0x005000a0` | `LocalWindowedDDSetup` — actual windowed-mode DirectDraw init. Internal "windowed mode" exists but is wired to a flag with no CLI toggle. (Patching the flag *did* take the windowed branch but nGlide overrides the display setup, so this is a dead code path in the Steam build.) | Static |

### Data (globals)

| VA | Meaning | Verified by |
|---|---|---|
| `0x00590970` | Cheat hash table — 94 entries × 16 bytes each | Static analysis + counted entries with valid handler ptrs |
| `0x0068b918` | Game state (`0` = menu/in-game; transitions during race start) | Frida snapshot at known game states |
| `0x0068b8e0` | Cheat mode flag — written by `set_cheat_mode` | Verified by injecting LAPMYLOVEPUMP |
| `0x0068c1e0` | Live cheat input hash h1 — updated each frame by `GetCheatInputHash` | Patched it to inject hashes |
| `0x0068c1e4` | Live cheat input hash h2 | Same |
| `0x00688abc` | Pointer to current menu struct | Frida read while navigating menus |
| `0x00688770` | Menu selection / global menu state | Frida read |
| `0x00762328` | Sound subsystem master flag (read in 65 places via `mov ecx, [0x762328]; test ecx; je SKIP`) | Hidden cheat toggles it |
| `0x007a06c0` | CD audio flag | Hidden cheat toggles it |
| `0x0075bc04` | Hidden cheat side-effect flag (mystery — read in 7 places) | Hidden cheat sets it to 1 |
| `0x0075bc24` | DoGame state machine variable (0..6) | Switch jump table at `0x00504154` |
| `0x006aa9e0` | Internal windowed-mode flag (used by `0x00500760`'s branch). Setting it non-zero takes the windowed code path but **doesn't actually run windowed in the Steam build** — nGlide handles display setup separately. | Patched and verified the branch was taken |

### Menu structures (in `.data`)

| VA | Name string |
|---|---|
| `0x005a80f0` | `"Main"` |
| `0x005b39b8` | `"Network"` |
| `0x0059c828` | `"Credits"` |
| `0x005bf280` | `"New Game"` (skill select) |
| `0x00632c60` | `"Options"` |
| `0x00649df0` | `"Quit"` |

Menu struct layout (relative to the menu's base address):

| Offset | Meaning |
|---|---|
| `0x000..0x1f` | name (ASCII, zero-padded) |
| `0x108` | cleanup function pointer (`0x00469a40` on Main) |
| `0x10c` | init function pointer (`0x00469df0` on Main) |
| `0x110` | per-frame update function pointer — always `0x0046a0e0` for menu screens |
| `0x114` | back-pointer to previous menu (written during a transition) |
| `0x118` | default `sel_global` on enter |
| **`+ sel * 0x158`** | **item slot for `sel`** |
| `0x8790` | item count for the carry-over loop |

Inside each item slot at `menu + sel * 0x158`:

| Offset in slot | Meaning |
|---|---|
| `+0x008` | display name string (ASCII, up to 16 bytes) |
| `+0x134` | **click callback** — thiscall, `ecx = menu`. Called when the item is clicked. May be `0x00466450` (generic, does nothing) or a specific button handler. |
| `+0x138` | **target menu** pointer — if non-null, a full menu transition runs after the callback returns |
| `+0x13c` | **type**. `1` sets `[0x6883a8] = 1` before calling the callback. `2` returns early. `5` is special in some screens. |

Known item mappings (discovered by dumping the Main/NewGame menus at runtime):

| Menu | sel | cb VA | target | type | Role |
|---|---|---|---|---|---|
| Main | 1 | `0x00467eb0` | Network | 0 | Network button |
| Main | 9 | `0x00466450` | Options | 0 | Options button |
| Main | **21** | **`0x00467270`** | **NewGame** | 0 | **Start button** |
| NewGame | **5** | **`0x00466450`** | `0` | **1** | **OK button (the `type=1` + callback trigger together kick off race loading)** |

**Click handler flow** (reimplemented in `start_race.py` and `menu_tool.py`):

1. set `[0x688770] = sel`
2. if `type == 2` → return
3. if `type == 1` → write `[0x6883a8] = 1`
4. if `item.callback != 0` → call it with `ecx = menu` (thiscall)
5. if `item.target != 0` and the callback didn't already transition → run the transition sequence:
   1. `menu_cleanup(old)`     (`0x0046ccb0`)
   2. write `[0x688abc] = new`
   3. `menu_init(new)`        (`0x0046c970`)
   4. if `old[0x114] != new`: `new[0x114] = old` (back-pointer)
   5. `menu_finalize(old, new)`  (`0x00470a90`, fastcall)
   6. `[0x688770] = new[0x118]` (or 0 if new == Quit)
   7. for each item: copy `new[+0x87c0 + i*0x34]` to `new[+0x87a0 + i*0x34]`
   8. `menu_postfx(new)`      (`0x00467a70`)

---

## Cheat-mode details

`set_cheat_mode` writes to `[0x68b8e0]`. The per-frame polling function at `0x00441600` (and 17 similar functions at `0x00441601 + N*0x80`) reads that flag and gates the **number-key cheats** (Shift/Ctrl/Alt + digits). Key findings:

- Two magic values unlock the number-key cheat system:
  - `0x564e78b9` — set by `LAPMYLOVEPUMP` (happens to be the h1 of `IBETYOUCANTPRINTCUNT` — the devs used that hash as a magic number).
  - `0xa11ee75d` — set by cheat-table entry 0 (string unknown — h1 = arg = 0xa11ee75d, self-referential).
- The polling function also checks `[0x68b918]` (game_state). **Number-key cheats only fire when game_state != 0 — i.e. during an active race.** This matches online docs that say "type cheats after the race countdown".
- The function-pointer table for number-key cheats lives at `0x005904f0`, indexed by `cheat_key * 144 + modifier_mask`.
- Text-cheats from the 94-entry table at `0x00590970` are independent of this — they fire from `CheatDetect` (`0x00443c90`) which watches `GetCheatInputHash`.

## Project status (2026-04-10 — COMPLETE)

All major reverse-engineering goals achieved:
- **94/94 cheat table strings known** (100% — final 38 from CWA Wiki cross-reference)
- **Hidden cheat string known**: `MWUCUZYSFUYHTQWXEPVU` (car carousel + sound toggle)
- **Entry 0 string known**: `XZSUYYUCWZZZZZWYVYOZVWVXPVQWJZ` (multiplayer dev mode)
- **`[0x75bc04]` traced**: enables hidden menu items (car carousel in main menu). 14 readers found.
- **`spawn_powerup`**: crashes from Frida thread — use hash injection via `fireByHash` instead
- **IBETYOUCANTPRINTCUNT**: confirmed NOT a typeable cheat in Steam build (h2 absent from binary). Wiki claim is a myth.
- **46 dev cheats** wired into trainer. **9 camera modes** unlockable (including Ped Cam + Drone Cam).
