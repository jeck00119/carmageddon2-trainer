"""
Frida backend for the Carma2 trainer.

Wraps spawn/attach lifecycle and exposes a clean Python API on top of
backend/agent.js. Designed to be driven from a Qt UI thread via signals,
but is fully usable from a REPL for testing.
"""
import os
import string
import sys
import time
import traceback
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

# Known good Steam build — all hardcoded VAs are for this exact binary
KNOWN_EXE_SIZE = 2680320
KNOWN_EXE_MD5 = '66a9c49483ff4415b518bb7df01385bd'

AGENT_JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'agent.js')

_log_stderr = lambda tag, msg: print(f'[{tag}] {msg}', file=sys.stderr, flush=True)


def find_game(saved_path: str = '') -> Optional[str]:
    """Auto-detect the game EXE path. Returns full path or None.

    Search order:
      1. saved_path (from QSettings — if valid, use it)
      2. Running process (get path from Frida's process list)
      3. Steam library folders (from Windows registry)
      4. Common install paths on all drives
    """
    _log_stderr('find_game', f'saved_path={saved_path!r}')

    # 1. Saved path
    if saved_path and os.path.isfile(saved_path):
        _log_stderr('find_game', f'using saved path: {saved_path}')
        return saved_path

    # 2. Running process — if game is already open, get its path
    try:
        device = frida.get_local_device()
        for proc in device.enumerate_processes():
            if proc.name.lower() == GAME_PROC_NAME:
                path = _get_process_path(proc.pid)
                if path and os.path.isfile(path):
                    _log_stderr('find_game', f'found running: pid={proc.pid} path={path}')
                    return path
    except Exception as e:
        _log_stderr('find_game', f'process scan failed: {type(e).__name__}: {e}')

    # 3. Steam library folders from registry
    try:
        steam_path = _get_steam_path()
        if steam_path:
            _log_stderr('find_game', f'Steam path: {steam_path}')
            for lib_folder in _get_steam_libraries(steam_path):
                candidate = os.path.join(lib_folder, 'steamapps', 'common',
                                         'Carmageddon2', GAME_EXE_NAME)
                if os.path.isfile(candidate):
                    _log_stderr('find_game', f'found in Steam lib: {candidate}')
                    return candidate
    except Exception as e:
        _log_stderr('find_game', f'Steam search failed: {type(e).__name__}: {e}')

    # 4. Common paths on all drives
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
                _log_stderr('find_game', f'found at common path: {candidate}')
                return candidate

    _log_stderr('find_game', 'game not found anywhere')
    return None


def _get_steam_path() -> Optional[str]:
    """Read Steam install path from Windows registry."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam')
        val, _ = winreg.QueryValueEx(key, 'SteamPath')
        winreg.CloseKey(key)
        return val.replace('/', '\\')
    except Exception as e:
        _log_stderr('steam', f'registry read failed: {e}')
        return None


def _get_steam_libraries(steam_path: str) -> list[str]:
    """Parse Steam's libraryfolders.vdf for all library paths."""
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
        except Exception as e:
            _log_stderr('steam', f'VDF parse failed: {e}')
    return libs


def check_nglide(game_dir: str) -> dict:
    """Check nGlide status in the game folder. Returns a dict with details."""
    result = {'found': False, 'version': '', 'size': 0, 'path': '', 'ok': False}
    if not game_dir:
        return result
    dll = os.path.join(game_dir, 'glide2x.dll')
    if not os.path.isfile(dll):
        return result
    result['found'] = True
    result['path'] = dll
    result['size'] = os.path.getsize(dll)

    try:
        import ctypes
        size = ctypes.windll.version.GetFileVersionInfoSizeW(dll, None)
        if size:
            buf = ctypes.create_string_buffer(size)
            ctypes.windll.version.GetFileVersionInfoW(dll, 0, size, buf)
            p = ctypes.c_void_p()
            l = ctypes.c_uint()
            if ctypes.windll.version.VerQueryValueW(buf, '\\\\', ctypes.byref(p), ctypes.byref(l)):
                import struct
                info = ctypes.string_at(p.value, l.value)
                if len(info) >= 48:
                    ms, ls = struct.unpack_from('<II', info, 8)
                    major = ms >> 16
                    minor = ms & 0xffff
                    result['version'] = f'{major}.{minor}'
    except Exception as e:
        _log_stderr('nglide', f'version read failed: {e}')

    if result['version']:
        try:
            major = int(result['version'].split('.')[0])
            result['ok'] = major >= 2
        except ValueError:
            result['ok'] = result['size'] > 150_000
    else:
        result['ok'] = result['size'] > 150_000

    _log_stderr('nglide', f'check result: {result}')
    return result


