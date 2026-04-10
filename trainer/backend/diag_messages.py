#!/usr/bin/env python3
"""
Message-flow diagnostic — log every activation-related Win32 message.

Kept as a reference template for future Win32-message debugging. The
findings from this script revealed that activation messages bypass the
queue (kernel SendMessage path), which is why the no-minimize fix in
agent.js subclasses the WndProc instead of filtering PeekMessage.

Hooks:
  PeekMessageA/W, GetMessageA/W      — msgs delivered from the queue
  DispatchMessageA/W                 — msgs dispatched to wndproc
  SendMessageA/W                     — synchronous delivery (bypasses queue)
  CallWindowProcA/W                  — wndproc chains
  DefWindowProcA/W                   — fallback handler
  ShowWindow / CloseWindow           — minimize calls

Usage:
    1. Start the game from the trainer.
    2. py -3 diag_messages.py
    3. Reproduce the message-flow event you want to investigate.
    4. Ctrl+C, read the log.
"""
import sys
import time
import frida

GAME_PROC = 'carma2_hw.exe'

# Message IDs of interest
WM_NAMES = {
    0x0006: 'WM_ACTIVATE',
    0x0007: 'WM_SETFOCUS',
    0x0008: 'WM_KILLFOCUS',
    0x001C: 'WM_ACTIVATEAPP',
    0x0086: 'WM_NCACTIVATE',
    0x0018: 'WM_SHOWWINDOW',
    0x0046: 'WM_WINDOWPOSCHANGING',
    0x0047: 'WM_WINDOWPOSCHANGED',
    0x0024: 'WM_GETMINMAXINFO',
    0x0112: 'WM_SYSCOMMAND',
}

SCRIPT = r"""
var WM_NAMES = %s;
var INTERESTING = {};
Object.keys(WM_NAMES).forEach(function (k) { INTERESTING[parseInt(k)] = WM_NAMES[k]; });

function fmtMsg(lpMsg) {
    if (lpMsg.isNull()) return null;
    try {
        var hwnd = lpMsg.readPointer();
        var msg  = lpMsg.add(4).readU32();
        var wp   = lpMsg.add(8).readU32();
        var lp   = lpMsg.add(12).readU32();
        return {hwnd: hwnd.toString(), msg: msg, wp: wp, lp: lp,
                name: INTERESTING[msg] || null};
    } catch (e) { return null; }
}

var u32 = Process.getModuleByName('user32.dll');

// PeekMessage / GetMessage — log activation msgs delivered from queue
['PeekMessageA','PeekMessageW','GetMessageA','GetMessageW'].forEach(function (name) {
    try {
        Interceptor.attach(u32.getExportByName(name), {
            onEnter: function (args) { this.lpMsg = args[0]; },
            onLeave: function (retval) {
                if (retval.toInt32() === 0) return;
                var m = fmtMsg(this.lpMsg);
                if (m && m.name) {
                    send({h: 'queue', api: name, msg: m});
                }
            }
        });
    } catch (e) { send({h: 'err', name: name, e: '' + e}); }
});

// SendMessage — synchronous delivery, bypasses the queue
['SendMessageA','SendMessageW'].forEach(function (name) {
    try {
        Interceptor.attach(u32.getExportByName(name), {
            onEnter: function (args) {
                var m = args[1].toInt32();
                if (INTERESTING[m]) {
                    send({h: 'send', api: name, hwnd: args[0].toString(),
                          msg: m, name: INTERESTING[m],
                          wp: args[2].toInt32(), lp: args[3].toInt32()});
                }
            }
        });
    } catch (e) { send({h: 'err', name: name, e: '' + e}); }
});

// DispatchMessage — what the game's pump is actually feeding to wndprocs
['DispatchMessageA','DispatchMessageW'].forEach(function (name) {
    try {
        Interceptor.attach(u32.getExportByName(name), {
            onEnter: function (args) {
                var m = fmtMsg(args[0]);
                if (m && m.name) {
                    send({h: 'dispatch', api: name, msg: m});
                }
            }
        });
    } catch (e) { send({h: 'err', name: name, e: '' + e}); }
});

// CallWindowProc / DefWindowProc — wndproc-level
['CallWindowProcA','CallWindowProcW','DefWindowProcA','DefWindowProcW'].forEach(function (name) {
    try {
        Interceptor.attach(u32.getExportByName(name), {
            onEnter: function (args) {
                var m;
                if (name.indexOf('Call') === 0) m = args[2].toInt32();
                else m = args[1].toInt32();
                if (INTERESTING[m]) {
                    send({h: 'wndproc', api: name, msg: m, name: INTERESTING[m]});
                }
            }
        });
    } catch (e) { send({h: 'err', name: name, e: '' + e}); }
});

// ShowWindow — direct minimize calls
try {
    Interceptor.attach(u32.getExportByName('ShowWindow'), {
        onEnter: function (args) {
            send({h: 'show', hwnd: args[0].toString(), nCmdShow: args[1].toInt32()});
        }
    });
} catch (e) { send({h: 'err', name: 'ShowWindow', e: '' + e}); }

// CloseWindow — also minimizes
try {
    Interceptor.attach(u32.getExportByName('CloseWindow'), {
        onEnter: function (args) { send({h: 'closewin', hwnd: args[0].toString()}); }
    });
} catch (e) { send({h: 'err', name: 'CloseWindow', e: '' + e}); }

send({h: 'init'});
""" % (str({hex(k): v for k, v in WM_NAMES.items()}).replace("'", '"'))


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
            ts = time.strftime('%H:%M:%S')
            h = p.get('h')
            if h == 'init':
                print(f'[{ts}] [init] hooks installed')
            elif h == 'err':
                print(f'[{ts}] [err]  {p["name"]}: {p["e"]}')
            elif h == 'queue':
                m = p['msg']
                print(f'[{ts}] queue/{p["api"]:13s} {m["name"]:18s} hwnd={m["hwnd"]} wp={m["wp"]} lp={m["lp"]}')
            elif h == 'send':
                print(f'[{ts}] send/ {p["api"]:13s} {p["name"]:18s} hwnd={p["hwnd"]} wp={p["wp"]} lp={p["lp"]}')
            elif h == 'dispatch':
                m = p['msg']
                print(f'[{ts}] disp/ {p["api"]:13s} {m["name"]:18s} hwnd={m["hwnd"]} wp={m["wp"]}')
            elif h == 'wndproc':
                print(f'[{ts}] wndp/ {p["api"]:13s} {p["name"]:18s}')
            elif h == 'show':
                print(f'[{ts}] ShowWindow         nCmdShow={p["nCmdShow"]}  hwnd={p["hwnd"]}')
            elif h == 'closewin':
                print(f'[{ts}] CloseWindow        hwnd={p["hwnd"]}')
        elif msg.get('type') == 'error':
            print(f'[script err] {msg.get("description")}')

    script.on('message', on_msg)
    script.load()
    print('hooks loaded. Now alt-tab away from the game and watch.')
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
