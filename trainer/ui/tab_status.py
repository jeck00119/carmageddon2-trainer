"""Status tab — connection info + game path + about text."""
from PySide6.QtWidgets import (QFileDialog, QFormLayout, QGroupBox,
                                QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                                QWidget)

MENU_NAMES = {
    0x5a80f0: 'Main menu',
    0x5b39b8: 'Network menu',
    0x5bf280: 'New Game menu',
    0x59c828: 'In race (StartGame)',
    0x632c60: 'Options menu',
    0x649df0: 'Quit menu',
    0x5d6410: 'Change Car menu',
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

        # Game path
        path_row = QHBoxLayout()
        game_path = self.bridge.game_path or '(not found)'
        self.lbl_path = QLabel(game_path)
        self.lbl_path.setStyleSheet('color: #9aa0a6; font-size: 9pt;')
        self.lbl_path.setWordWrap(True)
        btn_browse = QPushButton('Change...')
        btn_browse.setMaximumWidth(80)
        btn_browse.clicked.connect(self._browse_game)
        path_row.addWidget(self.lbl_path, 1)
        path_row.addWidget(btn_browse)
        conn.addRow('Game:', path_row)

        # Wrapper status (dgVoodoo 2)
        wi = self.bridge.wrapper_info
        if wi.get('type') == 'dgvoodoo':
            wrapper_text = 'dgVoodoo 2 (Alt+Tab / windowed OK)'
            wrapper_style = 'color: #4ec27a;'
        elif wi.get('ok'):
            wrapper_text = 'Glide wrapper present'
            wrapper_style = 'color: #e0b341;'
        else:
            wrapper_text = 'Not installed'
            wrapper_style = 'color: #e85050;'
        self.lbl_wrapper = QLabel(wrapper_text)
        self.lbl_wrapper.setStyleSheet(f'{wrapper_style} font-size: 9pt;')
        conn.addRow('Wrapper:', self.lbl_wrapper)

        layout.addWidget(conn_box)

        # About text
        info_box = QGroupBox('ABOUT')
        info = QVBoxLayout(info_box)
        info_text = QLabel(
            '<b>Carmageddon 2 Trainer</b><br><br>'
            'Re-enables the dev/edit mode that\'s broken on the Steam edition. '
            'Hooks the live game via runtime memory instrumentation — no binary '
            'patching, no save-file editing, no typed cheat codes.<br><br>'
            'Cheats are fired by injecting the game\'s own cheat hash '
            'dispatcher — one click fires any of the 94 cheats without typing.'
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

    def _reattach(self):
        self.bridge.detach()
        self.bridge.attach_or_spawn()

    def _browse_game(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Locate CARMA2_HW.EXE', 'C:\\',
            'Carmageddon 2 EXE (CARMA2_HW.EXE);;All files (*)')
        if path:
            if self.bridge.set_game_path(path):
                self.lbl_path.setText(path)
