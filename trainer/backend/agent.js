// Carma2 trainer — Frida agent.
//
// Responsibilities:
//   1. Input release           (user32 noops + dinput non-exclusive)
//   2. No-minimize on focus loss (WndProc subclass)
//   3. nGlide windowed toggle  (extracted from glide2x.dll WH_KEYBOARD proc)
//   4. Cheat hash injection    (hooks GetCheatInputHash)
//   5. Menu click reimpl       (calls menu_cleanup/init/finalize/postfx)
//
// Exposed RPCs:
//   snap()              -> {menu, sel, game_state, dogame_state, ...}
//   clickSel(sel)       -> menu click reimpl
//   fireByHash(h1, h2)  -> arm one-shot hash override
//   altEnter()          -> toggle nGlide windowed/fullscreen

// ===========================================================================
// Helpers
// ===========================================================================
function rd32(va) { try { return ptr(va).readU32(); } catch (e) { return 0xDEAD; } }
function wr32(va, v) {
    try { ptr(va).writeU32(v); }
    catch (e) { send({h: 'log', msg: 'wr32 FAILED @0x' + va.toString(16) + ': ' + e}); }
}

// ===========================================================================
// Constants
// ===========================================================================
// Verified Carma2 addresses
var VA = {
    GET_CHEAT_HASH:  0x482f10,
    HASH_BUF:        0x68c1e0,   // h1@+0, h2@+4
    MENU_PTR:        0x688abc,
    SEL:             0x688770,
    GAME_STATE:      0x68b918,
    DOGAME_STATE:    0x75bc24,
    RACE_LOAD_FLAG:  0x6883a8,
    MAIN_MENU:       0x5a80f0,
    NEWGAME_MENU:    0x5bf280,
    QUIT_MENU:       0x649df0,
    FN_CLEANUP:      0x0046ccb0,
    FN_INIT:         0x0046c970,
    FN_FINALIZE:     0x00470a90,
    FN_POSTFX:       0x00467a70,
};

// Menu item slot layout
var MENU_SLOT_SIZE   = 0x158;
var MENU_OFF_CB      = 0x134;
var MENU_OFF_TARGET  = 0x138;
var MENU_OFF_TYPE    = 0x13c;

