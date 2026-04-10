"""
Qt bridge over Carma2Backend.

Frida callbacks fire on Frida's own thread; we marshal them into Qt main
thread via signals. Long-running ops (auto_start_race) run on a QThread
worker so the UI stays responsive.
"""
import os
import sys
import threading
import traceback

from PySide6.QtCore import QObject, QSettings, QThread, Signal

from backend.cheat_db import load_cheat_table, powerups_only
from backend.dev_actions import find_action
from backend.frida_core import Carma2Backend, check_nglide, ensure_nglide, find_game

_log = lambda msg: print(f'[bridge] {msg}', file=sys.stderr, flush=True)

# First-run favorites: the curated 5 powerups that used to be hardcoded
# in the Race tab's IN-RACE TOGGLES group.
DEFAULT_FAVORITES = ['WHIZZ', 'MINGMING', 'WETWET', 'BIGTWAT', 'MOONINGMINNIE']


class BackendBridge(QObject):
    # User-facing signals
    log              = Signal(str)
    attached_changed = Signal(bool)              # True=attached, False=detached
    op_finished     = Signal(str, object)        # (op_name, result)
    favorites_changed = Signal()                 # user pinned/unpinned a powerup
    snap_updated    = Signal(dict)               # full compound snap (1 Hz from main_window poller)

    # Agent-side events (used internally by dispatch handlers)
    kbd_proc_captured = Signal(str)
    toggle_ready      = Signal()

    # Dispatch table: agent event 'h' -> handler method name
    _AGENT_DISPATCH = {
        'kbd_proc':    '_handle_kbd_proc',
        'toggle_ready':'_handle_toggle_ready',
        'log':         '_handle_agent_log',
        'init_done':   '_handle_init_done',
    }

    # Emitted when game EXE can't be found — main_window shows a file dialog
    game_not_found = Signal()
    # Emitted when nGlide status changes — UI should refresh windowed controls
    nglide_changed = Signal(bool)  # True = nGlide present

    def __init__(self, safe_mode: bool = False):
        super().__init__()
        _log(f'init (safe_mode={safe_mode})')
        self._settings = QSettings('carma2_tools', 'trainer')

        # Auto-detect game path
        saved = self._settings.value('game_exe', '')
        game_exe = find_game(saved_path=saved or '')
        self._settings.setValue('game_exe', game_exe or '')

        # Ensure correct nGlide DLL is installed, then check status
        if game_exe:
            ensure_nglide(os.path.dirname(game_exe))
        nglide_info = check_nglide(os.path.dirname(game_exe)) if game_exe else {'ok': False}
        self.has_nglide = nglide_info.get('ok', False)
        self.nglide_info = nglide_info

        self.backend = Carma2Backend(
            on_event=self._on_event,
            on_log=lambda s: self._emit_log(s),
            game_exe=game_exe,
            safe_mode=safe_mode,
        )
        self._worker: Worker | None = None
        self.kbd_proc_addr: str = ''
        self.wants_windowed = False
        # Cheat table loaded once at startup, shared by tabs.
        self.cheat_entries = load_cheat_table()
        self.powerup_entries = powerups_only(self.cheat_entries)
        # Persistent favorites
        saved = self._settings.value('favorites', None)
        if saved is None:
            self.favorites: list[str] = list(DEFAULT_FAVORITES)
            self._settings.setValue('favorites', self.favorites)
        elif isinstance(saved, str):
            self.favorites = [saved] if saved else []
        else:
            self.favorites = [str(x) for x in saved]
        _log('init complete')

    def _emit_log(self, s: str):
        """Safe signal emit — won't crash if called from non-Qt thread."""
        try:
            self.log.emit(s)
        except Exception as e:
            print(f'[bridge] log.emit failed: {e}', file=sys.stderr, flush=True)

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
        """Dispatches agent events — called from Frida's thread."""
        try:
            handler_name = self._AGENT_DISPATCH.get(e.get('h'))
            if handler_name:
                getattr(self, handler_name)(e)
        except Exception as ex:
            print(f'[bridge] _on_event exception: {ex}', file=sys.stderr, flush=True)
            traceback.print_exc(file=sys.stderr)

    def _handle_kbd_proc(self, e: dict):
        self.kbd_proc_addr = e.get('addr', '')
        self._emit_log(f'nGlide WH_KEYBOARD proc captured @ {self.kbd_proc_addr}')
        self.kbd_proc_captured.emit(self.kbd_proc_addr)

    def _handle_toggle_ready(self, e: dict):
        self._emit_log('nGlide toggle addresses extracted — windowed toggle ready')
        self.toggle_ready.emit()
        if self.wants_windowed:
            self.wants_windowed = False
            self._emit_log('Auto-toggling to windowed mode in 2s...')
            threading.Timer(2.0, self._safe_alt_enter_timer).start()

    def _safe_alt_enter_timer(self):
        """Timer callback for auto-windowed — runs on Timer thread."""
        try:
            self.alt_enter()
        except Exception as e:
            print(f'[bridge] auto-windowed timer failed: {e}', file=sys.stderr, flush=True)

    def _handle_agent_log(self, e: dict):
        self._emit_log(f'[agent] {e.get("msg", "")}')

    def _handle_init_done(self, e: dict):
        self._emit_log('agent loaded')

    # ----- attach lifecycle -----

    @property
    def game_path(self) -> str:
        return self.backend.game_exe or ''

    def set_game_path(self, path: str) -> bool:
        """Set or change the game EXE path. Validates and persists to QSettings."""
        if not os.path.isfile(path):
            self._emit_log(f'Invalid path: {path}')
            return False
        if os.path.basename(path).upper() != 'CARMA2_HW.EXE':
            self._emit_log(f'Wrong EXE: expected CARMA2_HW.EXE, got {os.path.basename(path)}')
            return False
        self.backend.set_game_path(path)
        self._settings.setValue('game_exe', path)
        old_nglide = self.has_nglide
        ensure_nglide(os.path.dirname(path))
        self.nglide_info = check_nglide(os.path.dirname(path))
        self.has_nglide = self.nglide_info.get('ok', False)
        if self.has_nglide != old_nglide:
            self.nglide_changed.emit(self.has_nglide)
        self._emit_log(f'Game path: {path}')
        return True

    def attach_or_spawn(self):
        _log(f'attach_or_spawn: exe={self.backend.game_exe} nglide={self.has_nglide}')
        self._emit_log(f'attach_or_spawn: exe={self.backend.game_exe} nglide={self.has_nglide}')
        try:
            if self.backend.attach_running():
                self._emit_log(f'attached to running process pid={self.backend.pid}')
                self.attached_changed.emit(True)
                return
        except Exception as e:
            _log(f'attach_running failed: {type(e).__name__}: {e}')
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
            _log(f'spawn failed: {type(e).__name__}: {e}')
            traceback.print_exc(file=sys.stderr)
            self._emit_log(f'spawn failed: {e}')

    def detach(self):
        try:
            self.backend.detach()
        except Exception as e:
            _log(f'detach exception: {e}')
        self.attached_changed.emit(False)

    def is_attached(self) -> bool:
        return self.backend.is_attached()

    # ----- snap (cheap, called from QTimer on main thread) -----

    def snap(self):
        return self.backend.snap()

    # ----- fire-and-forget ops -----

    def _safe_call(self, op_label: str, fn, *args, log_success: bool = True):
        """Generic wrapper: check attached, try call, log result/error."""
        if not self.is_attached():
            self._emit_log(f'{op_label}: not attached')
            return None
        try:
            result = fn(*args)
            if log_success:
                self._emit_log(f'{op_label}: {result}')
            return result
        except Exception as e:
            _log(f'{op_label} failed: {type(e).__name__}: {e}')
            self._emit_log(f'{op_label} failed: {e}')
            return None

    def fire_named(self, name: str):
        return self._safe_call(f'fire {name}', self.backend.fire_named, name)

    def fire_by_hash(self, h1: int, h2: int, label: str = ''):
        return self._safe_call(
            f'fire {label or f"0x{h1:08x}/0x{h2:08x}"}',
            self.backend.fire_by_hash, h1, h2)

    # ----- dev cheat dispatcher -----

    def dev_call(self, action_name: str, *runtime_args):
        """Look up a dev action by name and call its RPC."""
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

    # ----- long-running ops (worker thread) -----

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

    def alt_enter(self):
        return self._safe_call('alt+enter', self.backend.alt_enter)


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
            tb = traceback.format_exc()
            print(f'[worker] exception: {e}\n{tb}', file=sys.stderr, flush=True)
            result = f'error: {e}'
        self.done.emit(result)
