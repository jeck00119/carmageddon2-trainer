"""
Loads the full Carma2 cheat table from carma2hw.bin and joins with
KNOWN_CHEATS + POWERUP_NAMES so the UI can show all 94 entries with
human-readable labels.
"""
import os
import sys
import struct
from dataclasses import dataclass
from typing import Optional

_TOOLS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from hash_function import KNOWN_CHEATS

try:
    from powerup_names import POWERUP_NAMES
except ImportError:
    POWERUP_NAMES = {}

# Friendly effect overrides for powerup IDs whose POWERUP.TXT description
# is missing ('n/a') but whose effect we know from external sources.
# Verified 2026-04-10 via autonomous discovery probe.
# id 0 gives 200 credits, id 1 gives 9000 credits (the biggest single bonus).
KNOWN_EFFECTS = {
    0: '200 credits',            # WETWET (was "Credit bonus")
    1: '9000 credits',           # GLUGLUG — the LAST n/a, now decoded!
    28: 'Hot rod!',
    29: 'Peds with stupid heads!',
    30: 'Pedestrians shown on map',
    31: 'Giant pedestrians!',
    86: 'Extra power',
    87: 'Extra armour slot',
    88: 'Double extra power',
    89: 'Extra armour',
}

BIN_PATH = os.path.join(_TOOLS_DIR, 'carma2hw.bin')

TABLE_FILE_OFF = 0x18eb70
ENTRY_COUNT    = 94
ENTRY_SIZE     = 16

HANDLERS = {
    0x00441580: 'set_cheat_mode',
    0x004415c0: 'finish_race',
    0x00442e80: 'spawn_powerup',
    0x00444350: 'fly_toggle',
    0x00444f10: 'gonad_of_death',
}


@dataclass
class CheatEntry:
    idx: int
    h1: int
    h2: int
    handler_va: int
    handler: str         # 'spawn_powerup' or hex VA string
    arg: int
    name: Optional[str]  # known cheat string or None
    effect: str          # human-readable effect description

    @property
    def display(self) -> str:
        """Best label for a button — never returns 'n/a' or empty."""
        if self.handler == 'spawn_powerup':
            if self.effect:
                return self.effect
            return f'Unknown effect ({self.name or f"id {self.arg}"})'
        if self.handler == 'set_cheat_mode':
            return f'Cheat mode 0x{self.arg:08x}'
        if self.handler == 'finish_race':
            return 'Finish race'
        if self.handler == 'fly_toggle':
            return 'Fly toggle'
        if self.handler == 'gonad_of_death':
            return 'Gonad of death'
        return f'unknown handler {self.handler}'

    @property
    def in_race_only(self) -> bool:
        return self.handler in ('spawn_powerup', 'fly_toggle',
                                'gonad_of_death', 'finish_race')


def _normalize_effect(raw: str) -> str:
    """Clean POWERUP.TXT artifacts: 'n/a', mixed slashes, trailing punctuation."""
    if not raw or raw.strip().lower() in ('n/a', '?', ''):
        return ''
    # 'Timer frozen!/Timer thaw!/' -> 'Timer frozen / Timer thaw'
    s = raw.replace('!/', ' / ').replace('/', ' / ').rstrip(' /!.')
    # collapse runs of spaces
    return ' '.join(s.split())


def load_cheat_table() -> list[CheatEntry]:
    with open(BIN_PATH, 'rb') as f:
        data = f.read()
    hash_to_name = {h: name for name, h in KNOWN_CHEATS.items()}
    entries = []
    for i in range(ENTRY_COUNT):
        off = TABLE_FILE_OFF + i * ENTRY_SIZE
        h1, h2, handler, arg = struct.unpack_from('<IIII', data, off)
        handler_name = HANDLERS.get(handler, f'0x{handler:08x}')
        effect = ''
        if handler_name == 'spawn_powerup':
            effect = _normalize_effect(POWERUP_NAMES.get(arg, '')) \
                or KNOWN_EFFECTS.get(arg, '')
        entries.append(CheatEntry(
            idx=i, h1=h1, h2=h2,
            handler_va=handler,
            handler=handler_name,
            arg=arg,
            name=hash_to_name.get((h1, h2)),
            effect=effect,
        ))
    return entries


def powerups_only(entries: list[CheatEntry]) -> list[CheatEntry]:
    return [e for e in entries if e.handler == 'spawn_powerup']
