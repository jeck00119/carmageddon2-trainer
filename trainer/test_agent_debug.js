// test_agent_debug.js — full diagnostic agent for Alt+Tab debugging.
// Hooks EVERYTHING that could suppress system hotkeys and logs it all.
//
// What this agent does:
// 1. Installs OUR OWN WH_KEYBOARD_LL hook to see what keys flow through
// 2. Logs EVERY SetWindowsHookEx call (not just block — log ALL types)
// 3. Hooks RegisterRawInputDevices — RIDEV_NOHOTKEYS suppresses system keys
// 4. Hooks IDirectDraw::SetCooperativeLevel via COM vtable
// 5. Hooks IDirectDraw7::SetCooperativeLevel via COM vtable
// 6. Hooks DInput SetCooperativeLevel (and rewrites to non-exclusive)
// 7. Hooks RegisterHotKey — games can register Alt+Tab as a hotkey
// 8. Hooks SystemParametersInfo — can disable system keys
// 9. Logs WM_SYSKEYDOWN/WM_KEYDOWN/WM_ACTIVATE/WM_KILLFOCUS via DispatchMessage
// 10. Blocks WH_KEYBOARD_LL from DInput (same as before)

'use strict';

function emit(kind, data) {
    try { send({h: 'ev', kind: kind, data: data, t: Date.now()}); } catch (e) {}
}
function log(msg) { try { send({h: 'log', msg: msg}); } catch (e) {} }

var u32 = Process.findModuleByName('user32.dll');
var k32 = Process.findModuleByName('kernel32.dll');

// =========================================================================
// 1. OUR OWN WH_KEYBOARD_LL hook — see every keystroke at the LL level
// =========================================================================
var ourLLHook = null;
if (u32) {
    try {
        var SetWindowsHookExA = new NativeFunction(u32.getExportByName('SetWindowsHookExA'),
            'pointer', ['int', 'pointer', 'pointer', 'uint32'], 'stdcall');
        var CallNextHookEx = new NativeFunction(u32.getExportByName('CallNextHookEx'),
            'pointer', ['pointer', 'pointer', 'uint32', 'pointer'], 'stdcall');
        var GetKeyState = new NativeFunction(u32.getExportByName('GetKeyState'),
            'int16', ['int'], 'stdcall');

        var VK_NAMES = {};
        VK_NAMES[0x09] = 'TAB';
        VK_NAMES[0x0D] = 'ENTER';
        VK_NAMES[0x12] = 'ALT';
        VK_NAMES[0x1B] = 'ESC';
        VK_NAMES[0x5B] = 'LWIN';
        VK_NAMES[0x5C] = 'RWIN';
        VK_NAMES[0x70] = 'F1'; VK_NAMES[0x71] = 'F2'; VK_NAMES[0x72] = 'F3';
        VK_NAMES[0x73] = 'F4'; VK_NAMES[0x74] = 'F5';

        // Our LL keyboard hook proc: log everything, pass through
        var llProc = new NativeCallback(function (nCode, wParam, lParam) {
            if (nCode >= 0) {
                try {
                    var vkCode = lParam.readU32();
                    var scanCode = lParam.add(4).readU32();
                    var flags = lParam.add(8).readU32();
                    var vkName = VK_NAMES[vkCode] || ('0x' + vkCode.toString(16));
                    var altDown = (GetKeyState(0x12) & 0x8000) !== 0;
                    var action = (wParam.toUInt32() === 0x100 || wParam.toUInt32() === 0x104) ? 'DOWN' : 'UP';

                    // Log system-key combos and interesting keys
                    if (vkCode === 0x09 || vkCode === 0x5B || vkCode === 0x5C ||
                        vkCode === 0x12 || vkCode === 0x0D || vkCode === 0x1B ||
                        altDown) {
                        emit('LL_KEY', {
                            vk: vkName,
                            vkCode: '0x' + vkCode.toString(16),
                            action: action,
                            altDown: altDown,
                            flags: '0x' + flags.toString(16),
                            combo: altDown && vkCode === 0x09 ? 'ALT+TAB!' :
                                   altDown && vkCode === 0x0D ? 'ALT+ENTER' :
                                   vkCode === 0x5B ? 'WIN_KEY' : ''
                        });
                    }
                } catch (e) {}
            }
            return CallNextHookEx(ourLLHook, ptr(nCode >= 0 ? nCode : 0), wParam, lParam);
        }, 'pointer', ['int', 'pointer', 'pointer'], 'stdcall');

        ourLLHook = SetWindowsHookExA(13, llProc, ptr(0), 0);
        if (ourLLHook && !ourLLHook.isNull()) {
            log('OUR WH_KEYBOARD_LL hook installed: handle=' + ourLLHook);
        } else {
            log('FAILED to install our WH_KEYBOARD_LL hook!');
        }
    } catch (e) { log('LL hook setup error: ' + e); }
}

