"""
Qt bridge over Carma2Backend.

Frida callbacks fire on Frida's own thread; we marshal them into Qt main
thread via signals. Long-running ops (auto_start_race) run on a QThread
worker so the UI stays responsive.
"""
import os
import sys
import time

from PySide6.QtCore import QObject, QSettings, QThread, Signal

from backend.cheat_db import load_cheat_table, powerups_only
from backend.dev_actions import find_action
from backend.frida_core import (
    Carma2Backend, check_wrapper, ensure_dgvoodoo, find_game,
)

DEFAULT_FAVORITES = ['WHIZZ', 'MINGMING', 'WETWET', 'BIGTWAT', 'MOONINGMINNIE']


class BackendBridge(QObject):
    log              = Signal(str)
    attached_changed = Signal(bool)
    op_finished     = Signal(str, object)
    favorites_changed = Signal()
    snap_updated    = Signal(dict)

    _AGENT_DISPATCH = {
        'log':         '_handle_agent_log',
        'init_done':   '_handle_init_done',
    }

    game_not_found = Signal()
    wrapper_changed = Signal(bool)   # True = wrapper OK (dgVoodoo installed)

    def __init__(self):
        super().__init__()
        self._settings = QSettings('carma2_tools', 'trainer')

        saved = self._settings.value('game_exe', '')
        game_exe = find_game(saved_path=saved or '')
        self._settings.setValue('game_exe', game_exe or '')

        if game_exe:
            ensure_dgvoodoo(os.path.dirname(game_exe))
        wrapper_info = check_wrapper(os.path.dirname(game_exe)) if game_exe else {'ok': False}
        self.has_wrapper = wrapper_info.get('ok', False)
        self.wrapper_info = wrapper_info

        self.backend = Carma2Backend(
            on_event=self._on_event,
            on_log=lambda s: self._emit_log(s),
            game_exe=game_exe,
        )
        self._worker: Worker | None = None
        self.cheat_entries = load_cheat_table()
        self.powerup_entries = powerups_only(self.cheat_entries)

        saved = self._settings.value('favorites', None)
        if saved is None:
            self.favorites: list[str] = list(DEFAULT_FAVORITES)
            self._settings.setValue('favorites', self.favorites)
        elif isinstance(saved, str):
            self.favorites = [saved] if saved else []
        else:
            self.favorites = [str(x) for x in saved]

    def _emit_log(self, s: str):
        try:
            self.log.emit(s)
        except Exception:
            pass

    def is_favorite(self, name: str) -> bool:
        return name in self.favorites

    def toggle_favorite(self, name: str):
        if not name:
            return
        if name in self.favorites:
            self.favorites.remove(name)
        else:
            self.favorites.append(name)
        self._settings.setValue('favorites', self.favorites)
        self.favorites_changed.emit()

    # ----- agent event dispatch -----

    def _on_event(self, e: dict):
        try:
            handler_name = self._AGENT_DISPATCH.get(e.get('h'))
            if handler_name:
                getattr(self, handler_name)(e)
        except Exception:
            pass

    def _handle_agent_log(self, e: dict):
        self._emit_log(f'[agent] {e.get("msg", "")}')

    def _handle_init_done(self, e: dict):
        self._emit_log('agent loaded')

    # ----- attach lifecycle -----

    @property
    def game_path(self) -> str:
        return self.backend.game_exe or ''

    def set_game_path(self, path: str) -> bool:
        if not os.path.isfile(path):
            self._emit_log(f'Invalid path: {path}')
            return False
        if os.path.basename(path).upper() != 'CARMA2_HW.EXE':
            self._emit_log(f'Wrong EXE: expected CARMA2_HW.EXE, got {os.path.basename(path)}')
            return False
        self.backend.set_game_path(path)
        self._settings.setValue('game_exe', path)
        old = self.has_wrapper
        ensure_dgvoodoo(os.path.dirname(path))
        self.wrapper_info = check_wrapper(os.path.dirname(path))
        self.has_wrapper = self.wrapper_info.get('ok', False)
        if self.has_wrapper != old:
            self.wrapper_changed.emit(self.has_wrapper)
        self._emit_log(f'Game path: {path}')
        return True

    def attach_or_spawn(self):
        # Bug 5 fix: don't double-attach on rapid clicks
        if self.is_attached():
            self._emit_log('already attached')
            return
        try:
            if self.backend.attach_running():
                self._emit_log(f'attached to running process pid={self.backend.pid}')
                self.attached_changed.emit(True)
                return
        except Exception as e:
            self._emit_log(f'attach failed: {e}')

        if not self.backend.game_exe:
            self._emit_log('Game not found — please set the path')
            self.game_not_found.emit()
            return

        try:
            self.backend.spawn()
            self._emit_log(f'spawned pid={self.backend.pid}')
            self.attached_changed.emit(True)
        except FileNotFoundError:
            self._emit_log('Game EXE not found — please set the path')
            self.game_not_found.emit()
        except Exception as e:
            self._emit_log(f'spawn failed: {e}')

    def detach(self):
        try:
            self.backend.detach()
        except Exception:
            pass
        self.attached_changed.emit(False)

    def is_attached(self) -> bool:
        return self.backend.is_attached()

    def snap(self):
        return self.backend.snap()

    # ----- fire-and-forget ops -----

    _RPC_COOLDOWN = 0.3  # seconds between RPC calls (prevents game hangs)
    _last_rpc_time = 0.0

    def _safe_call(self, op_label: str, fn, *args, log_success: bool = True):
        if not self.is_attached():
            self._emit_log(f'{op_label}: not attached')
            return None
        now = time.monotonic()
        elapsed = now - self._last_rpc_time
        if elapsed < self._RPC_COOLDOWN:
            time.sleep(self._RPC_COOLDOWN - elapsed)
        self._last_rpc_time = time.monotonic()
        try:
            result = fn(*args)
            if log_success:
                self._emit_log(f'{op_label}: {result}')
            return result
        except Exception as e:
            self._emit_log(f'{op_label} failed: {e}')
            return None

    def fire_named(self, name: str):
        return self._safe_call(f'fire {name}', self.backend.fire_named, name)

    def fire_by_hash(self, h1: int, h2: int, label: str = ''):
        return self._safe_call(
            f'fire {label or f"0x{h1:08x}/0x{h2:08x}"}',
            self.backend.fire_by_hash, h1, h2)

    def dev_call(self, action_name: str, *runtime_args):
        action = find_action(action_name)
        if action is None:
            self._emit_log(f'dev_call: unknown action {action_name!r}')
            return None
        rpc = getattr(self.backend, action.rpc, None)
        if rpc is None:
            self._emit_log(f'dev_call: backend missing {action.rpc!r}')
            return None
        args = list(action.args) + list(runtime_args)
        return self._safe_call(action.label, rpc, *args)

    # ----- long-running ops -----

    def run_async(self, op_name: str, fn, *args):
        if self._worker is not None and self._worker.isRunning():
            self._emit_log(f'busy: {op_name} ignored')
            return
        self._worker = Worker(fn, *args)
        self._worker.done.connect(lambda r, n=op_name: self._on_worker_done(n, r))
        self._worker.start()

    def _on_worker_done(self, op_name: str, result):
        self._worker = None
        self.op_finished.emit(op_name, result)

    def auto_start_race(self):
        self.run_async('auto_start_race', self.backend.auto_start_race)


class Worker(QThread):
    done = Signal(object)

    def __init__(self, fn, *args):
        super().__init__()
        self._fn = fn
        self._args = args

    def run(self):
        try:
            result = self._fn(*self._args)
        except Exception as e:
            result = f'error: {e}'
        self.done.emit(result)
