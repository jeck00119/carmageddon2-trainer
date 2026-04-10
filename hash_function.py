#!/usr/bin/env python3
"""
Reversed Carmageddon 2 cheat code hash function.

The game's cheat-input system maintains 3 running 32-bit accumulators
(sum, shl, sq) over the typed letters and produces a 64-bit hash (h1, h2)
that is compared against a static table of 94 entries at file offset 0x18eb70
(VA 0x590970) of CARMA2_HW.EXE.

Each typed letter is mapped to ord('A')+22, then folded into the accumulators.
"""


def carma2_hash(s: str) -> tuple[int, int]:
    """Compute (h1, h2) for a candidate cheat string. Non-letters are ignored."""
    sum_acc = shl_acc = sq_acc = 0
    for c in s.upper():
        if not c.isalpha():
            continue
        ch = ord(c) - ord('A') + 22
        sum_acc = (sum_acc + ch) & 0xffffffff
        v = (shl_acc + (ch << 11)) & 0xffffffff
        shl_acc = (((v << 4) & 0xffffffff) + (v >> 17)) & 0xffffffff
        sq_acc = ((ch * ch) + ((sq_acc << 3) & 0xffffffff) + (sq_acc >> 29)) & 0xffffffff
    h1 = (((sum_acc << 21) & 0xffffffff) + (shl_acc >> 11)) & 0xffffffff
    return h1, sq_acc


