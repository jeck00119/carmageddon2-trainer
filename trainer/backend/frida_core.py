"""
Frida backend for the Carma2 trainer.

Wraps spawn/attach lifecycle and exposes a clean Python API on top of
backend/agent.js. Game detection and dgVoodoo management are in separate
modules (game_detect.py, dgvoodoo.py).
"""
import os
import time
from typing import Callable, Optional

import frida

from hash_function import KNOWN_CHEATS, carma2_hash, HIDDEN_CHEAT_HASH
from backend.game_detect import GAME_PROC_NAME, KNOWN_EXE_SIZE, KNOWN_EXE_MD5

AGENT_JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'agent.js')


class Carma2Backend:
    """High-level wrapper around the Frida agent."""

    def __init__(self, on_event: Optional[Callable[[dict], None]] = None,
                 on_log: Optional[Callable[[str], None]] = None,
                 game_exe: Optional[str] = None):
        self._on_event = on_event or (lambda e: None)
        self._on_log = on_log or (lambda s: None)
        self.game_exe: Optional[str] = game_exe
        self.game_dir: Optional[str] = os.path.dirname(game_exe) if game_exe else None

        self.session: Optional[frida.core.Session] = None
        self.script: Optional[frida.core.Script] = None
        self.api = None
        self.pid: Optional[int] = None
        self._cancelled = False

        try:
            self.device = frida.get_local_device()
        except Exception as e:
            self._log(f'Frida init failed: {e}')
            raise

    def set_game_path(self, exe_path: str):
        self.game_exe = exe_path
        self.game_dir = os.path.dirname(exe_path)

    def verify_exe(self) -> bool:
        if not self.game_exe or not os.path.isfile(self.game_exe):
            return False
        if os.path.getsize(self.game_exe) != KNOWN_EXE_SIZE:
            self._log('Warning: EXE size mismatch — hooks may not work')
            return False
        try:
            import hashlib
            with open(self.game_exe, 'rb') as f:
                if hashlib.md5(f.read()).hexdigest() != KNOWN_EXE_MD5:
                    self._log('Warning: EXE checksum mismatch — hooks may not work')
                    return False
        except Exception:
            pass
        return True

    # ----- attach/spawn -----

    def is_attached(self) -> bool:
        return self.session is not None and self.script is not None

    def find_running(self) -> Optional[int]:
        try:
            for p in self.device.enumerate_processes():
                if p.name.lower() == GAME_PROC_NAME:
                    return p.pid
        except Exception:
            return None
        return None

    def attach_running(self) -> bool:
        pid = self.find_running()
        if pid is None:
            return False
        self.verify_exe()
        self._attach(pid, resume=False)
        return True

    def spawn(self, nocutscene: bool = True) -> int:
        if not self.game_exe or not os.path.isfile(self.game_exe):
            raise FileNotFoundError(f'Game not found: {self.game_exe}')
        self.verify_exe()
        argv = [self.game_exe]
        if nocutscene:
            argv.append('-NOCUTSCENE')
        pid = self.device.spawn(argv, cwd=self.game_dir)
        self._attach(pid, resume=True)
        return pid

    def _attach(self, pid: int, resume: bool):
        self.detach()
        self._cancelled = False

        with open(AGENT_JS, 'r', encoding='utf-8') as f:
            src = f.read()

        session = self.device.attach(pid)
        session.on('detached',
                   lambda reason, crash, s=session: self._on_session_detached(reason, crash, s))

        script = session.create_script(src)
        script.on('message', self._on_message)
        try:
            script.load()
        except Exception:
            try:
                session.detach()
            except Exception:
                pass
            raise

        self.session = session
        self.script = script
        self.api = script.exports_sync
        self.pid = pid

        if resume:
            self.device.resume(pid)

    def _on_session_detached(self, reason, crash, detached_session=None):
        if detached_session is not None and detached_session is not self.session:
            return
        try:
            self._on_log(f'Session lost: {reason}')
        except Exception:
            pass
        self.session = None
        self.script = None
        self.api = None
        self.pid = None

    def detach(self):
        self._cancelled = True
        if self.session is not None:
            try:
                self.session.detach()
            except Exception:
                pass
        self.session = None
        self.script = None
        self.api = None
        self.pid = None

    # ----- RPC wrappers -----

    def _rpc(self, method: str, *args):
        api = self.api
        if api is None:
            raise frida.InvalidOperationError('not attached')
        fn = getattr(api, method, None)
        if fn is None:
            raise frida.InvalidOperationError(f'no RPC method {method!r}')
        return fn(*args)

    def snap(self) -> Optional[dict]:
        if self.api is None:
            return None
        try:
            return self.api.snap()
        except Exception:
            return None

    def click_sel(self, sel: int) -> str:
        return self._rpc('click_sel', sel)

    def fire_by_hash(self, h1: int, h2: int) -> str:
        return self._rpc('fire_by_hash', h1, h2)

    def fire_named(self, name: str) -> str:
        if name.upper() == 'HIDDEN':
            h = HIDDEN_CHEAT_HASH
        else:
            h = KNOWN_CHEATS.get(name.upper()) or carma2_hash(name)
        return self.fire_by_hash(h[0], h[1])

    # ----- dev cheat RPCs -----

    def dev_enable(self) -> str: return self._rpc('dev_enable')
    def dev_disable(self) -> str: return self._rpc('dev_disable')
    def dev_is_enabled(self) -> bool: return bool(self._rpc('dev_is_enabled'))

    def set_credits(self, amt: int) -> str: return self._rpc('set_credits', amt)
    def add_credits(self, delta: int) -> str: return self._rpc('add_credits', delta)

    def instant_repair(self) -> str: return self._rpc('instant_repair')
    def damage_cycle(self) -> str: return self._rpc('damage_cycle')
    def timer_toggle(self) -> str: return self._rpc('timer_toggle')
    def teleport(self) -> str: return self._rpc('teleport')

    def spawn_powerup(self, pid: int) -> str: return self._rpc('spawn_powerup', pid)

    def gravity_toggle(self) -> str: return self._rpc('gravity_toggle')
    def gonad_of_death(self) -> str: return self._rpc('gonad_of_death')

    def unlock_all_cameras(self) -> str: return self._rpc('unlock_all_cameras')

    def hud_cycle(self) -> str: return self._rpc('hud_cycle')

    def hidden_cheat(self) -> str: return self._rpc('hidden_cheat')

    def simple_toggle(self) -> str: return self._rpc('simple_toggle')

    # ----- high-level macros -----

    def _wait_for(self, predicate, timeout: float, poll: float = 0.1) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._cancelled:
                return False
            s = self.snap()
            if s is None:
                return False
            if predicate(s):
                return True
            time.sleep(poll)
        return False

    def _wait_stable(self, key: str, ticks: int = 8, poll: float = 0.1,
                     timeout: float = 8.0) -> bool:
        deadline = time.time() + timeout
        last = None
        stable = 0
        while time.time() < deadline:
            if self._cancelled:
                return False
            s = self.snap()
            if s is None:
                return False
            v = s.get(key)
            if v == last:
                stable += 1
                if stable >= ticks:
                    return True
            else:
                last = v
                stable = 1
            time.sleep(poll)
        return False

    def auto_start_race(self, timeout: float = 60.0) -> bool:
        snap = self.snap()
        if snap is None:
            return False
        main_menu = snap.get('main_menu', 0)
        newgame_menu = snap.get('newgame_menu', 0)

        if not self._wait_for(lambda s: s.get('menu') == main_menu, timeout):
            return False
        self._wait_stable('dogame_state', ticks=3, poll=0.1, timeout=1.0)

        try:
            self.click_sel(21)
        except Exception:
            return False

        if not self._wait_for(lambda s: s.get('menu') == newgame_menu, 2.0):
            return False
        self._wait_stable('dogame_state', ticks=6, poll=0.1, timeout=4.0)

        try:
            self.click_sel(5)
        except Exception:
            return False

        deadline = time.time() + 20.0
        while time.time() < deadline:
            if self._cancelled:
                return False
            s = self.snap()
            if s is None:
                return False
            if s.get('dogame_state', 0) >= 4 or s.get('game_state', 0) != 0:
                break
            time.sleep(0.2)
        else:
            return False

        return True

    # ----- internals -----

    def _on_message(self, msg, data):
        try:
            mtype = msg.get('type', '?')
            if mtype == 'send':
                payload = msg.get('payload')
                if payload:
                    self._on_event(payload)
            elif mtype == 'error':
                desc = msg.get('description', '')
                self._log(f'[script error] {desc}')
        except Exception:
            pass

    def _log(self, s: str):
        try:
            self._on_log(s)
        except Exception:
            pass
