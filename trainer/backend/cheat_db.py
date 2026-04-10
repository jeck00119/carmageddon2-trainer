"""
Carma2 cheat table — fully embedded, no binary file needed.

All 94 entries extracted from CARMA2_HW.EXE at VA 0x590970 (file offset 0x18eb70).
Joined with KNOWN_CHEATS (94/94 strings) + POWERUP_NAMES for human-readable labels.
"""
import os
import sys
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
# is missing ('n/a') but whose effect we know from in-game testing.
KNOWN_EFFECTS = {
    0: '200 credits',
    1: '9000 credits',
    28: 'Hot rod!',
    29: 'Peds with stupid heads!',
    30: 'Pedestrians shown on map',
    31: 'Giant pedestrians!',
    86: 'Extra power',
    87: 'Extra armour slot',
    88: 'Double extra power',
    89: 'Extra armour',
}

HANDLERS = {
    0x00441580: 'set_cheat_mode',
    0x004415c0: 'finish_race',
    0x00442e80: 'spawn_powerup',
    0x00444350: 'fly_toggle',
    0x00444f10: 'gonad_of_death',
}

# Embedded cheat table — 94 entries, format: (h1, h2, handler_va, arg)
_TABLE = [
    (0xa11ee75d, 0xf805eddd, 0x00441580, 2703157085),
    (0x398da28c, 0x44339dd4, 0x00441580, 1447983289),
    (0x7dc510f3, 0x65c61537, 0x00444350, 1),
    (0x309e4f55, 0xecc7daaf, 0x004415c0, 0),
    (0x1bcbe148, 0x040161b1, 0x00442e80, 0),
    (0x1d5e7725, 0x0ed62a70, 0x00442e80, 1),
    (0x22c65063, 0xe4331bc8, 0x00442e80, 2),
    (0x1a37d28a, 0x139787e4, 0x00442e80, 3),
    (0x1dcba360, 0x1e38bfa1, 0x00442e80, 4),
    (0x24c99afb, 0xd908f952, 0x00442e80, 5),
    (0x200c1bd4, 0x663de391, 0x00442e80, 6),
    (0x252a2e6b, 0x3304d647, 0x00442e80, 7),
    (0x218f555c, 0xe2d3ac58, 0x00442e80, 8),
    (0x1fc7655b, 0xa12f9258, 0x00442e80, 9),
    (0x2b2e6891, 0x4bd611c2, 0x00442e80, 10),
    (0x2db8b34a, 0x4418ac58, 0x00442e80, 11),
    (0x3001467e, 0xb323f944, 0x00442e80, 12),
    (0x23968eda, 0x9259246e, 0x00442e80, 13),
    (0x1f3baa55, 0x56c505a9, 0x00442e80, 15),
    (0x214a2558, 0x56cbf421, 0x00442e80, 16),
    (0x373ae69a, 0xef8c998f, 0x00442e80, 17),
    (0x327ebd75, 0x605a9e3e, 0x00442e80, 18),
    (0x350c0384, 0x73e576d2, 0x00442e80, 19),
    (0x17f03c24, 0x0071650c, 0x00442e80, 20),
    (0x32aeca21, 0x689d3168, 0x00442e80, 21),
    (0x191841aa, 0x10fbd770, 0x00442e80, 22),
    (0x26026896, 0x630e5fa9, 0x00442e80, 23),
    (0x2440ca1b, 0x2e68304c, 0x00442e80, 24),
    (0x37a11b1b, 0x6820b87d, 0x00442e80, 25),
    (0x2f2ea509, 0x6bb804b7, 0x00442e80, 26),
    (0x28f522f1, 0x2f52f8c0, 0x00442e80, 27),
    (0x26c15553, 0xba19a354, 0x00442e80, 32),
    (0x3964b52b, 0x40c94648, 0x00442e80, 33),
    (0x18bf123a, 0x0080c0a9, 0x00442e80, 34),
    (0x2a439e13, 0x3356c0b0, 0x00442e80, 35),
    (0x28769902, 0x50a5d8d1, 0x00442e80, 36),
    (0x2d5aa4e5, 0x427f9d82, 0x00442e80, 37),
    (0x1e73b354, 0x17741619, 0x00442e80, 38),
    (0x1cac0a7c, 0x0a461bb1, 0x00442e80, 39),
    (0x1e3c613a, 0x6b56e92c, 0x00442e80, 40),
    (0x2f4c3519, 0x082321f8, 0x00442e80, 41),
    (0x21f0d261, 0xdae090b9, 0x00442e80, 42),
    (0x1c727344, 0x78f65c91, 0x00442e80, 43),
    (0x2f574845, 0x75ff1428, 0x00442e80, 44),
    (0x1f0601e3, 0x9455c4c8, 0x00442e80, 45),
    (0x26219ff3, 0xfdfd8b46, 0x00442e80, 47),
    (0x26afbb31, 0xe3275e40, 0x00442e80, 48),
    (0x25205546, 0xcf86a14c, 0x00442e80, 49),
    (0x1a0a8e5b, 0x02035340, 0x00442e80, 51),
    (0x1bdea925, 0x5d98fd0c, 0x00442e80, 52),
    (0x2d4dd2a9, 0xf01ba696, 0x00442e80, 53),
    (0x2e7a7505, 0x8920e4f6, 0x00442e80, 54),
    (0x17290940, 0x00901801, 0x00442e80, 55),
    (0x1d4e7a9c, 0x030e2650, 0x00442e80, 56),
    (0x3579d64a, 0x3d2e34c3, 0x00442e80, 57),
    (0x28f4d49c, 0xb3418148, 0x00442e80, 58),
    (0x1d6ba9c3, 0x0e017749, 0x00442e80, 59),
    (0x310971ab, 0xcb973702, 0x00442e80, 60),
    (0x28451eeb, 0x30ff63cb, 0x00442e80, 61),
    (0x1ebfa5ba, 0x92e034ec, 0x00442e80, 62),
    (0x27079773, 0xd1ef511c, 0x00442e80, 63),
    (0x388de72c, 0x047a8dca, 0x00442e80, 64),
    (0x1a0da9fc, 0x0180e010, 0x00442e80, 65),
    (0x2975a10c, 0xefd65f5d, 0x00442e80, 66),
    (0x1e5cc6ca, 0x17b76391, 0x00442e80, 67),
    (0x250c6f99, 0xbdda24cc, 0x00442e80, 68),
    (0x33950e49, 0x2890738c, 0x00442e80, 69),
    (0x4e5f487a, 0x3dc635b8, 0x00442e80, 70),
    (0x3815584c, 0x91bbc26e, 0x00442e80, 71),
    (0x459732b2, 0xb571e010, 0x00442e80, 72),
    (0x62871003, 0x79b15084, 0x00442e80, 73),
    (0x2d72ebb4, 0x5fd4d3ca, 0x00442e80, 74),
    (0x2c3be2aa, 0x90e0eb9c, 0x00442e80, 75),
    (0x2b2be28b, 0x30e0eb7b, 0x00442e80, 76),
    (0x29be089d, 0x635ceb96, 0x00442e80, 77),
    (0x4897982d, 0x06c4fa99, 0x00442e80, 78),
    (0x44d50f49, 0x010edb42, 0x00442e80, 79),
    (0x403afae5, 0x0104a7d2, 0x00442e80, 80),
    (0x45c19e5e, 0x011b2cf9, 0x00442e80, 81),
    (0x2f790ebd, 0x2fd87f6b, 0x00442e80, 82),
    (0x244f60c9, 0x31f4fda3, 0x00442e80, 83),
    (0x2b0794d3, 0x12927dc9, 0x00442e80, 84),
    (0x2a44b628, 0x0c3e7edb, 0x00442e80, 85),
    (0x2998e46d, 0x1360a63e, 0x00442e80, 86),
    (0x23248728, 0xc84d9d51, 0x00442e80, 87),
    (0x289c1822, 0x136e9fc3, 0x00442e80, 88),
    (0x35abb7d0, 0xa08da57c, 0x00442e80, 90),
    (0x1c1fdd92, 0x01dd060c, 0x00442e80, 91),
    (0x253069c1, 0x4972796a, 0x00442e80, 92),
    (0x33ca4873, 0x3b005b24, 0x00442e80, 93),
    (0x1f56cde5, 0x8f213aae, 0x00442e80, 94),
    (0x1784995b, 0x0163c389, 0x00442e80, 96),
    (0x3003eccb, 0x1d74f36f, 0x00442e80, 97),
    (0x4b054b60, 0x6b6736cb, 0x00444f10, 0),
]


