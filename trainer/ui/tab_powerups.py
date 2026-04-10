"""Powerup tab — grid of all spawn_powerup cheats with search filter."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QGridLayout, QLabel, QLineEdit, QMenu,
                                QPushButton, QScrollArea, QVBoxLayout, QWidget)


class PowerupTab(QWidget):
    COLUMNS = 3

    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge
        self.entries = bridge.powerup_entries
        self.bridge.attached_changed.connect(self._set_actions_enabled)
        self.bridge.favorites_changed.connect(self._refresh_pinned_state)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Search bar with debounce
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search powerups by name or effect...')
        self.search.setClearButtonEnabled(True)
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self._refilter)
        self.search.textChanged.connect(lambda: self._search_timer.start())
        layout.addWidget(self.search)

        # Header
        self.header = QLabel(f'{len(self.entries)} powerups  ·  only work in-race')
        self.header.setStyleSheet('color: #9aa0a6;')
        layout.addWidget(self.header)

        # Scrollable grid
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setSpacing(8)
        self.grid.setContentsMargins(4, 4, 4, 4)
        self.scroll.setWidget(self.grid_host)
        layout.addWidget(self.scroll, 1)

        self.buttons: list[tuple[QPushButton, object]] = []
        self._build_buttons()
        self._set_actions_enabled(False)

    def _build_buttons(self):
        for btn, _ in self.buttons:
            btn.deleteLater()
        self.buttons.clear()

        for i, e in enumerate(self.entries):
            btn = QPushButton(e.display)
            btn.setMinimumHeight(58)
            # Tooltip carries the cheat string + idx (power-user info)
            if e.name:
                btn.setToolTip(f'Cheat: {e.name}  ·  table index {e.idx}'
                               '\nRight-click to pin to favorites')
            else:
                btn.setObjectName('unnamed')
                btn.setToolTip(f'Unnamed cheat  ·  table index {e.idx}')
            btn.clicked.connect(
                lambda _checked=False, ent=e: self._fire(ent)
            )
            # Right-click context menu (only for named cheats — favorites need a name to persist)
            if e.name:
                btn.setContextMenuPolicy(Qt.CustomContextMenu)
                btn.customContextMenuRequested.connect(
                    lambda pos, b=btn, ent=e: self._show_context_menu(b, ent, pos)
                )
            self.buttons.append((btn, e))
        self._refresh_pinned_state()

        self._refilter()

    def _refilter(self):
        q = self.search.text().lower().strip()
        # Clear grid
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        visible = 0
        for btn, e in self.buttons:
            text = (e.display + ' ' + (e.name or '')).lower()
            if q and q not in text:
                continue
            row, col = divmod(visible, self.COLUMNS)
            self.grid.addWidget(btn, row, col)
            visible += 1

        if q:
            self.header.setText(f'{visible} of {len(self.entries)} powerups')
        else:
            self.header.setText(f'{len(self.entries)} powerups')

    def _fire(self, entry):
        label = entry.name or entry.display
        self.bridge.fire_by_hash(entry.h1, entry.h2, label=label)

    def _set_actions_enabled(self, enabled: bool):
        for btn, _ in self.buttons:
            btn.setEnabled(enabled)

    def _show_context_menu(self, btn, entry, pos):
        if not entry.name:
            return
        menu = QMenu(btn)
        if self.bridge.is_favorite(entry.name):
            act = menu.addAction('★  Unpin from favorites')
        else:
            act = menu.addAction('☆  Pin to favorites')
        chosen = menu.exec(btn.mapToGlobal(pos))
        if chosen is act:
            self.bridge.toggle_favorite(entry.name)

    def _refresh_pinned_state(self):
        for btn, e in self.buttons:
            pinned = bool(e.name and self.bridge.is_favorite(e.name))
            btn.setProperty('pinned', pinned)
            # Force a restyle so the QSS rule for [pinned="true"] takes effect
            btn.style().unpolish(btn)
            btn.style().polish(btn)
