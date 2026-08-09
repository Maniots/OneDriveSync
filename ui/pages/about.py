from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt
from ..themes import spacing


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

        label = QLabel("About")
        label.setProperty("h2", "true")
        layout.addWidget(label)

        # Add some placeholder about text
        about_text = QLabel(
            "OneDrive PC Sync\n\n"
            "A utility to synchronize folders with OneDrive.\n\n"
            "Version: 1.0.0\n"
            "© 2026 OneDrive PC Sync Team"
        )
        about_text.setAlignment(Qt.AlignmentFlag.AlignLeft)
        about_text.setWordWrap(True)
        about_text.setProperty("value", "true")
        layout.addWidget(about_text)

        layout.addStretch()