// ===========================================================================
// DEV CHEAT SYSTEM (discovered 2026-04-10)
// ---------------------------------------------------------------------------
// All these are gated by [0x68b8e0] == 0xa11ee75d. Set DEV.MODE_VALUE to
// unlock; functions then run when called directly. Many are reachable from
// the polled-table dispatcher at 0x442e90 too, but direct calls bypass the
// edge-trigger requirement.
// See memory/project_dev_menu_discovery.md for the full reverse-engineering.
// ===========================================================================
var DEV = {
    // The magic value that unlocks the dev cheat system
    MODE_VALUE:  0xa11ee75d,

    // State / data addresses
    CHEAT_MODE:  0x68b8e0,   // write MODE_VALUE to enable
    CREDITS:     0x676920,   // player credits (HUD display)
    CREDITS_BUY: 0x75bb80,   // purchase/upgrade credits (separate from HUD credits!)
    DAMAGE_STATE:0x67c498,   // 0..7 damage cycler state
    HUD_MODE:    0x655e54,   // 0..5 HUD cycler state
    GRAVITY:     0x68b910,   // gravity flag (0=earth, 1=lift off)
    SPEC_FLAG:   0x6a0940,   // spectator camera enabled
    SPEC_INDEX:  0x6a0a58,   // spectator current index
    GAME_STATE_PTR: 0x75bc2c,  // game state struct passed to spawn_powerup
    SEL_DEV:     0x67c468,   // dev menu selection (0=Options, 1=Cheat)

    // Spawn fastcall + credit dispatcher
    SPAWN_POWERUP: 0x4d8d40,  // fastcall(ecx=GAME_STATE_PTR, edx=id, push 1, push 1)
    CREDIT_DELTA:  0x44b300,  // fastcall(ecx=delta, edx=&credits)

    // void(void) mscdecl functions — verified by static analysis
    FN_INSTANT_REPAIR:    0x5039b0, // F2 mask=0
    FN_DAMAGE_CYCLE:      0x444420, // F3 mask=0  (cycles DAMAGE_STATE 0..7)
    FN_TIMER_TOGGLE:      0x444590, // F5 mask=0  (timer freeze ↔ thaw)
    FN_TELEPORT:          0x4b5ab0, // F3 mask=4  (reset car position)
    FN_GRAVITY_TOGGLE:    0x444350, // toggles GRAVITY, prints "We have lift off!!" / "Back down to Earth"
    FN_GRAVITY_STATE:     0x4443c0, // gravity state reader (in-race maintenance)
    FN_MINIMAP_TOGGLE:    0x4420e0, // key 'j'
    FN_HUD_CYCLE:         0x444f40, // F12 (HUD_MODE cycler 0..5)
    FN_DEV_MENU:          0x4414b0, // F1 (Edit mode: Options ↔ Cheat)
    FN_SPECTATOR_TOGGLE:  0x4da9d0, // Tab
    FN_SPECTATOR_NEXT:    0x4dab80, // '['
    FN_SPECTATOR_PREV:    0x4daa00, // ']'
    FN_ITEM_NEXT:         0x4d6240, // F4 mask=0
    FN_ITEM_PREV:         0x4d6290, // F4 mask=4
    FN_ITEM_SORT:         0x4d62e0, // F4 mask=1
    FN_SHADOW_TOGGLE:     0x4e9b90, // F5 mask=1 (Solid ↔ Translucent)
    FN_SHADOW_3STATE:     0x4e9960, // F5 mask=4 (3-state cycler)
    FN_RESET_SOUND_STATE: 0x502e00, // F2 mask=1
    FN_QUICK_SAVE:        0x5032a0, // F7 mask=4
    FN_ZOOM_INCR:         0x4e4cd0, // 'y'  (camera/zoom 0..8 increment)
    FN_ZOOM_DECR:         0x4e4d00, // 'z'  (decrement)
    FN_CAMERA_STEP:       0x40e430, // 'print sc'
    FN_VISUAL_TOGGLE_7:   0x494840, // 'return'+'7' modifier
    FN_VISUAL_TOGGLE_9:   0x494880, // 'return'+'9' modifier
    FN_DEV_CHECK_9:       0x40e900, // '9'
    FN_DEV_SLASH:         0x502e50, // '/'
    FN_DEV_SEMI:          0x502fd0, // ';'
    FN_DEV_PERIOD:        0x503030, // '.'
    FN_DEV_Q:             0x4945f0, // 'q'
    FN_DEV_W:             0x494700, // 'w'
    FN_RECOVERY_COST:     0x442300, // 'o' (recovery cost editor)
    FN_SOUND_SUBSYS:      0x455a50, // 'p' (toggle_sound_subsystem)
    FN_SIMPLE_TOGGLE:     0x441490, // '8'
    FN_LIGHTING_PROFILER: 0x444ed0, // F12 secondary
    FN_GONAD_OF_DEATH:    0x444f10,
    FN_DEMOFILE_LOAD:     0x445000,

    // Powerup spawner family base addresses (10 fns at +0x60 stride)
    // base offset 0..9; modifier keys add 10/20/40/80
    FN_SPAWNER_BASE:      0x4dbdb0,
};

// Win32 message IDs we care about (others early-exit)
var WM_NULL             = 0x0000;
var WM_ACTIVATE         = 0x0006;
var WM_KILLFOCUS        = 0x0008;
var WM_ACTIVATEAPP      = 0x001C;
var WM_NCACTIVATE       = 0x0086;
var WM_TRAINER_ALTENTER = 0x8001;   // custom: trigger windowed toggle on main thread
var WA_INACTIVE         = 0;

// ===========================================================================
// Mutable state
// ===========================================================================
var gameHwnd            = NULL;     // captured by WndProc subclass
var nglideKeyboardProc  = NULL;     // first WH_KEYBOARD proc captured
var nglideToggleFlag    = NULL;     // ASLR-shifted addr of windowed flag
var nglideTogglePending = NULL;     // ASLR-shifted addr of pending flag
var injectArmed         = false;    // one-shot cheat hash override armed
var injectH1            = 0;
var injectH2            = 0;

// ===========================================================================
// Pre-flight: verify function prologues at hook addresses (on-disk bytes).
// ===========================================================================
function verifyAddresses() {
    var checks = [
        [VA.GET_CHEAT_HASH, 0x56, 'GetCheatInputHash'],  // push esi
        [VA.FN_CLEANUP,     0x81, 'menu_cleanup'],        // sub esp, ...
        [VA.FN_INIT,        0x81, 'menu_init'],           // sub esp, ...
    ];
    var ok = true;
    for (var i = 0; i < checks.length; i++) {
        var addr = checks[i][0];
        var expected = checks[i][1];
        var label = checks[i][2];
        try {
            var actual = ptr(addr).readU8();
            if (actual !== expected) {
                send({h: 'log', msg: 'ADDRESS MISMATCH: ' + label + ' @0x' +
                    addr.toString(16) + ' byte=0x' + actual.toString(16) +
                    ' expected=0x' + expected.toString(16)});
                ok = false;
            }
        } catch (e) {
            send({h: 'log', msg: 'ADDRESS UNREADABLE: ' + label + ' @0x' +
                addr.toString(16) + ': ' + e});
            ok = false;
        }
    }
    if (ok) send({h: 'log', msg: 'address verification: all OK'});
    return ok;
}
var addressesOk = verifyAddresses();

