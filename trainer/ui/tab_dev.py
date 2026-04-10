"""
Dev cheats tab — generic widget factory driven by the action registry.

The whole tab is built by iterating `dev_actions.DEV_ACTIONS`. Adding a new
dev feature is one row in that registry — no UI code touched.

Live state (credits, damage state, gravity, etc.) updates from the bridge's
`snap_updated` signal which fires on every poll tick (1 Hz from main_window).
"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QComboBox, QGridLayout, QGroupBox, QHBoxLayout,
                                QLabel, QLineEdit, QMessageBox, QPushButton,
                                QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from backend.dev_actions import Action, DEV_ACTIONS, actions_by_group


class DevTab(QWidget):
    """All dev cheats organized into group boxes with search filter."""

    GROUP_COLUMNS = 3   # buttons per row inside a group

    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge

        # Track widgets per action so we can update state labels + enabled flags
        self._action_widgets: dict[str, dict] = {}
        self._group_boxes: dict[str, QGroupBox] = {}

        # Search bar at top
        search_row = QHBoxLayout()
        search_row.setContentsMargins(16, 12, 16, 0)
        self._search = QLineEdit()
        self._search.setPlaceholderText('Search dev cheats...')
        self._search.setClearButtonEnabled(True)
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self._apply_filter)
        self._search.textChanged.connect(lambda: self._search_timer.start())
        search_row.addWidget(self._search)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(16, 8, 16, 16)
        layout.setSpacing(12)

        # Hint
        hint = QLabel(
            'Enable Dev Mode first. Some features need in-race state. '
            'Use the search bar to filter.')
        hint.setWordWrap(True)
        hint.setStyleSheet('color: #9aa0a6; font-style: italic;')
        layout.addWidget(hint)

        # Build each group from the registry
        for group_name, actions in actions_by_group():
            box = self._build_group(group_name, actions)
            self._group_boxes[group_name] = box
            layout.addWidget(box)

        layout.addStretch()
        scroll.setWidget(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(search_row)
        outer.addWidget(scroll)

        # Wire signals
        self.bridge.attached_changed.connect(self._on_attached_changed)
        self.bridge.snap_updated.connect(self._on_snap)
        # Start disabled — we're not attached yet
        self._set_groups_enabled(False)
        self._dev_mode_active = False

    # -------------------- group builder --------------------

    def _build_group(self, group_name: str, actions: list[Action]) -> QGroupBox:
        box = QGroupBox(group_name.upper())
        grid = QGridLayout(box)
        grid.setContentsMargins(14, 18, 14, 14)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        col_count = self.GROUP_COLUMNS
        row = col = 0
        for action in actions:
            widget, span = self._build_action_widget(action)
            grid.addWidget(widget, row, col, 1, span)
            col += span
            if col >= col_count:
                col = 0
                row += 1
        return box

    def _build_action_widget(self, action: Action) -> tuple[QWidget, int]:
        """Returns (widget, column_span). column_span = how many grid cells."""
        kind = action.kind

        if kind == 'display':
            # Just a state label, no button
            holder = QWidget()
            h = QHBoxLayout(holder)
            h.setContentsMargins(4, 0, 4, 0)
            h.setSpacing(6)
            h.addWidget(QLabel(action.label + ':'))
            value = QLabel('—')
            value.setStyleSheet('color: #4ec27a; font-weight: 600;')
            h.addWidget(value)
            h.addStretch()
            self._action_widgets[action.name] = {'value_label': value, 'action': action}
            return holder, self.GROUP_COLUMNS    # full width

        if kind == 'input':
            holder = QWidget()
            h = QHBoxLayout(holder)
            h.setContentsMargins(4, 0, 4, 0)
            h.setSpacing(6)
            label = QLabel(action.label + ':')

            # For spawn_powerup, use a combobox with powerup names
            if action.name == 'spawn_powerup':
                combo = QComboBox()
                combo.setMinimumWidth(200)
                for e in self.bridge.powerup_entries:
                    combo.addItem(f'{e.arg}: {e.display}', e.arg)
                combo.setCurrentIndex(0)
                btn = QPushButton('Spawn')
                btn.setMinimumHeight(34)
                btn.clicked.connect(
                    lambda _, a=action, c=combo: self._fire(a, c.currentData()))
                if action.tooltip:
                    btn.setToolTip(action.tooltip)
                h.addWidget(label)
                h.addWidget(combo)
                h.addWidget(btn)
                h.addStretch()
                self._action_widgets[action.name] = {
                    'btn': btn, 'spin': combo, 'action': action}
            else:
                spin = QSpinBox()
                spin.setRange(action.input_min, action.input_max)
                spin.setValue(action.input_default)
                spin.setMinimumWidth(80)
                btn = QPushButton('Apply')
                btn.setMinimumHeight(34)
                btn.clicked.connect(
                    lambda _, a=action, s=spin: self._fire(a, s.value()))
                if action.tooltip:
                    btn.setToolTip(action.tooltip)
                    spin.setToolTip(action.tooltip)
                h.addWidget(label)
                h.addWidget(spin)
                h.addWidget(btn)
                h.addStretch()
                self._action_widgets[action.name] = {
                    'btn': btn, 'spin': spin, 'action': action}
            return holder, self.GROUP_COLUMNS    # full width

        if kind in ('button', 'toggle', 'cycler'):
            btn = QPushButton(action.label)
            btn.setMinimumHeight(38)
            btn.clicked.connect(lambda _, a=action: self._fire(a))
            if action.tooltip:
                btn.setToolTip(action.tooltip)
            if action.danger:
                btn.setStyleSheet('color: #e85050;')

            self._action_widgets[action.name] = {'btn': btn, 'action': action}

            if kind == 'cycler':
                # Add a state label below the button
                holder = QWidget()
                v = QVBoxLayout(holder)
                v.setContentsMargins(0, 0, 0, 0)
                v.setSpacing(2)
                v.addWidget(btn)
                state_lbl = QLabel('—')
                state_lbl.setAlignment(Qt.AlignCenter)
                state_lbl.setStyleSheet('color: #4ec27a; font-size: 9pt;')
                v.addWidget(state_lbl)
                self._action_widgets[action.name]['state_label'] = state_lbl
                return holder, 1
            return btn, 1

        # Unknown kind — fallback to button
        btn = QPushButton(action.label)
        btn.clicked.connect(lambda _, a=action: self._fire(a))
        self._action_widgets[action.name] = {'btn': btn, 'action': action}
        return btn, 1

    # -------------------- click handler --------------------

    def _fire(self, action: Action, *runtime_args):
        # Special-case the dev_enable toggle button
        if action.name == 'dev_enable':
            if self._dev_mode_active:
                self.bridge.dev_call('dev_disable_btn')
            else:
                self.bridge.dev_call('dev_enable')
            return
        # Confirmation for dangerous actions
        if action.danger:
            reply = QMessageBox.question(
                self, 'Confirm',
                f'Are you sure you want to: {action.label}?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
        self.bridge.dev_call(action.name, *runtime_args)

    # -------------------- live state updates --------------------

    def _on_attached_changed(self, attached: bool):
        # When detached, force everything off
        if not attached:
            self._dev_mode_active = False
            self._set_groups_enabled(False)
            self._update_dev_toggle_state(False)

    def _on_snap(self, snap: dict):
        # Update dev mode state
        was_active = self._dev_mode_active
        self._dev_mode_active = bool(snap.get('dev_active'))
        if was_active != self._dev_mode_active:
            self._update_dev_toggle_state(self._dev_mode_active)

        # Apply per-action requirements (re-enable buttons based on prereqs)
        attached = True   # we only get snap if attached
        in_race = snap.get('dogame_state', 0) == 5  # dogame_state=5 = in race (game_state stays 0 during SP)
        for name, w in self._action_widgets.items():
            action: Action = w['action']
            ok = self._meets_requirements(action, attached, self._dev_mode_active, in_race)
            for key in ('btn', 'spin'):
                if key in w:
                    w[key].setEnabled(ok)
            # Update state label/value
            if 'value_label' in w and action.state_key:
                v = snap.get(action.state_key, 0)
                if action.state_key == 'credits':
                    w['value_label'].setText(f'{v}')
                else:
                    w['value_label'].setText(str(v))
            if 'state_label' in w and action.state_key:
                v = snap.get(action.state_key, 0)
                if action.state_labels and 0 <= v < len(action.state_labels):
                    w['state_label'].setText(action.state_labels[v])
                else:
                    w['state_label'].setText(str(v))

    def _meets_requirements(self, action: Action, attached: bool,
                             dev_active: bool, in_race: bool) -> bool:
        for req in action.requires:
            if req == 'attached' and not attached:
                return False
            if req == 'dev_mode' and not dev_active:
                return False
            if req == 'in_race' and not in_race:
                return False
        return True

    def _update_dev_toggle_state(self, on: bool):
        w = self._action_widgets.get('dev_enable')
        if w is None:
            return
        btn: QPushButton = w['btn']
        if on:
            btn.setText('● Dev mode ACTIVE  (click to disable)')
            btn.setStyleSheet('background: #4ec27a; color: black; font-weight: 700;')
        else:
            btn.setText('Enable dev mode')
            btn.setStyleSheet('')

    def _set_groups_enabled(self, enabled: bool):
        for name, w in self._action_widgets.items():
            for key in ('btn', 'spin'):
                if key in w:
                    w[key].setEnabled(enabled)

    def _apply_filter(self):
        """Filter groups/buttons based on search text (debounced 250ms)."""
        query = self._search.text().strip().lower()
        for group_name, box in self._group_boxes.items():
            if not query:
                box.setVisible(True)
                continue
            # Show group if group name or any action label/tooltip matches
            group_match = query in group_name.lower()
            action_match = False
            for a in DEV_ACTIONS:
                if a.group == group_name:
                    if (query in a.label.lower() or
                            query in a.tooltip.lower() or
                            query in a.name.lower()):
                        action_match = True
                        break
            box.setVisible(group_match or action_match)
