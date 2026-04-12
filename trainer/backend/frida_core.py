"""
Frida backend for the Carma2 trainer.

Wraps spawn/attach lifecycle and exposes a clean Python API on top of
backend/agent.js.
"""
import os
import shutil
import string
import sys
import time
import winreg
from typing import Callable, Optional

# Make carma2_tools/ importable so we can pull in hash_function etc.
_TOOLS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import frida

from hash_function import KNOWN_CHEATS, carma2_hash, HIDDEN_CHEAT_HASH

GAME_PROC_NAME = 'carma2_hw.exe'
GAME_EXE_NAME = 'CARMA2_HW.EXE'

KNOWN_EXE_SIZE = 2680320
KNOWN_EXE_MD5 = '66a9c49483ff4415b518bb7df01385bd'

AGENT_JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'agent.js')

DGVOODOO_BUNDLED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'deps', 'dgvoodoo')
DGVOODOO_FILES = [
    ('Glide.dll',       'glide.dll'),
    ('Glide2x.dll',     'glide2x.dll'),
    ('Glide3x.dll',     'glide3x.dll'),
    ('dgVoodoo.conf',   'dgVoodoo.conf'),
    ('dgVoodooCpl.exe', 'dgVoodooCpl.exe'),
]

# Detect dgVoodoo 2's glide2x.dll so we don't replace it with nGlide.
# dgVoodoo's Glide2x.dll is ~200 KB and contains the literal "dgVoodoo" in its
# VERSIONINFO block as a UTF-16 string. Use a size-range + wide-string magic
# check (robust across minor dgVoodoo versions).
_DGVOODOO_MAGIC = 'dgVoodoo'.encode('utf-16-le')  # b'd\0g\0V\0o\0o\0d\0o\0o\0'

def _is_dgvoodoo_glide(path: str) -> bool:
    try:
        if not os.path.isfile(path):
            return False
        size = os.path.getsize(path)
        if not (100_000 <= size <= 400_000):
            return False
        with open(path, 'rb') as f:
            data = f.read()
        return _DGVOODOO_MAGIC in data
    except Exception:
        return False


def find_game(saved_path: str = '') -> Optional[str]:
    """Auto-detect the game EXE path."""
    if saved_path and os.path.isfile(saved_path):
        return saved_path

    try:
        device = frida.get_local_device()
        for proc in device.enumerate_processes():
            if proc.name.lower() == GAME_PROC_NAME:
                path = _get_process_path(proc.pid)
                if path and os.path.isfile(path):
                    return path
    except Exception:
        pass

    try:
        steam_path = _get_steam_path()
        if steam_path:
            for lib_folder in _get_steam_libraries(steam_path):
                candidate = os.path.join(lib_folder, 'steamapps', 'common',
                                         'Carmageddon2', GAME_EXE_NAME)
                if os.path.isfile(candidate):
                    return candidate
    except Exception:
        pass

    drives = [f'{d}:\\' for d in string.ascii_uppercase
              if os.path.exists(f'{d}:\\')]
    subdirs = [
        os.path.join('Program Files (x86)', 'Steam', 'steamapps', 'common', 'Carmageddon2'),
        os.path.join('Program Files', 'Steam', 'steamapps', 'common', 'Carmageddon2'),
        os.path.join('Steam', 'steamapps', 'common', 'Carmageddon2'),
        os.path.join('SteamLibrary', 'steamapps', 'common', 'Carmageddon2'),
        os.path.join('Games', 'Carmageddon2'),
        os.path.join('GOG Games', 'Carmageddon 2'),
        os.path.join('GOG Games', 'Carmageddon2'),
    ]
    for drive in drives:
        for sub in subdirs:
            candidate = os.path.join(drive, sub, GAME_EXE_NAME)
            if os.path.isfile(candidate):
                return candidate

    return None


def _get_steam_path() -> Optional[str]:
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam')
        val, _ = winreg.QueryValueEx(key, 'SteamPath')
        winreg.CloseKey(key)
        return val.replace('/', '\\')
    except Exception:
        return None


