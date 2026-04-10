"""Modern dark theme stylesheet for the Carma2 trainer."""

# Palette
BG          = '#1e1f22'
BG_ALT      = '#2b2d30'
BG_ELEV     = '#363a3f'
BORDER      = '#3e4147'
TEXT        = '#e6e6e6'
TEXT_DIM    = '#9aa0a6'
ACCENT      = '#e8503a'   # Carma red
ACCENT_HOV  = '#ff6b52'
ACCENT_DOWN = '#c93c25'
GOOD        = '#4ec27a'
WARN        = '#e0b341'
BAD         = '#e85050'

QSS = f"""
* {{
    color: {TEXT};
    font-family: 'Segoe UI', 'Inter', sans-serif;
    font-size: 10pt;
}}

QMainWindow, QWidget {{
    background-color: {BG};
}}

QLabel {{
    background: transparent;
}}

QLabel#title {{
    font-size: 14pt;
    font-weight: 600;
    color: {ACCENT};
}}

/* ---------- Tabs ---------- */
QTabWidget::pane {{
    border: 1px solid {BORDER};
    background: {BG_ALT};
    border-radius: 6px;
    top: -1px;
}}

QTabBar {{
    background: transparent;
}}

QTabBar::tab {{
    background: {BG};
    color: {TEXT_DIM};
    padding: 10px 22px;
    margin-right: 2px;
    border: 1px solid {BORDER};
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: 500;
}}

QTabBar::tab:hover {{
    background: {BG_ELEV};
    color: {TEXT};
}}

QTabBar::tab:selected {{
    background: {BG_ALT};
    color: {ACCENT};
    border-bottom: 2px solid {ACCENT};
}}

/* ---------- Group boxes ---------- */
QGroupBox {{
    background: {BG_ALT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 14px;
    font-weight: 600;
    color: {TEXT_DIM};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    background: {BG_ALT};
}}

/* ---------- Buttons ---------- */
QPushButton {{
    background: {BG_ELEV};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 14px;
    font-weight: 500;
}}

QPushButton:hover {{
    background: #444850;
    border-color: {ACCENT};
}}

QPushButton:pressed {{
    background: {ACCENT_DOWN};
    color: white;
    border-color: {ACCENT_DOWN};
}}

QPushButton:disabled {{
    background: {BG_ALT};
    color: #555;
    border-color: {BG_ALT};
}}

QPushButton#primary {{
    background: {ACCENT};
    color: white;
    border: none;
    font-weight: 600;
}}

QPushButton#primary:hover {{
    background: {ACCENT_HOV};
}}

QPushButton#primary:pressed {{
    background: {ACCENT_DOWN};
}}

QPushButton#unnamed {{
    color: {WARN};
    font-style: italic;
}}

QPushButton[pinned="true"] {{
    border: 2px solid {ACCENT};
}}

QPushButton#unnamed[pinned="true"] {{
    border: 2px solid {ACCENT};
    color: {WARN};
    font-style: italic;
}}

/* ---------- Inputs ---------- */
QLineEdit {{
    background: {BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 12px;
    selection-background-color: {ACCENT};
}}

QLineEdit:focus {{
    border-color: {ACCENT};
}}

/* ---------- Tables ---------- */
QTableWidget {{
    background: {BG};
    alternate-background-color: {BG_ALT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    gridline-color: {BORDER};
    selection-background-color: {ACCENT};
    selection-color: white;
}}

QTableWidget::item {{
    padding: 6px;
    border: none;
}}

QHeaderView::section {{
    background: {BG_ELEV};
    color: {TEXT_DIM};
    padding: 8px 10px;
    border: none;
    border-right: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER};
    font-weight: 600;
}}

/* ---------- Scroll area / scrollbar ---------- */
QScrollArea {{
    background: transparent;
    border: none;
}}

QScrollBar:vertical {{
    background: {BG};
    width: 12px;
    border: none;
}}

QScrollBar::handle:vertical {{
    background: {BG_ELEV};
    border-radius: 6px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background: #4a4e55;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: {BG};
    height: 12px;
    border: none;
}}

QScrollBar::handle:horizontal {{
    background: {BG_ELEV};
    border-radius: 6px;
    min-width: 30px;
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ---------- Status bar ---------- */
QStatusBar {{
    background: {BG_ALT};
    color: {TEXT_DIM};
    border-top: 1px solid {BORDER};
}}

QStatusBar::item {{
    border: none;
}}
"""
