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

AGENT_JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'agent.js')


def find_game(saved_path: str = '') -> Optional[str]:
    """Auto-detect the game EXE path. Returns full path or None.

    Search order:
      1. saved_path (from QSettings — if valid, use it)
      2. Running process (get path from Frida's process list)
      3. Steam library folders (from Windows registry)
      4. Common install paths on all drives
    """
    # 1. Saved path
    if saved_path and os.path.isfile(saved_path):
        return saved_path

    # 2. Running process — if game is already open, get its path
    try:
        device = frida.get_local_device()
        for proc in device.enumerate_processes():
            if proc.name.lower() == GAME_PROC_NAME:
                # Frida doesn't expose exe path directly, but we know it's running
                # Try to get path via Windows API
                path = _get_process_path(proc.pid)
                if path and os.path.isfile(path):
                    return path
    except Exception:
        pass

    # 3. Steam library folders from registry
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
                return candidate

    return None


def _get_steam_path() -> Optional[str]:
    """Read Steam install path from Windows registry."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam')
        val, _ = winreg.QueryValueEx(key, 'SteamPath')
        winreg.CloseKey(key)
        return val.replace('/', '\\')
    except Exception:
        return None


def _get_steam_libraries(steam_path: str) -> list[str]:
    """Parse Steam's libraryfolders.vdf for all library paths."""
    libs = [steam_path]
    vdf = os.path.join(steam_path, 'steamapps', 'libraryfolders.vdf')
    if not os.path.isfile(vdf):
        # Try alternate location
        vdf = os.path.join(steam_path, 'config', 'libraryfolders.vdf')
    if os.path.isfile(vdf):
        try:
            with open(vdf, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if '"path"' in line:
                        # Format: "path"		"D:\\SteamLibrary"
                        parts = line.split('"')
                        if len(parts) >= 4:
                            path = parts[3].replace('\\\\', '\\')
                            if os.path.isdir(path) and path not in libs:
                                libs.append(path)
        except Exception:
            pass
    return libs


def check_nglide(game_dir: str) -> bool:
    """Check if nGlide is installed in the game folder.
    nGlide's glide2x.dll is ~200KB+; the stock Steam wrapper is ~50KB."""
    if not game_dir:
        return False
    dll = os.path.join(game_dir, 'glide2x.dll')
    if not os.path.isfile(dll):
        return False
    # nGlide 2.x is typically 150KB-300KB; stock wrappers are much smaller
    size = os.path.getsize(dll)
    return size > 100_000  # >100KB = likely nGlide


def _get_process_path(pid: int) -> Optional[str]:
    """Get the full exe path for a running process by PID."""
    try:
        import ctypes
        from ctypes import wintypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if h:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            ok = ctypes.windll.kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
            ctypes.windll.kernel32.CloseHandle(h)
            if ok:
                return buf.value
    except Exception:
        pass
    return None


class Carma2Backend:
    """High-level wrapper around the Frida agent."""

    def __init__(self, on_event: Optional[Callable[[dict], None]] = None,
                 on_log: Optional[Callable[[str], None]] = None,
                 game_exe: Optional[str] = None):
        self.device = frida.get_local_device()
        self.session: Optional[frida.core.Session] = None
        self.script: Optional[frida.core.Script] = None
        self.api = None
        self.pid: Optional[int] = None
        self.game_exe: Optional[str] = game_exe
        self.game_dir: Optional[str] = os.path.dirname(game_exe) if game_exe else None
        self._on_event = on_event or (lambda e: None)
        self._on_log = on_log or (lambda s: None)

    def set_game_path(self, exe_path: str):
        """Set or change the game EXE path."""
        self.game_exe = exe_path
        self.game_dir = os.path.dirname(exe_path)

    # ----- attach/spawn -----

    def is_attached(self) -> bool:
        return self.script is not None

    def find_running(self) -> Optional[int]:
        for p in self.device.enumerate_processes():
            if p.name.lower() == GAME_PROC_NAME:
                return p.pid
        return None

    def attach_running(self) -> bool:
        pid = self.find_running()
        if pid is None:
            return False
        self._attach(pid, resume=False)
        return True

    def spawn(self, nocutscene: bool = True) -> int:
        if not self.game_exe or not os.path.isfile(self.game_exe):
            raise FileNotFoundError(f'Game not found: {self.game_exe}')
        argv = [self.game_exe]
        if nocutscene:
            argv.append('-NOCUTSCENE')
        self._log(f'spawning {argv}')
        pid = self.device.spawn(argv, cwd=self.game_dir)
        self._attach(pid, resume=True)
        return pid

    def _attach(self, pid: int, resume: bool):
        with open(AGENT_JS, 'r', encoding='utf-8') as f:
            src = f.read()
        session = self.device.attach(pid)
        script = session.create_script(src)
        script.on('message', self._on_message)
        script.load()
        self.session = session
        self.script = script
        self.api = script.exports_sync
        self.pid = pid
        if resume:
            self.device.resume(pid)
        self._log(f'attached pid={pid}')

    def detach(self):
        if self.session is not None:
            try:
                self.session.detach()
            except Exception:
                pass
        self.session = None
        self.script = None
        self.api = None
        self.pid = None
        self._log('detached')

    # ----- RPC wrappers -----

    def snap(self) -> Optional[dict]:
        if self.api is None:
            return None
        try:
            return self.api.snap()
        except (frida.InvalidOperationError, frida.TransportError):
            return None

    def click_sel(self, sel: int) -> str:
        return self.api.click_sel(sel)

    def fire_by_hash(self, h1: int, h2: int) -> str:
        return self.api.fire_by_hash(h1, h2)

    def alt_enter(self) -> str:
        return self.api.alt_enter()

    def fire_named(self, name: str) -> str:
        if name.upper() == 'HIDDEN':
            h = HIDDEN_CHEAT_HASH
        else:
            h = KNOWN_CHEATS.get(name.upper()) or carma2_hash(name)
        return self.fire_by_hash(h[0], h[1])

    # ----- dev cheat RPC wrappers (proxies the agent's dev_* RPCs) -----
    # These are thin wrappers — error handling lives in BackendBridge._safe_call.

    def dev_enable(self) -> str: return self.api.dev_enable()
    def dev_disable(self) -> str: return self.api.dev_disable()
    def dev_is_enabled(self) -> bool: return bool(self.api.dev_is_enabled())

    def set_credits(self, amt: int) -> str: return self.api.set_credits(amt)
    def add_credits(self, delta: int) -> str: return self.api.add_credits(delta)
    def set_damage_state(self, n: int) -> str: return self.api.set_damage_state(n)
    def set_hud_mode(self, n: int) -> str: return self.api.set_hud_mode(n)
    def set_gravity(self, v: int) -> str: return self.api.set_gravity(v)

    def instant_repair(self) -> str: return self.api.instant_repair()
    def damage_cycle(self) -> str: return self.api.damage_cycle()
    def timer_toggle(self) -> str: return self.api.timer_toggle()
    def teleport(self) -> str: return self.api.teleport()
    def gravity_toggle(self) -> str: return self.api.gravity_toggle()
    def gravity_state(self) -> str: return self.api.gravity_state()

    def spawn_powerup(self, pid: int) -> str: return self.api.spawn_powerup(pid)
    def spawner_family(self, base_idx: int) -> str: return self.api.spawner_family(base_idx)

    def item_next(self) -> str: return self.api.item_next()
    def item_prev(self) -> str: return self.api.item_prev()
    def item_sort(self) -> str: return self.api.item_sort()

    def hud_cycle(self) -> str: return self.api.hud_cycle()
    def minimap_toggle(self) -> str: return self.api.minimap_toggle()
    def shadow_toggle(self) -> str: return self.api.shadow_toggle()
    def shadow_3state(self) -> str: return self.api.shadow_3_state()
    def zoom_incr(self) -> str: return self.api.zoom_incr()
    def zoom_decr(self) -> str: return self.api.zoom_decr()
    def camera_step(self) -> str: return self.api.camera_step()

    def spectator_toggle(self) -> str: return self.api.spectator_toggle()
    def spectator_next(self) -> str: return self.api.spectator_next()
    def spectator_prev(self) -> str: return self.api.spectator_prev()

    def quick_save(self) -> str: return self.api.quick_save()
    def reset_sound_state(self) -> str: return self.api.reset_sound_state()

    def sound_subsystem(self) -> str: return self.api.sound_subsystem()
    def simple_toggle(self) -> str: return self.api.simple_toggle()
    def dev_menu_cycle(self) -> str: return self.api.dev_menu_cycle()
    def recovery_cost(self) -> str: return self.api.recovery_cost()

    def visual_toggle_7(self) -> str: return self.api.visual_toggle_7()
    def visual_toggle_9(self) -> str: return self.api.visual_toggle_9()

    def lighting_profiler(self) -> str: return self.api.lighting_profiler()
    def gonad_of_death(self) -> str: return self.api.gonad_of_death()
    def demo_file_load(self) -> str: return self.api.demo_file_load()
    def hidden_cheat(self) -> str: return self.api.hidden_cheat()
    def unlock_all_cameras(self) -> str: return self.api.unlock_all_cameras()

    def dev_check_9(self) -> str: return self.api.dev_check_9()
    def dev_slash(self) -> str: return self.api.dev_slash()
    def dev_semi(self) -> str: return self.api.dev_semi()
    def dev_period(self) -> str: return self.api.dev_period()
    def dev_q(self) -> str: return self.api.dev_q()
    def dev_w(self) -> str: return self.api.dev_w()

    def call_addr(self, addr: int) -> str: return self.api.call_addr(addr)
    def read_u32(self, addr: int) -> int: return self.api.read_u32(addr)
    def write_u32(self, addr: int, val: int) -> str: return self.api.write_u32(addr, val)

    def get_string(self, sid: int) -> str | None: return self.api.get_string(sid)
    def get_strings(self, start: int, count: int) -> dict: return self.api.get_strings(start, count)

    # ----- high-level macros -----

    def _wait_for(self, predicate, timeout: float, poll: float = 0.1) -> bool:
        """Poll snap() at `poll` interval until `predicate(snap)` is true.
        Returns False on timeout or session loss."""
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
        """Wait until snap()[key] returns the same value for `ticks` consecutive
        polls — used to detect 'transition settled'. Returns False on timeout."""
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
        main_menu = snap['main_menu']
        newgame_menu = snap['newgame_menu']

        # 1. Wait for Main menu to appear.
        self._log('waiting for Main menu...')
        if not self._wait_for(lambda s: s['menu'] == main_menu, timeout):
            self._log('TIMEOUT waiting for Main menu')
            return False

        # 2. Brief settle — the menu is usually ready within 0.3s.
        self._wait_stable('dogame_state', ticks=3, poll=0.1, timeout=1.0)

        # 3. Click Start (sel=21 in Main menu).
        self._log('clicking Start')
        try:
            self.click_sel(21)
        except frida.InvalidOperationError:
            self._log('crash on Start click')
            return False

        # 4. Wait for NewGame menu to appear.
        if not self._wait_for(lambda s: s['menu'] == newgame_menu, 2.0):
            self._log('did not reach NewGame menu')
            return False

        # 5. Wait for NewGame to settle (1s stable = ready to click OK).
        self._wait_stable('dogame_state', ticks=6, poll=0.1, timeout=4.0)

        # 6. Click OK (sel=5 in NewGame menu).
        self._log('clicking NewGame.sel=5 (OK)')
        try:
            self.click_sel(5)
        except frida.InvalidOperationError:
            self._log('crash on OK click')
            return False

        # 7. Wait for race load — either dogame_state advances, game_state
        #    becomes nonzero, or the session is lost (race loading often
        #    interrupts Frida briefly).
        self._log('watching race load...')
        deadline = time.time() + 20.0
        while time.time() < deadline:
            s = self.snap()
            if s is None:
                self._log('session lost (race likely loading)')
                return True
            if s['dogame_state'] >= 4 or s['game_state'] != 0:
                self._log('race loading...')
                break
            time.sleep(0.2)
        else:
            self._log('race load TIMEOUT')
            return False

        # 8. dogame_state >= 5 = in-race. game_state stays 0 during normal
        #    single-player racing (this is expected, not an error).
        self._log('race started (dogame_state >= 4)')
        return True

    # ----- internals -----

    def _on_message(self, msg, data):
        if msg.get('type') == 'send':
            payload = msg['payload']
            self._on_event(payload)
        elif msg.get('type') == 'error':
            self._log(f'[script error] {msg.get("description")}')

    def _log(self, s: str):
        self._on_log(s)


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
