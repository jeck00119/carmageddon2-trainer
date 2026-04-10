#!/usr/bin/env python3
"""
Optimized discovery probe — single run, all tests.

Spawns game → fast auto_start_race → runs all discovery tests:
  a) Fire 11 n/a powerups via fireByHash, capture effects
  b) Cycle camera modes 10x, capture mode names
  c) Give credits + buy 3 upgrades, read upgrade state
  d) Lock-on test: fire q/w 5x, capture target names
  e) Fire hidden cheat, observe sound/flag toggle
  f) Read runtime string table (key IDs from dev functions)
  g) Read BSS table at 0x74bce8 (CheatDetect special branch data)

Uses:
  - agent.js (trainer) for fireByHash, snap, getString, state writes
  - dev_probe_agent.js for setFakeAction (game-thread-safe triggering)

Optimized: 1-cycle setFakeAction, 0.2s delays, batch reads.
"""
import json
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, 'trainer'))
sys.path.insert(0, os.path.join(_HERE, 'trainer', 'backend'))

from frida_core import Carma2Backend

PROBE_AGENT = os.path.join(_HERE, 'dev_probe_agent.js')
LOG_PATH = os.path.join(_HERE, 'discovery.log')
JSON_PATH = os.path.join(_HERE, 'discovery.json')

# n/a powerup IDs (effect unknown in POWERUP.TXT)
NA_POWERUP_IDS = [1, 14, 28, 29, 30, 31, 46, 86, 87, 88, 89]

# Hidden cheat hash
HIDDEN_H1 = 0x616fb8e4
HIDDEN_H2 = 0x7c6100a8

# String IDs found in dev function disasm
STRING_IDS = [29, 41, 42, 179, 214, 250, 251, 254, 255]

HUD_FMTS = {'%d %s', '%d/%d %s', '%s %d/%d', '%s %d/%d %s %d/%d'}

_log_lines = []
findings = {}


def log(msg):
    line = f'[{time.strftime("%H:%M:%S")}] {msg}'
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        pass
    _log_lines.append(line)


