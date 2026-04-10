"""Status tab — connection info + live game state + advanced toggle."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QFormLayout, QGroupBox, QLabel,
                                QPushButton, QVBoxLayout, QWidget)

MENU_NAMES = {
    0x5a80f0: 'Main menu',
    0x5bf280: 'New Game menu',
    0x59c828: 'In race (StartGame)',
    0x649df0: 'Quit menu',
}


class StatusTab(QWidget):
    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # Connection group
        conn_box = QGroupBox('CONNECTION')
        conn = QFormLayout(conn_box)
        self.lbl_state = QLabel('Detached')
        self.lbl_pid = QLabel('—')
        conn.addRow('State:', self.lbl_state)
        conn.addRow('PID:', self.lbl_pid)

        self.btn_reattach = QPushButton('Force reattach')
        self.btn_reattach.setToolTip(
            'Use this if the trainer loses connection to the game '
            '(e.g. after the game crashes or is restarted).')
        self.btn_reattach.clicked.connect(self._reattach)
        conn.addRow(self.btn_reattach)

        self.cb_advanced = QCheckBox('Advanced / developer mode')
        self.cb_advanced.setToolTip(
            'Show internal debug info: live game state, full cheat table, '
            'memory addresses. Off by default.')
        conn.addRow(self.cb_advanced)
        layout.addWidget(conn_box)

        # Live state group (only visible in advanced mode)
        self.state_box = QGroupBox('LIVE GAME STATE  ·  1 Hz')
        state = QFormLayout(self.state_box)
        self.lbl_menu = QLabel('—')
        self.lbl_sel = QLabel('—')
        self.lbl_gs = QLabel('—')
        self.lbl_dgs = QLabel('—')
        self.lbl_in_race = QLabel('—')
        state.addRow('Menu:', self.lbl_menu)
        state.addRow('Selection:', self.lbl_sel)
        state.addRow('game_state:', self.lbl_gs)
        state.addRow('dogame_state:', self.lbl_dgs)
        state.addRow('In race:', self.lbl_in_race)
        layout.addWidget(self.state_box)
        self.state_box.hide()  # default off; main_window flips on Advanced toggle

        # Info group
        info_box = QGroupBox('ABOUT')
        info = QVBoxLayout(info_box)
        info_text = QLabel(
            '<b>Carmageddon 2 Trainer</b><br><br>'
            'Frida-based runtime trainer. Hooks the live game and calls '
            'its internal cheat dispatcher directly — no key simulation, '
            'no save-file editing.<br><br>'
            'Cheat strings are reverse-engineered from the binary; '
            'unnamed cheats still work because we know the (h1, h2) hash '
            'of every table entry.'
        )
        info_text.setWordWrap(True)
        info.addWidget(info_text)
        layout.addWidget(info_box)

        layout.addStretch()

    def update_snap(self, snap, attached: bool, pid):
        if attached:
            self.lbl_state.setText('Attached')
            self.lbl_state.setStyleSheet('color: #2a2; font-weight: bold;')
            self.lbl_pid.setText(str(pid) if pid else '—')
        else:
            self.lbl_state.setText('Detached')
            self.lbl_state.setStyleSheet('color: #c33; font-weight: bold;')
            self.lbl_pid.setText('—')

        if snap is None:
            for lbl in (self.lbl_menu, self.lbl_sel, self.lbl_gs,
                        self.lbl_dgs, self.lbl_in_race):
                lbl.setText('—')
            return

        menu_va = snap['menu']
        menu_name = MENU_NAMES.get(menu_va, '?')
        self.lbl_menu.setText(f'0x{menu_va:08x}  ({menu_name})')
        self.lbl_sel.setText(str(snap['sel']))
        self.lbl_gs.setText(str(snap['game_state']))
        self.lbl_dgs.setText(str(snap['dogame_state']))
        in_race = snap['game_state'] != 0
        self.lbl_in_race.setText('YES' if in_race else 'no')
        self.lbl_in_race.setStyleSheet(
            'color: #2a2; font-weight: bold;' if in_race
            else 'color: #888;'
        )

    def set_advanced(self, on: bool):
        self.state_box.setVisible(on)

    def _reattach(self):
        self.bridge.detach()
        self.bridge.attach_or_spawn()
