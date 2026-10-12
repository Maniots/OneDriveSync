from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt, QSize
from ..themes import spacing
from ..resources.icons import get_icon


class AboutPage(QWidget):
    def __init__(self, config_service=None, parent=None):
        super().__init__(parent)
        # config_service is accepted for consistency but not used
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(spacing.LARGE, spacing.LARGE, spacing.LARGE, spacing.LARGE)
        layout.setSpacing(spacing.MEDIUM)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        card = QFrame()
        card.setProperty("card", "true")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 28, 28, 28)
        card_layout.setSpacing(16)
        icon = QLabel()
        icon.setPixmap(get_icon("cloud").pixmap(QSize(44, 44)))
        card_layout.addWidget(icon)
        label = QLabel("OneDrive PC Sync")
        label.setProperty("h2", "true")
        card_layout.addWidget(label)

        # Add some placeholder about text
        about_text = QLabel(
            "Keep your game saves, editor settings, and application data in sync "
            "between this PC and OneDrive. Choose the folders that matter to you.\n\n"
            "Synchronization adds and updates files without deleting them. "
            "Optional backups preserve OneDrive contents before an upload.\n\n"
            "Version: 1.0.0\n"
            "© 2026 OneDrive PC Sync Team"
        )
        about_text.setAlignment(Qt.AlignmentFlag.AlignLeft)
        about_text.setWordWrap(True)
        about_text.setProperty("description", "true")
        card_layout.addWidget(about_text)
        layout.addWidget(card)

        layout.addStretch()
