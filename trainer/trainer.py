#!/usr/bin/env python3
"""Carmageddon 2 trainer — entry point."""
import os
import sys
import traceback

# Make sibling packages importable.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


def main():
    print('[trainer] === Carmageddon 2 Trainer starting ===', file=sys.stderr, flush=True)
    print(f'[trainer] Python {sys.version}', file=sys.stderr, flush=True)
    print(f'[trainer] cwd={os.getcwd()}', file=sys.stderr, flush=True)
    print(f'[trainer] argv={sys.argv}', file=sys.stderr, flush=True)

    safe_mode = '--safe' in sys.argv
    if safe_mode:
        print('[trainer] *** SAFE MODE — all hooks disabled, only snap/RPC ***',
              file=sys.stderr, flush=True)

    try:
        from PySide6.QtWidgets import QApplication
        from ui.main_window import MainWindow
        from ui.style import QSS
    except ImportError as e:
        print(f'[trainer] FATAL import error: {e}', file=sys.stderr, flush=True)
        print('[trainer] Install deps: pip install frida PySide6', file=sys.stderr, flush=True)
        sys.exit(1)

    try:
        app = QApplication(sys.argv)
        app.setApplicationName('Carma2 Trainer')
        app.setStyle('Fusion')
        app.setStyleSheet(QSS)
        win = MainWindow(safe_mode=safe_mode)
        win.show()
        print('[trainer] window shown — entering event loop', file=sys.stderr, flush=True)
        sys.exit(app.exec())
    except Exception:
        print('[trainer] FATAL unhandled exception:', file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