// =========================================================================
// 2. Log ALL SetWindowsHookEx calls + block DInput's WH_KEYBOARD_LL
// =========================================================================
var HOOK_NAMES = {
    0: 'WH_JOURNALRECORD', 1: 'WH_JOURNALPLAYBACK', 2: 'WH_KEYBOARD',
    3: 'WH_GETMESSAGE', 4: 'WH_CALLWNDPROC', 5: 'WH_CBT',
    6: 'WH_SYSMSGFILTER', 7: 'WH_MOUSE', 8: 'WH_HARDWARE',
    9: 'WH_DEBUG', 10: 'WH_SHELL', 11: 'WH_FOREGROUNDIDLE',
    12: 'WH_CALLWNDPROCRET', 13: 'WH_KEYBOARD_LL', 14: 'WH_MOUSE_LL'
};

function hookSetWHE(name) {
    try {
        Interceptor.attach(u32.getExportByName(name), {
            onEnter: function (args) {
                var idHook = args[0].toInt32();
                var proc = args[1];
                var hMod = args[2];
                var tid = args[3].toUInt32();
                var hookName = HOOK_NAMES[idHook] || ('type_' + idHook);
                var mod = null;
                try { mod = Process.findModuleByAddress(proc); } catch (e) {}
                var modName = mod ? mod.name : 'unknown';

                emit('SetWindowsHookEx', {
                    api: name,
                    type: hookName,
                    typeId: idHook,
                    proc: proc.toString(),
                    procModule: modName,
                    hMod: hMod.toString(),
                    tid: tid,
                });

                // Block WH_KEYBOARD_LL from anyone except ourselves
                if (idHook === 13 && proc.toString() !== llProc.toString()) {
                    this.blocked = true;
                    args[0] = ptr(99);
                }
            },
            onLeave: function (retval) {
                if (this.blocked) {
                    retval.replace(ptr(0xDEADBEEF));
                    log('BLOCKED external WH_KEYBOARD_LL install');
                }
            }
        });
    } catch (e) { log(name + ' hook fail: ' + e); }
}
if (u32) {
    hookSetWHE('SetWindowsHookExA');
    hookSetWHE('SetWindowsHookExW');
}

// =========================================================================
// 3. RegisterRawInputDevices — RIDEV_NOHOTKEYS (0x200) suppresses Alt+Tab
// =========================================================================
if (u32) {
    try {
        Interceptor.attach(u32.getExportByName('RegisterRawInputDevices'), {
            onEnter: function (args) {
                var pDevices = args[0];
                var numDevices = args[1].toUInt32();
                for (var i = 0; i < numDevices && i < 10; i++) {
                    var base = pDevices.add(i * 12); // sizeof(RAWINPUTDEVICE) = 12 on x86
                    var usagePage = base.readU16();
                    var usage = base.add(2).readU16();
                    var flags = base.add(4).readU32();
                    var hwnd = base.add(8).readPointer();

                    var flagNames = [];
                    if (flags & 0x01) flagNames.push('RIDEV_REMOVE');
                    if (flags & 0x10) flagNames.push('RIDEV_EXCLUDE');
                    if (flags & 0x20) flagNames.push('RIDEV_PAGEONLY');
                    if (flags & 0x100) flagNames.push('RIDEV_NOLEGACY');
                    if (flags & 0x200) flagNames.push('RIDEV_NOHOTKEYS');
                    if (flags & 0x400) flagNames.push('RIDEV_APPKEYS');
                    if (flags & 0x1000) flagNames.push('RIDEV_CAPTUREMOUSE');
                    if (flags & 0x2000) flagNames.push('RIDEV_INPUTSINK');
                    if (flags & 0x4000) flagNames.push('RIDEV_DEVNOTIFY');
                    if (flags & 0x8000) flagNames.push('RIDEV_EXINPUTSINK');

                    emit('RegisterRawInputDevices', {
                        idx: i,
                        usagePage: '0x' + usagePage.toString(16),
                        usage: '0x' + usage.toString(16),
                        flags: '0x' + flags.toString(16),
                        flagNames: flagNames.join('|') || 'none',
                        hwnd: hwnd.toString(),
                        NOHOTKEYS: !!(flags & 0x200),
                    });

                    // STRIP RIDEV_NOHOTKEYS if present
                    if (flags & 0x200) {
                        var newFlags = flags & ~0x200;
                        base.add(4).writeU32(newFlags);
                        log('STRIPPED RIDEV_NOHOTKEYS from RegisterRawInputDevices!');
                    }
                }
            }
        });
    } catch (e) { log('RegisterRawInputDevices hook fail: ' + e); }
}

