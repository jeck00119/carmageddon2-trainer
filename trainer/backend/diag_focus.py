#!/usr/bin/env python3
"""
Focus diagnostic — log every window-state-related Win32 call.

Kept as a reference template for future window/focus debugging. The
findings from this script are baked into agent.js (no-minimize WndProc
subclass). Use this to investigate new focus/window-state issues.

Hooks: SetWindowPos, MoveWindow, SetWindowPlacement, ShowWindow, CloseWindow,
OpenIcon, SetForegroundWindow, SetActiveWindow, SetFocus, ChangeDisplaySettings*

Usage:
    1. Start the game from the trainer.
    2. py -3 diag_focus.py
    3. Reproduce the focus/window event you want to investigate.
    4. Ctrl+C, read the log.
"""
import os
import sys
import time
import frida

GAME_PROC = 'carma2_hw.exe'

SCRIPT = r"""
function logCall(name, args, fmt) {
    send({h: 'call', name: name, args: fmt(args), bt: ''});
}

function btShort() {
    try {
        return Thread.backtrace(this.context, Backtracer.ACCURATE)
            .slice(0, 5)
            .map(DebugSymbol.fromAddress).map(String).join(' | ');
    } catch (e) { return ''; }
}

var u32 = Process.getModuleByName('user32.dll');

function attachLog(name, parser) {
    try {
        var fn = u32.getExportByName(name);
        Interceptor.attach(fn, {
            onEnter: function (args) {
                var info = parser(args);
                send({h: 'call', name: name, info: info});
            }
        });
    } catch (e) {
        send({h: 'err', msg: name + ': ' + e});
    }
}

attachLog('ShowWindow', function (args) {
    return {hwnd: args[0].toString(), nCmdShow: args[1].toInt32()};
});
attachLog('SetWindowPos', function (args) {
    return {
        hwnd: args[0].toString(),
        after: args[1].toInt32(),
        x: args[2].toInt32(), y: args[3].toInt32(),
        cx: args[4].toInt32(), cy: args[5].toInt32(),
        flags: '0x' + args[6].toInt32().toString(16),
    };
});
attachLog('MoveWindow', function (args) {
    return {
        hwnd: args[0].toString(),
        x: args[1].toInt32(), y: args[2].toInt32(),
        w: args[3].toInt32(), h: args[4].toInt32(),
        repaint: args[5].toInt32(),
    };
});
attachLog('SetWindowPlacement', function (args) {
    var p = args[1];
    try {
        var flags = p.add(4).readU32();
        var showCmd = p.add(8).readU32();
        var rectL = p.add(28).readU32();
        var rectT = p.add(32).readU32();
        var rectR = p.add(36).readU32();
        var rectB = p.add(40).readU32();
        return {hwnd: args[0].toString(), flags: flags, showCmd: showCmd,
                rect: [rectL, rectT, rectR, rectB]};
    } catch (e) { return {err: '' + e}; }
});
attachLog('SetForegroundWindow', function (args) {
    return {hwnd: args[0].toString()};
});
attachLog('SetActiveWindow', function (args) {
    return {hwnd: args[0].toString()};
});
attachLog('SetFocus', function (args) {
    return {hwnd: args[0].toString()};
});
attachLog('CloseWindow', function (args) {
    return {hwnd: args[0].toString()};
});
attachLog('OpenIcon', function (args) {
    return {hwnd: args[0].toString()};
});
attachLog('ChangeDisplaySettingsA', function (args) {
    return {devmode: args[0].toString(), flags: '0x' + args[1].toInt32().toString(16)};
});
attachLog('ChangeDisplaySettingsExA', function (args) {
    return {devname: args[0].toString(), devmode: args[1].toString(),
            flags: '0x' + args[3].toInt32().toString(16)};
});

send({h: 'init', msg: 'hooks installed'});
"""


def main():
    device = frida.get_local_device()
    pid = None
    for p in device.enumerate_processes():
        if p.name.lower() == GAME_PROC:
            pid = p.pid
            break
    if pid is None:
        print(f'{GAME_PROC} not running. Start it from the trainer first.')
        return 1

    print(f'attaching to pid {pid}...')
    session = device.attach(pid)
    script = session.create_script(SCRIPT)

    def on_msg(msg, data):
        if msg.get('type') == 'send':
            p = msg['payload']
            if p.get('h') == 'init':
                print(f'[init] {p["msg"]}')
            elif p.get('h') == 'err':
                print(f'[err]  {p["msg"]}')
            elif p.get('h') == 'call':
                ts = time.strftime('%H:%M:%S')
                print(f'[{ts}] {p["name"]:24s} {p["info"]}')
        elif msg.get('type') == 'error':
            print(f'[script err] {msg.get("description")}')

    script.on('message', on_msg)
    script.load()
    print('hooks loaded. Now alt-tab away from the game and back.')
    print('Ctrl+C to stop.')
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    session.detach()
    return 0


if __name__ == '__main__':
    sys.exit(main())
