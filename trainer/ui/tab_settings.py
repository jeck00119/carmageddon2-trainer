"""Game Settings tab — graphics, display, and game world config editor."""
import os
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QGroupBox,
                                QHBoxLayout, QLabel, QPushButton, QScrollArea,
                                QSlider, QSpinBox, QVBoxLayout, QWidget)

from backend.config_io import (read_dgvoodoo, read_options_txt,
                                write_dgvoodoo, write_options_txt)
from ui.style import TEXT_DIM, WARN


@dataclass
class Setting:
    key: str
    file: str           # 'dgv' or 'opt'
    section: str        # INI section (dgv only)
    widget: str         # 'combo', 'check', 'slider', 'spin'
    options: list       # [(display, config_value), ...] for combos
    default: str
    group: str
    label: str
    tip: str = ''       # tooltip


SETTINGS = [
    # --- DISPLAY ---
    Setting('FullScreenMode', 'dgv', 'General', 'combo',
            [('Fullscreen', 'true'), ('Windowed', 'false')],
            'true', 'DISPLAY', 'Display mode',
            'Fullscreen takes over the monitor. Windowed shows a resizable window.\n'
            'Press Alt+Enter in-game to toggle between them.'),
    Setting('ForceVerticalSync', 'dgv', 'Glide', 'check', [], 'true',
            'DISPLAY', 'VSync',
            'Synchronize frame rate with your monitor refresh rate.\n'
            'Prevents screen tearing but may add slight input lag.'),
    Setting('KeepWindowAspectRatio', 'dgv', 'General', 'check', [], 'true',
            'DISPLAY', 'Keep aspect ratio',
            'Keep the window at the game\'s native 4:3 aspect ratio.\n'
            'Uncheck to allow any window shape (image may stretch).'),
    Setting('FPSLimit', 'dgv', 'GeneralExt', 'spin', [], '0',
            'DISPLAY', 'FPS limit',
            'Cap the frame rate. 0 = unlimited.\n'
            'Useful if the game runs too fast on modern hardware.'),
    Setting('Brightness', 'dgv', 'General', 'spin', [(0, 200, '')], '100',
            'DISPLAY', 'Brightness',
            'Display brightness. 100 = default.'),
    Setting('Color', 'dgv', 'General', 'spin', [(0, 200, '')], '100',
            'DISPLAY', 'Color saturation',
            'Color intensity. 100 = default. Lower = more desaturated.'),
    Setting('Contrast', 'dgv', 'General', 'spin', [(0, 200, '')], '100',
            'DISPLAY', 'Contrast',
            'Display contrast. 100 = default.'),

    # --- GRAPHICS ---
    Setting('Resolution', 'dgv', 'Glide', 'combo',
            [('Native (640x480)', 'unforced'),
             ('Monitor resolution', 'max'),
             ('2x integer scale', 'max_isf'),
             ('1080p max', 'max_fhd'),
             ('1440p max', 'max_qhd'),
             ('2x (1280x960)', '2x'),
             ('4x (2560x1920)', '4x')],
            'max', 'GRAPHICS', 'Render resolution',
            'Internal rendering resolution.\n'
            '"Monitor resolution" = sharpest, uses your display\'s native pixels.\n'
            '"Native" = original 640x480 for an authentic 1998 look.'),
    Setting('Antialiasing', 'dgv', 'Glide', 'combo',
            [('Off', 'off'),
             ('2x MSAA', '2x'), ('4x MSAA', '4x'),
             ('8x MSAA', '8x'), ('16x MSAA', '16x')],
            '4x', 'GRAPHICS', 'Antialiasing',
            'Multisample anti-aliasing — smooths jagged edges on 3D geometry.\n'
            '4x is a good balance of quality and performance.\n'
            'If you see rendering artifacts, try lowering or turning off.'),
    Setting('TMUFiltering', 'dgv', 'Glide', 'combo',
            [('Default', 'appdriven'),
             ('Point (sharp pixels)', 'pointsampled'),
             ('Bilinear (smooth)', 'bilinear')],
            'bilinear', 'GRAPHICS', 'Texture filtering',
            'How textures are sampled when viewed at an angle.\n'
            '"Default" = the game\'s original filtering.\n'
            '"Point" = sharp/blocky pixels. "Bilinear" = smooth blending.'),
    Setting('Resampling', 'dgv', 'GeneralExt', 'combo',
            [('Nearest', 'pointsampled'),
             ('Bilinear', 'bilinear'),
             ('Bicubic', 'bicubic'),
             ('Lanczos-2 (recommended)', 'lanczos-2'),
             ('Lanczos-3', 'lanczos-3')],
            'lanczos-2', 'GRAPHICS', 'Upscale filter',
            'Filter used to scale the rendered image to your screen.\n'
            'Only relevant when render resolution differs from your monitor.\n'
            'Lanczos-2 gives the best sharpness for most setups.'),
    Setting('RoadTexturingLevel', 'opt', '', 'combo',
            [('Off', '0'), ('On', '1')],
            '1', 'GRAPHICS', 'Road textures',
            'Texture mapping on road surfaces. Off = solid color only.'),
    Setting('WallTexturingLevel', 'opt', '', 'combo',
            [('Off', '0'), ('Linear', '1'), ('Perspective-correct', '2')],
            '2', 'GRAPHICS', 'Wall textures',
            'Texture mapping on walls and buildings.\n'
            '"Perspective-correct" reduces texture warping at angles.'),
    Setting('CarTexturingLevel', 'opt', '', 'combo',
            [('Off', '0'), ('Linear', '1'), ('Perspective-correct', '2')],
            '2', 'GRAPHICS', 'Car textures',
            'Texture mapping on vehicles.\n'
            '"Perspective-correct" reduces warping on angled surfaces.'),
    Setting('ShadowLevel', 'opt', '', 'combo',
            [('None', '0'), ('Cars only', '1'),
             ('Everything (cars + peds + props)', '3')],
            '3', 'GRAPHICS', 'Shadows',
            'Which objects cast shadows on the ground.'),
    Setting('SmokeOn', 'opt', '', 'check', [], '1',
            'GRAPHICS', 'Smoke effects',
            'Show tire smoke, exhaust, and explosion particles.'),
    Setting('SkyTextureOn', 'opt', '', 'check', [], '1',
            'GRAPHICS', 'Sky',
            'Show the sky texture. Off = solid color background.'),
    Setting('DepthCueingOn', 'opt', '', 'check', [], '1',
            'GRAPHICS', 'Fog',
            'Fade distant objects into the background.\n'
            'Hides pop-in at the draw distance limit.'),

    # --- GAMEPLAY ---
    Setting('SkillLevel', 'opt', '', 'combo',
            [('Easy', '0'), ('Normal', '1'), ('Hard', '2')],
            '0', 'GAMEPLAY', 'Difficulty',
            'AI opponent difficulty level.'),
    Setting('GoreLevel', 'opt', '', 'combo',
            [('Maximum', '0'), ('Medium', '1'), ('Minimal', '2')],
            '0', 'GAMEPLAY', 'Gore level',
            'Amount of blood and giblets.\n'
            '0 = stomach-churning, 2 = nice and fluffy.'),
    Setting('Yon', 'opt', '', 'slider', [(20, 200, 10, 20)], '100.000000',
            'GAMEPLAY', 'Draw distance',
            'How far you can see in the game world.\n'
            'Higher = see further, but values above 50 may cause AI to behave oddly.'),
    Setting('AccessoryRendering', 'opt', '', 'check', [], '1',
            'GAMEPLAY', 'Scenery props',
            'Show destructible props like signs, fences, and cones.\n'
            'Also affects collision with these objects.'),
    Setting('AnimalsOn', 'opt', '', 'check', [], '1',
            'GAMEPLAY', 'Animals',
            'Show animals in the game world (cows, dogs, etc).'),
    Setting('DronesOn', 'opt', '', 'check', [], '1',
            'GAMEPLAY', 'Traffic',
            'Show civilian drone cars driving around the level.'),
    Setting('MinesOn', 'opt', '', 'check', [], '1',
            'GAMEPLAY', 'Mines',
            'Enable mine pickups and deployment in levels.'),
    Setting('FlameThrowerOn', 'opt', '', 'check', [], '1',
            'GAMEPLAY', 'Ped flamethrowers',
            'Some pedestrians carry flamethrowers and fight back.'),
    Setting('MiniMapVisible', 'opt', '', 'check', [], '0',
            'GAMEPLAY', 'Minimap',
            'Show the minimap on the HUD.'),

    # --- AUDIO ---
    Setting('EVolume', 'opt', '', 'slider', [(0, 255, 5, 25)], '220',
            'AUDIO', 'Effects volume',
            'Volume for sound effects (impacts, engine, explosions).\n'
            '0 = silent, 255 = maximum.'),
    Setting('MVolume', 'opt', '', 'slider', [(0, 255, 5, 25)], '255',
            'AUDIO', 'Music volume',
            'Volume for background music.\n'
            '0 = silent, 255 = maximum.'),
    Setting('SoundDetailLevel', 'opt', '', 'combo',
            [('Minimal', '0'), ('Medium', '1'), ('Full', '2')],
            '2', 'AUDIO', 'Sound detail',
            'How many objects produce sounds.\n'
            '"Full" = most things make a sound. "Minimal" = only essential sounds.'),
    Setting('AmbientSound', 'opt', '', 'check', [], '1',
            'AUDIO', 'Ambient sounds',
            'Environmental background audio (wind, birds, etc).'),
]