// Safe mode: disable ALL hooks (user32, dinput, cheat injection, wndproc).
// Only snap/RPC will work. Controlled via CARMA2_SAFE_MODE env var at spawn.
var SAFE_MODE = false;
try {
    // Check if safe mode was requested (set by Python before script load)
    if (typeof globalThis._safeMode !== 'undefined' && globalThis._safeMode) {
        SAFE_MODE = true;
    }
} catch (e) {}
send({h: 'log', msg: 'SAFE_MODE=' + SAFE_MODE});

// ===========================================================================
// nGlide WH_KEYBOARD toggle extraction
// ---------------------------------------------------------------------------
// nGlide installs SetWindowsHookEx(WH_KEYBOARD=2, ...) with a proc inside
// glide2x.dll. The proc detects Alt+Enter and flips two globals:
//     mov [TOGGLE_PENDING], 1
//     mov [TOGGLE_FLAG], eax     ; eax = old_flag XOR 1
// We disassemble the proc once at install time, extract the addresses, then
// write them directly. Bypasses every guard check inside the proc.
// ===========================================================================
function extractToggle(addr) {
    try {
        // Follow incremental-link thunk if present.
        var firstInsn = Instruction.parse(addr);
        var pc = (firstInsn.mnemonic === 'jmp') ? ptr(firstInsn.opStr) : addr;

        var pastCall = false;
        var sawPending = false;
        for (var i = 0; i < 80; i++) {
            var insn = Instruction.parse(pc);
            if (!pastCall) {
                if (insn.mnemonic === 'call') pastCall = true;
            } else if (insn.mnemonic === 'mov') {
                var m = insn.opStr.match(/\[0x([0-9a-f]+)\],\s*(\S+)/i);
                if (m) {
                    var addrVal = ptr('0x' + m[1]);
                    if (!sawPending && m[2] === '1') {
                        nglideTogglePending = addrVal;
                        sawPending = true;
                    } else if (sawPending && m[2] === 'eax') {
                        nglideToggleFlag = addrVal;
                        send({h: 'log', msg: 'toggle extracted: flag=' +
                              nglideToggleFlag.toString() + ' pending=' +
                              nglideTogglePending.toString()});
                        send({h: 'toggle_ready'});
                        return;
                    }
                }
            }
            pc = insn.next;
        }
        send({h: 'log', msg: 'extractToggle: pattern not found'});
    } catch (e) {
        send({h: 'log', msg: 'extractToggle error: ' + e});
    }
}

function doToggle() {
    if (nglideToggleFlag.isNull() || nglideTogglePending.isNull()) {
        send({h: 'log', msg: 'toggle: not extracted yet'});
        return;
    }
    try {
        var newFlag = nglideToggleFlag.readU32() ^ 1;
        nglideTogglePending.writeU32(1);
        nglideToggleFlag.writeU32(newFlag);
    } catch (e) {
        send({h: 'log', msg: 'toggle exception: ' + e});
    }
}

// ===========================================================================
// user32 hooks (single block)
// ===========================================================================
var u32 = Process.findModuleByName('user32.dll');
var postMessageA = null;

