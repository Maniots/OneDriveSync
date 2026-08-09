from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QHBoxLayout, QSizePolicy
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont
from ..themes.theme import get_card_stylesheet
from ..themes import spacing
from ..resources.icons import get_icon


class Card(QFrame):
    def __init__(self, title="", value="", icon_name="", description="", parent=None):
        super().__init__(parent)
        self.setProperty("card", "true")
        self.setFrameStyle(QFrame.StyledPanel)
        self.setLineWidth(1)
        self.setMidLineWidth(0)
        # Apply card-specific stylesheet from theme
        self.setStyleSheet(get_card_stylesheet())
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.setup_ui(title, value, icon_name, description)

    def setup_ui(self, title, value, icon_name, description):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            spacing.SMALL, spacing.SMALL, spacing.SMALL, spacing.SMALL
        )
        layout.setSpacing(spacing.XSMALL)

        # Icon and title row
        top_layout = QHBoxLayout()
        if icon_name:
            icon = get_icon(icon_name)
            pixmap = icon.pixmap(QSize(24, 24))
            icon_label = QLabel()
            icon_label.setPixmap(pixmap)
            top_layout.addWidget(icon_label)

        title_label = QLabel(title)
        title_label.setProperty("title", "true")
        top_layout.addWidget(title_label)
        top_layout.addStretch()
        layout.addLayout(top_layout)

        # Value
        value_label = QLabel(value)
        value_label.setProperty("value", "true")
        layout.addWidget(value_label)

        # Description (optional)
        if description:
            desc_label = QLabel(description)
            desc_label.setProperty("description", "true")
            layout.addWidget(desc_label)

        layout.addStretch()