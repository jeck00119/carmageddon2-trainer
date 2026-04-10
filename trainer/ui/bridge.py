"""
Qt bridge over Carma2Backend.

Frida callbacks fire on Frida's own thread; we marshal them into Qt main
thread via signals. Long-running ops (auto_start_race) run on a QThread
worker so the UI stays responsive.
"""
import threading

from PySide6.QtCore import QObject, QSettings, QThread, Signal

from backend.cheat_db import load_cheat_table, powerups_only
from backend.dev_actions import find_action
from backend.frida_core import Carma2Backend, find_game


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

    # Agent-side events surfaced as named signals (less stringly-typed)
    kbd_proc_captured = Signal(str)              # hook proc address
    toggle_ready      = Signal()                 # nGlide toggle addrs extracted

    # Dispatch table: agent event 'h' -> handler method name
    _AGENT_DISPATCH = {
        'kbd_proc':    '_handle_kbd_proc',
        'toggle_ready':'_handle_toggle_ready',
        'log':         '_handle_agent_log',
        'init_done':   '_handle_init_done',
    }

    # Emitted when game EXE can't be found — main_window shows a file dialog
    game_not_found = Signal()

    def __init__(self):
        super().__init__()
        self._settings = QSettings('carma2_tools', 'trainer')

        # Auto-detect game path
        saved = self._settings.value('game_exe', '')
        game_exe = find_game(saved_path=saved or '')
        if game_exe:
            self._settings.setValue('game_exe', game_exe)

        self.backend = Carma2Backend(
            on_event=self._on_event,
            on_log=lambda s: self.log.emit(s),
            game_exe=game_exe,
        )
        self._worker: Worker | None = None
        self.kbd_proc_addr: str = ''
        self.wants_windowed = False  # if True, fire alt_enter once toggle_ready
        # Cheat table loaded once at startup, shared by tabs.
        self.cheat_entries = load_cheat_table()
        self.powerup_entries = powerups_only(self.cheat_entries)
        # Persistent favorites (cheat names) — reuse self._settings from above
        saved = self._settings.value('favorites', None)
        if saved is None:
            self.favorites: list[str] = list(DEFAULT_FAVORITES)
            self._settings.setValue('favorites', self.favorites)
        elif isinstance(saved, str):
            # QSettings on some platforms returns a single string for a 1-item list
            self.favorites = [saved] if saved else []
        else:
            self.favorites = [str(x) for x in saved]

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
        handler_name = self._AGENT_DISPATCH.get(e.get('h'))
        if handler_name:
            getattr(self, handler_name)(e)

    def _handle_kbd_proc(self, e: dict):
        self.kbd_proc_addr = e.get('addr', '')
        self.log.emit(f'nGlide WH_KEYBOARD proc captured @ {self.kbd_proc_addr}')
        self.kbd_proc_captured.emit(self.kbd_proc_addr)

    def _handle_toggle_ready(self, e: dict):
        self.log.emit('nGlide toggle ready')
        self.toggle_ready.emit()
        if self.wants_windowed:
            self.wants_windowed = False
            # Defer slightly so the game's render context is fully up.
            # threading.Timer is used because this callback runs on the Frida
            # thread, not Qt main; alt_enter ultimately calls PostMessageA
            # which is thread-safe.
            threading.Timer(2.0, self.alt_enter).start()

    def _handle_agent_log(self, e: dict):
        self.log.emit(f'[agent] {e.get("msg", "")}')

    def _handle_init_done(self, e: dict):
        self.log.emit('agent loaded')

    # ----- attach lifecycle -----

    @property
    def game_path(self) -> str:
        return self.backend.game_exe or ''

    def set_game_path(self, path: str):
        """Set or change the game EXE path. Persists to QSettings."""
        self.backend.set_game_path(path)
        self._settings.setValue('game_exe', path)
        self.log.emit(f'Game path set: {path}')

    def attach_or_spawn(self):
        if self.backend.attach_running():
            self.attached_changed.emit(True)
        elif not self.backend.game_exe:
            self.log.emit('Game not found — please set the path')
            self.game_not_found.emit()
        else:
            try:
                self.backend.spawn()
                self.attached_changed.emit(True)
            except FileNotFoundError:
                self.log.emit('Game EXE not found — please set the path')
                self.game_not_found.emit()
            except Exception as e:
                self.log.emit(f'spawn failed: {e}')

    def detach(self):
        self.backend.detach()
        self.attached_changed.emit(False)

    def is_attached(self) -> bool:
        return self.backend.is_attached()

    # ----- snap (cheap, called from QTimer on main thread) -----

    def snap(self):
        return self.backend.snap()

    # ----- fire-and-forget ops -----

    def _safe_call(self, op_label: str, fn, *args, log_success: bool = True):
        """Generic wrapper: check attached, try call, log result/error.

        Returns the call result or None on failure. All bridge methods that
        wrap a backend RPC should go through this.
        """
        if not self.is_attached():
            self.log.emit(f'{op_label}: not attached')
            return None
        try:
            result = fn(*args)
            if log_success:
                self.log.emit(f'{op_label}: {result}')
            return result
        except Exception as e:
            self.log.emit(f'{op_label} failed: {e}')
            return None

    def fire_named(self, name: str):
        return self._safe_call(f'fire {name}', self.backend.fire_named, name)

    def fire_by_hash(self, h1: int, h2: int, label: str = ''):
        return self._safe_call(
            f'fire {label or f"0x{h1:08x}/0x{h2:08x}"}',
            self.backend.fire_by_hash, h1, h2)

    # ----- dev cheat dispatcher -----

    def dev_call(self, action_name: str, *runtime_args):
        """Look up a dev action by name and call its RPC. Used by DevTab.

        runtime_args are appended to the action's static args (e.g. a
        spinbox value passed in for an 'input' kind action).
        """
        action = find_action(action_name)
        if action is None:
            self.log.emit(f'dev_call: unknown action {action_name!r}')
            return None
        rpc = getattr(self.backend, action.rpc, None)
        if rpc is None:
            self.log.emit(f'dev_call: backend missing {action.rpc!r}')
            return None
        args = list(action.args) + list(runtime_args)
        return self._safe_call(action.label, rpc, *args)

    # ----- long-running ops (worker thread) -----

    def run_async(self, op_name: str, fn, *args):
        if self._worker is not None and self._worker.isRunning():
            self.log.emit(f'busy: {op_name} ignored')
            return
        self._worker = Worker(fn, *args)
        self._worker.done.connect(lambda r, n=op_name: self.op_finished.emit(n, r))
        self._worker.start()

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
            result = f'error: {e}'
        self.done.emit(result)
