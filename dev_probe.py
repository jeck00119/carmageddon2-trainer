#!/usr/bin/env python3
"""
Carmageddon 2 dev mode probe — comprehensive polled-table mapper.

Spawns the game with the trainer's agent.js, loads dev_probe_agent.js as a
second script on the same Frida session, then for each entry in the polled
table at 0x5900a0:

- Sets cheat_mode = 0xa11ee75d (dev mode)
- Hooks 0x4833a0 (is_action_pressed) to fake the record's action_id as
  pressed for the next dispatcher walk (edge-triggered cycle: clear, set,
  wait, repeat to fire each function multiple times)
- Tests both sel=0 (Options) and sel=1 (Cheat) dev menu states
- Captures sprintf, print_text, sound, num_key, cheat-handler events
- Outputs structured map to dev_action_map.json + log to dev_probe.log

Notes:
- Skips action 0x19 (fn 0x441900 is a 1-byte ret stub that breaks Frida)
- Skips num_key handlers that crash because spawn_powerup needs game_state != 0
  (auto_start_race only reaches dogame_state=5 = loading; powerup spawns
  must wait for true in-race body which the trainer's auto-race doesn't yet)

Output:
  dev_probe.log         — full trace
  dev_action_map.json   — structured action_id -> {fn, sel_0, sel_1} map
"""
import os
import sys
import time
import traceback
import json

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, 'trainer'))
sys.path.insert(0, os.path.join(_HERE, 'trainer', 'backend'))

from frida_core import Carma2Backend  # noqa: E402

PROBE_AGENT = os.path.join(_HERE, 'dev_probe_agent.js')
LOG_PATH = os.path.join(_HERE, 'dev_probe.log')
MAP_PATH = os.path.join(_HERE, 'dev_action_map.json')

CHEAT_MODE_DEV = 0xa11ee75d

# Polled-table records (action_id, fn, type) extracted from binary at 0x5900a0
# SKIPPING action 0x19 -> fn 0x441900 (1-byte stub, breaks Frida)
POLLED_TABLE = [
    (0x23, 0x004420e0, 1),
    (0x4a, 0x0042dd50, 1),
    (0x39, 0x00444610, 1),
    (0x39, 0x00444600, 1),
    (0x39, 0x00494840, 1),
    (0x39, 0x00494880, 1),
    (0x3c, 0x00442300, 1),
    (0x04, 0x00441490, 1),
    (0x25, 0x00455a50, 0),
    (0x05, 0x00518780, 0),
    (0x4c, 0x00444f40, 1),
    (0x12, 0x004414b0, 0),  # DEV MENU
    (0x13, 0x00441600, 1),
    (0x14, 0x00441680, 1),
    (0x15, 0x00441700, 1),
    (0x16, 0x00441780, 1),
    (0x17, 0x00441800, 1),
    (0x18, 0x00441880, 1),
    # (0x19, 0x00441900, 1),  # SKIP — 1-byte stub
    (0x0f, 0x00441910, 1),
    (0x26, 0x00441990, 1),
    (0x27, 0x00441a10, 1),
    (0x28, 0x00441a90, 1),
    (0x29, 0x00441b10, 1),
    (0x2a, 0x00441b90, 1),
    (0x2b, 0x00441c10, 1),
    (0x2c, 0x00441c90, 1),
    (0x10, 0x00441d10, 1),
    (0x11, 0x00441d90, 1),
    (0x0b, 0x004443c0, 1),
    (0x41, 0x004e4cd0, 1),
    (0x42, 0x004e4d00, 1),
    (0x43, 0x00502e50, 1),
    (0x44, 0x00502fd0, 1),
    (0x45, 0x00503030, 1),
    (0x46, 0x0040e430, 1),
    (0x47, 0x004448f0, 1),
    (0x48, 0x004945f0, 1),
    (0x49, 0x00494700, 1),
    (0x3e, 0x004da9d0, 1),
]


_log_lines = []


def log(msg):
    line = f'[{time.strftime("%H:%M:%S")}] {msg}'
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode('ascii', errors='replace').decode('ascii'), flush=True)
    _log_lines.append(line)


def save_log():
    try:
        with open(LOG_PATH, 'w', encoding='utf-8') as f:
            f.write('\n'.join(_log_lines))
    except Exception as e:
        print(f'log save failed: {e}', flush=True)


HUD_FORMATS = {'%d %s', '%d/%d %s', '%s %d/%d', '%s %d/%d %s %d/%d'}


def filter_dev_events(trace):
    keep = []
    for ev in trace:
        if not isinstance(ev, dict):
            continue
        t = ev.get('t')
        if t in ('fake_key_used', 'fake_action_consumed'):
            continue
        if t == 'sprintf':
            fmt = ev.get('fmt', '')
            if fmt in HUD_FORMATS:
                continue
        keep.append(ev)
    return keep


def fmt_event(ev):
    if not isinstance(ev, dict):
        return repr(ev)
    parts = []
    for k in ('t', 'i', 'sel', 'cm', 'gs', 'ch', 'id', 'fmt', 'out', 's',
              'arg', 'arg0', 'key'):
        if k in ev:
            v = ev[k]
            if isinstance(v, int):
                parts.append(f'{k}={v}')
            else:
                parts.append(f'{k}={v!r}')
    return ' '.join(parts)


def clean_text_string(s):
    """Truncate at first non-printable run."""
    if not s:
        return ''
    out = ''
    for c in s:
        if 0x20 <= ord(c) < 0x7f:
            out += c
        else:
            break
    return out


