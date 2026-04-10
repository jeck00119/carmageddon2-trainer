"""Full cheat table tab — all 94 entries, click row to fire."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView,
                                QLabel, QLineEdit, QPushButton, QTableWidget,
                                QTableWidgetItem, QVBoxLayout, QWidget)

COLS = ['#', 'Handler', 'Arg', 'Cheat string', 'Effect']


class CheatsTab(QWidget):
    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge
        self.entries = bridge.cheat_entries
        self.bridge.attached_changed.connect(self._on_attached_changed)
        self._attached = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.search = QLineEdit()
        self.search.setPlaceholderText('Filter by string, effect, handler...')
        self.search.setClearButtonEnabled(True)
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self._refilter)
        self.search.textChanged.connect(lambda: self._search_timer.start())
        layout.addWidget(self.search)

        named = sum(1 for e in self.entries if e.name)
        header_row = QHBoxLayout()
        self.header = QLabel(
            f'{len(self.entries)} entries  ·  {named} named  ·  '
            f'only work in-race'
        )
        self.header.setStyleSheet('color: #9aa0a6;')
        header_row.addWidget(self.header)
        header_row.addStretch()

        self.btn_fire = QPushButton('▶  FIRE selected')
        self.btn_fire.setObjectName('primary')
        self.btn_fire.setMinimumHeight(36)
        self.btn_fire.setEnabled(False)
        self.btn_fire.clicked.connect(self._fire_selected)
        header_row.addWidget(self.btn_fire)
        layout.addLayout(header_row)

        self.table = QTableWidget(len(self.entries), len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.doubleClicked.connect(self._on_double_click)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        for row, e in enumerate(self.entries):
            self._set_row(row, e)

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.Stretch)

        layout.addWidget(self.table, 1)

        hint = QLabel('Click a row to select it, then press FIRE  ·  '
                      'or double-click any row to fire instantly')
        hint.setStyleSheet('color: #9aa0a6; font-style: italic;')
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

    def _set_row(self, row, e):
        items = [
            QTableWidgetItem(str(e.idx)),
            QTableWidgetItem(e.handler),
            QTableWidgetItem(str(e.arg)),
            QTableWidgetItem(e.name or '—'),
            QTableWidgetItem(e.effect or e.display),
        ]
        if not e.name:
            for it in items:
                it.setForeground(QBrush(QColor('#e0b341')))
        for col, it in enumerate(items):
            self.table.setItem(row, col, it)

    def _refilter(self):
        q = self.search.text().lower().strip()
        for row, e in enumerate(self.entries):
            text = f'{e.handler} {e.arg} {e.name or ""} {e.effect}'.lower()
            self.table.setRowHidden(row, bool(q) and q not in text)

    def _on_double_click(self, index):
        self._fire_row(index.row())

    def _on_selection_changed(self):
        rows = self.table.selectionModel().selectedRows()
        self.btn_fire.setEnabled(self._attached and bool(rows))

    def _on_attached_changed(self, attached: bool):
        self._attached = attached
        # Keep table readable (scrollable/selectable) when detached — only disable FIRE
        self.btn_fire.setEnabled(attached and bool(self.table.selectionModel().selectedRows()))

    def _fire_selected(self):
        rows = self.table.selectionModel().selectedRows()
        if rows:
            self._fire_row(rows[0].row())

    def _fire_row(self, row: int):
        e = self.entries[row]
        label = e.name or f'idx {e.idx} ({e.handler})'
        self.bridge.fire_by_hash(e.h1, e.h2, label=label)
