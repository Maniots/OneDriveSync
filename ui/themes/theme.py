"""Shared native desktop styling; widgets retain their existing behavior."""

from . import colors, typography, spacing
from pathlib import Path


def get_dark_theme() -> str:
    c, t, s = colors, typography, spacing
    assets = (Path(__file__).resolve().parent.parent / "resources").as_posix()
    return f"""
QWidget {{
    background-color: {c.BACKGROUND}; color: {c.TEXT_PRIMARY};
    font-family: {t.FONT_FAMILY}; font-size: {t.FONT_SIZE_MEDIUM}pt;
    selection-background-color: {c.SELECTED}; selection-color: {c.SELECTED_TEXT};
}}
QLabel, QCheckBox, QRadioButton {{ background: transparent; }}
QLabel {{ border: none; }}
QFrame {{ border: none; }}
QLabel[h1="true"] {{ font-size: {t.FONT_SIZE_TITLE}pt; font-weight: 600; }}
QLabel[h2="true"] {{ font-size: 16pt; font-weight: 600; }}
QLabel[h3="true"] {{ font-size: 12pt; font-weight: 600; }}
QLabel[title="true"], QLabel[description="true"], QLabel[class="subtitle"] {{
    color: {c.TEXT_SECONDARY}; font-size: 9pt;
}}
QLabel[value="true"] {{ font-size: 10pt; font-weight: 500; }}
QLabel[metric="true"] {{ font-size: 18pt; font-weight: 600; }}
QLabel[eyebrow="true"] {{ color: {c.SECONDARY}; font-size: 9pt; font-weight: 600; }}
QLabel[badge="true"] {{
    background: {c.SELECTED}; color: {c.SECONDARY}; border-radius: 8px;
    padding: 6px 10px; font-size: 9pt;
}}
QFrame[card="true"] {{
    background-color: {c.SURFACE}; border: 1px solid {c.BORDER};
    border-radius: {s.CARD_BORDER_RADIUS}px;
}}
QFrame#header {{ background: {c.BACKGROUND}; border-bottom: 1px solid {c.BORDER}; }}
QStatusBar {{ background: {c.SIDEBAR}; color: {c.TEXT_SECONDARY}; border-top: 1px solid {c.BORDER}; }}
QStatusBar QLabel {{ color: {c.TEXT_SECONDARY}; font-size: 9pt; }}
QStatusBar::item {{ border: none; }}
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {c.INPUT_BACKGROUND}; border: 1px solid {c.BORDER};
    border-radius: 7px; padding: 7px 10px; min-height: 20px; color: {c.TEXT_PRIMARY};
}}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover {{ border-color: {c.TEXT_DISABLED}; }}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {c.FOCUS}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{ color: {c.TEXT_DISABLED}; }}
QComboBox {{ padding-right: 26px; }}
QComboBox::drop-down {{ width: 24px; border: none; }}
QComboBox::down-arrow {{ image: url("{assets}/chevron-down.svg"); width: 12px; height: 12px; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 22px; border: none; background: transparent; }}
QSpinBox::up-arrow {{ image: url("{assets}/chevron-up.svg"); width: 12px; height: 12px; }}
QSpinBox::down-arrow {{ image: url("{assets}/chevron-down.svg"); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{
    background: {c.SURFACE}; border: 1px solid {c.BORDER}; padding: 4px;
    selection-background-color: {c.SELECTED};
}}
QPushButton, QToolButton {{
    background: {c.SURFACE}; color: {c.TEXT_PRIMARY}; border: 1px solid {c.BORDER};
    border-radius: 7px; padding: 8px 14px; min-height: 20px; font-weight: 500;
}}
QPushButton:hover, QToolButton:hover {{ background: {c.HOVER}; border-color: {c.TEXT_DISABLED}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {c.SELECTED}; }}
QPushButton[primary="true"], QPushButton:default {{
    background: {c.PRIMARY}; border-color: {c.PRIMARY}; color: {c.SELECTED_TEXT};
}}
QPushButton[primary="true"]:hover, QPushButton:default:hover {{ background: #3273df; }}
QPushButton:focus, QToolButton:focus {{ border: 2px solid {c.FOCUS}; padding: 7px 13px; }}
QPushButton:disabled, QToolButton:disabled {{
    background: {c.INPUT_BACKGROUND}; color: {c.TEXT_DISABLED}; border-color: {c.BORDER};
}}
QCheckBox, QRadioButton {{ spacing: 8px; min-height: 26px; }}
QCheckBox:focus, QRadioButton:focus {{ color: {c.SECONDARY}; }}
QCheckBox::indicator {{ width: 16px; height: 16px; }}
QCheckBox::indicator:unchecked {{
    background: {c.INPUT_BACKGROUND}; border: 1px solid {c.TEXT_DISABLED}; border-radius: 4px;
}}
QCheckBox::indicator:checked {{
    background: {c.PRIMARY}; border: 1px solid {c.FOCUS}; border-radius: 4px;
    image: url("{assets}/check.svg");
}}
QCheckBox::indicator:disabled {{ border-color: {c.BORDER}; }}
QGroupBox {{
    background: {c.SURFACE}; border: 1px solid {c.BORDER}; border-radius: 10px;
    margin-top: 14px; padding: 24px 16px 16px; font-weight: 600;
}}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; left: 18px; padding: 0 6px; }}
QGroupBox QLabel, QGroupBox QCheckBox {{ background: transparent; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px 0; }}
QScrollBar::handle:vertical {{ background: {c.BORDER}; min-height: 32px; border-radius: 4px; }}
QScrollBar::handle:vertical:hover {{ background: {c.TEXT_DISABLED}; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 0 4px; }}
QScrollBar::handle:horizontal {{ background: {c.BORDER}; min-width: 32px; border-radius: 4px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QTableWidget, QTableView {{
    background: {c.SURFACE}; alternate-background-color: {c.INPUT_BACKGROUND};
    border: 1px solid {c.BORDER}; border-radius: 10px;
    selection-background-color: {c.SELECTED}; selection-color: {c.SELECTED_TEXT};
    gridline-color: {c.BORDER};
}}
QTableWidget::item {{ padding: 8px; border-bottom: 1px solid {c.BORDER}; }}
QTableWidget::item:focus {{ border: 1px solid {c.FOCUS}; }}
QHeaderView {{ background: {c.INPUT_BACKGROUND}; }}
QHeaderView::section {{
    background: {c.INPUT_BACKGROUND}; color: {c.TEXT_SECONDARY};
    padding: 12px 8px; border: none; border-bottom: 1px solid {c.BORDER}; font-weight: 600;
}}
QTableCornerButton::section {{ background: {c.INPUT_BACKGROUND}; border: none; }}
QMenu {{ background: {c.SURFACE}; border: 1px solid {c.BORDER}; padding: 6px; }}
QMenu::item {{ padding: 8px 24px; border-radius: 4px; }}
QMenu::item:selected {{ background: {c.SELECTED}; }}
QMenu::separator {{ height: 1px; background: {c.BORDER}; margin: 6px; }}
QToolTip {{ background: {c.HOVER}; color: {c.TEXT_PRIMARY}; border: 1px solid {c.BORDER}; padding: 8px; }}
QProgressBar {{ background: {c.INPUT_BACKGROUND}; border: 1px solid {c.BORDER}; border-radius: 6px; text-align: center; }}
QProgressBar::chunk {{ background: {c.PRIMARY}; border-radius: 5px; }}
QLabel[statusSuccess="true"] {{ color: {c.SUCCESS}; }}
QLabel[statusError="true"] {{ color: {c.ERROR}; }}
QLabel[statusWarning="true"] {{ color: {c.WARNING}; }}
QLabel[statusInfo="true"] {{ color: {c.TEXT_SECONDARY}; }}
QLabel[statusPaused="true"] {{ color: {c.SECONDARY}; }}
"""