// =========================================================================
// 4. DirectDraw SetCooperativeLevel via COM vtable hook
// =========================================================================
function hookDDrawCoopLevel() {
    var dd = Process.findModuleByName('ddraw.dll');
    if (!dd) return;
    // Hook DirectDrawCreate to get the IDirectDraw pointer
    try {
        var DDCreate = dd.getExportByName('DirectDrawCreate');
        Interceptor.attach(DDCreate, {
            onEnter: function (args) { this.ppDD = args[1]; },
            onLeave: function (retval) {
                if (retval.toInt32() !== 0 || !this.ppDD) return;
                try {
                    var ddObj = this.ppDD.readPointer();
                    // IDirectDraw vtable: SetCooperativeLevel is at index 20
                    var vtbl = ddObj.readPointer();
                    var setCoopVA = vtbl.add(20 * 4).readPointer();
                    Interceptor.attach(setCoopVA, {
                        onEnter: function (args) {
                            var hwnd = args[1];
                            var flags = args[2].toUInt32();
                            var flagNames = [];
                            if (flags & 0x01) flagNames.push('DDSCL_FULLSCREEN');
                            if (flags & 0x08) flagNames.push('DDSCL_ALLOWREBOOT');
                            if (flags & 0x10) flagNames.push('DDSCL_EXCLUSIVE');
                            if (flags & 0x20) flagNames.push('DDSCL_ALLOWMODEX');
                            if (flags & 0x40) flagNames.push('DDSCL_SETFOCUSWINDOW');
                            if (flags & 0x80) flagNames.push('DDSCL_SETDEVICEWINDOW');
                            if (flags & 0x100) flagNames.push('DDSCL_CREATEDEVICEWINDOW');
                            if (flags & 0x800) flagNames.push('DDSCL_NORMAL');
                            if (flags & 0x2000) flagNames.push('DDSCL_FPUSETUP');
                            if (flags & 0x4000) flagNames.push('DDSCL_FPUPRESERVE');
                            emit('DDraw_SetCooperativeLevel', {
                                hwnd: hwnd.toString(),
                                flags: '0x' + flags.toString(16),
                                flagNames: flagNames.join('|') || 'raw',
                                EXCLUSIVE: !!(flags & 0x10),
                            });
                        }
                    });
                    log('DDraw SetCooperativeLevel vtable hook installed');
                } catch (e) { log('DDraw vtable hook fail: ' + e); }
            }
        });
    } catch (e) { log('DirectDrawCreate hook fail: ' + e); }
}

// =========================================================================
// 5. RegisterHotKey — can claim system hotkeys
// =========================================================================
if (u32) {
    try {
        Interceptor.attach(u32.getExportByName('RegisterHotKey'), {
            onEnter: function (args) {
                var hwnd = args[0];
                var id = args[1].toUInt32();
                var modifiers = args[2].toUInt32();
                var vk = args[3].toUInt32();
                var modNames = [];
                if (modifiers & 1) modNames.push('ALT');
                if (modifiers & 2) modNames.push('CTRL');
                if (modifiers & 4) modNames.push('SHIFT');
                if (modifiers & 8) modNames.push('WIN');
                emit('RegisterHotKey', {
                    hwnd: hwnd.toString(),
                    id: id,
                    modifiers: modNames.join('+') || 'none',
                    vk: '0x' + vk.toString(16),
                    vkName: VK_NAMES[vk] || '?',
                });
            }
        });
    } catch (e) {}
}

