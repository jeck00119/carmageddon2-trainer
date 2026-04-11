"""
Dev cheat action registry — declarative spec of every dev feature.

The DevTab UI iterates this list and builds widgets via a generic factory.
Adding a new dev feature is one entry here + one RPC in agent.js. No UI code.

Each action's group, label, and tooltip reflect behavior verified by
runtime testing (snap-state diff + rendered-text capture). Actions with
no visible/measurable effect are grouped under 'experimental'.

Requirements semantics:
- 'attached'   — game must be attached
- 'dev_mode'   — cheat_mode must be 0xa11ee75d (dev mode active)
- 'in_race'    — dogame_state == 5 (in-race body)

Kinds:
- 'button'   — single QPushButton, calls rpc once on click
- 'toggle'   — checkable button. The bridge.snap state field tells us "is on"
- 'cycler'   — button + label showing current state
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
    args: list[Any] = field(default_factory=list)
    requires: tuple = ('attached', 'dev_mode')
    state_key: str = ''
    state_labels: list[str] = field(default_factory=list)
    tooltip: str = ''
    input_min: int = 0
    input_max: int = 100
    input_default: int = 0
    danger: bool = False

    def __post_init__(self):
        if not self.rpc:
            self.rpc = self.name


# ============================================================================
# DEV CHEAT REGISTRY — grouped by verified behavior
# Standard Carma2 dev/edit mode features (documented in the Carmashit
# cheat executable article), accessed via direct function calls after
# setting cheat_mode = 0xa11ee75d. Bypasses the typed-code dispatcher
# which is broken on the Steam edition.
# ============================================================================
DEV_ACTIONS = [
    # ============================================================
    # DEV MODE — enable/disable the dev system
    # ============================================================
    Action('dev_enable', 'Enable dev mode', group='dev mode',
           kind='toggle', rpc='dev_enable',
           requires=('attached',), state_key='dev_active',
           tooltip='Writes 0xa11ee75d to [0x68b8e0]. Required for all other dev cheats.'),

    Action('dev_disable_btn', 'Disable dev mode', group='dev mode',
           rpc='dev_disable', requires=('attached',)),

    Action('dev_menu_cycle', 'Edit mode toggle', group='dev mode',
           rpc='dev_menu_cycle',
           tooltip='Cycles [0x67c468] between 0 (Options) and 1 (Cheat). '
                   'Renders "Edit mode: Options" / "Edit mode: Cheat".'),

    Action('credits_display', 'Credits', group='dev mode',
           kind='display', state_key='credits',
           requires=('attached',)),

    # ============================================================
    # PLAYER — actions that affect your car
    # ============================================================
    Action('instant_repair', 'Instant repair', group='player',
           tooltip='Repairs your car. Renders "Instant repair" + sound 4550.'),

    Action('damage_cycle', 'Cycle damage state', group='player',
           kind='cycler', state_key='damage_state',
           state_labels=['NO DAMAGE', 'NO CRUSHAGE', 'NO WASTAGE',
                         'NO DAMAGE+CRUSHAGE', 'FULLY VULNERABLE',
                         'Unknown (5)', 'Unknown (6)', 'Unknown (7)'],
           tooltip='Cycles [0x67c498] (damage_state) 0..7. '
                   'Renders NO DAMAGE / NO CRUSHAGE / etc.'),

    Action('timer_toggle', 'Timer freeze toggle', group='player',
           tooltip='Freezes/unfreezes the race timer. Renders '
                   '"Timer frozen" / "Timer thawed out".'),

    Action('teleport', 'Teleport / reset position', group='player',
           tooltip='Resets car to a fixed world position (pushes -155, +7.13, -54). '
                   'Requires in-race. Position change not captured in snap.'),

    # ============================================================
    # CREDITS — money operations
    # ============================================================
    Action('add_credits_p2k', '+2000 credits', group='credits',
           rpc='add_credits', args=[2000],
           tooltip='Adds 2000 to both HUD and purchase credits. '
                   'Renders "2000 credits" + sound 8012.'),
    Action('add_credits_p5k', '+5000 credits', group='credits',
           rpc='add_credits', args=[5000],
           tooltip='Adds 5000 to both credit addresses.'),
    Action('add_credits_m2k', '-2000 credits', group='credits',
           rpc='add_credits', args=[-2000],
           tooltip='Subtracts 2000. Negative delta is race-y — '
                   'may crash if it hits mid-write timing.'),
    Action('add_credits_m5k', '-5000 credits', group='credits',
           rpc='add_credits', args=[-5000],
           tooltip='Subtracts 5000. See m2k warning.'),
    Action('set_credits', 'Set credits to', group='credits',
           kind='input', rpc='set_credits',
           input_min=0, input_max=999_999, input_default=10000,
           tooltip='Direct write to both [0x676920] (HUD) and '
                   '[0x75bb80] (purchase).'),
    Action('set_credits_max', 'MAX credits', group='credits',
           rpc='set_credits', args=[999999],
           tooltip='Set credits to 999999.'),
    Action('set_credits_zero', 'Drain credits', group='credits',
           rpc='set_credits', args=[0], danger=True,
           tooltip='Set credits to 0.'),

    # ============================================================
    # POWERUPS — spawn any powerup
    # ============================================================
    Action('spawn_powerup', 'Spawn powerup ID', group='powerups',
           kind='input', rpc='spawn_powerup',
           input_min=0, input_max=98, input_default=34,
           requires=('attached', 'dev_mode', 'in_race'),
           tooltip='Fires any of the 89 cheat-table powerups via hash '
                   'injection (game-thread-safe). Only works in race '
                   '(dogame_state=5).'),

    # ============================================================
    # PHYSICS — gravity and special weapons
    # ============================================================
    Action('gravity_toggle', 'Gravity toggle', group='physics',
           kind='cycler', state_key='gravity',
           state_labels=['Back down to Earth', 'We have lift off!!'],
           tooltip='Toggles [0x68b910] gravity flag. Renders '
                   '"We have lift off!!" / "Back down to Earth".'),

    Action('gonad_of_death', 'Steel Gonad O\' Death', group='physics',
           rpc='gonad_of_death',
           tooltip='Transforms the car into a giant indestructible ball. '
                   'Cheat handler at 0x444f10 (EZPZKBALLXXEWAZON).'),

    # ============================================================
    # CAMERAS — camera modes and spectator
    # ============================================================
    Action('unlock_all_cameras', 'Unlock all 9 cameras', group='cameras',
           requires=('attached',),
           tooltip='Enables all 9 camera modes, including the documented-but-unused '
                   'Ped Cam and Drone Cam (referenced in TEXT.TXT lines 268-269). '
                   'Modes: Standard, Panning, Action-tracking, Manual, Rigid, '
                   'Ped Cam, Drone Cam, Reversing, Internal. Writes flag arrays '
                   'at 0x58f600/0x58f610.'),

    # NOTE: internal name is 'lighting_profiler' but the function at that VA
    # actually drives the camera mode cycler at runtime. Name kept for history.
    Action('lighting_profiler', 'Camera mode cycler', group='cameras',
           requires=('attached', 'dev_mode', 'in_race'),
           tooltip='Cycles through enabled camera modes (4 default, 9 after unlock). '
                   'Requires in-race state.'),

    Action('spectator_toggle', 'Spectator camera', group='cameras',
           kind='cycler', state_key='spec_active',
           state_labels=['off', 'ON'],
           tooltip='Toggles [0x6a0940] spectator flag. Shows opponent cameras.'),
    Action('spectator_next', 'Spec: next opponent', group='cameras',
           tooltip='Next spectator target (bound to "[" in dev mode). '
                   'Requires spectator to be ON.'),
    Action('spectator_prev', 'Spec: prev opponent', group='cameras',
           tooltip='Previous spectator target (bound to "]" in dev mode). '
                   'Requires spectator to be ON.'),

    # ============================================================
    # DISPLAY — HUD and rendering toggles
    # ============================================================
    Action('hud_cycle', 'HUD mode', group='display',
           kind='cycler', state_key='hud_mode',
           state_labels=['Full HUD', 'No HUD', 'Minimal HUD',
                         'mode 3', 'mode 4', 'mode 5'],
           tooltip='Cycles [0x655e54] HUD mode 0..5. Renders '
                   'Full HUD / No HUD / Minimal HUD.'),

    Action('shadow_toggle', 'Shadow type', group='display',
           kind='cycler', state_key='shadow_type',
           state_labels=['Translucent', 'Solid'],
           tooltip='Toggles [0x6a23d8] 0↔1 (Solid ↔ Translucent shadows).'),
    Action('shadow_3state', 'Shadow 3-state', group='display',
           kind='cycler', state_key='shadow_3st',
           state_labels=['mode 0', 'mode 1', 'mode 2', 'mode 3'],
           tooltip='Cycles [0x65fdc8] 0..3 (shadow rendering mode).'),

    # ============================================================
    # OPPONENTS — item/opponent cycler (F4 dev function)
    # ============================================================
    Action('item_next', 'Opponent next', group='opponents',
           requires=('attached', 'dev_mode', 'in_race'),
           tooltip='Cycles to next opponent (F4 mask=0). '
                   'Effect not captured in snap — may depend on race state.'),
    Action('item_prev', 'Opponent prev', group='opponents',
           requires=('attached', 'dev_mode', 'in_race'),
           tooltip='Cycles to previous opponent (F4 mask=4).'),
    Action('item_sort', 'Opponent sort', group='opponents',
           requires=('attached', 'dev_mode', 'in_race'),
           tooltip='Sorts opponent list by distance (F4 mask=1). '
                   'Effect not captured in snap.'),

    # ============================================================
    # DEBUG — debug output triggers
    # ============================================================
    Action('visual_toggle_9', 'AI debug log', group='debug',
           tooltip='Triggers opponent AI log messages like '
                   '"JENNY TAYLIA: Ha! Bet you weren\'t expecting that!"'),
    Action('dev_check_9', 'AI state checker', group='debug',
           tooltip='Compares [0x655f54] with game state struct. '
                   'No visible effect observed.'),

    # ============================================================
    # MAIN MENU — fires only from the main menu
    # ============================================================
    Action('hidden_cheat', 'Unlock all cars & races', group='main menu',
           requires=('attached',),
           tooltip='Unlocks all cars and all races (except Ron Dumpster). '
                   'Plays FlaskGone.WAV for audible confirmation. '
                   'ONLY fires from the main menu (not in race). '
                   'Internal: MWUCUZYSFUYHTQWXEPVU — sets flag [0x75bc04]=1.'),

    # ============================================================
    # EXPERIMENTAL — effect unclear or unverified
    # ============================================================
    Action('simple_toggle', 'Force race end', group='experimental',
           tooltip='Sets [0x74d1a0]=1. Runtime-verified: forces you out '
                   'of the race back to the main menu (dogame_state 5→2). '
                   'Bound to "8" key in dev mode.'),

    Action('reset_sound_state', 'Reset sound state', group='experimental',
           tooltip='Calls 0x502e00 — restores 12-byte sound/color state from '
                   'defaults (loops 0..0xc, copies from [0x762130]). '
                   'No visible effect observed.'),

    Action('quick_save', 'Quick-save snapshot', group='experimental',
           requires=('attached', 'dev_mode', 'in_race'),
           tooltip='Calls 0x5032a0 — saves [0x761ce8] to [0x6aaa34] '
                   '(some game state buffer). Purpose unclear. '
                   'Crashes outside race (NULL struct at [0x762438]+0x210).'),

    Action('demo_file_load', 'Load DEMOFILE.TXT', group='experimental',
           tooltip='Would load DEMOFILE.TXT from disk — file does not '
                   'exist in retail, so no effect. Kept for completeness.'),
]


# Display group order
GROUP_ORDER = [
    'dev mode',
    'player',
    'credits',
    'powerups',
    'physics',
    'cameras',
    'display',
    'opponents',
    'debug',
    'main menu',
    'experimental',
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
