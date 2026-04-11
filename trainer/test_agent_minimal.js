// test_agent_minimal.js — strip the trainer agent down to just the dinput
// non-exclusive hook + the WH_KEYBOARD_LL blocker. No user32 noops, no WndProc
// subclass, no nGlide toggle extraction, no game RPCs.
//
// Goal: verify whether the dinput non-exclusive fix alone is what the game
// needs to support Alt+Tab, without any of the nGlide-specific stuff that
// might conflict with dgVoodoo 2.

'use strict';

send({h: 'log', msg: 'minimal agent loaded pid=' + Process.id});

// -------- DInput non-exclusive --------
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
                            onEnter: function (args) {
                                // DISCL_NONEXCLUSIVE (2) | DISCL_BACKGROUND (8)
                                args[2] = ptr(2 | 8);
                                send({h: 'log', msg: 'SetCooperativeLevel -> NONEXCLUSIVE|BACKGROUND'});
                            }
                        });
                    }
                });
            }
        });
        dinputHooked = true;
        send({h: 'log', msg: 'dinput hook installed'});
    } catch (e) { send({h: 'log', msg: 'dinput hook fail: ' + e}); }
}
tryHookDInput();
try {
    Interceptor.attach(Module.getGlobalExportByName('LoadLibraryA'),
        { onLeave: function () { tryHookDInput(); } });
} catch (e) {}

// -------- WH_KEYBOARD_LL blocker --------
var u32 = Process.findModuleByName('user32.dll');
function hookSetWHE(name) {
    try {
        Interceptor.attach(u32.getExportByName(name), {
            onEnter: function (args) {
                var idHook = args[0].toInt32();
                if (idHook === 13) {
                    this.blocked = true;
                    args[0] = ptr(99); // invalid hook type -> real call returns NULL
                }
            },
            onLeave: function (retval) {
                if (this.blocked) {
                    retval.replace(ptr(0xDEADBEEF)); // fake success handle
                    send({h: 'log', msg: 'BLOCKED WH_KEYBOARD_LL install'});
                }
            }
        });
    } catch (e) { send({h: 'log', msg: name + ' hook fail: ' + e}); }
}
if (u32) {
    hookSetWHE('SetWindowsHookExA');
    hookSetWHE('SetWindowsHookExW');
}

rpc.exports = {};
send({h: 'init_done'});
