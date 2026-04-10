#!/usr/bin/env python3
"""
Dump the full Carmageddon 2 cheat table as Markdown.

The table is 94 entries x 16 bytes at file offset 0x18eb70 (VA 0x00590970).
Each entry:  struct { u32 h1; u32 h2; void* handler; u32 arg; }
"""
import struct
import os

from hash_function import KNOWN_CHEATS
try:
    from powerup_names import POWERUP_NAMES
except ImportError:
    POWERUP_NAMES = {}

# Known overrides for powerup IDs whose POWERUP.TXT says 'n/a'
try:
    from trainer.backend.cheat_db import KNOWN_EFFECTS
except ImportError:
    KNOWN_EFFECTS = {0: 'Credit bonus'}

BIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'carma2hw.bin')
TABLE_FILE_OFF = 0x18eb70
TABLE_VA       = 0x00590970
ENTRY_COUNT    = 94
ENTRY_SIZE     = 16

HANDLERS = {
    0x00441580: 'set_cheat_mode',
    0x004415c0: 'finish_race',
    0x00442e80: 'spawn_powerup',
    0x00444350: 'fly_toggle',
    0x00444f10: 'gonad_of_death',
}

def main():
    with open(BIN, 'rb') as f:
        data = f.read()

    # Reverse map: (h1, h2) -> string name
    hash_to_name = {h: name for name, h in KNOWN_CHEATS.items()}

    rows = []
    for i in range(ENTRY_COUNT):
        off = TABLE_FILE_OFF + i * ENTRY_SIZE
        h1, h2, handler, arg = struct.unpack_from('<IIII', data, off)
        handler_name = HANDLERS.get(handler, f'0x{handler:08x}')
        known = hash_to_name.get((h1, h2), '')
        rows.append({
            'idx': i,
            'h1': h1,
            'h2': h2,
            'handler_va': handler,
            'handler_name': handler_name,
            'arg': arg,
            'known_name': known,
        })

    # Emit markdown
    lines = []
    lines.append('# Carmageddon 2 Cheat Table')
    lines.append('')
    lines.append(f'Extracted from `CARMA2_HW.EXE` at VA `0x{TABLE_VA:08x}` (file offset `0x{TABLE_FILE_OFF:x}`).')
    lines.append(f'**{ENTRY_COUNT} entries × 16 bytes** = {ENTRY_COUNT * ENTRY_SIZE} bytes total.')
    lines.append('')
    lines.append('Each entry: `struct { u32 h1; u32 h2; void* handler; u32 arg; }`')
    lines.append('')
    lines.append('## Handlers')
    lines.append('')
    for va, name in sorted(HANDLERS.items()):
        lines.append(f'- `0x{va:08x}` — **{name}**')
    lines.append('')
    lines.append('## Entries')
    lines.append('')
    lines.append('| #  | handler | arg | known string | effect |')
    lines.append('|---:|---|---:|---|---|')
    for r in rows:
        arg_display = f'{r["arg"]}' if r['arg'] else '-'
        known = f'**`{r["known_name"]}`**' if r['known_name'] else '?'
        effect = ''
        if r['handler_name'] == 'spawn_powerup':
            raw = POWERUP_NAMES.get(r['arg'], '?')
            if raw.strip().lower() in ('n/a', '?', ''):
                effect = KNOWN_EFFECTS.get(r['arg'], 'n/a')
            else:
                effect = raw
        elif r['handler_name'] == 'set_cheat_mode':
            effect = f'cheat_mode = 0x{r["arg"]:08x}'
        elif r['handler_name'] == 'finish_race':
            effect = 'instant win'
        elif r['handler_name'] == 'fly_toggle':
            effect = 'toggle fly cam'
        elif r['handler_name'] == 'gonad_of_death':
            effect = 'steel gonad O\' death'
        lines.append(
            f'| {r["idx"]:2d} '
            f'| {r["handler_name"]} '
            f'| {arg_display} '
            f'| {known} '
            f'| {effect} |'
        )
    lines.append('')

    # Summary
    by_handler = {}
    for r in rows:
        by_handler.setdefault(r['handler_name'], []).append(r)
    lines.append('## Summary')
    lines.append('')
    for name, items in sorted(by_handler.items()):
        lines.append(f'- **{name}**: {len(items)} entries')
        args = sorted({it['arg'] for it in items})
        if name == 'spawn_powerup':
            # Powerup IDs
            ids = sorted({it['arg'] for it in items})
            lines.append(f'  - powerup ids referenced: {", ".join(f"{a}" for a in ids)}')
            lines.append(f'  - range: {min(ids)}..{max(ids)}  ({len(ids)} distinct ids)')
        elif name == 'set_cheat_mode':
            lines.append(f'  - distinct mode values: {len(args)}')
    lines.append('')

    out = '\n'.join(lines)
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cheats.md')
    with open(out_path, 'w') as f:
        f.write(out)
    print(f'Wrote {out_path}')
    print(f'  {len(rows)} entries')
    print(f'  {sum(1 for r in rows if r["known_name"])} with known names')
    print(f'  handler breakdown:')
    for name, items in sorted(by_handler.items()):
        print(f'    {name:20s}: {len(items)}')


if __name__ == '__main__':
    main()
