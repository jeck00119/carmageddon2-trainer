"""Game path auto-detection — Steam registry, running processes, common paths."""
import os
import string
import winreg
from typing import Optional

import frida

GAME_PROC_NAME = 'carma2_hw.exe'
GAME_EXE_NAME = 'CARMA2_HW.EXE'
KNOWN_EXE_SIZE = 2680320
KNOWN_EXE_MD5 = '66a9c49483ff4415b518bb7df01385bd'

# Menu address → human-readable name (game-binary constants).
MENU_NAMES = {
    0x5a80f0: 'Main menu',
    0x5b39b8: 'Network menu',
    0x5bf280: 'New Game menu',
    0x59c828: 'In race (StartGame)',
    0x632c60: 'Options menu',
    0x649df0: 'Quit menu',
    0x5d6410: 'Change Car menu',
}


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
