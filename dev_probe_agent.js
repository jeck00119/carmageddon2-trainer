// Carma2 dev mode probe agent — loaded as a SECOND script alongside agent.js
// on the same Frida session. The trainer agent handles input release, WndProc
// subclass, etc; we just add probe-specific RPCs and hooks.
//
// Verified addresses (from analysis 2026-04-09):
//   0x68b8e0  cheat_mode flag       — write 0xa11ee75d to unlock dev menu always
//   0x67c468  dev menu selection    — cycles 0..11 over the 12 categories
//   0x68b918  game_state            — 0=menu, !=0 in-race
//   0x4414b0  dev menu function     — gated by cheat_mode == 0xa11ee75d / 0x564e78b9
//   0x441600  number-key #0 handler — 18 of these at +0x80 stride
//   0x482550  is_key_pressed(ecx)   — fastcall, key index in ecx
//   0x575de0  sprintf-like          — captures dev menu's "Edit mode: %s" text
//   0x449fd0  print/render text     — text rendering pipeline
//   0x455690  PlaySound (fastcall)  — ecx=channel edx=sound_id
//   0x4414a3  simple flag toggle    — for sanity check (lives next to dev menu)
//   0x444f40  gonad-related fn      — also in the polled table
//   0x518780  fn from polled table  — index 5
//   0x590100  polled function table base
//   0x5904c0  dev menu option ptr table
//   0x5904f0  per-action fn ptr sub-table for number key #0

var VA = {
    CHEAT_MODE:       0x68b8e0,
    SELECTION:        0x67c468,
    GAME_STATE:       0x68b918,
    DOGAME_STATE:     0x75bc24,

    DEV_MENU_FN:      0x4414b0,
    NUM_KEY_FN_BASE:  0x441600,
    NUM_KEY_FN_STRIDE: 0x80,
    NUM_KEY_FN_COUNT: 18,
    SIMPLE_TOGGLE:    0x441490,
    GONAD_RELATED:    0x444f40,
    // 0x441900 is a 1-byte `ret` stub — Frida can't hook it, must skip
    BAD_HOOK_ADDRS:   [0x441900],

    IS_KEY_PRESSED:   0x482550,
    IS_ACTION_PRESSED: 0x4833a0,   // is_action_pressed(ecx=action_id) — used by polled dispatcher
    DISPATCHER:       0x442e90,    // walks polled-table at 0x5900a0..0x5904c0
    KEYBINDING_TABLE: 0x74b5e0,    // action_id -> key index
    KEYSTATE_TABLE:   0x68bee0,    // key_idx -> pressed flag
    SPRINTF:          0x575de0,
    PRINT_TEXT:       0x449fd0,
    PLAY_SOUND:       0x455690,

    // The 5 cheat-table handlers — hook these to detect if dev keys fire cheats
    H_SET_CHEAT_MODE: 0x441580,
    H_FINISH_RACE:    0x4415c0,
    H_SPAWN_POWERUP:  0x442e80,
    H_FLY_TOGGLE:     0x444350,
    H_GONAD_OF_DEATH: 0x444f10,

    OPTION_TABLE:     0x5904c0,
    POLLED_TABLE:     0x590100,
};

var traceLog = [];
var listeners = [];   // (label, listener) pairs
var fakeKeyTarget = -1;
var fakeKeyTtl = 0;
var fakeKeyListener = null;

var fakeActionTarget = -1;
var fakeActionTtl = 0;
var fakeActionListener = null;

function pushTrace(ev) {
    if (traceLog.length < 20000) {
        ev.ts = Date.now();
        traceLog.push(ev);
    }
}

function safeReadU32(addr) {
    try { return ptr(addr).readU32(); } catch (e) { return 0; }
}