def save():
    with open(LOG_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(_log_lines))
    with open(JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(findings, f, indent=2, default=str)


def filter_texts(trace):
    """Extract unique meaningful texts from a probe trace."""
    texts = []
    seen = set()
    for ev in trace:
        if not isinstance(ev, dict):
            continue
        t = ev.get('t')
        if t == 'sprintf':
            fmt = ev.get('fmt', '')
            out = ev.get('out', '')
            if fmt in HUD_FMTS or not out:
                continue
            # Clean to ASCII
            clean = ''.join(c for c in out if 0x20 <= ord(c) < 0x7f)
            if clean and clean not in seen:
                seen.add(clean)
                texts.append(clean)
        elif t == 'print_text':
            s = ev.get('s', '')
            clean = ''
            for c in s:
                if 0x20 <= ord(c) < 0x7f:
                    clean += c
                else:
                    break
            if clean and clean not in seen:
                seen.add(clean)
                texts.append(clean)
        elif t == 'play_sound':
            tag = f'[sound:{ev.get("id",-1)}]'
            if tag not in seen:
                seen.add(tag)
                texts.append(tag)
    return texts


def fire_action_once(probe, action_id):
    """Single-cycle edge-trigger: set → brief wait → clear."""
    probe.set_fake_action(action_id, 2)
    time.sleep(0.12)
    probe.clear_fake_action()
    time.sleep(0.08)


def main():
    be = Carma2Backend(on_event=lambda e: None, on_log=lambda s: log(f'[be] {s}'))

    log('=== Discovery probe start ===')
    be.spawn()
    time.sleep(2)

    # Fast wait for menu
    for _ in range(20):
        s = be.snap()
        if s and s.get('menu') == s.get('main_menu'):
            break
        time.sleep(0.2)

    log('Auto-starting race...')
    be.auto_start_race(timeout=30.0)
    time.sleep(1)

    # Reattach if needed
    s = be.snap()
    if s is None:
        log('Reattaching...')
        for attempt in range(5):
            time.sleep(2)
            if be.attach_running():
                log(f'Reattached attempt {attempt+1}')
                time.sleep(1)
                s = be.snap()
                break
        if s is None:
            log('ABORT: could not reattach')
            save()
            return

    log(f'State: dgs={s["dogame_state"]} gs={s["game_state"]} credits={s["credits"]}')

    # Load probe agent
    log('Loading probe agent...')
    with open(PROBE_AGENT, 'r', encoding='utf-8') as f:
        probe_src = f.read()

    probe_script = be.session.create_script(probe_src)
    probe_script.on('message', lambda m, d: None)
    probe_script.load()
    probe = probe_script.exports_sync
    probe.install_trace()
    be.dev_enable()
    probe.set_selection(1)  # Cheat mode
    log('Ready')

    # ==================================================================
    # TEST A: Fire 11 n/a powerups via fireByHash
    # ==================================================================
    log('\n=== A: n/a powerup effects ===')
    na_results = {}
    for pid in NA_POWERUP_IDS:
        probe.clear_trace()
        try:
            r = be.spawn_powerup(pid)
        except Exception as e:
            na_results[pid] = {'error': str(e)}
            log(f'  id={pid:2d}: ERROR {e}')
            continue
        time.sleep(0.3)
        trace = probe.get_trace()
        texts = filter_texts(trace)
        na_results[pid] = {'result': r, 'texts': texts}
        log(f'  id={pid:2d}: {r:30s} {", ".join(texts[:3]) or "(no output)"}')
    findings['na_powerups'] = na_results

    # ==================================================================
    # TEST B: Camera mode full cycle (action 0x4b, 10 cycles)
    # ==================================================================
    log('\n=== B: Camera mode cycler ===')
    cam_modes = []
    for i in range(10):
        probe.clear_trace()
        fire_action_once(probe, 0x4b)
        time.sleep(0.2)
        trace = probe.get_trace()
        texts = filter_texts(trace)
        # Filter to just print_text entries (camera mode names)
        mode_texts = [t for t in texts if not t.startswith('[sound:') and ':' not in t[:20]]
        if mode_texts:
            for mt in mode_texts:
                if mt not in cam_modes:
                    cam_modes.append(mt)
        log(f'  cycle {i}: {", ".join(mode_texts) or "(no new output)"}')
    findings['camera_modes'] = cam_modes
    log(f'  All modes: {cam_modes}')

    # ==================================================================
    # TEST C: Upgrade purchase
    # ==================================================================
    log('\n=== C: Upgrade purchase ===')
    # Read upgrade state before
    upgrades_before = {
        'cur_0': be.read_u32(0x75d4d4), 'max_0': be.read_u32(0x75d4e0),
        'cur_4': be.read_u32(0x75d4d8), 'max_4': be.read_u32(0x75d4e4),
        'cur_8': be.read_u32(0x75d4dc), 'max_8': be.read_u32(0x75d4e8),
    }
    log(f'  Before: {upgrades_before}')

    # Give max credits
    be.set_credits(999999)
    time.sleep(0.2)

    # Buy each upgrade
    for action_id, slot_name in [(0x43, 'Armour'), (0x44, 'Power'), (0x45, 'Offensive')]:
        probe.clear_trace()
        fire_action_once(probe, action_id)
        time.sleep(0.3)
        trace = probe.get_trace()
        texts = filter_texts(trace)
        log(f'  Buy {slot_name}: {", ".join(texts[:3]) or "(no output)"}')

    # Read upgrade state after
    upgrades_after = {
        'cur_0': be.read_u32(0x75d4d4), 'max_0': be.read_u32(0x75d4e0),
        'cur_4': be.read_u32(0x75d4d8), 'max_4': be.read_u32(0x75d4e4),
        'cur_8': be.read_u32(0x75d4dc), 'max_8': be.read_u32(0x75d4e8),
    }
    log(f'  After: {upgrades_after}')
    findings['upgrades'] = {'before': upgrades_before, 'after': upgrades_after}

    credits_after = be.snap().get('credits', 0)
    log(f'  Credits remaining: {credits_after}')

    # ==================================================================
    # TEST D: Lock-on targeting
    # ==================================================================
    log('\n=== D: Lock-on targeting ===')
    lockon_targets = []
    for i in range(6):
        action = 0x48 if i % 2 == 0 else 0x49  # alternate q/w
        probe.clear_trace()
        fire_action_once(probe, action)
        time.sleep(0.2)
        trace = probe.get_trace()
        texts = filter_texts(trace)
        # Look for "LOCKED ONTO ..." text
        locked = [t for t in texts if 'LOCKED' in t]
        if locked:
            lockon_targets.append(locked[0])
        label = 'q' if action == 0x48 else 'w'
        log(f'  {label}: {", ".join(texts[:3]) or "(no output)"}')
    findings['lockon_targets'] = lockon_targets
    log(f'  Targets seen: {lockon_targets}')

    # ==================================================================
    # TEST E: Hidden cheat
    # ==================================================================
    log('\n=== E: Hidden cheat ===')
    sound_before = be.read_u32(0x762328)
    cd_before = be.read_u32(0x7a06c0)
    flag_before = be.read_u32(0x75bc04)
    probe.clear_trace()
    be.fire_by_hash(HIDDEN_H1, HIDDEN_H2)
    time.sleep(0.5)
    sound_after = be.read_u32(0x762328)
    cd_after = be.read_u32(0x7a06c0)
    flag_after = be.read_u32(0x75bc04)
    trace = probe.get_trace()
    texts = filter_texts(trace)
    log(f'  sound_master: {sound_before} -> {sound_after}')
    log(f'  cd_audio:     {cd_before} -> {cd_after}')
    log(f'  side_flag:    {flag_before} -> {flag_after}')
    log(f'  output: {", ".join(texts[:5]) or "(no output)"}')
    findings['hidden_cheat'] = {
        'sound_master': [sound_before, sound_after],
        'cd_audio': [cd_before, cd_after],
        'side_flag': [flag_before, flag_after],
        'texts': texts,
    }

    # ==================================================================
    # TEST F: Runtime string table
    # ==================================================================
    log('\n=== F: String table (key IDs) ===')
    strings_found = {}
    for sid in STRING_IDS:
        s = be.get_string(sid)
        if s:
            strings_found[sid] = s
            log(f'  [{sid:3d}] {s[:80]}')
        else:
            log(f'  [{sid:3d}] (null)')
    findings['string_table'] = strings_found

    # Also dump a range around the dev menu area (200..260)
    log('  Range 200..260:')
    batch = be.get_strings(200, 60)
    for sid_str, s in sorted(batch.items(), key=lambda x: int(x[0])):
        sid = int(sid_str)
        if s:
            strings_found[sid] = s
            log(f'  [{sid:3d}] {s[:80]}')
    findings['string_table_extended'] = strings_found

    # ==================================================================
    # TEST G: BSS table at 0x74bce8
    # ==================================================================
    log('\n=== G: BSS table at 0x74bce8 ===')
    bss_strings = []
    for i in range(10):
        addr = 0x74bce8 + i * 212  # stride 53*4 = 212
        try:
            s = be.api.read_u32(addr)
            if s != 0 and s != 0xDEAD:
                try:
                    text = be.api.get_string(0)  # dummy — need to read as CString
                except Exception:
                    text = None
                # Just read the raw bytes as a string at the address
                raw = ''
                for j in range(60):
                    b = be.read_u32(addr + j * 4)
                    if b == 0:
                        break
                bss_strings.append(f'[{i}] @0x{addr:x} = 0x{s:08x}')
                log(f'  [{i}] @0x{addr:x} = 0x{s:08x}')
            else:
                log(f'  [{i}] @0x{addr:x} = 0 (empty)')
        except Exception as e:
            log(f'  [{i}] @0x{addr:x} = ERR: {e}')
    findings['bss_table'] = bss_strings

    # ==================================================================
    # Done
    # ==================================================================
    log('\n=== Final state ===')
    s = be.snap()
    if s:
        log(f'  credits={s["credits"]} damage={s["damage_state"]} gravity={s["gravity"]} hud={s["hud_mode"]}')

    save()
    log(f'Saved: {LOG_PATH}, {JSON_PATH}')

    try:
        be.detach()
    except Exception:
        pass
    log('Done.')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        import traceback
        log(f'FATAL: {e}')
        log(traceback.format_exc())
        save()
