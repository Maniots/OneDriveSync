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
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from backend.services.configuration_service import ConfigurationService
from backend.services.backup_service import BackupService
from ..resources.icons import get_icon
import datetime


class BackupsPage(QWidget):
    def __init__(self, config_service: ConfigurationService, backup_service: BackupService, parent=None):
        super().__init__(parent)
        self.config_service = config_service
        self.backup_service = backup_service
        self.backup_data = []  # List of backup info dicts for the table
        self.setup_ui()
        # Load configuration data if backend is available
        app_config = self.config_service.get_app_config()
        if app_config:
            QTimer.singleShot(0, self.load_configuration_data)
        else:
            self.show_no_config_message()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # Toolbar
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(8)

        # Refresh button
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setIcon(get_icon("refresh"))
        self.refresh_btn.clicked.connect(self.refresh_backups)
        toolbar_layout.addWidget(self.refresh_btn)

        toolbar_layout.addStretch()

        layout.addLayout(toolbar_layout)

        # Table for backups
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Folder", "Timestamp", "Size", "Age", "Status", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table, 1)  # stretch factor 1

        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

    def load_configuration_data(self):
        """Load and display backup data from the configuration and backup service."""
        try:
            app_config = self.config_service.get_app_config()
            if not app_config:
                self.show_no_config_message()
                return

            self.table.setRowCount(0)
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
                        status_item.setForeground(QColor("#107c10"))  # Green
                        self.table.setItem(row, 4, status_item)
                        # Actions placeholder
                        actions_layout = QHBoxLayout()
                        actions_layout.setContentsMargins(0, 0, 0, 0)
                        actions_layout.setSpacing(4)
                        restore_btn = QPushButton("Restore")
                        restore_btn.setIcon(get_icon("restore"))
                        open_btn = QPushButton("Open")
                        open_btn.setIcon(get_icon("open"))
                        delete_btn = QPushButton("Delete")
                        delete_btn.setIcon(get_icon("delete"))
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
        self.table.setRowCount(0)
        label = QLabel("No configuration available.\n"
                       "Backup information cannot be displayed.")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        # We'll replace the table with a label for simplicity
        self.layout().replaceWidget(self.table, label)
        self.table.hide()
        self.table.deleteLater()
        self.table = label  # Keep reference to avoid issues

    def show_error(self, message):
        """Show an error message."""
        self.table.setRowCount(0)
        label = QLabel(f"Error:\n{message}")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        self.layout().replaceWidget(self.table, label)
        self.table.hide()
        self.table.deleteLater()
        self.table = label

    # For compatibility with the existing MainWindow, we keep the config_backend argument
    # even though we don't use it.