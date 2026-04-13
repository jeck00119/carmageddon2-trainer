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
            'DISPLAY', 'Lock window to 4:3',
            'Keep the window at the game\'s native 4:3 aspect ratio.\n'
            'Uncheck to allow any window shape (image may stretch).'),
    Setting('FPSLimit', 'dgv', 'GeneralExt', 'spin', [], '0',
            'DISPLAY', 'FPS limit',
            'Cap the frame rate. 0 = unlimited.\n'
            'Useful if the game runs too fast on modern hardware.'),

    # --- GRAPHICS QUALITY ---
    Setting('Resolution', 'dgv', 'Glide', 'combo',
            [('Original (640x480)', 'unforced'),
             ('Your monitor (best)', 'max'),
             ('Pixel-perfect scaling', 'max_isf'),
             ('Up to 1080p', 'max_fhd'),
             ('Up to 1440p', 'max_qhd'),
             ('2x (1280x960)', '2x'),
             ('4x (2560x1920)', '4x')],
            'max', 'GRAPHICS QUALITY', 'Render resolution',
            'How many pixels the game renders internally.\n'
            '"Your monitor" = sharpest. "Original" = authentic 1998 look.\n'
            'Higher values look better but use more GPU power.'),
    Setting('Antialiasing', 'dgv', 'Glide', 'combo',
            [('Off', 'off'), ('Let game decide', 'appdriven'),
             ('2x (subtle)', '2x'), ('4x (recommended)', '4x'),
             ('8x (heavy)', '8x'), ('16x (maximum)', '16x')],
            '4x', 'GRAPHICS QUALITY', 'Edge smoothing',
            'Smooths jagged edges on 3D objects.\n'
            'Higher = smoother but heavier on GPU. 4x is a good balance.\n'
            'If you see visual glitches, try lowering or turning off.'),
    Setting('TMUFiltering', 'dgv', 'Glide', 'combo',
            [('Let game decide', 'appdriven'),
             ('Sharp pixels (retro look)', 'pointsampled'),
             ('Smooth (modern look)', 'bilinear')],
            'bilinear', 'GRAPHICS QUALITY', 'Texture smoothing',
            'How textures look when viewed at an angle or up close.\n'
            '"Sharp pixels" = blocky/retro. "Smooth" = blended/modern.'),
    Setting('Resampling', 'dgv', 'GeneralExt', 'combo',
            [('Nearest (blocky)', 'pointsampled'),
             ('Bilinear (soft)', 'bilinear'),
             ('Bicubic (balanced)', 'bicubic'),
             ('Lanczos-2 (sharp)', 'lanczos-2'),
             ('Lanczos-3 (sharpest)', 'lanczos-3')],
            'lanczos-2', 'GRAPHICS QUALITY', 'Upscale filter',
            'How the game image is scaled up to your screen.\n'
            'Only matters if render resolution differs from your monitor.\n'
            'Lanczos-2 is recommended for the best sharpness.'),

    # --- GAME WORLD ---
    Setting('Yon', 'opt', '', 'slider', [], '100.000000',
            'GAME WORLD', 'Draw distance',
            'How far you can see in the game world.\n'
            'Higher = see further, but values above 50 may cause AI to behave oddly.'),
    Setting('RoadTexturingLevel', 'opt', '', 'combo',
            [('Off (solid color)', '0'), ('On', '1')],
            '1', 'GAME WORLD', 'Road textures',
            'Show texture detail on road surfaces.'),
    Setting('WallTexturingLevel', 'opt', '', 'combo',
            [('Off (solid color)', '0'), ('Basic', '1'), ('Best', '2')],
            '2', 'GAME WORLD', 'Wall textures',
            'Texture quality on walls and buildings.\n'
            '"Best" uses perspective-correct mapping for less warping.'),
    Setting('CarTexturingLevel', 'opt', '', 'combo',
            [('Off (solid color)', '0'), ('Basic', '1'), ('Best', '2')],
            '2', 'GAME WORLD', 'Car textures',
            'Texture quality on vehicles.\n'
            '"Best" uses perspective-correct mapping.'),
    Setting('ShadowLevel', 'opt', '', 'combo',
            [('None', '0'), ('Cars only', '1'),
             ('Everything (cars + peds + props)', '3')],
            '3', 'GAME WORLD', 'Shadows',
            'Which objects cast shadows on the ground.'),
    Setting('SmokeOn', 'opt', '', 'check', [], '1',
            'GAME WORLD', 'Smoke & particles',
            'Show tire smoke, exhaust, and explosion particles.'),
    Setting('AccessoryRendering', 'opt', '', 'check', [], '1',
            'GAME WORLD', 'Props & scenery objects',
            'Show destructible props like signs, fences, and cones.\n'
            'Also affects collision with these objects.'),
    Setting('SkyTextureOn', 'opt', '', 'check', [], '1',
            'GAME WORLD', 'Sky',
            'Show the sky texture. Off = solid color background.'),
    Setting('DepthCueingOn', 'opt', '', 'check', [], '1',
            'GAME WORLD', 'Distance fog',
            'Fade distant objects into the background.\n'
            'Hides pop-in at the draw distance limit.'),
    Setting('AnimalsOn', 'opt', '', 'check', [], '1',
            'GAME WORLD', 'Animals',
            'Show animals in the game world (cows, dogs, etc).'),
    Setting('DronesOn', 'opt', '', 'check', [], '1',
            'GAME WORLD', 'Civilian traffic',
            'Show civilian drone cars driving around the level.'),
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
            row = QHBoxLayout()
            w = QSlider(Qt.Horizontal)
            w.setMinimum(20)
            w.setMaximum(200)
            w.setSingleStep(10)
            w.setTickInterval(20)
            w.setTickPosition(QSlider.TicksBelow)
            lbl = QLabel('100')
            lbl.setMinimumWidth(30)
            w.valueChanged.connect(lambda v, l=lbl: l.setText(str(v)))
            row.addWidget(w, 1)
            row.addWidget(lbl)
            note = QLabel('(>50 may affect AI)')
            note.setStyleSheet(f'color: {TEXT_DIM}; font-size: 8pt;')
            row.addWidget(note)
            if s.tip:
                w.setToolTip(s.tip)
            self.widgets[s.key] = w
            form.addRow(s.label + ':', row)
        elif s.widget == 'spin':
            w = QSpinBox()
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
