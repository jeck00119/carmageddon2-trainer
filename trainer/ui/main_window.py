"""Main trainer window."""
import ctypes
import ctypes.wintypes
import sys

from PySide6.QtCore import QSettings, QTimer, Qt
from PySide6.QtWidgets import (QApplication, QFileDialog, QHBoxLayout,
                                QLabel, QMainWindow, QPushButton,
                                QStatusBar, QTabWidget, QVBoxLayout, QWidget)

from ui.bridge import BackendBridge
from ui.tab_dev import DevTab
from ui.tab_powerups import PowerupTab
from ui.tab_race import RaceTab
from ui.tab_status import MENU_NAMES, StatusTab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Carmageddon 2 Trainer')
        self.resize(900, 640)

        self.bridge = BackendBridge()
        self.bridge.log.connect(self._on_log)
        self.bridge.attached_changed.connect(self._on_attached_changed)
        self.bridge.op_finished.connect(self._on_op_finished)
        self.bridge.game_not_found.connect(self._on_game_not_found)

        # --- Top bar: title + attach controls ---
        top = QWidget()
        top_lay = QHBoxLayout(top)
        top_lay.setContentsMargins(16, 14, 16, 8)
        top_lay.setSpacing(12)

        title = QLabel('CARMAGEDDON 2  ·  TRAINER')
        title.setObjectName('title')
        top_lay.addWidget(title)

        top_lay.addSpacing(20)

        self.lbl_state = QLabel('●  Detached')
        self.lbl_state.setStyleSheet('color: #e85050; font-weight: 600;')
        top_lay.addWidget(self.lbl_state)

        top_lay.addStretch()

        self.btn_attach = QPushButton('Attach / Spawn game')
        self.btn_attach.setObjectName('primary')
        self.btn_attach.setMinimumHeight(36)
        self.btn_attach.clicked.connect(self._attach_clicked)
        top_lay.addWidget(self.btn_attach)

        self.btn_detach = QPushButton('Detach')
        self.btn_detach.setMinimumHeight(36)
        self.btn_detach.clicked.connect(self.bridge.detach)
        self.btn_detach.setEnabled(False)
        top_lay.addWidget(self.btn_detach)

        # --- Tabs ---
        self.tabs = QTabWidget()
        self.tab_status = StatusTab(self.bridge)
        self.tabs.addTab(RaceTab(self.bridge), 'Race')
        self.tabs.addTab(DevTab(self.bridge), 'Dev cheats')
        self.tabs.addTab(PowerupTab(self.bridge), 'Powerups')
        self.tabs.addTab(self.tab_status, 'Status')

        # --- Layout ---
        central = QWidget()
        v = QVBoxLayout(central)
        v.setContentsMargins(12, 0, 12, 12)
        v.setSpacing(8)
        v.addWidget(top)
        v.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

        # --- Status bar ---
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.lbl_state_friendly = QLabel('Game not running')
        self.status.addPermanentWidget(self.lbl_state_friendly)

        # --- Snap poller ---
        self.snap_timer = QTimer(self)
        self.snap_timer.setInterval(1000)
        self.snap_timer.timeout.connect(self._poll_snap)
        self.snap_timer.start()
        self._snap_fail_count = 0
        self._was_attached = False   # Bug 1 fix: track attached state for transition detection

        # --- Restore window geometry ---
        self.settings = QSettings('carma2_tools', 'trainer')
        geom = self.settings.value('geometry')
        if geom:
            self.restoreGeometry(geom)

    def _attach_clicked(self):
        self.bridge.attach_or_spawn()

    def _on_game_not_found(self):
        self._browse_game_exe()

    def _browse_game_exe(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Locate CARMA2_HW.EXE',
            'C:\\',
            'Carmageddon 2 EXE (CARMA2_HW.EXE);;All files (*)')
        if path:
            if self.bridge.set_game_path(path):
                self.status.showMessage(f'Game path: {path}', 8000)
                if hasattr(self.tab_status, 'lbl_path'):
                    self.tab_status.lbl_path.setText(path)
            else:
                self.status.showMessage('Invalid selection — please choose CARMA2_HW.EXE', 5000)
        else:
            self.status.showMessage('No game selected — click Attach/Spawn to try again', 5000)

    # --- slots ---

    def _on_log(self, msg: str):
        self.status.showMessage(msg, 5000)

    def _on_attached_changed(self, attached: bool):
        if attached:
            self.lbl_state.setText(f'●  Attached  ·  pid {self.bridge.backend.pid}')
            self.lbl_state.setStyleSheet('color: #4ec27a; font-weight: 600;')
            self.btn_attach.setEnabled(False)
            self.btn_detach.setEnabled(True)
        else:
            self.lbl_state.setText('●  Detached')
            self.lbl_state.setStyleSheet('color: #e85050; font-weight: 600;')
            self.btn_attach.setEnabled(True)
            self.btn_detach.setEnabled(False)

    def _on_op_finished(self, op_name: str, result):
        self.status.showMessage(f'{op_name}: {result}', 5000)

    def _poll_snap(self):
        attached = self.bridge.is_attached()
        if not attached:
            # Bug 1 fix: detect attached→detached transition (game died/crashed)
            # and emit the signal so all buttons reset correctly.
            if self._was_attached:
                self._was_attached = False
                self.bridge.detach()   # cleans up pid, emits attached_changed(False)
            self.lbl_state_friendly.setText('Game not running')
            self.tab_status.update_snap(None, False, None)
            if self.snap_timer.interval() != 1000:
                self.snap_timer.setInterval(1000)
                self._snap_fail_count = 0
            return
        self._was_attached = True
        s = self.bridge.snap()
        if s is None:
            self._snap_fail_count += 1
            if self._snap_fail_count >= 3:
                self.lbl_state_friendly.setText('Connection lost')
                self.tab_status.update_snap(None, False, None)
                self.bridge.log.emit('Connection lost — detached automatically')
                self.bridge.detach()
                self._snap_fail_count = 0
            return
        self._snap_fail_count = 0
        try:
            gs = s.get('game_state', 0)
            menu = s.get('menu', 0)
            if gs != 0:
                friendly = 'In race'
            else:
                menu_name = MENU_NAMES.get(menu)
                friendly = f'In {menu_name}' if menu_name else 'In menu'
            self.lbl_state_friendly.setText(friendly)
            self.tab_status.update_snap(s, True, self.bridge.backend.pid)
            self.bridge.snap_updated.emit(s)
        except Exception:
            pass

    def closeEvent(self, ev):
        self.settings.setValue('geometry', self.saveGeometry())
        if hasattr(self.bridge, '_worker') and self.bridge._worker and self.bridge._worker.isRunning():
            self.bridge._worker.wait(2000)
        try:
            self.bridge.detach()
        except Exception:
            pass
        super().closeEvent(ev)
