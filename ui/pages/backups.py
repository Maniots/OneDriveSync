from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QHBoxLayout,
    QHeaderView,
    QFrame,
    QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QColor, QBrush
from backend.services.configuration_service import ConfigurationService
from backend.services.backup_service import BackupService
from ..resources.icons import get_icon
from ..themes import colors, spacing
import datetime


class BackupsPage(QWidget):
    def __init__(self, config_service: ConfigurationService, backup_service: BackupService, parent=None):
        super().__init__(parent)
        self.config_service = config_service
        self.backup_service = backup_service
        self.backup_data = []  # List of backup info dicts for the table
        self.setup_ui()
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.timeout.connect(self.load_configuration_data)
        if hasattr(self.config_service, "changed"):
            self.config_service.changed.connect(self.load_configuration_data)
        # Load configuration data if backend is available
        app_config = self.config_service.get_app_config()
        if app_config:
            self.refresh_timer.start(0)
        else:
            self.show_no_config_message()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(spacing.LARGE, spacing.LARGE, spacing.LARGE, spacing.LARGE)
        layout.setSpacing(spacing.MEDIUM)

        # Toolbar
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(spacing.SMALL)

        # Refresh button
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setIcon(get_icon("refresh"))
        self.refresh_btn.setToolTip("Refresh backup list")
        self.refresh_btn.setProperty("value", "true")
        self.refresh_btn.clicked.connect(self.refresh_backups)
        toolbar_layout.addWidget(self.refresh_btn)

        toolbar_layout.addStretch()

        layout.addLayout(toolbar_layout)

        # Table for backups
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Folder", "Timestamp", "Size", "Age", "Status", "Actions"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(52)
        layout.addWidget(self.table, 1)  # stretch factor 1

        self.error_label = QLabel(self)
        self.error_label.setWordWrap(True)
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setProperty("description", "true")
        layout.addWidget(self.status_label)

    @Slot()
    def load_configuration_data(self):
        """Load and display backup data from the configuration and backup service."""
        try:
            app_config = self.config_service.get_app_config()
            if not app_config:
                self.show_no_config_message()
                return

            self.table.setRowCount(0)
            self.error_label.hide()
            self.table.show()
            self.backup_data = []

            # We'll gather backup info for each folder that has backup enabled
            row = 0
            for folder in app_config.folders:
                if folder.backup and folder.backup.enabled:
                    backup_infos = self.backup_service.get_backup_info_formatted(folder.id)
                    for info in backup_infos:
                        self.table.insertRow(row)
                        # Folder name
                        folder_item = QTableWidgetItem(folder.name)
                        self.table.setItem(row, 0, folder_item)
                        # Timestamp
                        timestamp_item = QTableWidgetItem(info["timestamp"])
                        self.table.setItem(row, 1, timestamp_item)
                        # Size (already formatted)
                        size_item = QTableWidgetItem(info["size"])
                        self.table.setItem(row, 2, size_item)
                        # Age (we'll calculate from timestamp)
                        age_item = QTableWidgetItem(self.calculate_age(info["timestamp"]))
                        self.table.setItem(row, 3, age_item)
                        # Status (we don't have real status, so we'll show "Available" if backup exists)
                        status_item = QTableWidgetItem("Available")
                        status_item.setForeground(QBrush(QColor(colors.SUCCESS)))
                        self.table.setItem(row, 4, status_item)
                        # Actions placeholder
                        actions_layout = QHBoxLayout()
                        actions_layout.setContentsMargins(0, 0, 0, 0)
                        actions_layout.setSpacing(spacing.XSMALL)
                        restore_btn = QPushButton("Restore")
                        restore_btn.setIcon(get_icon("restore"))
                        restore_btn.setToolTip("Restore backup")
                        restore_btn.setProperty("value", "true")
                        open_btn = QPushButton("Open")
                        open_btn.setIcon(get_icon("open"))
                        open_btn.setToolTip("Open backup location")
                        open_btn.setProperty("value", "true")
                        delete_btn = QPushButton("Delete")
                        delete_btn.setIcon(get_icon("delete"))
                        delete_btn.setToolTip("Delete backup")
                        delete_btn.setProperty("value", "true")
                        actions_layout.addWidget(restore_btn)
                        actions_layout.addWidget(open_btn)
                        actions_layout.addWidget(delete_btn)
                        actions_widget = QWidget()
                        actions_widget.setLayout(actions_layout)
                        self.table.setCellWidget(row, 5, actions_widget)
                        row += 1

            if row == 0:
                self.status_label.setText("No backups found")
            else:
                self.status_label.setText(f"Found {row} backup(s)")
        except Exception as e:
            self.show_error(f"Error loading backup data: {e}")

    def calculate_age(self, timestamp_str: str) -> str:
        """Calculate age from timestamp string (YYYY-MM-DD) and return a human-readable string."""
        try:
            backup_date = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d").date()
            today = datetime.date.today()
            delta = today - backup_date
            if delta.days == 0:
                return "Today"
            elif delta.days == 1:
                return "Yesterday"
            elif delta.days < 7:
                return f"{delta.days} days ago"
            elif delta.days < 30:
                weeks = delta.days // 7
                return f"{weeks} week{'s' if weeks > 1 else ''} ago"
            else:
                months = delta.days // 30
                return f"{months} month{'s' if months > 1 else ''} ago"
        except Exception:
            return "Unknown"

    def refresh_backups(self):
        """Refresh the backup table."""
        self.load_configuration_data()

    def show_no_config_message(self):
        """Show a message when no configuration is available."""
        self.show_error("No configuration available. Backup information cannot be displayed.")

    def show_error(self, message):
        """Show an error message."""
        self.table.setRowCount(0)
        self.table.hide()
        self.error_label.setText(message)
        self.error_label.show()
        self.status_label.setText(message)

    # For compatibility with the existing MainWindow, we keep the config_backend argument
    # even though we don't use it.