class SettingsTab(QWidget):
    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge
        self.game_dir = os.path.dirname(bridge.game_path) if bridge.game_path else None
        self.widgets: dict[str, QWidget] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(10)

        # Warning banner
        warn = QLabel('Changes take effect on next game launch')
        warn.setStyleSheet(f'color: {WARN}; font-style: italic; font-size: 10pt;')
        outer.addWidget(warn)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget()
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(0, 0, 0, 0)
        inner_lay.setSpacing(14)

        # Build groups
        groups: dict[str, QFormLayout] = {}
        for s in SETTINGS:
            if s.group not in groups:
                box = QGroupBox(s.group)
                form = QFormLayout(box)
                groups[s.group] = form
                inner_lay.addWidget(box)
            self._add_widget(groups[s.group], s)

        # Buttons
        btn_row = QHBoxLayout()
        btn_reset = QPushButton('Reset to defaults')
        btn_reset.clicked.connect(self._reset_defaults)
        btn_row.addWidget(btn_reset)
        btn_row.addStretch()
        btn_apply = QPushButton('Apply')
        btn_apply.setObjectName('primary')
        btn_apply.setMinimumHeight(36)
        btn_apply.clicked.connect(self._apply)
        btn_row.addWidget(btn_apply)
        inner_lay.addLayout(btn_row)
        inner_lay.addStretch()

        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

        # Load current values
        self._load()

    def _add_widget(self, form: QFormLayout, s: Setting):
        if s.widget == 'combo':
            w = QComboBox()
            for display, _ in s.options:
                w.addItem(display)
            if s.tip:
                w.setToolTip(s.tip)
            self.widgets[s.key] = w
            form.addRow(s.label + ':', w)
        elif s.widget == 'check':
            w = QCheckBox()
            if s.tip:
                w.setToolTip(s.tip)
            self.widgets[s.key] = w
            form.addRow(s.label + ':', w)
        elif s.widget == 'slider':
            # options = [(min, max, step, tick)] or empty for defaults
            smin, smax, sstep, stick = (20, 200, 10, 20)
            if s.options:
                smin, smax, sstep, stick = s.options[0]
            row = QHBoxLayout()
            w = QSlider(Qt.Horizontal)
            w.setMinimum(smin)
            w.setMaximum(smax)
            w.setSingleStep(sstep)
            w.setTickInterval(stick)
            w.setTickPosition(QSlider.TicksBelow)
            lbl = QLabel(str(smin))
            lbl.setMinimumWidth(30)
            w.valueChanged.connect(lambda v, l=lbl: l.setText(str(v)))
            row.addWidget(w, 1)
            row.addWidget(lbl)
            if s.tip:
                w.setToolTip(s.tip)
            self.widgets[s.key] = w
            form.addRow(s.label + ':', row)
        elif s.widget == 'spin':
            w = QSpinBox()
            # options = [(min, max, special_text)] or empty for FPS default
            if s.options:
                smin, smax, special = s.options[0]
                w.setMinimum(smin)
                w.setMaximum(smax)
                if special:
                    w.setSpecialValueText(special)
            else:
                w.setMinimum(0)
                w.setMaximum(240)
                w.setSpecialValueText('Unlimited')
            if s.tip:
                w.setToolTip(s.tip)
            self.widgets[s.key] = w
            form.addRow(s.label + ':', w)

    def _load(self):
        if not self.game_dir:
            return
        dgv = read_dgvoodoo(self.game_dir)
        opt = read_options_txt(self.game_dir)
        for s in SETTINGS:
            w = self.widgets.get(s.key)
            if not w:
                continue
            if s.file == 'dgv':
                val = dgv.get(s.section, {}).get(s.key, s.default)
            else:
                val = opt.get(s.key, s.default)
            self._set_widget(s, w, val)

    def _set_widget(self, s: Setting, w, val: str):
        if s.widget == 'combo':
            for i, (_, cfg_val) in enumerate(s.options):
                if cfg_val == val:
                    w.setCurrentIndex(i)
                    return
            w.setCurrentIndex(0)
        elif s.widget == 'check':
            w.setChecked(val in ('true', '1', 'True'))
        elif s.widget == 'slider':
            try:
                w.setValue(int(float(val)))
            except (ValueError, TypeError):
                w.setValue(int(float(s.default)))
        elif s.widget == 'spin':
            try:
                w.setValue(int(val))
            except (ValueError, TypeError):
                w.setValue(0)

    def _get_widget_value(self, s: Setting) -> str:
        w = self.widgets.get(s.key)
        if not w:
            return s.default
        if s.widget == 'combo':
            idx = w.currentIndex()
            if 0 <= idx < len(s.options):
                return s.options[idx][1]
            return s.default
        elif s.widget == 'check':
            if s.file == 'opt':
                return '1' if w.isChecked() else '0'
            return 'true' if w.isChecked() else 'false'
        elif s.widget == 'slider':
            return f'{w.value():.6f}'
        elif s.widget == 'spin':
            return str(w.value())
        return s.default

    def _apply(self):
        if not self.game_dir:
            self.bridge.log.emit('No game path set')
            return
        dgv_changes: dict[str, dict[str, str]] = {}
        opt_changes: dict[str, str] = {}
        for s in SETTINGS:
            val = self._get_widget_value(s)
            if s.file == 'dgv':
                dgv_changes.setdefault(s.section, {})[s.key] = val
            else:
                opt_changes[s.key] = val

        ok1 = write_dgvoodoo(self.game_dir, dgv_changes) if dgv_changes else True
        ok2 = write_options_txt(self.game_dir, opt_changes) if opt_changes else True

        if ok1 and ok2:
            self.bridge.log.emit('Settings saved — restart the game to apply')
        else:
            self.bridge.log.emit('Failed to save some settings (check file permissions)')

    def _reset_defaults(self):
        for s in SETTINGS:
            w = self.widgets.get(s.key)
            if w:
                self._set_widget(s, w, s.default)
