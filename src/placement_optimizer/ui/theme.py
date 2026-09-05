"""Token-based light and dark styling.

One QSS layer over the Fusion style keeps the treatment consistent between
Windows and macOS. Every color used by custom widgets comes from these tokens
so the whole application follows OS color-scheme changes.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

LIGHT = {
    "window": "#F6F6F4",
    "surface": "#FFFFFF",
    "border": "#E3E1DC",
    "text": "#23251F",
    "secondary": "#6E6B64",
    "accent": "#2F6F5E",
    "accent_text": "#FFFFFF",
    "disabled_text": "#23251F",
    "accent_pressed": "#276050",
    "accent_soft": "#DCE9E4",
    "success": "#2F8F4E",
    "success_bg": "#E4F3E9",
    "warning": "#B5760A",
    "warning_bg": "#FFF4E0",
    "error": "#C23535",
    "error_bg": "#FCECEC",
    "info_bg": "#EDF1F0",
    "alt_row": "#FAFAF8",
    "hover": "#EFEEE9",
    "disabled": "#A9A69E",
}

# Dark tokens keep the same restrained contrast relationships as the light set.
DARK = {
    "window": "#1F201D",
    "surface": "#282925",
    "border": "#3D3E38",
    "text": "#E9E7E1",
    "secondary": "#A8A49B",
    "accent": "#5E9C89",
    "accent_text": "#0B1510",
    "disabled_text": "#FFFFFF",
    "accent_pressed": "#4E8A77",
    "accent_soft": "#31463D",
    "success": "#62AC77",
    "success_bg": "#2A3C2F",
    "warning": "#D89A32",
    "warning_bg": "#40331A",
    "error": "#E08A8A",
    "error_bg": "#422726",
    "info_bg": "#2E3532",
    "alt_row": "#2E2F2A",
    "hover": "#34352F",
    "disabled": "#6B6963",
}


def tokens_for(app: QApplication) -> dict[str, str]:
    scheme = app.styleHints().colorScheme()
    return dict(DARK if scheme is Qt.ColorScheme.Dark else LIGHT)


def apply_theme(app: QApplication) -> None:
    """Apply the token palette and QSS for the current OS color scheme."""

    tokens = tokens_for(app)
    app.setStyle("Fusion")
    app.setPalette(_palette(tokens))
    app.setStyleSheet(_qss(tokens))


def watch_color_scheme(app: QApplication) -> None:
    """Re-apply the theme when the OS switches between light and dark."""

    app.styleHints().colorSchemeChanged.connect(lambda _scheme: apply_theme(app))


def _palette(tokens: dict[str, str]) -> QPalette:
    palette = QPalette()
    window = QColor(tokens["window"])
    surface = QColor(tokens["surface"])
    text = QColor(tokens["text"])
    secondary = QColor(tokens["secondary"])
    accent = QColor(tokens["accent"])

    palette.setColor(QPalette.ColorRole.Window, window)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, surface)
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(tokens["alt_row"]))
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, surface)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.Highlight, accent)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(tokens["accent_text"]))
    palette.setColor(QPalette.ColorRole.ToolTipBase, surface)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.PlaceholderText, secondary)
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(tokens["disabled"])
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.ButtonText,
        QColor(tokens["disabled"]),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.WindowText,
        QColor(tokens["disabled"]),
    )
    return palette


def _qss(t: dict[str, str]) -> str:
    return f"""
QWidget {{
    color: {t["text"]};
    font-size: 11pt;
}}
QMainWindow, QDialog {{
    background: {t["window"]};
}}
QToolTip {{
    background: {t["surface"]};
    color: {t["text"]};
    border: 1px solid {t["border"]};
    padding: 4px 6px;
}}

/* Cards and banners */
QFrame[card="true"] {{
    background: {t["surface"]};
    border: 1px solid {t["border"]};
    border-radius: 8px;
}}
QFrame[banner="success"] {{
    background: {t["success_bg"]};
    border: 1px solid {t["success"]};
    border-radius: 8px;
}}
QFrame[banner="warning"] {{
    background: {t["warning_bg"]};
    border: 1px solid {t["warning"]};
    border-radius: 8px;
}}
QFrame[banner="error"] {{
    background: {t["error_bg"]};
    border: 1px solid {t["error"]};
    border-radius: 8px;
}}
QFrame[banner="info"] {{
    background: {t["info_bg"]};
    border: 1px solid {t["border"]};
    border-radius: 8px;
}}
QFrame[banner] QLabel {{ background: transparent; border: none; }}
QFrame[card="true"] QLabel {{ background: transparent; border: none; }}

