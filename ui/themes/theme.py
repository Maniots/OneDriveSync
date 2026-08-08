"""
Theme module providing centralized design tokens and stylesheet generation.
"""

from . import colors, typography, spacing


def get_dark_theme() -> str:
    """
    Returns the application-wide dark theme stylesheet using centralized design tokens.
    """
    # Extract tokens for readability
    c = colors
    t = typography
    s = spacing

    # Build stylesheet using f-strings and token values
    return f"""
/* OneDrive PC Sync - Dark Theme */
QWidget {{
    background-color: {c.BACKGROUND};
    color: {c.TEXT_PRIMARY};
    font-family: {t.FONT_FAMILY};
    font-size: {t.FONT_SIZE_MEDIUM}pt;
}}
QMainWindow {{
    background-color: {c.BACKGROUND};
}}
QStatusBar {{
    background-color: {c.SURFACE};
    border-top: 1px solid {c.BORDER};
}}
QListWidget {{
    background-color: {c.SURFACE};
    border: none;
    outline: none;
}}
QListWidget::item {{
    padding: {s.SMALL}px {s.MEDIUM}px;
    border-radius: {s.CARD_BORDER_RADIUS}px;
    margin: {s.XSMALL}px {s.SMALL}px;
}}
QListWidget::item:selected {{
    background-color: {c.PRIMARY};
    color: {c.SELECTED_TEXT};
}}
QListWidget::item:hover:!selected {{
    background-color: {c.HOVER};
}}
QFrame {{
    background-color: {c.SURFACE};
}}
QLabel {{
    color: {c.TEXT_PRIMARY};
}}
/* Heading labels */
QLabel[h1="true"] {{
    font-size: {t.FONT_SIZE_TITLE}pt;
    font-weight: {t.FONT_WEIGHT_BOLD};
}}
QLabel[h2="true"] {{
    font-size: {t.FONT_SIZE_XXLARGE}pt;
    font-weight: {t.FONT_WEIGHT_SEMIBOLD};
}}
QLabel[h3="true"] {{
    font-size: {t.FONT_SIZE_XLARGE}pt;
    font-weight: {t.FONT_WEIGHT_MEDIUM};
}}
/* Card-specific styling */
QFrame[card="true"] {{
    background-color: {c.SURFACE};
    border-radius: {s.CARD_BORDER_RADIUS}px;
    border: 1px solid {c.BORDER};
}}
QLabel[title="true"] {{
    font-size: {t.FONT_SIZE_SMALL}pt;
    font-weight: {t.FONT_WEIGHT_NORMAL};
    color: {c.TEXT_SECONDARY};
}}
QLabel[value="true"] {{
    font-size: {t.FONT_SIZE_LARGE}pt;
    font-weight: {t.FONT_WEIGHT_BOLD};
}}
QLabel[description="true"] {{
    font-size: {t.FONT_SIZE_XSMALL}pt;
    color: {c.TEXT_SECONDARY};
}}
/* Input styling */
QLineEdit, QTextEdit, QComboBox {{
    background-color: {c.INPUT_BACKGROUND};
    border: 1px solid {c.BORDER};
    border-radius: {s.CARD_BORDER_RADIUS}px;
    padding: {s.XSMALL}px {s.SMALL}px;
    color: {c.TEXT_PRIMARY};
}}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{
    border: 1px solid {c.PRIMARY};
}}
QPushButton {{
    background-color: {c.PRIMARY};
    color: {c.TEXT_PRIMARY};
    border: none;
    border-radius: {s.CARD_BORDER_RADIUS}px;
    padding: {s.SMALL}px {s.MEDIUM}px;
    font-weight: {t.FONT_WEIGHT_MEDIUM};
}}
QPushButton:hover {{
    background-color: {c.SECONDARY};
}}
QPushButton:pressed {{
    background-color: {c.PRIMARY};
}}
QPushButton:disabled {{
    background-color: {c.TEXT_DISABLED};
    color: {c.TEXT_SECONDARY};
}}
/* Scrollbar styling */
QScrollBar:vertical {{
    border: none;
    background: {c.SURFACE};
    width: {s.XSMALL}px;
    margin: {s.SMALL}px 0 {s.SMALL}px 0;
}}
QScrollBar::handle:vertical {{
    background: {c.BORDER};
    border-radius: {s.CARD_BORDER_RADIUS}px;
    min-height: {s.MEDIUM}px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}

/* Status labels */
QLabel[statusSuccess="true"] {{
    color: {c.SUCCESS};
}}
QLabel[statusError="true"] {{
    color: {c.ERROR};
}}
QLabel[statusWarning="true"] {{
    color: {c.WARNING};
}}
QLabel[statusInfo="true"] {{
    color: {c.TEXT_SECONDARY};
}}
QLabel[statusPaused="true"] {{
    color: {c.SECONDARY};
}}

"""


def get_card_stylesheet() -> str:
    """
    Returns a stylesheet string specifically for Card widgets.
    Intended to be applied per-instance if needed.
    """
    c = colors
    t = typography
    s = spacing
    return f"""
    QFrame {{
        background-color: {c.SURFACE};
        border-radius: {s.CARD_BORDER_RADIUS}px;
        border: 1px solid {c.BORDER};
    }}
    QLabel[title="true"] {{
        font-size: {t.FONT_SIZE_SMALL}pt;
        font-weight: {t.FONT_WEIGHT_NORMAL};
        color: {c.TEXT_SECONDARY};
    }}
    QLabel[value="true"] {{
        font-size: {t.FONT_SIZE_LARGE}pt;
        font-weight: {t.FONT_WEIGHT_BOLD};
    }}
    QLabel[description="true"] {{
        font-size: {t.FONT_SIZE_XSMALL}pt;
        color: {c.TEXT_SECONDARY};
    }}
    """


def get_sidebar_stylesheet() -> str:
    """
    Returns a stylesheet for the sidebar frame.
    """
    c = colors
    t = typography
    s = spacing
    return f"""
    QFrame#sidebar {{
        background-color: {c.SURFACE};
        border-right: 1px solid {c.BORDER};
    }}
    QListWidget {{
        background-color: transparent;
        border: none;
    }}
    QListWidget::item {{
        padding: {s.SMALL}px {s.MEDIUM}px;
        border-bottom: 1px solid {c.BORDER};
        border-radius: 0px;
        margin: 0px;
    }}
    QListWidget::item:selected {{
        background-color: {c.PRIMARY};
        color: white;
    }}
    QListWidget::item:hover:!selected {{
        background-color: {c.HOVER};
    }}
    QLabel#sidebarTitle {{
        font-size: {t.FONT_SIZE_MEDIUM}pt;
        font-weight: {t.FONT_WEIGHT_BOLD};
        color: {c.TEXT_PRIMARY};
        padding: {s.MEDIUM}px;
        border-bottom: 1px solid {c.BORDER};
    }}
    """