if (u32 && !SAFE_MODE) {
    var _hookOk = 0, _hookFail = 0;
    try {
        postMessageA = new NativeFunction(u32.getExportByName('PostMessageA'),
            'int', ['pointer', 'uint32', 'uint32', 'uint32'], 'stdcall');
    } catch (e) { send({h: 'log', msg: 'PostMessageA resolve failed: ' + e}); }

    // ---- Input release: blanket-ignore window-focus-stealing APIs ----
    function noop(name, ret, sig) {
        try {
            Interceptor.replace(u32.getExportByName(name),
                new NativeCallback(function () { return ret; }, sig[0], sig[1], sig[2]));
            _hookOk++;
        } catch (e) { _hookFail++; send({h: 'log', msg: 'noop(' + name + ') failed: ' + e}); }
    }
    noop('ClipCursor',              1,      ['int',     ['pointer'],                     'stdcall']);
    noop('SetCapture',              ptr(0), ['pointer', ['pointer'],                     'stdcall']);
    noop('SetForegroundWindow',     1,      ['int',     ['pointer'],                     'stdcall']);
    noop('BringWindowToTop',        1,      ['int',     ['pointer'],                     'stdcall']);
    noop('LockSetForegroundWindow', 1,      ['int',     ['uint32'],                      'stdcall']);
    noop('RegisterRawInputDevices', 1,      ['int',     ['pointer','uint32','uint32'],   'stdcall']);

    try {
        Interceptor.attach(u32.getExportByName('SetActiveWindow'),
            { onEnter: function (args) { args[0] = ptr(0); } });
        _hookOk++;
    } catch (e) { _hookFail++; send({h: 'log', msg: 'SetActiveWindow hook failed: ' + e}); }

    try {
        Interceptor.attach(u32.getExportByName('SetWindowPos'), {
            onEnter: function (args) {
                if (args[1].toInt32() === -1) args[1] = ptr(-2);
                args[6] = ptr(args[6].toInt32() | 0x10);  // | SWP_NOACTIVATE
            }
        });
        _hookOk++;
    } catch (e) { _hookFail++; send({h: 'log', msg: 'SetWindowPos hook failed: ' + e}); }

    // ---- WndProc subclass (no-minimize + WM_TRAINER_ALTENTER dispatch) ----
    // This runs for every message dispatched to the game window. The hot path
    // is the `default` switch case which is just a return.
    var hookedProcs = {};
    function hookWndProc(addr) {
        var key = addr.toString();
        if (hookedProcs[key]) return;
        hookedProcs[key] = true;
        try {
            Interceptor.attach(addr, {
                onEnter: function (args) {
                    if (gameHwnd.isNull()) gameHwnd = args[0];
                    var msg = args[1].toInt32();
                    // Hot-path early exit: most messages are uninteresting.
                    if (msg !== WM_TRAINER_ALTENTER &&
                        msg !== WM_ACTIVATEAPP &&
                        msg !== WM_ACTIVATE &&
                        msg !== WM_NCACTIVATE &&
                        msg !== WM_KILLFOCUS) return;

                    var wp = args[2].toInt32();
                    var swallow = false;

                    if (msg === WM_TRAINER_ALTENTER) {
                        doToggle();
                        swallow = true;
                    } else if (msg === WM_ACTIVATEAPP && wp === 0) {
                        swallow = true;
                    } else if (msg === WM_ACTIVATE && (wp & 0xFFFF) === WA_INACTIVE) {
                        swallow = true;
                    } else if (msg === WM_NCACTIVATE && wp === 0) {
                        swallow = true;
                    } else if (msg === WM_KILLFOCUS) {
                        swallow = true;
                    }

                    if (swallow) {
                        args[1] = ptr(WM_NULL);
                        args[2] = ptr(0);
                        args[3] = ptr(0);
                    }
                }
            });
        } catch (e) { send({h: 'log', msg: 'hookWndProc failed @' + addr + ': ' + e}); }
    }

    // Capture the game's WndProc by snooping RegisterClass[Ex]A/W.
    function captureFromRegister(name, wpOffset) {
        try {
            Interceptor.attach(u32.getExportByName(name), {
                onEnter: function (args) {
                    try {
                        var wp = args[0].add(wpOffset).readPointer();
                        if (!wp.isNull()) hookWndProc(wp);
                    } catch (e) { send({h: 'log', msg: name + ' readPointer failed: ' + e}); }
                }
            });
            _hookOk++;
        } catch (e) { _hookFail++; send({h: 'log', msg: name + ' hook failed: ' + e}); }
    }
    // WNDCLASSA   layout: style@+0, lpfnWndProc@+4
    // WNDCLASSEXA layout: cbSize@+0, style@+4, lpfnWndProc@+8
    captureFromRegister('RegisterClassA',   4);
    captureFromRegister('RegisterClassW',   4);
    captureFromRegister('RegisterClassExA', 8);
    captureFromRegister('RegisterClassExW', 8);

    // ---- Capture nGlide WH_KEYBOARD hook proc once, extract toggle addrs ----
    function hookSetWHE(name) {
        try {
            Interceptor.attach(u32.getExportByName(name), {
                onEnter: function (args) {
                    if (args[0].toInt32() !== 2) return;          // WH_KEYBOARD only
                    if (!nglideKeyboardProc.isNull()) return;     // first one only
                    nglideKeyboardProc = args[1];
                    send({h: 'kbd_proc', addr: nglideKeyboardProc.toString()});
                    extractToggle(nglideKeyboardProc);
                }
            });
            _hookOk++;
        } catch (e) { _hookFail++; send({h: 'log', msg: name + ' hook failed: ' + e}); }
    }
    hookSetWHE('SetWindowsHookExA');
    hookSetWHE('SetWindowsHookExW');
    send({h: 'log', msg: 'user32 hooks: ' + _hookOk + ' OK, ' + _hookFail + ' failed'});
}