function safeReadCString(addr, max) {
    try {
        // Read raw bytes ourselves so we can stop at the first non-printable
        // run (the game's text buffers aren't always null-terminated).
        var bytes = ptr(addr).readByteArray(max || 128);
        if (!bytes) return null;
        var arr = new Uint8Array(bytes);
        var clean = '';
        var bad_run = 0;
        for (var i = 0; i < arr.length; i++) {
            var c = arr[i];
            if (c === 0) break;                 // null terminator
            if (c >= 0x20 && c < 0x7f) {
                clean += String.fromCharCode(c);
                bad_run = 0;
            } else {
                bad_run++;
                if (bad_run >= 2) break;        // stop after 2 bad bytes
            }
        }
        return clean;
    } catch (e) { return null; }
}

function attachLabeled(label, addr, callbacks) {
    try {
        var l = Interceptor.attach(ptr(addr), callbacks);
        listeners.push([label, l]);
        return true;
    } catch (e) {
        send({h: 'probe_log', msg: 'attach ' + label + ' @' + ptr(addr) + ' failed: ' + e});
        return false;
    }
}

function uninstallAll() {
    for (var i = 0; i < listeners.length; i++) {
        try { listeners[i][1].detach(); } catch (e) {}
    }
    listeners = [];
    if (fakeKeyListener) {
        try { fakeKeyListener.detach(); } catch (e) {}
        fakeKeyListener = null;
    }
    if (fakeActionListener) {
        try { fakeActionListener.detach(); } catch (e) {}
        fakeActionListener = null;
    }
    fakeKeyTarget = -1;
    fakeKeyTtl = 0;
    fakeActionTarget = -1;
    fakeActionTtl = 0;
}

