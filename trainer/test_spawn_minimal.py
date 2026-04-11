#!/usr/bin/env python3
"""
test_spawn_minimal.py — spawn Carma2 with a MINIMAL Frida agent that has only:
  - DInput non-exclusive cooperative level
  - WH_KEYBOARD_LL install blocker
  - dgVoodoo glide2x.dll detector (leaves it alone if present)

Purpose: verify whether those two hooks alone give us working Alt+Tab when
combined with dgVoodoo 2 as the Glide wrapper.

Prerequisite: dgVoodoo 2 must already be installed in the game folder
(replace glide2x.dll/glide.dll/glide3x.dll with dgVoodoo's 3Dfx/x86/*.dll,
drop dgVoodoo.conf into the game folder, set FullScreenMode = false and
WindowedAttributes = borderless).

Usage:
    py -3 trainer/test_spawn_minimal.py
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import frida
from backend.frida_core import find_game, _is_dgvoodoo_glide

try: sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
except Exception: pass
os.environ['PYTHONUNBUFFERED'] = '1'

AGENT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_agent_minimal.js')


def on_message(msg, data):
    if msg['type'] == 'error':
        print(f'[agent-err] {msg.get("description")}')
        return
    p = msg.get('payload', {})
    if isinstance(p, dict):
        h = p.get('h')
        if h == 'log':
            print(f'[agent] {p.get("msg")}')
        else:
            print(f'[agent] {p}')


def main():
    game = find_game()
    if not game:
        print('[!] Carmageddon 2 not found. Start Steam or pass the path.')
        return 1
    game_dir = os.path.dirname(game)
    print(f'[*] game:     {game}')
    print(f'[*] game dir: {game_dir}')

    dg = _is_dgvoodoo_glide(os.path.join(game_dir, 'glide2x.dll'))
    print(f'[*] dgVoodoo glide2x.dll detected: {dg}')
    if not dg:
        print('[!] dgVoodoo 2 not installed — install it first:')
        print('    1. Download dgVoodoo2_87_1.zip from https://github.com/dege-diosg/dgVoodoo2/releases')
        print('    2. Copy 3Dfx/x86/Glide*.dll over the game folder glide*.dll')
        print('    3. Copy dgVoodoo.conf and dgVoodooCpl.exe to the game folder')
        print('    4. In dgVoodoo.conf set: FullScreenMode = false, WindowedAttributes = borderless')
        return 1

    print(f'[*] spawning {game}')
    pid = frida.spawn([game], cwd=game_dir)
    session = frida.attach(pid)
    with open(AGENT, 'r', encoding='utf-8') as f:
        src = f.read()
    script = session.create_script(src)
    script.on('message', on_message)
    script.load()
    print(f'[*] pid={pid} — resuming')
    frida.resume(pid)
    print('[*] TEST Alt+Tab NOW. Ctrl+C to quit.')
    try:
        while True:
            time.sleep(1)
            try: os.kill(pid, 0)
            except Exception:
                print('[*] game exited')
                break
    except KeyboardInterrupt:
        print('\n[*] Ctrl+C')
        try: frida.kill(pid)
        except Exception: pass


if __name__ == '__main__':
    sys.exit(main() or 0)