// ===========================================================================
// DirectInput non-exclusive (so the game doesn't grab mouse/keyboard)
// ===========================================================================
var dinputHooked = false;
function tryHookDInput() {
    if (dinputHooked) return;
    var mod = Process.findModuleByName('dinput.dll');
    if (!mod) return;
    try {
        Interceptor.attach(mod.getExportByName('DirectInputCreateA'), {
            onEnter: function (args) { this.outPtr = args[2]; },
            onLeave: function (retval) {
                if (retval.toInt32() !== 0 || !this.outPtr) return;
                var diObj = ptr(this.outPtr).readPointer();
                var createDevice = diObj.readPointer().add(3 * 4).readPointer();
                Interceptor.attach(createDevice, {
                    onEnter: function (args) { this.outDev = args[2]; },
                    onLeave: function (retval) {
                        if (retval.toInt32() !== 0 || !this.outDev) return;
                        var devObj = ptr(this.outDev).readPointer();
                        var setCoop = devObj.readPointer().add(13 * 4).readPointer();
                        Interceptor.attach(setCoop, {
                            onEnter: function (args) { args[2] = ptr(2 | 8); }
                        });
                    }
                });
            }
        });
        dinputHooked = true;
    } catch (e) { send({h: 'log', msg: 'DirectInput hook failed: ' + e}); }
}
if (!SAFE_MODE) {
    tryHookDInput();
    try {
        Interceptor.attach(Module.getGlobalExportByName('LoadLibraryA'),
            { onLeave: function () { tryHookDInput(); } });
        send({h: 'log', msg: 'LoadLibraryA hook OK'});
    } catch (e) { send({h: 'log', msg: 'LoadLibraryA hook failed: ' + e}); }
}

// ===========================================================================
// Cheat hash injection
// ---------------------------------------------------------------------------
// One-shot override: when armed, the next call to GetCheatInputHash gets our
// (h1, h2) written into the hash buffer, then disarms. The game's CheatDetect
// compares the buffer to its 94-entry table and dispatches the matching handler.
// ===========================================================================
if (addressesOk && !SAFE_MODE) {
    try {
        Interceptor.attach(ptr(VA.GET_CHEAT_HASH), {
            onLeave: function (retval) {
                if (injectArmed) {
                    ptr(VA.HASH_BUF).writeU32(injectH1);
                    ptr(VA.HASH_BUF + 4).writeU32(injectH2);
                    injectArmed = false;
                }
            }
        });
        send({h: 'log', msg: 'cheat hash hook OK @0x' + VA.GET_CHEAT_HASH.toString(16)});
    } catch (e) {
        send({h: 'log', msg: 'cheat hash hook FAILED: ' + e});
    }
} else {
    send({h: 'log', msg: 'SKIPPED cheat hash hook (addresses=' + addressesOk + ' safe=' + SAFE_MODE + ')'});
}

// ===========================================================================
// Menu click reimplementation
// ===========================================================================
var fn_cleanup  = new NativeFunction(ptr(VA.FN_CLEANUP),  'void', ['pointer'],            'thiscall');
var fn_init     = new NativeFunction(ptr(VA.FN_INIT),     'void', ['pointer'],            'thiscall');
var fn_finalize = new NativeFunction(ptr(VA.FN_FINALIZE), 'void', ['pointer', 'pointer'], 'fastcall');
var fn_postfx   = new NativeFunction(ptr(VA.FN_POSTFX),   'void', ['pointer'],            'thiscall');

function transition(oldMenu, newMenu) {
    try {
        fn_cleanup(ptr(oldMenu));
        wr32(VA.MENU_PTR, newMenu);
        fn_init(ptr(newMenu));
        if (rd32(oldMenu + 0x114) !== newMenu) {
            wr32(newMenu + 0x114, oldMenu);
        }
        fn_finalize(ptr(oldMenu), ptr(newMenu));
        if (newMenu === VA.QUIT_MENU) {
            wr32(VA.SEL, 0);
        } else {
            wr32(VA.SEL, rd32(newMenu + 0x118));
        }
        var n = rd32(newMenu + 0x8790);
        if (n > 0 && n < 256) {
            for (var i = 0; i < n; i++) {
                wr32(newMenu + i * 0x34 + 0x87a0, rd32(newMenu + i * 0x34 + 0x87c0));
            }
        }
        fn_postfx(ptr(newMenu));
    } catch (e) {
        send({h: 'log', msg: 'transition CRASHED: old=0x' + oldMenu.toString(16) +
              ' new=0x' + newMenu.toString(16) + ' err=' + e});
        throw e;
    }
}

