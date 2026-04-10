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
    try:
        from PySide6.QtWidgets import QApplication
        from ui.main_window import MainWindow
        from ui.style import QSS
    except ImportError as e:
        print(f'FATAL: {e}\nInstall deps: pip install frida PySide6',
              file=sys.stderr, flush=True)
        sys.exit(1)

    try:
        app = QApplication(sys.argv)
        app.setApplicationName('Carma2 Trainer')
        app.setStyle('Fusion')
        app.setStyleSheet(QSS)
        win = MainWindow()
        win.show()
        sys.exit(app.exec())
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
