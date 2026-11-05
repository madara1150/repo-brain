"""Look and feel: light theme, Thai-friendly font."""
import os
import sys

ACCENT = "#4f46e5"
ACCENT_DARK = "#4338ca"
TEXT = "#111827"
MUTED = "#6b7280"
BORDER = "#e5e7eb"
BG = "#f6f7fb"
CARD = "#ffffff"
OK = "#059669"
WARN = "#d97706"
BAD = "#dc2626"


def resource(*parts) -> str:
    base = getattr(sys, "_MEIPASS", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
    return os.path.join(base, *parts)


def load_fonts() -> str:
    from PySide6.QtGui import QFontDatabase
    family = ""
    for name in ("IBMPlexSansThai-Regular.ttf", "IBMPlexSansThai-Bold.ttf"):
        fid = QFontDatabase.addApplicationFont(resource("assets", "fonts", name))
        if fid >= 0 and not family:
            family = (QFontDatabase.applicationFontFamilies(fid) or [""])[0]
    return family or "Sans Serif"


def stylesheet(family: str) -> str:
    chevron = resource("assets", "chevron.svg").replace("\\", "/")
    return f"""
* {{ font-family: "{family}"; font-size: 13px; color: {TEXT}; }}
QMainWindow, QDialog {{ background: {BG}; }}
QWidget#central {{ background: {BG}; }}
QLabel#title {{ font-size: 22px; font-weight: 700; }}
QLabel#subtitle {{ color: {MUTED}; font-size: 13px; }}
QLabel#hint, QLabel.hint {{ color: {MUTED}; }}
QLabel#sectionTitle {{ font-size: 16px; font-weight: 700; }}
QFrame#card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; }}
QFrame#updateBanner {{ background: #eef2ff; border: 1px solid #c7d2fe; border-radius: 12px; }}
QFrame#updateBar {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; padding: 9px 16px; margin-right: 4px; border-radius: 8px;
               color: {MUTED}; font-weight: 600; }}
QTabBar::tab:selected {{ background: {CARD}; color: {ACCENT}; border: 1px solid {BORDER}; }}
QTabBar::tab:hover:!selected {{ color: {TEXT}; }}
QPushButton {{ background: {CARD}; border: 1px solid #d1d5db; border-radius: 8px; padding: 7px 14px; font-weight: 600; }}
QPushButton:hover {{ background: #f3f4f6; }}
QPushButton:disabled {{ color: #9ca3af; background: #f9fafb; }}
QPushButton#primary {{ background: {ACCENT}; color: white; border: none; padding: 9px 22px; font-size: 14px; }}
QPushButton#primary:hover {{ background: {ACCENT_DARK}; }}
QPushButton#primary:disabled {{ background: #a5b4fc; color: #eef2ff; }}
QPushButton#danger {{ color: {BAD}; }}
QLineEdit, QPlainTextEdit, QComboBox, QTextBrowser {{ background: white; border: 1px solid #d1d5db; border-radius: 8px;
    padding: 6px 8px; selection-background-color: {ACCENT}; selection-color: white; }}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border: 1px solid {ACCENT}; }}
QTableWidget, QListWidget {{ background: white; border: 1px solid {BORDER}; border-radius: 10px; gridline-color: #f1f5f9;
    selection-background-color: #eef2ff; selection-color: {TEXT}; }}
QListWidget::item {{ padding: 8px; border-bottom: 1px solid #f1f5f9; }}
QHeaderView::section {{ background: #f9fafb; border: none; border-bottom: 1px solid {BORDER}; padding: 7px 8px;
    color: {MUTED}; font-weight: 600; }}
QProgressBar {{ background: #eef2ff; border: none; border-radius: 4px; height: 8px; text-align: center; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
QComboBox {{ padding-right: 24px; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ image: url("{chevron}"); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{ background: white; border: 1px solid {BORDER}; selection-background-color: #eef2ff; }}
QRadioButton {{ spacing: 8px; padding: 3px 0; }}
QCheckBox {{ spacing: 8px; }}
"""
