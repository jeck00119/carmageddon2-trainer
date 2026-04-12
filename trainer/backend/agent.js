// Carma2 trainer — Frida agent.
//
// Responsibilities:
//   1. Input release           (cursor noops + dinput non-exclusive)
//   2. Alt+Tab fix             (block DInput WH_KEYBOARD_LL hook)
//   3. Cheat hash injection    (hooks GetCheatInputHash)
//   4. Menu click reimpl       (calls menu_cleanup/init/finalize/postfx)
//
// Windowed mode and Alt+Enter are handled natively by dgVoodoo 2.
//
// Exposed RPCs:
//   snap()              -> {menu, sel, game_state, dogame_state, ...}
//   clickSel(sel)       -> menu click reimpl
//   fireByHash(h1, h2)  -> arm one-shot hash override

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
// DEV CHEAT SYSTEM — runtime addresses for the Steam binary
// ---------------------------------------------------------------------------
// These are the standard Carma2 dev/edit mode features (documented in the
// Carmashit cheat executable article). On the Steam edition, the typed-code
// dispatcher is broken, so the trainer unlocks the system via direct memory
// write: [0x68b8e0] = 0xa11ee75d, then calls the functions directly.
// Many are also reachable via the polled-table dispatcher at 0x442e90.
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
    GAME_STATE_PTR: 0x75bc2c,  // game state struct passed to spawn_powerup

    // Spawn fastcall + credit dispatcher
    SPAWN_POWERUP: 0x4d8d40,  // fastcall(ecx=GAME_STATE_PTR, edx=id, push 1, push 1)
    CREDIT_DELTA:  0x44b300,  // fastcall(ecx=delta, edx=&credits)

    // void(void) mscdecl functions
    FN_INSTANT_REPAIR:    0x5039b0, // F2 mask=0
    FN_DAMAGE_CYCLE:      0x444420, // F3 mask=0  (cycles DAMAGE_STATE 0..7)
    FN_TIMER_TOGGLE:      0x444590, // F5 mask=0  (timer freeze ↔ thaw)
    FN_TELEPORT:          0x4b5ab0, // F3 mask=4  (reset car position)
    FN_GRAVITY_TOGGLE:    0x444350, // toggles GRAVITY, prints "We have lift off!!" / "Back down to Earth"
    FN_HUD_CYCLE:         0x444f40, // F12 (HUD_MODE cycler 0..5)
    FN_SIMPLE_TOGGLE:     0x441490, // '8' — force race end
    FN_GONAD_OF_DEATH:    0x444f10,
};

// ===========================================================================
// Mutable state
// ===========================================================================
var injectArmed         = false;    // one-shot cheat hash override armed
var injectH1            = 0;
var injectH2            = 0;

// ===========================================================================
// user32 hooks
// ===========================================================================
var u32 = Process.findModuleByName('user32.dll');