# Known cheat strings, pinned to table indices by matching computed hashes against
# the in-binary cheat table at 0x590970. See pin_cheats.py for how these were found.
KNOWN_CHEATS = {
    'LAPMYLOVEPUMP':                 (0x398da28c, 0x44339dd4),  # idx  1  set_cheat_mode   enable cheat mode
    'IWISHICOULDFLYRIGHTUPTOTHESKY': (0x7dc510f3, 0x65c61537),  # idx  2  fly_toggle       flight mode
    'SMARTBASTARD':                  (0x309e4f55, 0xecc7daaf),  # idx  3  finish_race      finish race
    'WETWET':                        (0x1bcbe148, 0x040161b1),  # idx  4  spawn_powerup    credit bonus
    'GLUGLUG':                       (0x1d5e7725, 0x0ed62a70),  # idx  5  spawn_powerup    powerup id 1 (n/a)
    'STICKITS':                      (0x22c65063, 0xe4331bc8),  # idx  6  spawn_powerup    Pedestrians with greased shoes!
    'MEGABUM':                       (0x1a37d28a, 0x139787e4),  # idx  7  spawn_powerup    Giant pedestrians!
    'TWATOFF':                       (0x1dcba360, 0x1e38bfa1),  # idx  8  spawn_powerup    explosive peds
    'FASTBAST':                      (0x200c1bd4, 0x663de391),  # idx 10  spawn_powerup    fast peds
    'TINGTING':                      (0x218f555c, 0xe2d3ac58),  # idx 12  spawn_powerup    free repairs
    'MINGMING':                      (0x1fc7655b, 0xa12f9258),  # idx 13  spawn_powerup    Instant repair!
    'STOPSNATCH':                    (0x2b2e6891, 0x4bd611c2),  # idx 14  spawn_powerup    toggle timer
    'WATERSPORT':                    (0x2db8b34a, 0x4418ac58),  # idx 15  spawn_powerup    underwater driving
    'WHIZZ':                         (0x18bf123a, 0x0080c0a9),  # idx 33  spawn_powerup    Turbo!
    'LEDSLEDS':                      (0x1f0601e3, 0x9455c4c8),  # idx 44  spawn_powerup    Gravity from jupiter!
    'TINYTOSS':                      (0x26afbb31, 0xe3275e40),  # idx 46  spawn_powerup    MiniAture Pedestrians!
    'HOTASS':                        (0x1a0a8e5b, 0x02035340),  # idx 48  spawn_powerup    Afterburner!
    'COWCOW':                        (0x1a0da9fc, 0x0180e010),  # idx 62  spawn_powerup    Pedestrian repulsificator!
    'OSOFAST':                       (0x1e5cc6ca, 0x17b76391),  # idx 64  spawn_powerup    Extra power
    'OSONASTY':                      (0x250c6f99, 0xbdda24cc),  # idx 65  spawn_powerup    Extra offensive
    'OSOSTRONG':                     (0x2975a10c, 0xefd65f5d),  # idx 63  spawn_powerup    Extra armour
    'GETDOWN':                       (0x1d6ba9c3, 0x0e017749),  # idx 56  spawn_powerup    Groovin' Pedestrians!
    'LARGEONE':                      (0x1ebfa5ba, 0x92e034ec),  # idx 59  spawn_powerup    DRUNK pedestrians!
    'RANDYPOT':                      (0x23248728, 0xc84d9d51),  # idx 84  spawn_powerup    powerup id 87 (n/a)
    'INEEDAPILL':                    (0x253069c1, 0x4972796a),  # idx 88  spawn_powerup    Pedestrian Valium
    'BONBON':                        (0x1784995b, 0x0163c389),  # idx 91  spawn_powerup    Slaughter Mortar
    'TIMMYTITTY':                    (0x3001467e, 0xb323f944),  # idx 16  spawn_powerup    time bonus
    'CLANGCLANG':                    (0x23968eda, 0x9259246e),  # idx 17  spawn_powerup    bodywork trashed
    'BLUEBALZ':                      (0x1f3baa55, 0x56c505a9),  # idx 18  spawn_powerup    Frozen opponents!
    'BLUEPIGZ':                      (0x214a2558, 0x56cbf421),  # idx 19  spawn_powerup    Frozen cops!
    'MOONINGMINNIE':                 (0x350c0384, 0x73e576d2),  # idx 22  spawn_powerup    lunar gravity
    'TILTY':                         (0x17f03c24, 0x0071650c),  # idx 23  spawn_powerup    pinball mode
    'STICKYTYRES':                   (0x32aeca21, 0x689d3168),  # idx 24  spawn_powerup    wall climber
    'JIGAJIG':                       (0x191841aa, 0x10fbd770),  # idx 25  spawn_powerup    Bouncey bouncey!
    'DOTACTION':                     (0x2440ca1b, 0x2e68304c),  # idx 27  spawn_powerup    peds on map
    'FRYINGTONIGHT':                 (0x37a11b1b, 0x6820b87d),  # idx 28  spawn_powerup    zap peds
    'WOTATWATAMI':                   (0x2f2ea509, 0x6bb804b7),  # idx 29  spawn_powerup    flame thrower
    'LEMMINGIZE':                    (0x28769902, 0x50a5d8d1),  # idx 35  spawn_powerup    disable ped AI
    'TAKEMETAKEME':                  (0x2d5aa4e5, 0x427f9d82),  # idx 36  spawn_powerup    suicidal peds
    'PILLPOP':                       (0x1e73b354, 0x17741619),  # idx 37  spawn_powerup    5 Free recovery vouchers
    'BIGTWAT':                       (0x1cac0a7c, 0x0a461bb1),  # idx 38  spawn_powerup    solid granite car
    'DUFFRIDE':                      (0x1e3c613a, 0x6b56e92c),  # idx 39  spawn_powerup    Rock springs!
    'BLOODYHIPPY':                   (0x2f4c3519, 0x082321f8),  # idx 40  spawn_powerup    drugs
    'RUBBERUP':                      (0x21f0d261, 0xdae090b9),  # idx 41  spawn_powerup    Grip-o-matic tyres!
    'GOODHEAD':                      (0x1c727344, 0x78f65c91),  # idx 42  spawn_powerup    stupid-head peds
    'STIFFSPASMS':                   (0x2f574845, 0x75ff1428),  # idx 43  spawn_powerup    timer reversed
    'DIDEDODI':                      (0x1bdea925, 0x5d98fd0c),  # idx 49  spawn_powerup    mine shitting ability
    'SKIPPYPOOS':                    (0x2e7a7505, 0x8920e4f6),  # idx 51  spawn_powerup    kangaroo on command
    'ZAZAZ':                         (0x17290940, 0x00901801),  # idx 52  spawn_powerup    ped annihilator
    'POWPOW':                        (0x1d4e7a9c, 0x030e2650),  # idx 53  spawn_powerup    opponent repulsificator
    'XRAYSPEKS':                     (0x28f4d49c, 0xb3418148),  # idx 55  spawn_powerup    ethereal peds
    'MRMAINWARING':                  (0x310971ab, 0xcb973702),  # idx 57  spawn_powerup    panicked peds
    'EVENINGOCCIFER':                (0x35abb7d0, 0xa08da57c),  # idx 86  spawn_powerup    drunk driving
    'FRYFRY':                        (0x1c1fdd92, 0x01dd060c),  # idx 87  spawn_powerup    ped flamethrower
    'OYPOWERUPNO':                   (0x33ca4873, 0x3b005b24),  # idx 89  spawn_powerup    powerup canceller
    'BIGDANGLE':                     (0x1f56cde5, 0x8f213aae),  # idx 90  spawn_powerup    mutant tail
    # Solved 2026-04-10 from Carmageddon Wiki — the final 38 (36 table + 2 special):
    'EZPZKBALLXXEWAZON':             (0x4b054b60, 0x6b6736cb),  # idx 93  gonad_of_death
    'XZSUYYUCWZZZZZWYVYOZVWVXPVQWJZ':(0xa11ee75d, 0xf805eddd),  # idx  0  set_cheat_mode (MP dev)
    'ANGELMOLESTERS':                (0x3964b52b, 0x40c94648),  # idx 32  immortal peds
    'BLOODYARTISTS':                 (0x388de72c, 0x047a8dca),  # idx 61  stick insects
    'CLINTONCO':                     (0x24c99afb, 0xd908f952),  # idx  9  hot rod
    'EASYPEASY':                     (0x26219ff3, 0xfdfd8b46),  # idx 45  slow-motion peds
    'EYEPOPPER':                     (0x26c15553, 0xba19a354),  # idx 31  instant handbrake
    'FARTSUITS':                     (0x28451eeb, 0x30ff63cb),  # idx 58  helium peds
    'FASTBONES':                     (0x244f60c9, 0x31f4fda3),  # idx 80  bonus power slots
    'FISTNESSES':                    (0x2b2be28b, 0x30e0eb7b),  # idx 73  max offensive
    'FURKINELL':                     (0x25205546, 0xcf86a14c),  # idx 47  mega turbo nitrous
    'GOTOINFRARED':                  (0x3003eccb, 0x1d74f36f),  # idx 92  cloaking device
    'HIPPOTART':                     (0x27079773, 0xd1ef511c),  # idx 60  fat bastards
    'LIQUIDLUNGE':                   (0x2d4dd2a9, 0xf01ba696),  # idx 50  oil slick
    'LOADSABONES':                   (0x2a44b628, 0x0c3e7edb),  # idx 82  bonus slots all round
    'MRWOBBLEY':                     (0x26026896, 0x630e5fa9),  # idx 26  jelly suspension
    'NASTYBONES':                    (0x2b0794d3, 0x12927dc9),  # idx 81  bonus offensive slots
    'OOHMESSYMESS':                  (0x3579d64a, 0x3d2e34c3),  # idx 54  dismemberfest
    'OSOFASTSOFAST':                 (0x3815584c, 0x91bbc26e),  # idx 68  double extra power
    'OSONASTYSONASTY':               (0x459732b2, 0xb571e010),  # idx 69  double extra offensive
    'OSOSTRONGSOSTRONG':             (0x4e5f487a, 0x3dc635b8),  # idx 67  double extra armour
    'OSOVERSATILE':                  (0x33950e49, 0x2890738c),  # idx 66  extra everything
    'OSOVERSATILESOVERSATILE':       (0x62871003, 0x79b15084),  # idx 70  double extra everything
    'PIGSMIGHTFLY':                  (0x327ebd75, 0x605a9e3e),  # idx 21  turbo cops
    'RANDYPANDY':                    (0x2998e46d, 0x1360a63e),  # idx 83  random APO
    'RANDYQUAID':                    (0x289c1822, 0x136e9fc3),  # idx 85  random good APO
    'SKEGNESSES':                    (0x29be089d, 0x635ceb96),  # idx 74  max everything
    'STRINGVEST':                    (0x2d72ebb4, 0x5fd4d3ca),  # idx 71  max armour
    'STRONGBONES':                   (0x2f790ebd, 0x2fd87f6b),  # idx 79  bonus armour slots
    'STUFFITUP':                     (0x28f522f1, 0x2f52f8c0),  # idx 30  acme damage magnifier
    'SUPACOCKS':                     (0x252a2e6b, 0x3304d647),  # idx 11  invulnerability
    'SUPAWHIZZ':                     (0x2a439e13, 0x3356c0b0),  # idx 34  mega-turbo
    'SWIFTYSHIFTY':                  (0x373ae69a, 0xef8c998f),  # idx 20  turbo opponents
    'THATSALOTOFARMOUR':             (0x4897982d, 0x06c4fa99),  # idx 75  extra armour slot
    'THATSALOTOFOFFAL':              (0x403afae5, 0x0104a7d2),  # idx 77  extra offensive slot
    'THATSALOTOFPOWER':              (0x44d50f49, 0x010edb42),  # idx 76  extra power slot
    'THATSALOTOFSLOTS':              (0x45c19e5e, 0x011b2cf9),  # idx 78  extra slots all round
    'VASTNESSES':                    (0x2c3be2aa, 0x90e0eb9c),  # idx 72  max power
}

# The HIDDEN cheat — hardcoded inline at VA 0x443c55 of CARMA2_HW.EXE,
# NOT in the cheat table. Toggles sound flags, plays FlaskGone.WAV,
# sets [0x75bc04]=1 which enables car carousel in main menu.
# SOLVED 2026-04-10: MWUCUZYSFUYHTQWXEPVU (from Carmageddon Wiki)
HIDDEN_CHEAT_HASH = (0x616fb8e4, 0x7c6100a8)
HIDDEN_CHEAT_STRING = 'MWUCUZYSFUYHTQWXEPVU'


if __name__ == '__main__':
    # Self-test: verify every KNOWN_CHEATS entry actually hashes to its declared value
    print(f'Self-testing {len(KNOWN_CHEATS)} known cheats:')
    ok = 0
    for name, expected in KNOWN_CHEATS.items():
        actual = carma2_hash(name)
        if actual == expected:
            ok += 1
        else:
            print(f'  [FAIL] {name:30s} expected 0x{expected[0]:08x} 0x{expected[1]:08x}')
            print(f'                                   got      0x{actual[0]:08x} 0x{actual[1]:08x}')
    print(f'  [OK] {ok}/{len(KNOWN_CHEATS)} pass')