def _get_steam_libraries(steam_path: str) -> list[str]:
    libs = [steam_path]
    vdf = os.path.join(steam_path, 'steamapps', 'libraryfolders.vdf')
    if not os.path.isfile(vdf):
        vdf = os.path.join(steam_path, 'config', 'libraryfolders.vdf')
    if os.path.isfile(vdf):
        try:
            with open(vdf, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if '"path"' in line:
                        parts = line.split('"')
                        if len(parts) >= 4:
                            path = parts[3].replace('\\\\', '\\')
                            if os.path.isdir(path) and path not in libs:
                                libs.append(path)
        except Exception:
            pass
    return libs


def check_wrapper(game_dir: str) -> dict:
    """Detect which Glide wrapper is installed in the game folder."""
    result = {'type': 'none', 'ok': False, 'path': ''}
    if not game_dir:
        return result
    dll = os.path.join(game_dir, 'glide2x.dll')
    if not os.path.isfile(dll):
        return result
    result['path'] = dll
    if _is_dgvoodoo_glide(dll):
        result['type'] = 'dgvoodoo'
        result['ok'] = True
    else:
        result['type'] = 'other'
        result['ok'] = os.path.getsize(dll) > 100_000
    return result


def ensure_dgvoodoo(game_dir: str) -> bool:
    """Install the bundled dgVoodoo 2 Glide wrapper into the game folder.

    dgVoodoo 2 fixes windowed mode, Alt+Enter, Alt+Tab and focus-loss
    handling for Carmageddon 2, which nGlide does not. On first run the
    trainer copies the bundled Glide DLLs + conf + control panel into the
    game folder, backing up any existing glide*.dll to glide*.dll.bak_nglide.

    Idempotent: if the installed glide2x.dll already matches the bundled
    version (by dgVoodoo signature), does nothing and returns True.
    """
    if not game_dir or not os.path.isdir(game_dir):
        return False
    src_dir = os.path.abspath(DGVOODOO_BUNDLED_DIR)
    if not os.path.isdir(src_dir):
        return False

    # Verify the bundle is complete before touching anything
    for src_name, _ in DGVOODOO_FILES:
        if not os.path.isfile(os.path.join(src_dir, src_name)):
            return False

    # Already installed? Check glide2x.dll signature.
    dst_glide2x = os.path.join(game_dir, 'glide2x.dll')
    if _is_dgvoodoo_glide(dst_glide2x):
        # Still copy conf + CPL if missing (user may have removed them)
        for src_name, dst_name in DGVOODOO_FILES:
            dst = os.path.join(game_dir, dst_name)
            if not os.path.isfile(dst):
                try:
                    shutil.copy2(os.path.join(src_dir, src_name), dst)
                except Exception:
                    pass
        return True

    # Fresh install — back up any existing glide*.dll (likely nGlide)
    for glide_name in ('glide.dll', 'glide2x.dll', 'glide3x.dll'):
        existing = os.path.join(game_dir, glide_name)
        if os.path.isfile(existing):
            backup = existing + '.bak_nglide'
            if not os.path.isfile(backup):
                try:
                    shutil.copy2(existing, backup)
                except Exception:
                    pass

    # Copy the bundle
    try:
        for src_name, dst_name in DGVOODOO_FILES:
            shutil.copy2(os.path.join(src_dir, src_name),
                         os.path.join(game_dir, dst_name))
        return True
    except Exception:
        return False


def _get_process_path(pid: int) -> Optional[str]:
    h = None
    try:
        import ctypes
        from ctypes import wintypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if h:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            if ctypes.windll.kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return buf.value
    except Exception:
        pass
    finally:
        if h:
            try:
                ctypes.windll.kernel32.CloseHandle(h)
            except Exception:
                pass
    return None


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
        self._cancelled = False   # set by detach() to abort in-flight workers

        try:
            self.device = frida.get_local_device()
        except Exception as e:
            self._log(f'Frida init failed: {e}')
            raise

    def set_game_path(self, exe_path: str):
        self.game_exe = exe_path
        self.game_dir = os.path.dirname(exe_path)

    def verify_exe(self) -> bool:
        """Check that the game EXE matches the known Steam build."""
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
        # Bug 4 fix: clean up any prior session before re-attaching
        self.detach()
        self._cancelled = False

        with open(AGENT_JS, 'r', encoding='utf-8') as f:
            src = f.read()

        session = self.device.attach(pid)
        # Bug 3 fix: capture session in closure so the callback only clears
        # THIS session, not a newer one from a subsequent _attach() call.
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
        # Bug 3 fix: ignore stale callbacks from old sessions
        if detached_session is not None and detached_session is not self.session:
            return
        try:
            self._on_log(f'Session lost: {reason}')
        except Exception:
            pass
        self.session = None
        self.script = None
        self.api = None
        self.pid = None     # Bug 2 fix: clear pid so UI doesn't show stale info

    def detach(self):
        self._cancelled = True  # Bug 7: abort in-flight workers
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
        """Main -> NewGame -> race. Returns True on success."""
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
                return False  # Bug 6 fix: session lost = game died, not success
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
                try:
                    self._on_log(f'[script error] {desc}')
                except Exception:
                    pass
        except Exception:
            pass

    def _log(self, s: str):
        try:
            self._on_log(s)
        except Exception:
            pass
