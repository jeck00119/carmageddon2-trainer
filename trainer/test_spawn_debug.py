#!/usr/bin/env python3
"""
test_spawn_debug.py — spawn Carma2 with the full diagnostic agent.
Logs EVERY keyboard hook, raw input device, DDraw cooperative level,
DInput cooperative level, system parameter change, hotkey registration,
and every LL keystroke including Alt+Tab and Win key.

Usage:
    py -3 trainer/test_spawn_debug.py
"""
import os, sys, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import frida
from backend.game_detect import find_game
from backend.dgvoodoo import ensure_dgvoodoo

try: sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
except Exception: pass
os.environ['PYTHONUNBUFFERED'] = '1'

AGENT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_agent_debug.js')
events = []


def on_message(msg, data):
    if msg['type'] == 'error':
        print(f'[agent-err] {msg.get("description")}')
        stk = msg.get('stack', '')
        if stk:
            print(stk[:300])
        return
    p = msg.get('payload', {})
    if not isinstance(p, dict):
        return
    h = p.get('h')
    if h == 'log':
        print(f'[log] {p.get("msg")}')
    elif h == 'ev':
        events.append(p)
        kind = p.get('kind')
        d = p.get('data', {})
        if kind == 'LL_KEY':
            combo = d.get('combo', '')
            mark = f'  *** {combo} ***' if combo else ''
            print(f'[LL_KEY] {d.get("action"):4} vk={d.get("vk"):8} alt={d.get("altDown")}{mark}')
        elif kind == 'SetWindowsHookEx':
            print(f'[HOOK] {d.get("type"):20} proc={d.get("proc")} module={d.get("procModule")} tid={d.get("tid")}')
        elif kind == 'RegisterRawInputDevices':
            print(f'[RAWINPUT] page={d.get("usagePage")} usage={d.get("usage")} flags={d.get("flagNames")} NOHOTKEYS={d.get("NOHOTKEYS")}')
        elif kind == 'DDraw_SetCooperativeLevel':
            print(f'[DDRAW COOP] flags={d.get("flagNames")} EXCLUSIVE={d.get("EXCLUSIVE")}')
        elif kind == 'DInput_SetCooperativeLevel':
            print(f'[DINPUT COOP] original={d.get("flagNames")} NOWINKEY={d.get("NOWINKEY")} -> {d.get("rewritten")}')
        elif kind == 'RegisterHotKey':
            print(f'[HOTKEY] mod={d.get("modifiers")} vk={d.get("vkName")} id={d.get("id")}')
        elif kind == 'SystemParametersInfo':
            print(f'[SYSPARAMS] action={d.get("action")} param={d.get("uiParam")}')
        elif kind == 'WndMsg':
            print(f'[MSG] {d.get("msg"):20} wp={d.get("wp")} lp={d.get("lp")}')
        else:
            print(f'[{kind}] {d}')
    elif h == 'init_done':
        print('[*] agent init done')


def main():
    game = find_game()
    if not game:
        print('[!] Carmageddon 2 not found.')
        return 1
    game_dir = os.path.dirname(game)
    print(f'[*] game: {game}')

    if not ensure_dgvoodoo(game_dir):
        print('[!] ensure_dgvoodoo failed')
        return 1

    print(f'[*] spawning...')
    pid = frida.spawn([game], cwd=game_dir)
    session = frida.attach(pid)
    with open(AGENT, 'r', encoding='utf-8') as f:
        src = f.read()
    script = session.create_script(src)
    script.on('message', on_message)
    script.load()
    print(f'[*] pid={pid} — resuming')
    frida.resume(pid)
    print()
    print('=' * 70)
    print('  PRESS THESE KEYS AND WATCH THE LOG:')
    print('    1. Alt+Tab       (should show LL_KEY ALT+TAB!)')
    print('    2. Win key       (should show LL_KEY WIN_KEY)')
    print('    3. Alt+Enter     (should show LL_KEY ALT+ENTER)')
    print('    4. Any letter    (baseline — should show LL_KEY)')
    print('  Ctrl+C to quit.')
    print('=' * 70)
    print()

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

    # Dump summary
    print()
    print('=' * 70)
    print('SUMMARY')
    print('=' * 70)
    by_kind = {}
    for e in events:
        k = e.get('kind')
        by_kind.setdefault(k, []).append(e.get('data'))
    for k, v in sorted(by_kind.items()):
        print(f'  {k}: {len(v)} events')
        if k in ('SetWindowsHookEx', 'RegisterRawInputDevices', 'DDraw_SetCooperativeLevel',
                 'DInput_SetCooperativeLevel', 'RegisterHotKey', 'SystemParametersInfo'):
            for d in v:
                print(f'    {d}')

    logpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'debug_log.json')
    with open(logpath, 'w', encoding='utf-8') as f:
        json.dump(events, f, indent=2)
    print(f'[*] full log: {logpath}')


if __name__ == '__main__':
    sys.exit(main() or 0)
