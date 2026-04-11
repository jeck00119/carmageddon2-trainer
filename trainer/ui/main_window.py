"""Main trainer window."""
import ctypes
import ctypes.wintypes
import sys
import webbrowser

from PySide6.QtCore import QAbstractNativeEventFilter, QSettings, QTimer, Qt
from PySide6.QtWidgets import (QApplication, QCheckBox, QFileDialog, QHBoxLayout,
                                QLabel, QMainWindow, QMessageBox, QPushButton,
                                QStatusBar, QTabWidget, QVBoxLayout, QWidget)

from ui.bridge import BackendBridge
from ui.tab_dev import DevTab
from ui.tab_powerups import PowerupTab
from ui.tab_race import RaceTab
from ui.tab_status import MENU_NAMES, StatusTab


WM_HOTKEY = 0x0312
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
VK_W = 0x57
HOTKEY_ID_ALT_ENTER = 0xC2A1


class _HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self.cb = callback

    def nativeEventFilter(self, eventType, message):
        try:
            if bytes(eventType).startswith(b'windows'):
                msg = ctypes.wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY:
                    self.cb(int(msg.wParam))
        except Exception:
            pass
        return False, 0


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
        self.bridge.nglide_changed.connect(self._on_nglide_changed)

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

        self.cb_windowed = QCheckBox('Start in windowed')
        self.cb_windowed.setToolTip(
            'When enabled, the trainer toggles to windowed mode automatically '
            'after spawning the game. Requires nGlide.')
        top_lay.addWidget(self.cb_windowed)

        self.btn_toggle_window = QPushButton('Windowed ⇄')
        self.btn_toggle_window.setMinimumHeight(36)
        self.btn_toggle_window.setToolTip(
            'Toggle between windowed and fullscreen at runtime '
            '(or use the global Ctrl+Shift+W hotkey). Requires nGlide.')
        self.btn_toggle_window.setEnabled(False)
        self.btn_toggle_window.clicked.connect(self.bridge.alt_enter)
        top_lay.addWidget(self.btn_toggle_window)

        # Disable windowed controls if nGlide not compatible
        info = self.bridge.nglide_info
        if not self.bridge.has_nglide:
            self.cb_windowed.setEnabled(False)
            tip = 'nGlide not installed — windowed mode unavailable'
            if info.get('found') and not info.get('ok'):
                tip = (f'nGlide version too old ({info.get("version") or "unknown"}, '
                       f'{info.get("size")} bytes) — need v2.0+ for windowed mode')
            self.cb_windowed.setToolTip(tip)
            self.btn_toggle_window.setToolTip(tip)

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

        # --- Restore window geometry ---
        self.settings = QSettings('carma2_tools', 'trainer')
        geom = self.settings.value('geometry')
        if geom:
            self.restoreGeometry(geom)

        # --- Global hotkey: Ctrl+Shift+W -> toggle windowed ---
        self._hk_filter = _HotkeyFilter(self._on_hotkey)
        QApplication.instance().installNativeEventFilter(self._hk_filter)
        try:
            ok = ctypes.windll.user32.RegisterHotKey(
                None, HOTKEY_ID_ALT_ENTER,
                MOD_CONTROL | MOD_SHIFT, VK_W)
            if ok:
                self.status.showMessage('Global hotkey: Ctrl+Shift+W = toggle windowed', 8000)
        except Exception:
            pass

    def _on_hotkey(self, hk_id: int):
        if hk_id == HOTKEY_ID_ALT_ENTER:
            if not self.bridge.has_nglide:
                return
            self.bridge.alt_enter()

    def _attach_clicked(self):
        if self.cb_windowed.isChecked() and not self.bridge.has_nglide:
            self._prompt_nglide_download()
            return
        self.bridge.wants_windowed = self.cb_windowed.isChecked()
        self.bridge.attach_or_spawn()

    def _on_nglide_changed(self, present: bool):
        self.cb_windowed.setEnabled(present)
        if present:
            self.cb_windowed.setToolTip(
                'When enabled, the trainer toggles to windowed mode automatically '
                'after spawning the game. Requires nGlide.')
            self.btn_toggle_window.setToolTip(
                'Toggle between windowed and fullscreen at runtime '
                '(or use the global Ctrl+Shift+W hotkey).')
        else:
            self.cb_windowed.setChecked(False)
            self.cb_windowed.setToolTip('nGlide not installed — windowed mode unavailable')
            self.btn_toggle_window.setToolTip('nGlide not installed — windowed mode unavailable')

    def _prompt_nglide_download(self):
        reply = QMessageBox.question(
            self, 'nGlide Required',
            'Windowed mode requires nGlide (a free Glide wrapper).\n\n'
            'The game will still work in fullscreen without it.\n\n'
            'Open the nGlide download page?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if reply == QMessageBox.Yes:
            webbrowser.open('https://www.zeus-software.com/downloads/nglide')
        self.cb_windowed.setChecked(False)

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
            self.btn_toggle_window.setEnabled(self.bridge.has_nglide)
        else:
            self.lbl_state.setText('●  Detached')
            self.lbl_state.setStyleSheet('color: #e85050; font-weight: 600;')
            self.btn_attach.setEnabled(True)
            self.btn_detach.setEnabled(False)
            self.btn_toggle_window.setEnabled(False)

    def _on_op_finished(self, op_name: str, result):
        self.status.showMessage(f'{op_name}: {result}', 5000)

    def _poll_snap(self):
        attached = self.bridge.is_attached()
        if not attached:
            self.lbl_state_friendly.setText('Game not running')
            self.tab_status.update_snap(None, False, None)
            if self.snap_timer.interval() != 1000:
                self.snap_timer.setInterval(1000)
                self._snap_fail_count = 0
            return
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
        try:
            ctypes.windll.user32.UnregisterHotKey(None, HOTKEY_ID_ALT_ENTER)
        except Exception:
            pass
        self.settings.setValue('geometry', self.saveGeometry())
        if hasattr(self.bridge, '_worker') and self.bridge._worker and self.bridge._worker.isRunning():
            self.bridge._worker.wait(2000)
        try:
            self.bridge.detach()
        except Exception:
            pass
        super().closeEvent(ev)
