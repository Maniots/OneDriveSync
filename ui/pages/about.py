from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QPushButton, QHBoxLayout, QCheckBox, QProgressBar, QScrollArea, QPlainTextEdit, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
from PySide6.QtCore import Qt, QSize
from ..themes import spacing
from ..resources.icons import get_icon
from src.app_info import VERSION, release_notes
from datetime import datetime


class AboutPage(QWidget):
    def __init__(self, config_service=None, parent=None, update_service=None):
        super().__init__(parent)
        self.update_service = update_service
        self.setup_ui()

    def setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        layout = QVBoxLayout(body)
        scroll.setWidget(body)
        outer.addWidget(scroll)
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

        self.setup_history(layout)

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
        self.available_changes = QPlainTextEdit()
        self.available_changes.setReadOnly(True)
        self.available_changes.setAccessibleName("Available update release notes")
        self.available_changes.setMaximumHeight(120)
        self.available_changes.hide()
        content.addWidget(self.available_changes)
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
        changes = service.update.changes if service.update is not None else ""
        self.available_changes.setPlainText(changes)
        self.available_changes.setVisible(bool(changes))
        self.check_updates_button.setEnabled(not service.busy and service.state != "ready")
        self.install_update_button.setEnabled(service.can_install and not service.busy and service.update is not None)
        self.install_update_button.setText("Install update" if service.installer else "Download and install")
        self.update_progress.setVisible(service.state == "downloading")
        self.update_progress.setValue(service.progress)
        self.automatic_updates.blockSignals(True)
        self.automatic_updates.setChecked(service.automatic)
        self.automatic_updates.blockSignals(False)
        self.automatic_updates.setEnabled(service.can_install and service.state != "installing")

    def setup_history(self, layout):
        card = QFrame()
        card.setProperty("card", "true")
        content = QVBoxLayout(card)
        content.setContentsMargins(28, 24, 28, 24)
        title = QLabel("Update history")
        title.setProperty("h2", "true")
        content.addWidget(title)
        self.history_status = QLabel()
        self.history_status.setWordWrap(True)
        self.history_status.setTextFormat(Qt.TextFormat.PlainText)
        content.addWidget(self.history_status)
        self.history_table = QTableWidget(0, 3)
        self.history_table.setHorizontalHeaderLabels(["Installed at", "Previous version", "Installed version"])
        self.history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.history_table.verticalHeader().hide()
        self.history_table.setFixedHeight(150)
        self.history_table.setAccessibleName("Installation history")
        self.history_table.itemSelectionChanged.connect(self.show_history_notes)
        content.addWidget(self.history_table)
        self.history_notes = QPlainTextEdit()
        self.history_notes.setReadOnly(True)
        self.history_notes.setAccessibleName("Changelog for selected installation")
        self.history_notes.setMinimumHeight(110)
        self.history_notes.setMaximumHeight(150)
        content.addWidget(self.history_notes)
        refresh = QPushButton("Refresh history")
        refresh.clicked.connect(self.refresh_history)
        content.addWidget(refresh)
        layout.addWidget(card)
        self.refresh_history()

    def showEvent(self, event):
        self.refresh_history()
        super().showEvent(event)

    def refresh_history(self):
        self.installations = []
        self.history_table.setRowCount(0)
        try:
            if self.update_service is not None:
                self.installations = self.update_service.client.installation_history()
            self.history_table.setRowCount(len(self.installations))
            for index, installation in enumerate(self.installations):
                installed_at = datetime.fromisoformat(installation["timestamp"]).astimezone().strftime("%d/%m/%Y %H:%M:%S")
                values = (installed_at, installation["previous_version"] or "—", installation["version"])
                for column, value in enumerate(values):
                    self.history_table.setItem(index, column, QTableWidgetItem(value))
            self.history_status.setText("Select an installation to view its changelog." if self.installations
                                        else "No installation dates recorded yet. Current release notes are shown below.")
            if self.installations:
                self.history_table.selectRow(0)
            else:
                self.history_notes.setPlainText(release_notes())
        except Exception as exc:
            self.history_status.setText(f"Cannot read update history. Use Refresh history to retry: {exc}")
            self.history_notes.setPlainText(release_notes())

    def show_history_notes(self):
        row = self.history_table.currentRow()
        if 0 <= row < len(self.installations):
            self.history_notes.setPlainText(self.installations[row]["changes"])