function installTrace() {
    uninstallAll();

    // ---- Dev menu function ----
    attachLabeled('dev_menu', VA.DEV_MENU_FN, {
        onEnter: function (args) {
            pushTrace({
                t: 'dev_menu',
                sel: safeReadU32(VA.SELECTION),
                cm: safeReadU32(VA.CHEAT_MODE),
                gs: safeReadU32(VA.GAME_STATE),
            });
        }
    });

    // ---- 18 number-key handlers (skip bad-hook addrs) ----
    for (var i = 0; i < VA.NUM_KEY_FN_COUNT; i++) {
        var addr = VA.NUM_KEY_FN_BASE + i * VA.NUM_KEY_FN_STRIDE;
        if (VA.BAD_HOOK_ADDRS.indexOf(addr) >= 0) continue;
        (function (idx, address) {
            attachLabeled('num_key_' + idx, address, {
                onEnter: function (args) {
                    pushTrace({
                        t: 'num_key',
                        i: idx,
                        sel: safeReadU32(VA.SELECTION),
                        cm: safeReadU32(VA.CHEAT_MODE),
                    });
                }
            });
        })(i, addr);
    }

    // ---- Other polled-table fns ----
    attachLabeled('simple_toggle', VA.SIMPLE_TOGGLE, {
        onEnter: function (args) {
            pushTrace({t: 'simple_toggle'});
        }
    });

    attachLabeled('gonad_related', VA.GONAD_RELATED, {
        onEnter: function (args) {
            pushTrace({t: 'gonad_rel'});
        }
    });

    // ---- The 5 cheat-table HANDLERS ----
    // If dev mode keys secretly call cheat handlers, this catches it.
    attachLabeled('h_set_cheat_mode', VA.H_SET_CHEAT_MODE, {
        onEnter: function (args) {
            pushTrace({t: 'h_set_cheat_mode',
                       sel: safeReadU32(VA.SELECTION),
                       cm: safeReadU32(VA.CHEAT_MODE)});
        }
    });
    attachLabeled('h_finish_race', VA.H_FINISH_RACE, {
        onEnter: function (args) {
            pushTrace({t: 'h_finish_race', sel: safeReadU32(VA.SELECTION)});
        }
    });
    attachLabeled('h_spawn_powerup', VA.H_SPAWN_POWERUP, {
        onEnter: function (args) {
            // Try to read the arg if it's on the stack — but spawn_powerup
            // is called via fn ptr from the cheat table with the arg in
            // [eax+0xc]. Just log selection state.
            pushTrace({t: 'h_spawn_powerup',
                       sel: safeReadU32(VA.SELECTION),
                       arg0: args[0] ? args[0].toInt32() : -1});
        }
    });
    attachLabeled('h_fly_toggle', VA.H_FLY_TOGGLE, {
        onEnter: function (args) {
            pushTrace({t: 'h_fly_toggle', sel: safeReadU32(VA.SELECTION)});
        }
    });
    attachLabeled('h_gonad_of_death', VA.H_GONAD_OF_DEATH, {
        onEnter: function (args) {
            pushTrace({t: 'h_gonad_of_death', sel: safeReadU32(VA.SELECTION)});
        }
    });

    // ---- sprintf — capture dev menu's formatted strings ----
    attachLabeled('sprintf', VA.SPRINTF, {
        onEnter: function (args) {
            // sprintf(buf, fmt, ...)
            var fmt = safeReadCString(args[1]);
            if (fmt && fmt.length < 200 && fmt.length > 0) {
                // Filter to potentially-relevant patterns
                if (fmt.indexOf('%s') >= 0 || fmt.indexOf('Edit') >= 0 ||
                    fmt.indexOf('Cheat') >= 0 || fmt.indexOf('mode') >= 0 ||
                    fmt.indexOf('Powerup') >= 0 || fmt.indexOf('Damage') >= 0) {
                    // Try to capture the formatted result by reading buf after the call
                    this.buf = args[0];
                    this.fmt = fmt;
                    this.capture = true;
                }
            }
        },
        onLeave: function (retval) {
            if (this.capture) {
                var result = safeReadCString(this.buf);
                pushTrace({
                    t: 'sprintf',
                    fmt: this.fmt,
                    out: result,
                    sel: safeReadU32(VA.SELECTION),
                    cm: safeReadU32(VA.CHEAT_MODE),
                });
            }
        }
    });

    // ---- Print text (text rendering) ----
    // 0x449fd0 has unknown signature; we just count calls and try to read the
    // first arg as a string if it looks like a pointer.
    attachLabeled('print_text', VA.PRINT_TEXT, {
        onEnter: function (args) {
            try {
                // The function takes a string buffer somewhere. Look at the
                // first 5 stack args for a pointer that decodes as a string.
                var found = null;
                for (var i = 0; i < 6; i++) {
                    try {
                        var p = args[i];
                        if (!p.isNull()) {
                            var s = p.readCString(80);
                            if (s && s.length > 1 && /[A-Za-z]/.test(s)) {
                                found = {arg: i, s: s};
                                break;
                            }
                        }
                    } catch (e) {}
                }
                if (found) {
                    pushTrace({
                        t: 'print_text',
                        arg: found.arg,
                        s: found.s,
                        sel: safeReadU32(VA.SELECTION),
                    });
                }
            } catch (e) {}
        }
    });

    // ---- PlaySound — fastcall (ecx=channel, edx=sound_id) ----
    attachLabeled('play_sound', VA.PLAY_SOUND, {
        onEnter: function (args) {
            try {
                var ch = this.context.ecx ? this.context.ecx.toInt32() : -1;
                var sid = this.context.edx ? this.context.edx.toInt32() : -1;
                pushTrace({t: 'play_sound', ch: ch, id: sid});
            } catch (e) {
                pushTrace({t: 'play_sound', err: e.toString()});
            }
        }
    });

    return 'installed (' + listeners.length + ' listeners)';
}