def _get_process_path(pid: int) -> Optional[str]:
    """Get the full exe path for a running process by PID."""
    h = None
    try:
        import ctypes
        from ctypes import wintypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if h:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            ok = ctypes.windll.kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
            if ok:
                return buf.value
    except Exception as e:
        _log_stderr('process', f'path query failed for pid={pid}: {e}')
    finally:
        if h:
            try:
                import ctypes
                ctypes.windll.kernel32.CloseHandle(h)
            except Exception:
                pass
    return None


class Carma2Backend:
    """High-level wrapper around the Frida agent."""

    def __init__(self, on_event: Optional[Callable[[dict], None]] = None,
                 on_log: Optional[Callable[[str], None]] = None,
                 game_exe: Optional[str] = None,
                 safe_mode: bool = False):
        self._on_event = on_event or (lambda e: None)
        self._on_log = on_log or (lambda s: None)
        self.safe_mode = safe_mode
        self.game_exe: Optional[str] = game_exe
        self.game_dir: Optional[str] = os.path.dirname(game_exe) if game_exe else None

        self.session: Optional[frida.core.Session] = None
        self.script: Optional[frida.core.Script] = None
        self.api = None
        self.pid: Optional[int] = None

        try:
            self.device = frida.get_local_device()
            self._log(f'Frida device: {self.device.name} (frida {frida.__version__})')
        except Exception as e:
            self._log(f'FATAL: frida.get_local_device() failed: {type(e).__name__}: {e}')
            raise

    def set_game_path(self, exe_path: str):
        """Set or change the game EXE path."""
        self.game_exe = exe_path
        self.game_dir = os.path.dirname(exe_path)

    def verify_exe(self) -> bool:
        """Check that the game EXE matches the known Steam build."""
        if not self.game_exe or not os.path.isfile(self.game_exe):
            self._log(f'verify_exe: file not found: {self.game_exe}')
            return False
        size = os.path.getsize(self.game_exe)
        if size != KNOWN_EXE_SIZE:
            self._log(f'*** EXE MISMATCH: size={size} expected={KNOWN_EXE_SIZE} ***')
            return False
        try:
            import hashlib
            with open(self.game_exe, 'rb') as f:
                md5 = hashlib.md5(f.read()).hexdigest()
            if md5 != KNOWN_EXE_MD5:
                self._log(f'*** EXE MISMATCH: md5={md5} expected={KNOWN_EXE_MD5} ***')
                return False
        except Exception as e:
            self._log(f'MD5 check failed: {e} (continuing anyway)')
        self._log(f'EXE verified: size={size} md5 OK')
        return True

    # ----- attach/spawn -----

    def is_attached(self) -> bool:
        return self.session is not None and self.script is not None

    def find_running(self) -> Optional[int]:
        self._log(f'scanning for {GAME_PROC_NAME}...')
        try:
            for p in self.device.enumerate_processes():
                if p.name.lower() == GAME_PROC_NAME:
                    self._log(f'found pid={p.pid} name={p.name}')
                    return p.pid
        except Exception as e:
            self._log(f'enumerate_processes failed: {type(e).__name__}: {e}')
            return None
        self._log(f'{GAME_PROC_NAME} not running')
        return None

    def attach_running(self) -> bool:
        pid = self.find_running()
        if pid is None:
            return False
        self.verify_exe()
        self._log(f'attaching to existing process pid={pid}')
        self._attach(pid, resume=False)
        return True

    def spawn(self, nocutscene: bool = True) -> int:
        if not self.game_exe or not os.path.isfile(self.game_exe):
            raise FileNotFoundError(f'Game not found: {self.game_exe}')
        self.verify_exe()
        argv = [self.game_exe]
        if nocutscene:
            argv.append('-NOCUTSCENE')
        self._log(f'spawning {argv}')
        pid = self.device.spawn(argv, cwd=self.game_dir)
        self._attach(pid, resume=True)
        return pid

    def _attach(self, pid: int, resume: bool):
        self._log(f'attaching to pid={pid} (resume={resume}) safe_mode={self.safe_mode}')
        try:
            with open(AGENT_JS, 'r', encoding='utf-8') as f:
                src = f.read()
        except FileNotFoundError:
            self._log(f'FATAL: agent.js not found at {AGENT_JS}')
            raise
        if self.safe_mode:
            src = 'globalThis._safeMode = true;\n' + src
        self._log(f'agent.js loaded ({len(src)} bytes)')

        try:
            session = self.device.attach(pid)
        except Exception as e:
            self._log(f'device.attach() FAILED: {type(e).__name__}: {e}')
            raise
        self._log('session created')
        session.on('detached', self._on_session_detached)

        script = session.create_script(src)
        script.on('message', self._on_message)
        self._log('loading script...')
        try:
            script.load()
        except Exception as e:
            self._log(f'script.load() FAILED: {type(e).__name__}: {e}')
            try:
                session.detach()
            except Exception:
                pass
            raise
        self._log('script loaded — checking exports...')

        self.session = session
        self.script = script
        self.api = script.exports_sync
        self.pid = pid

        # Verify agent is responsive
        try:
            test = self.api.snap()
            self._log(f'agent alive — snap keys={list(test.keys()) if test else "None"}')
        except Exception as e:
            self._log(f'agent snap test FAILED: {type(e).__name__}: {e}')

        if resume:
            self._log('resuming process...')
            self.device.resume(pid)
            self._log('process resumed')
        self._log(f'fully attached pid={pid}')

    def _on_session_detached(self, reason, crash):
        """Called by Frida when the session drops (Frida's thread)."""
        print(f'[backend] *** SESSION DETACHED ***', file=sys.stderr, flush=True)
        print(f'[backend]   reason: {reason}', file=sys.stderr, flush=True)
        print(f'[backend]   crash:  {crash}', file=sys.stderr, flush=True)
        if crash:
            for attr in ('report', 'summary', 'type', 'address'):
                val = getattr(crash, attr, None)
                if val is not None:
                    print(f'[backend]   crash.{attr}: {val}', file=sys.stderr, flush=True)
        try:
            self._on_log(f'SESSION DETACHED: reason={reason}')
        except Exception:
            pass
        self.session = None
        self.script = None
        self.api = None

    def detach(self):
        self._log(f'detach() called (session={self.session is not None}, pid={self.pid})')
        if self.session is not None:
            try:
                self.session.detach()
            except Exception as e:
                self._log(f'session.detach() exception: {type(e).__name__}: {e}')
        self.session = None
        self.script = None
        self.api = None
        self.pid = None

    # ----- RPC wrappers -----

    def _rpc(self, method: str, *args):
        """Safe RPC call — returns result or raises with context."""
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
        except Exception as e:
            self._log(f'snap() failed: {type(e).__name__}: {e}')
            return None

    def window_state(self) -> Optional[dict]:
        if self.api is None:
            return None
        try:
            return self.api.window_state()
        except Exception as e:
            self._log(f'window_state() failed: {type(e).__name__}: {e}')
            return None

    def click_sel(self, sel: int) -> str:
        return self._rpc('click_sel', sel)

    def fire_by_hash(self, h1: int, h2: int) -> str:
        return self._rpc('fire_by_hash', h1, h2)

    def alt_enter(self) -> str:
        return self._rpc('alt_enter')

    def fire_named(self, name: str) -> str:
        if name.upper() == 'HIDDEN':
            h = HIDDEN_CHEAT_HASH
        else:
            h = KNOWN_CHEATS.get(name.upper()) or carma2_hash(name)
        return self.fire_by_hash(h[0], h[1])

    # ----- dev cheat RPC wrappers (proxies the agent's dev_* RPCs) -----
    # All go through _rpc() for consistent error handling.

    def dev_enable(self) -> str: return self._rpc('dev_enable')
    def dev_disable(self) -> str: return self._rpc('dev_disable')
    def dev_is_enabled(self) -> bool: return bool(self._rpc('dev_is_enabled'))

    def set_credits(self, amt: int) -> str: return self._rpc('set_credits', amt)
    def add_credits(self, delta: int) -> str: return self._rpc('add_credits', delta)
    def set_damage_state(self, n: int) -> str: return self._rpc('set_damage_state', n)
    def set_hud_mode(self, n: int) -> str: return self._rpc('set_hud_mode', n)
    def set_gravity(self, v: int) -> str: return self._rpc('set_gravity', v)

    def instant_repair(self) -> str: return self._rpc('instant_repair')
    def damage_cycle(self) -> str: return self._rpc('damage_cycle')
    def timer_toggle(self) -> str: return self._rpc('timer_toggle')
    def teleport(self) -> str: return self._rpc('teleport')
    def gravity_toggle(self) -> str: return self._rpc('gravity_toggle')
    def gravity_state(self) -> str: return self._rpc('gravity_state')

    def spawn_powerup(self, pid: int) -> str: return self._rpc('spawn_powerup', pid)
    def spawner_family(self, base_idx: int) -> str: return self._rpc('spawner_family', base_idx)

    def item_next(self) -> str: return self._rpc('item_next')
    def item_prev(self) -> str: return self._rpc('item_prev')
    def item_sort(self) -> str: return self._rpc('item_sort')

    def hud_cycle(self) -> str: return self._rpc('hud_cycle')
    def minimap_toggle(self) -> str: return self._rpc('minimap_toggle')
    def shadow_toggle(self) -> str: return self._rpc('shadow_toggle')
    def shadow_3state(self) -> str: return self._rpc('shadow_3_state')
    def zoom_incr(self) -> str: return self._rpc('zoom_incr')
    def zoom_decr(self) -> str: return self._rpc('zoom_decr')
    def camera_step(self) -> str: return self._rpc('camera_step')

    def spectator_toggle(self) -> str: return self._rpc('spectator_toggle')
    def spectator_next(self) -> str: return self._rpc('spectator_next')
    def spectator_prev(self) -> str: return self._rpc('spectator_prev')

    def quick_save(self) -> str: return self._rpc('quick_save')
    def reset_sound_state(self) -> str: return self._rpc('reset_sound_state')

    def sound_subsystem(self) -> str: return self._rpc('sound_subsystem')
    def simple_toggle(self) -> str: return self._rpc('simple_toggle')
    def dev_menu_cycle(self) -> str: return self._rpc('dev_menu_cycle')
    def recovery_cost(self) -> str: return self._rpc('recovery_cost')

    def visual_toggle_7(self) -> str: return self._rpc('visual_toggle_7')
    def visual_toggle_9(self) -> str: return self._rpc('visual_toggle_9')

    def lighting_profiler(self) -> str: return self._rpc('lighting_profiler')
    def gonad_of_death(self) -> str: return self._rpc('gonad_of_death')
    def demo_file_load(self) -> str: return self._rpc('demo_file_load')
    def hidden_cheat(self) -> str: return self._rpc('hidden_cheat')
    def unlock_all_cameras(self) -> str: return self._rpc('unlock_all_cameras')

    def dev_check_9(self) -> str: return self._rpc('dev_check_9')
    def dev_slash(self) -> str: return self._rpc('dev_slash')
    def dev_semi(self) -> str: return self._rpc('dev_semi')
    def dev_period(self) -> str: return self._rpc('dev_period')
    def dev_q(self) -> str: return self._rpc('dev_q')
    def dev_w(self) -> str: return self._rpc('dev_w')

    def call_addr(self, addr: int) -> str: return self._rpc('call_addr', addr)
    def read_u32(self, addr: int) -> int: return self._rpc('read_u32', addr)
    def write_u32(self, addr: int, val: int) -> str: return self._rpc('write_u32', addr, val)

    def get_string(self, sid: int) -> str | None: return self._rpc('get_string', sid)
    def get_strings(self, start: int, count: int) -> dict: return self._rpc('get_strings', start, count)

    # ----- high-level macros -----

    def _wait_for(self, predicate, timeout: float, poll: float = 0.1) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
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
            self._log('auto_start_race: not attached')
            return False
        main_menu = snap.get('main_menu', 0)
        newgame_menu = snap.get('newgame_menu', 0)

        self._log('waiting for Main menu...')
        if not self._wait_for(lambda s: s.get('menu') == main_menu, timeout):
            self._log('TIMEOUT waiting for Main menu')
            return False

        self._wait_stable('dogame_state', ticks=3, poll=0.1, timeout=1.0)

        self._log('clicking Start')
        try:
            self.click_sel(21)
        except Exception as e:
            self._log(f'click Start failed: {type(e).__name__}: {e}')
            return False

        if not self._wait_for(lambda s: s.get('menu') == newgame_menu, 2.0):
            self._log('did not reach NewGame menu')
            return False

        self._wait_stable('dogame_state', ticks=6, poll=0.1, timeout=4.0)

        self._log('clicking NewGame.sel=5 (OK)')
        try:
            self.click_sel(5)
        except Exception as e:
            self._log(f'click OK failed: {type(e).__name__}: {e}')
            return False

        self._log('watching race load...')
        deadline = time.time() + 20.0
        while time.time() < deadline:
            s = self.snap()
            if s is None:
                self._log('session lost (race likely loading)')
                return True
            if s.get('dogame_state', 0) >= 4 or s.get('game_state', 0) != 0:
                self._log('race loading...')
                break
            time.sleep(0.2)
        else:
            self._log('race load TIMEOUT')
            return False

        self._log('race started (dogame_state >= 4)')
        return True

    # ----- internals -----

    def _on_message(self, msg, data):
        try:
            mtype = msg.get('type', '?')
            print(f'[frida msg] type={mtype} payload={msg.get("payload", "")!r}',
                  file=sys.stderr, flush=True)
            if mtype == 'send':
                payload = msg.get('payload')
                if payload:
                    self._on_event(payload)
            elif mtype == 'error':
                desc = msg.get('description', '')
                stack = msg.get('stack', '')
                print(f'[frida error] {desc}\n{stack}', file=sys.stderr, flush=True)
                try:
                    self._on_log(f'[script error] {desc}')
                except Exception:
                    pass
        except Exception as e:
            print(f'[backend] _on_message exception: {e}', file=sys.stderr, flush=True)
            traceback.print_exc(file=sys.stderr)

    def _log(self, s: str):
        print(f'[backend] {s}', file=sys.stderr, flush=True)
        try:
            self._on_log(s)
        except Exception:
            pass


# ----- REPL test entry point -----

if __name__ == '__main__':
    import sys

    def log(s): print(f'[backend] {s}', flush=True)
    def evt(e): print(f'[event]   {e}', flush=True)

    be = Carma2Backend(on_event=evt, on_log=log)

    if be.attach_running():
        log(f'attached to existing pid {be.pid}')
    else:
        log('no running game; spawning')
        be.spawn()

    time.sleep(2)
    log(f'snap: {be.snap()}')

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == 'race':
            be.auto_start_race()
        elif cmd == 'fire':
            log(be.fire_named(sys.argv[2]))

    log('press Ctrl+C to detach')
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        be.detach()
