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
from ..config import convert_to_ui_models
from ..models.backup_model import BackupModel
import datetime


class BackupsPage(QWidget):
    def __init__(self, config_backend=None, parent=None):
        super().__init__(parent)
        self.config_backend = config_backend
        self.backup_data = []  # List of BackupModel for the table
        self.setup_ui()
        # Load configuration data if backend is available
        if self.config_backend:
            QTimer.singleShot(0, self.load_configuration_data)
        else:
            self.show_no_config_message()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Title
        title = QLabel("Backups")
        title.setProperty("h2", "true")
        layout.addWidget(title)

        # Summary section
        summary_frame = QFrame()
        summary_frame.setFrameShape(QFrame.StyledPanel)
        summary_layout = QVBoxLayout(summary_frame)
        summary_layout.setContentsMargins(16, 16, 16, 16)
        summary_layout.setSpacing(8)

        # Summary labels
        self.total_backups_label = QLabel("Total Backups: 0")
        self.total_backups_label.setProperty("class", "summary-text")
        summary_layout.addWidget(self.total_backups_label)

        self.total_storage_label = QLabel("Total Storage Used: 0 B")
        self.total_storage_label.setProperty("class", "summary-text")
        summary_layout.addWidget(self.total_storage_label)

        self.retention_period_label = QLabel("Retention Period: N/A")
        self.retention_period_label.setProperty("class", "summary-text")
        summary_layout.addWidget(self.retention_period_label)

        self.last_backup_label = QLabel("Last Backup: Never")
        self.last_backup_label.setProperty("class", "summary-text")
        summary_layout.addWidget(self.last_backup_label)

        self.backup_health_label = QLabel("Backup Health: Unknown")
        self.backup_health_label.setProperty("class", "summary-text")
        summary_layout.addWidget(self.backup_health_label)

        layout.addWidget(summary_frame)

        # Table for backups
        self.table = QTableWidget()
        self.table.setColumnCount(8)  # Folder, Timestamp, Size, Age, Status, Restore, Open, Delete
        self.table.setHorizontalHeaderLabels([
            "Folder",
            "Timestamp",
            "Archive Size",
            "Age",
            "Status",
            "Restore",
            "Open Location",
            "Delete"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)  # Folder
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Timestamp
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Size
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Age
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Status
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Restore
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)  # Open Location
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeToContents)  # Delete
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(40)  # Set default row height
        layout.addWidget(self.table, 1)  # stretch factor

    def load_configuration_data(self):
        """Load and display backup data."""
        try:
            if not self.config_backend:
                self.show_error("No configuration backend available")
                return

            # Clear existing data
            self.backup_data.clear()
            self.table.setRowCount(0)

            # Get the configuration
            config = self.config_backend.config

            # Convert to UI models to get backup configuration per folder
            _, _, backup_models_config, _ = convert_to_ui_models(config)

            # Generate fake backup data for demonstration
            # In a real app, this would come from a backup service
            fake_backups = []
            for backup_config in backup_models_config:
                folder_id = backup_config.folder_id
                folder_name = backup_config.folder_name
                backup_path = backup_config.backup_path

                # Generate 3 fake backups per folder
                for i in range(3):
                    # Calculate timestamp (i days ago)
                    timestamp_dt = datetime.datetime.now() - datetime.timedelta(days=i*2, hours=i*3)
                    timestamp = timestamp_dt.strftime("%Y-%m-%d %H:%M:%S")

                    # Fake size (in MB)
                    size_mb = 10.5 * (i + 1)
                    size = f"{size_mb:.1f} MB"

                    # Age
                    age_delta = datetime.datetime.now() - timestamp_dt
                    if age_delta.days > 0:
                        age = f"{age_delta.days} days ago"
                    elif age_delta.seconds > 3600:
                        age = f"{age_delta.seconds // 3600} hours ago"
                    else:
                        age = f"{age_delta.seconds // 60} minutes ago"

                    # Status (alternating for demo)
                    status = "Success" if i % 2 == 0 else "Failed"

                    fake_backups.append({
                        "folder_id": folder_id,
                        "folder_name": folder_name,
                        "backup_path": backup_path,
                        "timestamp": timestamp,
                        "size": size,
                        "status": status,
                        "timestamp_dt": timestamp_dt,  # For sorting and age calculation
                    })

            # Sort by timestamp descending (newest first)
            fake_backups.sort(key=lambda x: x["timestamp_dt"], reverse=True)

            # Convert to BackupModel objects (for consistency, though we don't use the model directly in the table)
            self.backup_data = [
                BackupModel(
                    folder_id=item["folder_id"],
                    folder_name=item["folder_name"],
                    backup_path=item["backup_path"],
                    timestamp=item["timestamp"],
                    size=item["size"],
                    status=item["status"]
                )
                for item in fake_backups
            ]

            # Update summary
            self.update_summary()

            # Populate table
            self.populate_table()

        except Exception as e:
            self.show_error(f"Error loading backup data: {e}")

    def update_summary(self):
        """Update the summary labels based on backup data."""
        if not self.backup_data:
            self.total_backups_label.setText("Total Backups: 0")
            self.total_storage_label.setText("Total Storage Used: 0 B")
            self.retention_period_label.setText("Retention Period: N/A")
            self.last_backup_label.setText("Last Backup: Never")
            self.backup_health_label.setText("Backup Health: Unknown")
            return

        total_backups = len(self.backup_data)
        # Calculate total storage (parsing size strings like "10.5 MB")
        total_storage_bytes = 0
        for backup in self.backup_data:
            size_str = backup.size
            try:
                # Extract number and unit
                parts = size_str.split()
                if len(parts) == 2:
                    value = float(parts[0])
                    unit = parts[1].upper()
                    if unit == "B":
                        total_storage_bytes += value
                    elif unit == "KB":
                        total_storage_bytes += value * 1024
                    elif unit == "MB":
                        total_storage_bytes += value * 1024 * 1024
                    elif unit == "GB":
                        total_storage_bytes += value * 1024 * 1024 * 1024
            except:
                pass  # If parsing fails, skip

        # Format total storage
        if total_storage_bytes < 1024:
            total_storage_str = f"{total_storage_bytes} B"
        elif total_storage_bytes < 1024 * 1024:
            total_storage_str = f"{total_storage_bytes / 1024:.1f} KB"
        elif total_storage_bytes < 1024 * 1024 * 1024:
            total_storage_str = f"{total_storage_bytes / (1024 * 1024):.1f} MB"
        else:
            total_storage_str = f"{total_storage_bytes / (1024 * 1024 * 1024):.1f} GB"

        # Retention period (from the first folder's backup config, assuming same for all)
        retention_period = "N/A"
        if self.config_backend and self.config_backend.config.folders:
            for folder in self.config_backend.config.folders:
                if folder.backup and folder.backup.enabled:
                    retention_period = f"{folder.backup.retention_days} days"
                    break

        # Last backup (newest timestamp)
        last_backup = "Never"
        if self.backup_data:
            # Since we sorted by timestamp descending, the first is the newest
            last_backup = self.backup_data[0].timestamp

        # Backup health (percentage of successful backups)
        successful = sum(1 for backup in self.backup_data if backup.status == "Success")
        health_percentage = (successful / len(self.backup_data)) * 100 if self.backup_data else 0
        health_str = f"{health_percentage:.0f}% Healthy"
        if health_percentage == 100:
            health_str += " (Good)"
        elif health_percentage >= 80:
            health_str += " (Fair)"
        else:
            health_str += " (Poor)"

        # Update labels
        self.total_backups_label.setText(f"Total Backups: {total_backups}")
        self.total_storage_label.setText(f"Total Storage Used: {total_storage_str}")
        self.retention_period_label.setText(f"Retention Period: {retention_period}")
        self.last_backup_label.setText(f"Last Backup: {last_backup}")
        self.backup_health_label.setText(f"Backup Health: {health_str}")

    def populate_table(self):
        """Populate the table with backup data."""
        self.table.setRowCount(len(self.backup_data))
        for row, backup in enumerate(self.backup_data):
            # Folder
            folder_item = QTableWidgetItem(backup.folder_name)
            self.table.setItem(row, 0, folder_item)

            # Timestamp
            timestamp_item = QTableWidgetItem(backup.timestamp)
            self.table.setItem(row, 1, timestamp_item)

            # Archive Size
            size_item = QTableWidgetItem(backup.size)
            self.table.setItem(row, 2, size_item)

            # Age (calculate from timestamp)
            try:
                timestamp_dt = datetime.datetime.strptime(backup.timestamp, "%Y-%m-%d %H:%M:%S")
                age_delta = datetime.datetime.now() - timestamp_dt
                if age_delta.days > 0:
                    age = f"{age_delta.days} days ago"
                elif age_delta.seconds > 3600:
                    age = f"{age_delta.seconds // 3600} hours ago"
                else:
                    age = f"{age_delta.seconds // 60} minutes ago"
            except:
                age = "Unknown"
            age_item = QTableWidgetItem(age)
            self.table.setItem(row, 3, age_item)

            # Status
            status_item = QTableWidgetItem(backup.status)
            # Color code status
            if backup.status == "Success":
                status_item.setBackground(QColor("#4CAF50"))  # Green
                status_item.setForeground(QColor("white"))
            elif backup.status == "Failed":
                status_item.setBackground(QColor("#F44336"))  # Red
                status_item.setForeground(QColor("white"))
            else:
                status_item.setBackground(QColor("#FFC107"))  # Amber
                status_item.setForeground(QColor("black"))
            self.table.setItem(row, 4, status_item)

            # Restore button (placeholder)
            restore_btn = QPushButton("Restore")
            restore_btn.setProperty("class", "outline")
            restore_btn.setStyleSheet("QPushButton { padding: 5px 10px; }")
            restore_btn.clicked.connect(lambda checked, r=row: self.on_restore_clicked(r))
            self.table.setCellWidget(row, 5, restore_btn)

            # Open location button (placeholder)
            open_btn = QPushButton("Open")
            open_btn.setProperty("class", "outline")
            open_btn.setStyleSheet("QPushButton { padding: 5px 10px; }")
            open_btn.clicked.connect(lambda checked, r=row: self.on_open_clicked(r))
            self.table.setCellWidget(row, 6, open_btn)

            # Delete button (placeholder)
            delete_btn = QPushButton("Del")
            delete_btn.setProperty("class", "outline")
            delete_btn.setStyleSheet("QPushButton { padding: 5px 10px; background-color: #F44336; color: white; }")
            delete_btn.clicked.connect(lambda checked, r=row: self.on_delete_clicked(r))
            self.table.setCellWidget(row, 7, delete_btn)

    def on_restore_clicked(self, row):
        """Handle Restore button click (placeholder)."""
        # In a real app, this would restore the backup
        # For now, just show a message
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            "Restore Backup",
            f"Restore functionality is not implemented in this version.\n"
            f"Would restore backup for {self.backup_data[row].folder_name} from {self.backup_data[row].timestamp}."
        )

    def on_open_clicked(self, row):
        """Handle Open location button click (placeholder)."""
        # In a real app, this would open the backup location in file explorer
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            "Open Location",
            f"Open location functionality is not implemented in this version.\n"
            f"Would open: {self.backup_data[row].backup_path}"
        )

    def on_delete_clicked(self, row):
        """Handle Delete button click (placeholder)."""
        # In a real app, this would delete the backup
        # For now, just show a message and remove from UI (but not actual file)
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self,
            "Delete Backup",
            f"Are you sure you want to delete the backup for {self.backup_data[row].folder_name} from {self.backup_data[row].timestamp}?\n"
            f"This action does not actually delete files in this version.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            # Remove from UI only
            self.backup_data.pop(row)
            self.populate_table()  # Refresh table
            self.update_summary()

    def show_no_config_message(self):
        """Show a message when no configuration backend is available."""
        self.clear_layout()
        label = QLabel("No configuration backend available.\n"
                       "Backup information cannot be displayed.")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        self.layout().addWidget(label)

    def show_error(self, message):
        """Show an error state."""
        self.clear_layout()
        label = QLabel(f"Error:\n{message}")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        self.layout().addWidget(label)

    def clear_layout(self):
        """Clear the layout."""
        while self.layout().count():
            item = self.layout().takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()