@dataclass
class CheatEntry:
    idx: int
    h1: int
    h2: int
    handler_va: int
    handler: str
    arg: int
    name: Optional[str]
    effect: str

    @property
    def display(self) -> str:
        if self.handler == 'spawn_powerup':
            return self.effect or f'Unknown effect ({self.name or f"id {self.arg}"})'
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
    if not raw or raw.strip().lower() in ('n/a', '?', ''):
        return ''
    s = raw.replace('!/', ' / ').replace('/', ' / ').rstrip(' /!.')
    return ' '.join(s.split())


def load_cheat_table() -> list[CheatEntry]:
    hash_to_name = {h: name for name, h in KNOWN_CHEATS.items()}
    entries = []
    for i, (h1, h2, handler_va, arg) in enumerate(_TABLE):
        handler_name = HANDLERS.get(handler_va, f'0x{handler_va:08x}')
        effect = ''
        if handler_name == 'spawn_powerup':
            effect = _normalize_effect(POWERUP_NAMES.get(arg, '')) \
                or KNOWN_EFFECTS.get(arg, '')
        entries.append(CheatEntry(
            idx=i, h1=h1, h2=h2,
            handler_va=handler_va,
            handler=handler_name,
            arg=arg,
            name=hash_to_name.get((h1, h2)),
            effect=effect,
        ))
    return entries


def powerups_only(entries: list[CheatEntry]) -> list[CheatEntry]:
    return [e for e in entries if e.handler == 'spawn_powerup']