function setFakeKey(keyIdx, ttl) {
    fakeKeyTarget = keyIdx;
    fakeKeyTtl = ttl;
    if (fakeKeyListener === null) {
        try {
            fakeKeyListener = Interceptor.attach(ptr(VA.IS_KEY_PRESSED), {
                onEnter: function (args) {
                    try {
                        this.matched = (this.context.ecx.toInt32() === fakeKeyTarget);
                    } catch (e) { this.matched = false; }
                },
                onLeave: function (retval) {
                    if (this.matched && fakeKeyTtl > 0) {
                        retval.replace(ptr(1));
                        fakeKeyTtl--;
                        if (fakeKeyTtl === 0) fakeKeyTarget = -1;
                        pushTrace({t: 'fake_key_used', key: fakeKeyTarget,
                                   sel: safeReadU32(VA.SELECTION)});
                    }
                }
            });
        } catch (e) {
            return 'attach err: ' + e;
        }
    }
    return 'set';
}

// is_action_pressed (0x4833a0) is the function the polled-table dispatcher
// uses to check if a record's action_id is "pressed". Hooking this is what
// actually makes the dispatcher fire dev functions.
function setFakeAction(actionId, ttl) {
    fakeActionTarget = actionId;
    fakeActionTtl = ttl;
    if (fakeActionListener === null) {
        try {
            fakeActionListener = Interceptor.attach(ptr(VA.IS_ACTION_PRESSED), {
                onEnter: function (args) {
                    try {
                        this.matched = (this.context.ecx.toInt32() === fakeActionTarget);
                    } catch (e) { this.matched = false; }
                },
                onLeave: function (retval) {
                    if (this.matched && fakeActionTtl > 0) {
                        retval.replace(ptr(1));
                        fakeActionTtl--;
                        if (fakeActionTtl === 0) {
                            pushTrace({t: 'fake_action_consumed', id: fakeActionTarget});
                            fakeActionTarget = -1;
                        }
                    }
                }
            });
        } catch (e) {
            return 'attach err: ' + e;
        }
    }
    return 'set';
}

// Read the action -> physical key binding from runtime state.
function getActionKey(actionId) {
    try {
        var keyIdx = ptr(VA.KEYBINDING_TABLE + actionId * 4).readU32();
        return keyIdx;
    } catch (e) {
        return -1;
    }
}

// Write the keystate table directly: faster path that doesn't need a hook.
function pokeKeyState(keyIdx, val) {
    try {
        ptr(VA.KEYSTATE_TABLE + keyIdx * 4).writeU32(val >>> 0);
        return 'ok';
    } catch (e) {
        return 'err: ' + e;
    }
}

function callDevMenu() {
    try {
        // Frida x86 win32 supports 'mscdecl', 'stdcall', 'thiscall', 'fastcall'
        var fn = new NativeFunction(ptr(VA.DEV_MENU_FN), 'void', [], 'mscdecl');
        fn();
        return 'called';
    } catch (e) {
        return 'error: ' + e;
    }
}

// Direct-call any of the 18 number-key polling functions.
// They take no args (read globals + is_key_pressed internally).
function callNumKey(idx) {
    if (idx < 0 || idx >= VA.NUM_KEY_FN_COUNT) return 'bad idx';
    var addr = VA.NUM_KEY_FN_BASE + idx * VA.NUM_KEY_FN_STRIDE;
    try {
        var fn = new NativeFunction(ptr(addr), 'void', [], 'mscdecl');
        fn();
        return 'called 0x' + addr.toString(16);
    } catch (e) {
        return 'error: ' + e;
    }
}

