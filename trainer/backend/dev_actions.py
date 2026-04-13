"""
Dev cheat action registry — cheat and gameplay-advantage features only.

The DevTab UI iterates this list and builds widgets via a generic factory.
Adding a new cheat is one entry here + one RPC in agent.js. No UI code.

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
# DEV CHEAT REGISTRY — cheat and gameplay-advantage features only.
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
                   'NO DAMAGE = god mode.'),

    Action('timer_toggle', 'Timer freeze toggle', group='player',
           tooltip='Freezes/unfreezes the race timer. Renders '
                   '"Timer frozen" / "Timer thawed out".'),

    Action('teleport', 'Teleport / reset position', group='player',
           tooltip='Resets car to a fixed world position. Useful if stuck. '
                   'Requires in-race.'),

    # ============================================================
    # CREDITS — money operations
    # ============================================================
    Action('add_credits_p2k', '+2000 credits', group='credits',
           rpc='add_credits', args=[2000],
           tooltip='Adds 2000 to both HUD and purchase credits.'),
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
                   'injection (game-thread-safe). Only works in race.'),

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
    # CAMERAS — unlock hidden camera modes
    # ============================================================
    Action('unlock_all_cameras', 'Unlock all 9 cameras', group='cameras',
           requires=('attached',),
           tooltip='Enables all 9 camera modes, including the documented-but-unused '
                   'Ped Cam and Drone Cam (TEXT.TXT lines 268-269). '
                   'Writes flag arrays at 0x58f600/0x58f610.'),

    # ============================================================
    # DISPLAY — HUD visibility
    # ============================================================
    Action('hud_cycle', 'HUD mode', group='display',
           kind='cycler', state_key='hud_mode',
           state_labels=['Full HUD', 'No HUD', 'Minimal HUD',
                         'mode 3', 'mode 4', 'mode 5'],
           tooltip='Cycles [0x655e54] HUD mode 0..5. Full HUD / No HUD / Minimal HUD.'),

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
    # UTILITY — gameplay convenience
    # ============================================================
    Action('simple_toggle', 'Force race end', group='utility',
           tooltip='Sets [0x74d1a0]=1. Forces you out of the race back '
                   'to the main menu without finishing. Quick escape cheat.'),

    # --- TEST FEATURES (cut from retail — non-functional, kept for RE reference) ---
    # The spectator/lock-on system was cut from the retail build. The functions
    # exist but crash because opponent car structs lack required camera fields
    # (NULL function pointer at +0x40). The Carmashit article confirms the
    # Opponents edit mode is "very crashy." These remain here for future RE work.
    Action('spectator_toggle', 'Spectator camera [CRASHES]', group='test features',
           requires='in_race',
           tooltip='KNOWN CRASH — cut feature from retail binary.\n'
                   'Toggles spectator flag at [0x6a0940] but the camera\n'
                   'positioning code dereferences NULL, crashing the game.\n'
                   'Requires opponent tracking infrastructure that was never\n'
                   'completed in the shipped build.'),
    Action('spectator_next', 'Next opponent [CRASHES]', group='test features',
           requires='in_race',
           tooltip='KNOWN CRASH — requires populated opponent tracking array.'),
    Action('spectator_prev', 'Prev opponent [CRASHES]', group='test features',
           requires='in_race',
           tooltip='KNOWN CRASH — requires populated opponent tracking array.'),
    Action('lockon_target', 'Lock-on target [CRASHES]', group='test features',
           requires='in_race',
           tooltip='KNOWN CRASH — accesses opponent data that is not\n'
                   'properly initialized in the retail binary.'),
    Action('lockon_cycle', 'Cycle lock-on [CRASHES]', group='test features',
           requires='in_race',
           tooltip='KNOWN CRASH — same issue as lock-on target.'),
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
    'main menu',
    'utility',
    'test features',
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