/* Buttons */
QPushButton {{
    background: {t["surface"]};
    border: 1px solid {t["border"]};
    border-radius: 6px;
    padding: 5px 14px;
    min-height: 20px;
}}
QPushButton:hover {{ background: {t["hover"]}; }}
QPushButton:focus {{ border: 2px solid {t["accent"]}; }}
QPushButton:disabled {{ color: {t["disabled"]}; background: {t["window"]}; }}
QPushButton[kind="primary"] {{
    background: {t["accent"]};
    color: {t["accent_text"]};
    border: none;
    font-weight: 600;
}}
QPushButton[kind="primary"]:hover {{ background: {t["accent_pressed"]}; }}
QPushButton[kind="primary"]:pressed {{ background: {t["accent_pressed"]}; }}
QPushButton[kind="primary"]:focus {{ border: 2px solid {t["accent_soft"]}; }}
QPushButton[kind="primary"]:checked {{ background: {t["accent_pressed"]}; }}
QPushButton[kind="primary"]:disabled {{
    background: {t["disabled"]}; color: {t["disabled_text"]};
}}
QPushButton[kind="quiet"] {{
    background: transparent;
    border: none;
    color: {t["accent"]};
}}
QPushButton[kind="quiet"]:hover {{ background: {t["hover"]}; }}
QToolButton {{
    background: transparent;
    border: none;
    border-radius: 6px;
    color: {t["accent"]};
    padding: 4px 8px;
}}
QToolButton:hover {{ background: {t["hover"]}; }}
QToolButton:focus {{ border: 2px solid {t["accent"]}; }}

/* Inputs */
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit {{
    background: {t["surface"]};
    border: 1px solid {t["border"]};
    border-radius: 6px;
    padding: 4px 8px;
    selection-background-color: {t["accent_soft"]};
    selection-color: {t["text"]};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus {{
    border: 2px solid {t["accent"]};
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {t["surface"]};
    border: 1px solid {t["border"]};
    selection-background-color: {t["accent_soft"]};
    selection-color: {t["text"]};
    outline: none;
}}

/* Tables */
QTableView {{
    background: {t["surface"]};
    alternate-background-color: {t["alt_row"]};
    border: 1px solid {t["border"]};
    border-radius: 6px;
    selection-background-color: {t["accent_soft"]};
    selection-color: {t["text"]};
}}
QTableView:focus {{ border: 2px solid {t["accent"]}; }}
QTableView::item {{ padding: 2px 6px; border: none; }}
QHeaderView::section {{
    background: {t["surface"]};
    color: {t["secondary"]};
    border: none;
    border-bottom: 1px solid {t["border"]};
    padding: 5px 8px;
    font-weight: 500;
}}
QTableCornerButton::section {{
    background: {t["surface"]};
    border: none;
    border-bottom: 1px solid {t["border"]};
}}

/* Navigation rail */
QListView#stepsRail {{
    background: {t["window"]};
    border: none;
    outline: none;
}}
QListView#stepsRail::item {{
    border-radius: 8px;
    padding: 6px 10px;
    margin: 1px 8px;
}}
QListView#stepsRail::item:selected {{
    background: {t["accent_soft"]};
}}
QListView#stepsRail::item:hover:!selected {{
    background: {t["hover"]};
}}

/* Footer */
QFrame#footer {{
    background: {t["window"]};
    border-top: 1px solid {t["border"]};
}}

/* Menus and misc */
QMenuBar {{ background: {t["window"]}; }}
QMenuBar::item:selected {{ background: {t["hover"]}; }}
QMenu {{
    background: {t["surface"]};
    border: 1px solid {t["border"]};
    padding: 4px;
}}
QMenu::item {{ padding: 5px 24px 5px 16px; border-radius: 4px; }}
QMenu::item:selected {{ background: {t["accent_soft"]}; }}
QMenu::item:disabled {{ color: {t["disabled"]}; }}
QProgressBar {{
    background: {t["window"]};
    border: 1px solid {t["border"]};
    border-radius: 5px;
    text-align: center;
    color: {t["secondary"]};
    min-height: 10px;
}}
QProgressBar::chunk {{ background: {t["accent"]}; border-radius: 4px; }}
QTabBar::tab {{
    background: transparent;
    border: 1px solid {t["border"]};
    border-bottom: none;
    padding: 6px 16px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    color: {t["secondary"]};
}}
QTabBar::tab:selected {{ background: {t["surface"]}; color: {t["text"]}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar::handle:vertical {{
    background: {t["border"]};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {t["secondary"]}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle:horizontal {{
    background: {t["border"]};
    border-radius: 5px;
    min-width: 30px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QCheckBox, QRadioButton {{ spacing: 8px; background: transparent; }}
QCheckBox:focus, QRadioButton:focus {{ outline: none; }}
QLabel[role="title"] {{ font-size: 15pt; font-weight: 600; }}
QLabel[role="stat"] {{ font-size: 17pt; font-weight: 600; }}
QLabel[role="secondary"] {{ color: {t["secondary"]}; font-size: 10pt; }}
QLabel[role="heading"] {{ font-weight: 600; }}
"""