def get_card_stylesheet() -> str:
    # Scope the border to the card itself, rather than every descendant frame.
    return f"""
    QFrame[card="true"] {{
        background: {colors.SURFACE}; border: 1px solid {colors.BORDER};
        border-radius: {spacing.CARD_BORDER_RADIUS}px;
    }}
    QLabel {{ background: transparent; border: none; }}
    """


def get_sidebar_stylesheet() -> str:
    c = colors
    return f"""
    QFrame#sidebar {{ background: {c.SIDEBAR}; border-right: 1px solid {c.BORDER}; }}
    QFrame#sidebar QWidget {{ background: transparent; }}
    QLabel#sidebarTitle {{ font-size: 13pt; font-weight: 600; color: {c.TEXT_PRIMARY}; }}
    QLabel#sidebarCaption {{ color: {c.TEXT_SECONDARY}; font-size: 9pt; }}
    QListWidget {{ border: none; outline: none; padding: 0; }}
    QListWidget::item {{
        padding: 12px; margin: 3px 0; border: 1px solid transparent; border-radius: 8px;
        color: {c.TEXT_SECONDARY};
    }}
    QListWidget::item:selected {{ background: {c.SELECTED}; color: {c.SELECTED_TEXT}; border-color: #355983; }}
    QListWidget::item:hover:!selected {{ background: {c.HOVER}; color: {c.TEXT_PRIMARY}; }}
    QListWidget::item:focus {{ border: 1px solid {c.FOCUS}; }}
    QFrame[class="separator"] {{ background: {c.BORDER}; max-height: 1px; }}
    """
