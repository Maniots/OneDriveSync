from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QPushButton, QHBoxLayout, QCheckBox, QProgressBar
from PySide6.QtCore import Qt, QSize
from ..themes import spacing
from ..resources.icons import get_icon
from src.app_info import VERSION


class AboutPage(QWidget):
    def __init__(self, config_service=None, parent=None, update_service=None):
        super().__init__(parent)
        self.update_service = update_service
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
            f"Version: {VERSION}\n"
            "© 2026 OneDrive PC Sync Team"
        )
        about_text.setAlignment(Qt.AlignmentFlag.AlignLeft)
        about_text.setWordWrap(True)
        about_text.setProperty("description", "true")
        card_layout.addWidget(about_text)
        layout.addWidget(card)

        if self.update_service is not None:
            self.setup_updates(layout)

        layout.addStretch()

    def setup_updates(self, layout):
        card = QFrame()
        card.setProperty("card", "true")
        content = QVBoxLayout(card)
        content.setContentsMargins(28, 24, 28, 24)
        title = QLabel("Updates")
        title.setProperty("h2", "true")
        content.addWidget(title)
        self.update_status = QLabel()
        self.update_status.setTextFormat(Qt.TextFormat.PlainText)
        self.update_status.setWordWrap(True)
        content.addWidget(self.update_status)
        self.update_progress = QProgressBar()
        self.update_progress.setRange(0, 100)
        self.update_progress.setAccessibleName("Update download progress")
        content.addWidget(self.update_progress)
        actions = QHBoxLayout()
        self.check_updates_button = QPushButton("Check for updates")
        self.check_updates_button.clicked.connect(lambda: self.update_service.check())
        self.install_update_button = QPushButton("Download and install")
        self.install_update_button.setProperty("primary", True)
        self.install_update_button.clicked.connect(self.update_service.download_and_install)
        actions.addWidget(self.check_updates_button)
        actions.addWidget(self.install_update_button)
        actions.addStretch()
        content.addLayout(actions)
        self.automatic_updates = QCheckBox("Install updates automatically when idle")
        self.automatic_updates.setToolTip("The app restarts after updating. Active synchronization finishes first.")
        self.automatic_updates.toggled.connect(self.update_service.set_automatic)
        content.addWidget(self.automatic_updates)
        note = QLabel("Updates are checked at startup and every four hours while the app is running. Your folders and settings are preserved.")
        note.setWordWrap(True)
        note.setProperty("description", "true")
        content.addWidget(note)
        layout.addWidget(card)
        self.update_service.changed.connect(self.refresh_updates)
        self.refresh_updates()

    def refresh_updates(self):
        service = self.update_service
        self.update_status.setText(service.message)
        self.check_updates_button.setEnabled(not service.busy and service.state != "ready")
        self.install_update_button.setEnabled(service.can_install and not service.busy and service.update is not None)
        self.install_update_button.setText("Install update" if service.installer else "Download and install")
        self.update_progress.setVisible(service.state == "downloading")
        self.update_progress.setValue(service.progress)
        self.automatic_updates.blockSignals(True)
        self.automatic_updates.setChecked(service.automatic)
        self.automatic_updates.blockSignals(False)
        self.automatic_updates.setEnabled(service.can_install and service.state != "installing")
