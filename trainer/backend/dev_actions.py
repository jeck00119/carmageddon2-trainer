"""
Dev cheat action registry — declarative spec of every dev feature.

The DevTab UI iterates this list and builds widgets via a generic factory.
Adding a new dev feature is one entry here + one RPC in agent.js. No UI code.

Labels verified 2026-04-10 via autonomous truth-table test (test_dev_truth.py).
Each label matches the ACTUAL text the game renders when the fn fires.

Requirements semantics:
- 'attached'   — game must be attached
- 'dev_mode'   — cheat_mode must be 0xa11ee75d (dev mode active)
- 'in_race'    — dogame_state == 5 (in-race body; game_state stays 0 during normal SP racing)

Kinds:
- 'button'   — single QPushButton, calls rpc once on click
- 'toggle'   — checkable button. The bridge.snap state field tells us "is on"
- 'cycler'   — button + label showing current state (e.g. damage state, HUD mode)
- 'input'    — QSpinBox + button. Args = [spinbox_value]
- 'display'  — read-only label, no button (live state from snap)
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Action:
    name: str            # unique id (matches rpc name unless overridden)
    label: str           # button text
    group: str           # group title (UPPERCASE in UI)
    rpc: str = ''        # name of bridge.dev_call rpc; defaults to `name`
    kind: str = 'button' # button | toggle | cycler | input | display
    args: list[Any] = field(default_factory=list)   # static args to pass
    requires: tuple = ('attached', 'dev_mode')      # prereqs
    state_key: str = ''  # snap field for cycler/toggle/display state
    state_labels: list[str] = field(default_factory=list)  # cycler label list
    tooltip: str = ''
    input_min: int = 0
    input_max: int = 100
    input_default: int = 0
    danger: bool = False  # red border / confirm

    def __post_init__(self):
        if not self.rpc:
            self.rpc = self.name


# ============================================================================
# DEV CHEAT REGISTRY — verified 2026-04-10 via truth-table test
# Order = display order. Group field controls grouping.
# ============================================================================
DEV_ACTIONS = [
    # ----- Dev Mode (always shown, never gated on dev_mode itself) -----
    Action('dev_enable', 'Enable dev mode', group='dev mode',
           kind='toggle', rpc='dev_enable',
           requires=('attached',), state_key='dev_active',
           tooltip='Writes 0xa11ee75d to [0x68b8e0]. Required for all other dev cheats.'),

    Action('dev_disable_btn', 'Disable dev mode', group='dev mode',
           rpc='dev_disable', requires=('attached',)),

    Action('dev_menu_cycle', 'Edit mode toggle', group='dev mode',
           rpc='dev_menu_cycle',
           tooltip='Cycles Options ↔ Cheat. Verified: renders "Edit mode: Options/Cheat".'),

    Action('credits_display', 'Credits', group='dev mode',
           kind='display', state_key='credits',
           requires=('attached',)),

    # ----- Player actions (VERIFIED in-race) -----
    Action('instant_repair', 'Instant repair', group='player',
           tooltip='Verified: renders "Instant repair" text + sound 4550.'),

    Action('damage_cycle', 'Cycle damage state', group='player',
           kind='cycler', state_key='damage_state',
           state_labels=['NO DAMAGE', 'NO CRUSHAGE', 'NO WASTAGE',
                         'NO DAMAGE+CRUSHAGE', 'FULLY VULNERABLE',
                         'Unknown (5)', 'Unknown (6)', 'Unknown (7)'],
           tooltip='Verified: cycles damage_state 0..7. Renders NO DAMAGE / NO CRUSHAGE / etc.'),

    Action('timer_toggle', 'Timer freeze toggle', group='player',
           tooltip='Verified: renders "Timer frozen" / "Timer thawed out".'),

    Action('teleport', 'Teleport / reset position', group='player',
           tooltip='Resets car to a fixed position. No crash text — may need race state to see effect.'),

    # ----- Credits (VERIFIED) -----
    Action('add_credits_p2k', '+2000 credits', group='credits',
           rpc='add_credits', args=[2000],
           tooltip='Verified: renders "2000 credits" + sound 8012.'),
    Action('add_credits_p5k', '+5000 credits', group='credits',
           rpc='add_credits', args=[5000],
           tooltip='Verified: renders "5000 credits".'),
    Action('add_credits_m2k', '-2000 credits', group='credits',
           rpc='add_credits', args=[-2000]),
    Action('add_credits_m5k', '-5000 credits', group='credits',
           rpc='add_credits', args=[-5000]),
    Action('set_credits', 'Set credits to', group='credits',
           kind='input', rpc='set_credits',
           input_min=0, input_max=999_999, input_default=10000,
           tooltip='Direct write to both [0x676920] (HUD) and [0x75bb80] (purchase).'),
    Action('set_credits_max', 'MAX credits', group='credits',
           rpc='set_credits', args=[999999],
           tooltip='Set credits to 999999.'),
    Action('set_credits_zero', 'Drain credits', group='credits',
           rpc='set_credits', args=[0], danger=True,
           tooltip='Set credits to 0.'),

    # ----- Powerup spawner -----
    Action('spawn_powerup', 'Spawn powerup ID', group='powerups',
           kind='input', rpc='spawn_powerup',
           input_min=0, input_max=98, input_default=34,
           requires=('attached', 'dev_mode', 'in_race'),
           tooltip='Uses hash injection for 89 cheat-table IDs (game-thread-safe). '
                   'Only works in race (dogame_state=5).'),

    # ----- Movement (VERIFIED) -----
    Action('gravity_toggle', 'Gravity toggle', group='movement',
           kind='cycler', state_key='gravity',
           state_labels=['Back down to Earth', 'We have lift off!!'],
           tooltip='Verified: toggles [0x68b910]. Renders lift off / back to earth text.'),

    Action('gonad_of_death', 'Steel Gonad O\' Death', group='movement',
           rpc='gonad_of_death',
           tooltip='Cheat handler 0x444f10.'),

    # ----- Lock-on targeting (NEW — discovered 2026-04-10 truth test) -----
    Action('dev_q', 'Lock on target', group='lock-on',
           tooltip='Verified: renders "LOCKED ONTO <opponent name>". Selects a target.'),
    Action('dev_w', 'Lock on (cycle)', group='lock-on',
           tooltip='Verified: renders "LOCKED ONTO <different opponent>". Cycles target.'),

    # ----- Upgrade purchase (NEW — discovered 2026-04-10 truth test) -----
    Action('dev_slash', 'Buy upgrade: Armour', group='upgrades',
           tooltip='Reads credits from [0x75bb80] (NOT [0x676920]). '
                   'Cost = 50000. Renders "CAN\'T AFFORD IT" or upgrades [0x75d4d4].'),
    Action('dev_semi', 'Buy upgrade: Power', group='upgrades',
           tooltip='Same system — buys power upgrade from [0x75bb80] credits.'),
    Action('dev_period', 'Buy upgrade: Offensive', group='upgrades',
           tooltip='Same system — buys offensive upgrade from [0x75bb80] credits.'),

    # ----- Spectator camera (VERIFIED) -----
    Action('spectator_toggle', 'Spectator camera', group='spectator',
           kind='cycler', state_key='spec_active',
           state_labels=['off', 'ON'],
           tooltip='Verified: toggles [0x6a0940]. Spec_active changes in snap.'),
    Action('spectator_next', 'Spec: next', group='spectator',
           tooltip='Next spectator target.'),
    Action('spectator_prev', 'Spec: prev', group='spectator',
           tooltip='Previous spectator target.'),

    # ----- HUD / display (VERIFIED) -----
    Action('hud_cycle', 'HUD mode', group='hud',
           kind='cycler', state_key='hud_mode',
           state_labels=['Full HUD', 'No HUD', 'Minimal HUD',
                         'mode 3', 'mode 4', 'mode 5'],
           tooltip='Verified: cycles hud_mode 0..5. Renders Full HUD / No HUD / Minimal HUD.'),

    Action('unlock_all_cameras', 'Unlock all 9 cameras', group='hud',
           requires=('attached',),
           tooltip='Enables all 9 camera modes: Standard, Panning, Action-tracking, Manual, '
                   'Rigid, Ped Cam, Drone Cam, Reversing, Internal. Writes flag arrays at '
                   '0x58f600/0x58f610. Default: only 4 of 9 enabled.'),

    Action('lighting_profiler', 'Camera mode cycler', group='hud',
           requires=('attached', 'dev_mode', 'in_race'),
           tooltip='Cycles through enabled camera modes (4 default, 9 after unlock). '
                   'Crashes outside race.'),

    Action('minimap_toggle', 'MiniMap toggle', group='hud',
           tooltip='Sound 8005 confirmed. Visual effect not captured in snap.'),

    Action('recovery_cost', 'Recovery Cost display', group='hud',
           tooltip='Verified: renders "Recovery Cost: 1000".'),

    # ----- Sound / state -----
    Action('sound_subsystem', 'Sound subsystem toggle', group='sound',
           kind='cycler', state_key='sound_master',
           state_labels=['OFF (muted)', 'ON'],
           tooltip='Verified: toggles [0x762328] sound_master + [0x7a06c0] cd_audio.'),
    Action('reset_sound_state', 'Reset sound state', group='sound',
           tooltip='Restores 12-byte state from defaults.'),
    Action('quick_save', 'Quick-save snapshot', group='sound',
           requires=('attached', 'dev_mode', 'in_race'),
           tooltip='Crashes outside race (NULL struct at [0x762438]+0x210).'),

    # ----- Hidden cheat (menu only) -----
    Action('hidden_cheat', 'Hidden cheat (sound toggle)', group='hidden',
           requires=('attached',),
           tooltip='Verified: toggles sound_master [0x762328] and cd_audio [0x7a06c0]. '
                   'One-shot sets mystery flag [0x75bc04]=1. Plays FlaskGone.WAV. '
                   'ONLY works from MENU (not in race).'),

    # ----- AI debug (discovered 2026-04-10 — triggers opponent AI logging) -----
    Action('visual_toggle_9', 'AI debug log', group='ai debug',
           tooltip='Verified: triggers opponent AI messages like '
                   '"JENNY TAYLIA: Ha! Bet you weren\'t expecting that!"'),
    Action('dev_check_9', 'AI state checker', group='ai debug',
           tooltip='Triggers with specific F12 mode.'),

    # ----- Misc (sound-only or no visible effect in trace) -----
    Action('simple_toggle', 'Simple flag set', group='misc',
           tooltip='One-shot sets [0x74d1a0]=1. Not a toggle — stays set.'),
    Action('visual_toggle_7', 'Checkpoint finder toggle', group='misc',
           tooltip='Verified: string IDs 254/255 = "CHECKPOINT FINDER TURNED OFF/ON". '
                   'Shows path to next checkpoint.'),
    Action('shadow_toggle', 'Shadow type', group='misc',
           kind='cycler', state_key='shadow_type',
           state_labels=['Translucent', 'Solid'],
           tooltip='Verified: toggles [0x6a23d8] 0↔1 (Solid ↔ Translucent).'),
    Action('shadow_3state', 'Shadow 3-state', group='misc',
           kind='cycler', state_key='shadow_3st',
           state_labels=['mode 0', 'mode 1', 'mode 2', 'mode 3'],
           tooltip='Verified: cycles [0x65fdc8] 0..3.'),
    Action('zoom_incr', 'Zoom / LOD +', group='misc',
           kind='cycler', state_key='zoom_lod',
           state_labels=[str(i) for i in range(9)],
           tooltip='Verified: increments [0x68be38] (0..8).'),
    Action('zoom_decr', 'Zoom / LOD -', group='misc',
           tooltip='Decrements [0x68be38].'),
    Action('camera_step', 'Camera step', group='misc',
           requires=('attached', 'dev_mode', 'in_race'),
           tooltip='Increments camera position counter. Needs in-race (cam_max=0 in menu).'),
    Action('demo_file_load', 'Load DEMOFILE.TXT', group='misc',
           tooltip='Loads demo file from disk. File does not exist in retail — no effect.'),
    Action('item_next', 'Opponent next', group='misc',
           requires=('attached', 'dev_mode', 'in_race'),
           tooltip='Verified: cycles [0x7447f0]. Needs in-race (item_count=0 in menu).'),
    Action('item_prev', 'Opponent prev', group='misc',
           requires=('attached', 'dev_mode', 'in_race')),
    Action('item_sort', 'Opponent sort', group='misc',
           requires=('attached', 'dev_mode', 'in_race')),
]


# Display group order
GROUP_ORDER = [
    'dev mode',
    'player',
    'credits',
    'powerups',
    'movement',
    'lock-on',
    'upgrades',
    'spectator',
    'hud',
    'hidden',
    'sound',
    'ai debug',
    'misc',
]


def actions_by_group():
    """Yield (group_name, [actions]) in display order."""
    for group in GROUP_ORDER:
        actions = [a for a in DEV_ACTIONS if a.group == group]
        if actions:
            yield group, actions


def find_action(name: str) -> Action | None:
    for a in DEV_ACTIONS:
        if a.name == name:
            return a
    return None
