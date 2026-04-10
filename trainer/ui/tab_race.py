"""Race control tab — race flow + special cheats + user favorites."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QGridLayout, QGroupBox, QLabel, QPushButton,
                                QVBoxLayout, QWidget)


class RaceTab(QWidget):
    FAV_COLUMNS = 2

    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge
        self._action_buttons: list[QPushButton] = []
        self._fav_buttons: list[QPushButton] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # --- Race flow group ---
        flow_box = QGroupBox('RACE FLOW')
        flow = QGridLayout(flow_box)
        flow.setContentsMargins(16, 18, 16, 16)
        flow.setSpacing(10)

        self.btn_auto = QPushButton('▶  AUTO-START RACE')
        self.btn_auto.setObjectName('primary')
        self.btn_auto.setMinimumHeight(56)
        self.btn_auto.clicked.connect(self.bridge.auto_start_race)
        self._action_buttons.append(self.btn_auto)
        flow.addWidget(self.btn_auto, 0, 0, 1, 2)

        self.btn_finish = self._mk_named('Finish race', 'SMARTBASTARD')
        flow.addWidget(self.btn_finish, 1, 0)

        self.btn_cheat_mode = self._mk_named('Enable cheat mode', 'LAPMYLOVEPUMP')
        flow.addWidget(self.btn_cheat_mode, 1, 1)

        layout.addWidget(flow_box)

        # --- Special cheats group: non-powerup actions you can't reach via the
        #     Powerups tab (different handler types) ---
        special_box = QGroupBox('SPECIAL CHEATS')
        special = QGridLayout(special_box)
        special.setContentsMargins(16, 18, 16, 16)
        special.setSpacing(10)

        # Find entries by handler so we don't hardcode strings for unnamed cheats
        fly_entry = self._find_handler_entry('fly_toggle')
        gonad_entry = self._find_handler_entry('gonad_of_death')

        col = 0
        if fly_entry is not None:
            special.addWidget(self._mk_entry('Fly mode', fly_entry), 0, col)
            col += 1
        if gonad_entry is not None:
            special.addWidget(self._mk_entry('Gonad of death', gonad_entry), 0, col)
            col += 1

        layout.addWidget(special_box)

        # --- Favorites group: user-pinned powerups from the Powerups tab ---
        self.fav_box = QGroupBox('FAVORITES')
        self.fav_layout = QGridLayout(self.fav_box)
        self.fav_layout.setContentsMargins(16, 18, 16, 16)
        self.fav_layout.setSpacing(10)
        layout.addWidget(self.fav_box)
        self._build_favorites()

        # --- Hint ---
        hint = QLabel('Tip — most powerups only work in a race. '
                      'Right-click any powerup in the Powerups tab to pin it here.')
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet('color: #9aa0a6; font-style: italic;')
        layout.addWidget(hint)

        layout.addStretch()

        # Start disabled until attached
        self._set_actions_enabled(False)
        self.bridge.attached_changed.connect(self._set_actions_enabled)
        self.bridge.favorites_changed.connect(self._build_favorites)

    # ----- helpers -----

    def _find_handler_entry(self, handler_name):
        for e in self.bridge.cheat_entries:
            if e.handler == handler_name:
                return e
        return None

    def _mk_btn(self, label: str, handler, tooltip: str = '') -> QPushButton:
        """Generic button factory — handler is a no-arg callable."""
        btn = QPushButton(label)
        btn.setMinimumHeight(44)
        btn.clicked.connect(lambda: handler())
        if tooltip:
            btn.setToolTip(tooltip)
        self._action_buttons.append(btn)
        return btn

    def _mk_named(self, label: str, cheat_name: str) -> QPushButton:
        return self._mk_btn(label, lambda: self.bridge.fire_named(cheat_name))

    def _mk_entry(self, label: str, entry) -> QPushButton:
        return self._mk_btn(label,
            lambda: self.bridge.fire_by_hash(entry.h1, entry.h2, label=label))

    def _build_favorites(self):
        # Clear old favorite buttons
        for btn in self._fav_buttons:
            self._action_buttons.remove(btn) if btn in self._action_buttons else None
            btn.setParent(None)
            btn.deleteLater()
        self._fav_buttons.clear()
        # Clear the layout (just in case)
        while self.fav_layout.count():
            item = self.fav_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        # Look up entries by name
        by_name = {e.name: e for e in self.bridge.cheat_entries if e.name}
        favorites = [by_name[n] for n in self.bridge.favorites if n in by_name]

        if not favorites:
            empty = QLabel('No favorites yet — right-click a powerup in the '
                           'Powerups tab to pin it.')
            empty.setStyleSheet('color: #9aa0a6; font-style: italic;')
            empty.setAlignment(Qt.AlignCenter)
            self.fav_layout.addWidget(empty, 0, 0, 1, self.FAV_COLUMNS)
            return

        for i, e in enumerate(favorites):
            row, col = divmod(i, self.FAV_COLUMNS)
            btn = self._mk_entry(e.display, e)
            btn.setToolTip(f'Cheat: {e.name}\nRight-click in Powerups tab to unpin')
            self._fav_buttons.append(btn)
            self.fav_layout.addWidget(btn, row, col)

        # Re-apply enabled state to new buttons
        attached = self.bridge.is_attached()
        for btn in self._fav_buttons:
            btn.setEnabled(attached)

    def _set_actions_enabled(self, enabled: bool):
        for btn in self._action_buttons:
            btn.setEnabled(enabled)
