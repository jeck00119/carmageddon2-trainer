#!/usr/bin/env python3
"""Carmageddon 2 trainer — entry point."""
import os
import sys

# Make sibling packages importable.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow
from ui.style import QSS


def main():
    safe_mode = '--safe' in sys.argv
    if safe_mode:
        print('[trainer] *** SAFE MODE — all hooks disabled, only snap/RPC ***',
              file=sys.stderr, flush=True)

    app = QApplication(sys.argv)
    app.setApplicationName('Carma2 Trainer')
    app.setStyle('Fusion')
    app.setStyleSheet(QSS)
    win = MainWindow(safe_mode=safe_mode)
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