function click(sel) {
    var oldMenu = rd32(VA.MENU_PTR);
    var slot = ptr(oldMenu).add(sel * MENU_SLOT_SIZE);
    var cb     = rd32(slot.add(MENU_OFF_CB));
    var target = rd32(slot.add(MENU_OFF_TARGET));
    var type   = rd32(slot.add(MENU_OFF_TYPE));

    wr32(VA.SEL, sel);

    if (type === 2) return 'type2';
    if (type === 1) wr32(VA.RACE_LOAD_FLAG, 1);

    if (cb !== 0) {
        try {
            var cbFn = new NativeFunction(ptr(cb), 'int', ['pointer'], 'thiscall');
            cbFn(ptr(oldMenu));
        } catch (e) {
            return 'cb_err: ' + e;
        }
    }

    var newMenu = rd32(VA.MENU_PTR);
    if (newMenu !== oldMenu) return 'cb_transitioned';

    if (target !== 0) {
        transition(oldMenu, target);
        return 'ok';
    }
    return 'ok_no_target';
}

// ===========================================================================
// Dev cheat helpers
// ---------------------------------------------------------------------------
// Most dev fns are void(void) and use mscdecl (NOT 'cdecl' — Frida rejects
// that name on x86 win32). spawnPowerup is the one fastcall exception.
// ===========================================================================
var _devFnCache = {};

function callDev(addr) {
    try {
        var key = addr.toString();
        var fn = _devFnCache[key];
        if (!fn) {
            fn = new NativeFunction(ptr(addr), 'void', [], 'mscdecl');
            _devFnCache[key] = fn;
        }
        fn();
        return 'ok';
    } catch (e) {
        return 'err: ' + e;
    }
}

var _spawnPowerupFn = null;
function spawnPowerup(id) {
    try {
        if (_spawnPowerupFn === null) {
            _spawnPowerupFn = new NativeFunction(
                ptr(DEV.SPAWN_POWERUP), 'void',
                ['pointer', 'int', 'int', 'int'], 'fastcall');
        }
        _spawnPowerupFn(ptr(DEV.GAME_STATE_PTR), id >>> 0, 1, 1);
        return 'spawned ' + id;
    } catch (e) {
        return 'err: ' + e;
    }
}

function addCreditDelta(delta) {
    // Direct read+write to BOTH credit addresses.
    try {
        var cur = ptr(DEV.CREDITS).readU32();
        var next = (cur + (delta | 0)) >>> 0;
        ptr(DEV.CREDITS).writeU32(next);
        ptr(DEV.CREDITS_BUY).writeU32(next);  // keep purchase credits in sync
        return 'credits ' + cur + ' -> ' + next;
    } catch (e) {
        return 'err: ' + e;
    }
}

function callPowerupSpawnerFamily(baseIdx) {
    if (baseIdx < 0 || baseIdx > 9) return 'bad base';
    return callDev(DEV.FN_SPAWNER_BASE + baseIdx * 0x60);
}