// =========================================================================
// 6. SystemParametersInfo — can suppress system keys
// =========================================================================
if (u32) {
    try {
        Interceptor.attach(u32.getExportByName('SystemParametersInfoA'), {
            onEnter: function (args) {
                var action = args[0].toUInt32();
                // SPI_SETFOREGROUNDLOCKTIMEOUT = 0x2001
                // SPI_SETSCREENSAVERRUNNING = 0x0061 (disables Ctrl+Alt+Del on old Win)
                if (action === 0x2001 || action === 0x0061 || action === 0x0097) {
                    emit('SystemParametersInfo', {
                        action: '0x' + action.toString(16),
                        uiParam: args[1].toUInt32(),
                        pvParam: args[2].toString(),
                    });
                }
            }
        });
    } catch (e) {}
}

// =========================================================================
// 7. DInput SetCooperativeLevel (same fix as before + logging)
// =========================================================================
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
                                var oldFlags = args[2].toUInt32();
                                var flagNames = [];
                                if (oldFlags & 1) flagNames.push('DISCL_EXCLUSIVE');
                                if (oldFlags & 2) flagNames.push('DISCL_NONEXCLUSIVE');
                                if (oldFlags & 4) flagNames.push('DISCL_FOREGROUND');
                                if (oldFlags & 8) flagNames.push('DISCL_BACKGROUND');
                                if (oldFlags & 0x10) flagNames.push('DISCL_NOWINKEY');
                                emit('DInput_SetCooperativeLevel', {
                                    original: '0x' + oldFlags.toString(16),
                                    flagNames: flagNames.join('|'),
                                    NOWINKEY: !!(oldFlags & 0x10),
                                    rewritten: 'NONEXCLUSIVE|BACKGROUND',
                                });
                                args[2] = ptr(2 | 8); // NONEXCLUSIVE|BACKGROUND
                            }
                        });
                    }
                });
            }
        });
        dinputHooked = true;
        log('DInput hook chain installed');
    } catch (e) { log('DInput hook fail: ' + e); }
}
tryHookDInput();
try {
    Interceptor.attach(k32.getExportByName('LoadLibraryA'), {
        onLeave: function () {
            tryHookDInput();
            hookDDrawCoopLevel();
        }
    });
} catch (e) {}

// =========================================================================
// 8. Message dispatch logging (focus + keys only)
// =========================================================================
var MSG_NAMES = {
    0x0006: 'WM_ACTIVATE', 0x0007: 'WM_SETFOCUS', 0x0008: 'WM_KILLFOCUS',
    0x001C: 'WM_ACTIVATEAPP', 0x0086: 'WM_NCACTIVATE',
    0x0100: 'WM_KEYDOWN', 0x0101: 'WM_KEYUP',
    0x0104: 'WM_SYSKEYDOWN', 0x0105: 'WM_SYSKEYUP',
};
if (u32) {
    ['DispatchMessageA', 'DispatchMessageW'].forEach(function (name) {
        try {
            Interceptor.attach(u32.getExportByName(name), {
                onEnter: function (args) {
                    try {
                        var p = args[0];
                        var msg = p.add(4).readU32();
                        if (MSG_NAMES[msg]) {
                            var wp = p.add(8).readU32();
                            var lp = p.add(12).readU32();
                            emit('WndMsg', {
                                src: name,
                                msg: MSG_NAMES[msg],
                                wp: '0x' + wp.toString(16),
                                lp: '0x' + lp.toString(16),
                            });
                        }
                    } catch (e) {}
                }
            });
        } catch (e) {}
    });
}

// =========================================================================
// 9. Also try hooking DDraw cooperative level immediately (if ddraw already loaded)
// =========================================================================
hookDDrawCoopLevel();

rpc.exports = {};
send({h: 'init_done'});
log('debug agent fully loaded pid=' + Process.id);