// Drive the dev menu through one full cycle, capturing each output.
// Returns an array of the "Edit mode: <X>" strings or similar dev menu output.
function driveDevMenu(steps) {
    var results = [];
    for (var i = 0; i < steps; i++) {
        traceLog = [];
        try {
            var fn = new NativeFunction(ptr(VA.DEV_MENU_FN), 'void', [], 'mscdecl');
            fn();
        } catch (e) {
            results.push({step: i, err: e.toString()});
            continue;
        }
        // Capture sprintf events that might have the dev menu text
        var dev_strs = [];
        for (var j = 0; j < traceLog.length; j++) {
            var ev = traceLog[j];
            if (ev.t === 'sprintf' && ev.out &&
                (ev.out.indexOf('Edit') >= 0 || ev.out.indexOf('Cheat') >= 0 ||
                 ev.out.indexOf('mode') >= 0 || ev.fmt === 'Edit mode: %s' ||
                 ev.fmt === '%s %d %s')) {
                dev_strs.push({fmt: ev.fmt, out: ev.out});
            }
        }
        results.push({
            step: i,
            sel: safeReadU32(VA.SELECTION),
            cm: safeReadU32(VA.CHEAT_MODE),
            dev_strs: dev_strs,
            total_events: traceLog.length,
        });
    }
    return results;
}

function dumpOptionTable() {
    var out = [];
    for (var i = 0; i < 12; i++) {
        try {
            var ptrVal = ptr(VA.OPTION_TABLE + i * 4).readU32();
            var s = safeReadCString(ptr(ptrVal));
            out.push({i: i, ptr: ptrVal, s: s});
        } catch (e) {
            out.push({i: i, err: e.toString()});
        }
    }
    return out;
}

function memSnapshot() {
    return {
        cheat_mode: safeReadU32(VA.CHEAT_MODE),
        selection: safeReadU32(VA.SELECTION),
        game_state: safeReadU32(VA.GAME_STATE),
        dogame_state: safeReadU32(VA.DOGAME_STATE),
    };
}

rpc.exports = {
    setCheatMode: function (v) {
        try { ptr(VA.CHEAT_MODE).writeU32(v >>> 0); return 'ok'; }
        catch (e) { return 'err: ' + e; }
    },
    getCheatMode: function () { return safeReadU32(VA.CHEAT_MODE); },

    getSelection: function () { return safeReadU32(VA.SELECTION); },
    setSelection: function (v) {
        try { ptr(VA.SELECTION).writeU32(v >>> 0); return 'ok'; }
        catch (e) { return 'err: ' + e; }
    },

    getGameState: function () { return safeReadU32(VA.GAME_STATE); },
    snap: memSnapshot,

    installTrace: installTrace,
    uninstallTrace: uninstallAll,
    getTrace: function () {
        var t = traceLog;
        traceLog = [];
        return t;
    },
    clearTrace: function () { traceLog = []; return 'ok'; },
    traceCount: function () { return traceLog.length; },

    callDevMenu: callDevMenu,
    callNumKey: callNumKey,
    driveDevMenu: driveDevMenu,
    setFakeKey: setFakeKey,
    setFakeAction: setFakeAction,
    getActionKey: getActionKey,
    pokeKeyState: pokeKeyState,
    clearFakeKey: function () {
        fakeKeyTarget = -1;
        fakeKeyTtl = 0;
        return 'ok';
    },
    clearFakeAction: function () {
        fakeActionTarget = -1;
        fakeActionTtl = 0;
        return 'ok';
    },

    readU32: function (addr) {
        try { return ptr(addr >>> 0).readU32(); }
        catch (e) { return -1; }
    },
    writeU32: function (addr, val) {
        try { ptr(addr >>> 0).writeU32(val >>> 0); return 'ok'; }
        catch (e) { return 'err: ' + e; }
    },
    readBytes: function (addr, len) {
        try {
            var buf = ptr(addr >>> 0).readByteArray(len);
            return buf;
        } catch (e) { return null; }
    },

    // Read N u32s from a contiguous region — used for memory-diff snapshots.
    readU32Range: function (addr, count) {
        var out = [];
        var p = ptr(addr >>> 0);
        for (var i = 0; i < count; i++) {
            try { out.push(p.add(i * 4).readU32()); }
            catch (e) { out.push(0); }
        }
        return out;
    },

    dumpOptionTable: dumpOptionTable,
};

send({h: 'probe_init'});