def fire_action_cycle(probe, action_id, cycles=4):
    """Fire an action multiple times via clear+set cycles to defeat the
    edge-triggered dispatcher's debounce."""
    for _ in range(cycles):
        probe.clear_fake_action()
        time.sleep(0.05)
        probe.set_fake_action(action_id, 1)
        time.sleep(0.1)


def probe_run():
    be = Carma2Backend(on_event=lambda e: log(f'[trainer] {e}'),
                       on_log=log)

    log('=== dev probe start ===')
    be.spawn()
    time.sleep(2)

    log('loading probe agent')
    with open(PROBE_AGENT, 'r', encoding='utf-8') as f:
        probe_src = f.read()

    def on_probe_msg(msg, data):
        if msg.get('type') == 'send':
            log(f'[probe] {msg["payload"]}')
        elif msg.get('type') == 'error':
            log(f'[probe-err] {msg.get("description")}')

    probe_script = be.session.create_script(probe_src)
    probe_script.on('message', on_probe_msg)
    probe_script.load()
    probe = probe_script.exports_sync

    log('waiting for menu...')
    deadline = time.time() + 30
    while time.time() < deadline:
        s = be.snap()
        if s and s.get('menu') == s.get('main_menu'):
            break
        time.sleep(0.2)
    log(f'snap: {be.snap()}')
    log('install_trace')
    log(probe.install_trace())
    probe.set_cheat_mode(CHEAT_MODE_DEV)
    log(f'cheat_mode: 0x{probe.get_cheat_mode():08x}')

    # ===== Auto-start race =====
    log('=== auto-start race ===')
    try:
        be.auto_start_race(timeout=60.0)
    except Exception as e:
        log(f'auto_start_race exc: {e}')
    time.sleep(2)
    log(f'snap: {be.snap()}')

    cm = probe.get_cheat_mode()
    if cm != CHEAT_MODE_DEV:
        probe.set_cheat_mode(CHEAT_MODE_DEV)

    findings = {}

    # ===== Test each action at both sel=0 and sel=1, with cycling =====
    for action_id, fn, type_ in POLLED_TABLE:
        # Skip if it's the dev menu — we test it specially
        action_results = {}
        for sel in (0, 1):
            try:
                probe.set_selection(sel)
                probe.set_cheat_mode(CHEAT_MODE_DEV)
                probe.clear_fake_action()
                probe.clear_trace()
                fire_action_cycle(probe, action_id, cycles=4)
                trace = probe.get_trace()
            except Exception as e:
                log(f'  action=0x{action_id:02x} sel={sel} EXC: {e}')
                action_results[sel] = {'error': str(e)}
                continue

            events = filter_dev_events(trace)
            sprintfs = []
            print_texts = []
            sounds = []
            num_keys = []
            cheat_handlers = []
            dev_menu_count = 0
            for ev in events:
                if not isinstance(ev, dict):
                    continue
                t = ev.get('t')
                if t == 'sprintf':
                    sprintfs.append({'fmt': ev.get('fmt'), 'out': ev.get('out')})
                elif t == 'print_text':
                    pt = clean_text_string(ev.get('s', ''))
                    if pt:
                        print_texts.append(pt)
                elif t == 'play_sound':
                    sounds.append(ev.get('id', -1))
                elif t == 'num_key':
                    num_keys.append(ev.get('i', -1))
                elif t == 'dev_menu':
                    dev_menu_count += 1
                elif t and t.startswith('h_'):
                    cheat_handlers.append(t)

            action_results[sel] = {
                'event_count': len(events),
                'sprintf': sprintfs[:8],
                'print_text': print_texts[:8],
                'sound': sounds[:8],
                'num_key': num_keys[:8],
                'cheat_handler': cheat_handlers[:8],
                'dev_menu_count': dev_menu_count,
            }

        # Log results
        s0 = action_results.get(0, {})
        s1 = action_results.get(1, {})
        log(f'-- action=0x{action_id:02x} fn=0x{fn:08x} --')
        if s0.get('event_count') or s1.get('event_count'):
            log(f'  sel=0: events={s0.get("event_count",0)}')
            for k in ('sprintf', 'print_text', 'sound', 'num_key', 'cheat_handler'):
                if s0.get(k):
                    log(f'    {k}={s0[k]}')
            log(f'  sel=1: events={s1.get("event_count",0)}')
            for k in ('sprintf', 'print_text', 'sound', 'num_key', 'cheat_handler'):
                if s1.get(k):
                    log(f'    {k}={s1[k]}')

        findings[hex(action_id)] = {
            'fn': hex(fn),
            'type': type_,
            'sel_0': s0,
            'sel_1': s1,
        }

    # Save findings
    try:
        with open(MAP_PATH, 'w') as f:
            json.dump(findings, f, indent=2)
        log(f'action map saved to {MAP_PATH}')
    except Exception as e:
        log(f'map save failed: {e}')

    log('=== final ===')
    log(f'final snap: {be.snap()}')

    return be, probe


def main():
    be = None
    try:
        be, probe = probe_run()
    except Exception as e:
        log(f'EXCEPTION: {e}')
        log(traceback.format_exc())
    finally:
        if be is not None:
            try:
                log('detaching')
                be.detach()
            except Exception as e:
                log(f'detach exc: {e}')
        save_log()
        log('=== done ===')


if __name__ == '__main__':
    main()