// ===========================================================================
// RPC
// ===========================================================================
rpc.exports = {
    snap: function () {
        // Compound state read — single RPC returns everything the UI needs
        // including dev mode state. Polled at 1 Hz from the trainer.
        return {
            // Menu / race state (existing)
            menu:         rd32(VA.MENU_PTR),
            sel:          rd32(VA.SEL),
            game_state:   rd32(VA.GAME_STATE),
            dogame_state: rd32(VA.DOGAME_STATE),
            main_menu:    VA.MAIN_MENU,
            newgame_menu: VA.NEWGAME_MENU,
            // Dev cheat state
            cheat_mode:   rd32(DEV.CHEAT_MODE),
            dev_active:   rd32(DEV.CHEAT_MODE) === DEV.MODE_VALUE,
            credits:      rd32(DEV.CREDITS),
            damage_state: rd32(DEV.DAMAGE_STATE),
            hud_mode:     rd32(DEV.HUD_MODE),
            gravity:      rd32(DEV.GRAVITY),
            spec_active:  rd32(DEV.SPEC_FLAG),
            spec_index:   rd32(DEV.SPEC_INDEX),
            sel_dev:      rd32(DEV.SEL_DEV),
            // Extended state (verified 2026-04-10 — all 14 "no-effect" actions DO change these)
            sound_master: rd32(0x762328),
            shadow_type:  rd32(0x6a23d8),
            shadow_3st:   rd32(0x65fdc8),
            zoom_lod:     rd32(0x68be38),
            item_count:   rd32(0x7447d4),
            item_index:   rd32(0x7447f0),
        };
    },
    clickSel: function (sel) { return click(sel); },
    fireByHash: function (h1, h2) {
        injectH1 = h1 >>> 0;
        injectH2 = h2 >>> 0;
        injectArmed = true;
        return 'armed';
    },
    altEnter: function () {
        if (gameHwnd.isNull() || postMessageA === null) return 'no_hwnd';
        if (nglideToggleFlag.isNull()) return 'no_toggle';
        // Defer to game's main thread via custom message; the WndProc subclass
        // picks it up and calls doToggle() from the right thread.
        postMessageA(gameHwnd, WM_TRAINER_ALTENTER, 0, 0);
        return 'posted';
    },

    // ===== Dev cheat RPCs =====
    devEnable:     function () { wr32(DEV.CHEAT_MODE, DEV.MODE_VALUE); return 'on'; },
    devDisable:    function () { wr32(DEV.CHEAT_MODE, 0); return 'off'; },
    devIsEnabled:  function () { return rd32(DEV.CHEAT_MODE) === DEV.MODE_VALUE; },

    // Direct memory pokes (faster than calling the dev fns where possible)
    setCredits:    function (amt) {
        wr32(DEV.CREDITS, amt >>> 0);
        wr32(DEV.CREDITS_BUY, amt >>> 0);  // sync both credit addresses
        return 'ok';
    },
    setDamageState: function (n) {
        n = (n >>> 0) & 7;
        wr32(DEV.DAMAGE_STATE, n);
        return 'damage=' + n;
    },
    setHudMode:    function (n) { wr32(DEV.HUD_MODE, (n >>> 0) % 6); return 'ok'; },
    setGravity:    function (v) { wr32(DEV.GRAVITY, v ? 1 : 0); return 'ok'; },
    addCredits:    function (delta) { return addCreditDelta(delta | 0); },

    // Player actions
    instantRepair:    function () { return callDev(DEV.FN_INSTANT_REPAIR); },
    damageCycle:      function () { return callDev(DEV.FN_DAMAGE_CYCLE); },
    timerToggle:      function () { return callDev(DEV.FN_TIMER_TOGGLE); },
    teleport:         function () { return callDev(DEV.FN_TELEPORT); },
    gravityToggle:    function () { return callDev(DEV.FN_GRAVITY_TOGGLE); },
    gravityState:     function () { return callDev(DEV.FN_GRAVITY_STATE); },

    // Powerups
    // spawnPowerup uses hash injection for safety — calling spawn_powerup
    // directly from Frida's thread crashes because game structs aren't
    // accessible off the main thread. fireByHash arms a one-shot override;
    // the game's own CheatDetect calls the handler on the next frame.
    spawnPowerup:     function (id) {
        // Look up the hash for this powerup ID in the cheat table.
        // Entries are 16 bytes: {h1, h2, handler, arg}. Scan for arg == id
        // and handler == spawn_powerup trampoline (0x442e80).
        var base = 0x590970;
        for (var i = 0; i < 94; i++) {
            var off = base + i * 16;
            var handler = rd32(off + 8);
            var arg = rd32(off + 12);
            if (handler === 0x442e80 && arg === (id >>> 0)) {
                var h1 = rd32(off);
                var h2 = rd32(off + 4);
                injectH1 = h1;
                injectH2 = h2;
                injectArmed = true;
                return 'armed id=' + id + ' h=0x' + h1.toString(16);
            }
        }
        // ID not in cheat table — try direct call (may crash outside game thread)
        return spawnPowerup(id);
    },
    spawnerFamily:    function (baseIdx) { return callPowerupSpawnerFamily(baseIdx); },

    // Item / opponent cycler (F4 family)
    itemNext:         function () { return callDev(DEV.FN_ITEM_NEXT); },
    itemPrev:         function () { return callDev(DEV.FN_ITEM_PREV); },
    itemSort:         function () { return callDev(DEV.FN_ITEM_SORT); },

    // HUD / display
    hudCycle:         function () { return callDev(DEV.FN_HUD_CYCLE); },
    minimapToggle:    function () { return callDev(DEV.FN_MINIMAP_TOGGLE); },
    shadowToggle:     function () { return callDev(DEV.FN_SHADOW_TOGGLE); },
    shadow3State:     function () { return callDev(DEV.FN_SHADOW_3STATE); },
    zoomIncr:         function () { return callDev(DEV.FN_ZOOM_INCR); },
    zoomDecr:         function () { return callDev(DEV.FN_ZOOM_DECR); },
    cameraStep:       function () { return callDev(DEV.FN_CAMERA_STEP); },

    // Spectator camera
    spectatorToggle:  function () { return callDev(DEV.FN_SPECTATOR_TOGGLE); },
    spectatorNext:    function () { return callDev(DEV.FN_SPECTATOR_NEXT); },
    spectatorPrev:    function () { return callDev(DEV.FN_SPECTATOR_PREV); },

    // State / save (with NULL-guard for crash-prone fns)
    quickSave: function () {
        // 0x5032a0 reads [[0x762438]+0x210] — crashes if [0x762438] is NULL (not in race)
        var p = rd32(0x762438);
        if (p === 0 || p === 0xDEAD) return 'skip: not in race (NULL struct)';
        return callDev(DEV.FN_QUICK_SAVE);
    },
    resetSoundState:  function () { return callDev(DEV.FN_RESET_SOUND_STATE); },

    // Sound / misc
    soundSubsystem:   function () { return callDev(DEV.FN_SOUND_SUBSYS); },
    simpleToggle:     function () { return callDev(DEV.FN_SIMPLE_TOGGLE); },
    devMenuCycle:     function () { return callDev(DEV.FN_DEV_MENU); },
    recoveryCost:     function () { return callDev(DEV.FN_RECOVERY_COST); },

    // Visual toggles (return key + modifier variants)
    visualToggle7:    function () { return callDev(DEV.FN_VISUAL_TOGGLE_7); },
    visualToggle9:    function () { return callDev(DEV.FN_VISUAL_TOGGLE_9); },

    // Misc dev
    lightingProfiler: function () {
        // 0x444ed0 -> 0x40e7f0 -> chain reads struct fields that can be NULL
        // Guard: check [0x676914] — fn itself bails if non-zero anyway
        var flag = rd32(0x676914);
        if (flag !== 0) return 'skip: guard flag set';
        // Additional check: dogame_state must be 5 (in race)
        if (rd32(VA.DOGAME_STATE) !== 5) return 'skip: not in race';
        return callDev(DEV.FN_LIGHTING_PROFILER);
    },
    gonadOfDeath:     function () { return callDev(DEV.FN_GONAD_OF_DEATH); },
    demoFileLoad:     function () { return callDev(DEV.FN_DEMOFILE_LOAD); },

    // Unlock all 9 camera modes (default: only 4 enabled)
    // Writes to flag arrays at 0x58f600 and 0x58f610 — each byte is a mode enable flag
    // Modes: Standard(0), Panning(1), Action-tracking(2), Manual(3), Rigid(4),
    //        Ped Cam(5), Drone Cam(6), Reversing(7), Internal(8)
    unlockAllCameras: function () {
        for (var base = 0x58f600; base <= 0x58f610; base += 0x10) {
            for (var off = 0; off < 12; off += 4) {
                wr32(base + off, 0x01010101);
            }
        }
        return 'all 9 camera modes enabled';
    },

    // Hidden cheat (only fires from MENU — the check is in the menu update fn)
    hiddenCheat: function () {
        // Hash (0x616fb8e4, 0x7c6100a8) — toggles sound/cd, one-shot sets [0x75bc04]
        injectH1 = 0x616fb8e4;
        injectH2 = 0x7c6100a8;
        injectArmed = true;
        return 'armed (menu only)';
    },

    // Experimental / unmapped (raw fn calls)
    devCheck9:        function () { return callDev(DEV.FN_DEV_CHECK_9); },
    devSlash:         function () { return callDev(DEV.FN_DEV_SLASH); },
    devSemi:          function () { return callDev(DEV.FN_DEV_SEMI); },
    devPeriod:        function () { return callDev(DEV.FN_DEV_PERIOD); },
    devQ:             function () { return callDev(DEV.FN_DEV_Q); },
    devW:             function () { return callDev(DEV.FN_DEV_W); },

    // Generic (for trainer experimentation)
    callAddr:         function (addr) { return callDev(addr >>> 0); },
    readU32:          function (addr) {
        try { return ptr(addr >>> 0).readU32(); }
        catch (e) { return 0xDEAD; }
    },
    writeU32:         function (addr, val) {
        try { ptr(addr >>> 0).writeU32(val >>> 0); return 'ok'; }
        catch (e) { return 'err: ' + e; }
    },

    // String table reader — game builds a string table at 0x6b5f40 at
    // startup (from data files). 0x514d70(ecx=id) = [id*4 + 0x6b5f40].
    getString:        function (id) {
        try {
            var p = ptr(0x6b5f40 + (id >>> 0) * 4).readU32();
            if (p === 0) return null;
            return ptr(p).readCString(200);
        } catch (e) { return null; }
    },
    // Batch read N strings starting from id
    getStrings:       function (startId, count) {
        var out = {};
        for (var i = 0; i < count; i++) {
            var id = startId + i;
            var p = ptr(0x6b5f40 + id * 4).readU32();
            if (p !== 0) {
                try {
                    var s = ptr(p).readCString(200);
                    if (s && s.length > 0) out[id] = s;
                } catch (e) {}
            }
        }
        return out;
    },
};

send({h: 'init_done'});