if (u32) {
    // ---- Cursor release: stop the game from locking/capturing the cursor ----
    function noop(name, ret, sig) {
        try {
            Interceptor.replace(u32.getExportByName(name),
                new NativeCallback(function () { return ret; }, sig[0], sig[1], sig[2]));
        } catch (e) {}
    }
    noop('ClipCursor', 1,      ['int',     ['pointer'], 'stdcall']);
    noop('SetCapture', ptr(0), ['pointer', ['pointer'], 'stdcall']);

    // ---- Alt+Tab fix: own LL keyboard hook + block DInput's ----
    // Two-part fix for system hotkeys (Alt+Tab, Win):
    //
    // Part 1: Install our own WH_KEYBOARD_LL hook that passes all keys
    //   through via CallNextHookEx. This ensures the LL hook chain has
    //   a well-behaved hook that forwards system keys to Windows. Without
    //   this, RustDesk (and similar remote desktop tools) can't reliably
    //   inject Alt+Tab into the remote session's LL hook chain.
    //
    // Part 2: Block DInput's WH_KEYBOARD_LL install. DInput installs a
    //   LL hook that eats system keys before the shell sees them. We
    //   rewrite the hook type to invalid so the real call fails, then
    //   fake success so DInput moves on.
    var ourLLHook = NULL;
    try {
        var _SetWindowsHookExA = new NativeFunction(u32.getExportByName('SetWindowsHookExA'),
            'pointer', ['int', 'pointer', 'pointer', 'uint32'], 'stdcall');
        var _CallNextHookEx = new NativeFunction(u32.getExportByName('CallNextHookEx'),
            'pointer', ['pointer', 'pointer', 'uint32', 'pointer'], 'stdcall');

        var llProc = new NativeCallback(function (nCode, wParam, lParam) {
            return _CallNextHookEx(ourLLHook, ptr(nCode >= 0 ? nCode : 0), wParam, lParam);
        }, 'pointer', ['int', 'pointer', 'pointer'], 'stdcall');

        ourLLHook = _SetWindowsHookExA(13, llProc, ptr(0), 0);
    } catch (e) {}

    function hookSetWHE(name) {
        try {
            Interceptor.attach(u32.getExportByName(name), {
                onEnter: function (args) {
                    if (args[0].toInt32() === 13) { // WH_KEYBOARD_LL
                        this.blocked = true;
                        args[0] = ptr(99);
                    }
                },
                onLeave: function (retval) {
                    if (this.blocked) {
                        retval.replace(ptr(0xDEADBEEF));
                        send({h: 'log', msg: 'BLOCKED WH_KEYBOARD_LL install'});
                    }
                }
            });
        } catch (e) { send({h: 'log', msg: name + ' hook failed: ' + e}); }
    }
    hookSetWHE('SetWindowsHookExA');
    hookSetWHE('SetWindowsHookExW');
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
tryHookDInput();
try {
    Interceptor.attach(Module.getGlobalExportByName('LoadLibraryA'),
        { onLeave: function () { tryHookDInput(); } });
} catch (e) {}

// ===========================================================================
// Cheat hash injection
// ---------------------------------------------------------------------------
// One-shot override: when armed, the next call to GetCheatInputHash gets our
// (h1, h2) written into the hash buffer, then disarms. The game's CheatDetect
// compares the buffer to its 94-entry table and dispatches the matching handler.
// ===========================================================================
Interceptor.attach(ptr(VA.GET_CHEAT_HASH), {
    onLeave: function (retval) {
        if (injectArmed) {
            ptr(VA.HASH_BUF).writeU32(injectH1);
            ptr(VA.HASH_BUF + 4).writeU32(injectH2);
            injectArmed = false;
        }
    }
});

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

// ===========================================================================
// RPC
// ===========================================================================
rpc.exports = {
    snap: function () {
        // Compound state read — single RPC returns everything the UI needs.
        // Polled at 1 Hz from the trainer.
        return {
            // Menu / race state
            menu:         rd32(VA.MENU_PTR),
            sel:          rd32(VA.SEL),
            game_state:   rd32(VA.GAME_STATE),
            dogame_state: rd32(VA.DOGAME_STATE),
            main_menu:    VA.MAIN_MENU,
            newgame_menu: VA.NEWGAME_MENU,
            // Dev cheat state (for cyclers and displays)
            cheat_mode:   rd32(DEV.CHEAT_MODE),
            dev_active:   rd32(DEV.CHEAT_MODE) === DEV.MODE_VALUE,
            credits:      rd32(DEV.CREDITS),
            damage_state: rd32(DEV.DAMAGE_STATE),
            hud_mode:     rd32(DEV.HUD_MODE),
            gravity:      rd32(DEV.GRAVITY),
        };
    },
    clickSel: function (sel) { return click(sel); },
    fireByHash: function (h1, h2) {
        injectH1 = h1 >>> 0;
        injectH2 = h2 >>> 0;
        injectArmed = true;
        return 'armed';
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
        return 'not_found: id=' + id + ' not in cheat table';
    },
    // HUD / display
    hudCycle:         function () { return callDev(DEV.FN_HUD_CYCLE); },

    // Utility — force race end (sets [0x74d1a0]=1, kicks you back to main menu)
    simpleToggle:     function () { return callDev(DEV.FN_SIMPLE_TOGGLE); },

    // Steel Gonad o' Death
    gonadOfDeath:     function () { return callDev(DEV.FN_GONAD_OF_DEATH); },

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
    // MWUCUZYSFUYHTQWXEPVU — unlocks all cars and races
    hiddenCheat: function () {
        injectH1 = 0x616fb8e4;
        injectH2 = 0x7c6100a8;
        injectArmed = true;
        return 'armed (menu only)';
    },

};

send({h: 'init_done'});
