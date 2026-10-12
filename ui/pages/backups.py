from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QHBoxLayout,
    QHeaderView,
    QApplication,
    QFileDialog,
    QMessageBox,
)
from PySide6.QtCore import Qt, QTimer, QThread, QUrl, Slot
from PySide6.QtGui import QColor, QBrush, QDesktopServices
from backend.services.configuration_service import ConfigurationService
from backend.services.backup_service import BackupService
from ..resources.icons import get_icon
from ..themes import colors, spacing
from ..workers.backup_worker import BackupWorker
from shiboken6 import isValid
import datetime


class BackupsPage(QWidget):
    def __init__(self, config_service: ConfigurationService, backup_service: BackupService, parent=None):
        super().__init__(parent)
        self.config_service = config_service
        self.backup_service = backup_service
        self.backup_data = []  # List of backup info dicts for the table
        self._thread = None
        self._worker = None
        self._operation_result = None
        self._thread_cleanup = None
        self.setup_ui()
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.timeout.connect(self.load_configuration_data)
        if hasattr(self.config_service, "changed"):
            self.config_service.changed.connect(self.load_configuration_data)
        QApplication.instance().aboutToQuit.connect(self.wait_for_finished)
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
        if self._thread is not None:
            return
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
                        self.backup_data.append({**info, "folder_id": folder.id})
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
                        # Capture archive identity, not the row index: rows can move.
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
                        restore_btn.clicked.connect(
                            lambda checked=False, fid=folder.id, path=info["path"]: self.restore_backup(fid, path))
                        open_btn.clicked.connect(
                            lambda checked=False, fid=folder.id, path=info["path"]: self.open_backup(fid, path))
                        delete_btn.clicked.connect(
                            lambda checked=False, fid=folder.id, path=info["path"]: self.delete_backup(fid, path))
                        dry_run = app_config.general.dry_run
                        restore_btn.setEnabled(not dry_run)
                        delete_btn.setEnabled(not dry_run)
                        if dry_run:
                            restore_btn.setToolTip("Restore is disabled in dry-run mode")
                            delete_btn.setToolTip("Deletion is disabled in dry-run mode")
                        actions_layout.addWidget(restore_btn)
                        actions_layout.addWidget(open_btn)
                        actions_layout.addWidget(delete_btn)
                        actions_widget = QWidget()
                        actions_widget.setLayout(actions_layout)
                        for button in (restore_btn, open_btn, delete_btn):
                            button.ensurePolished()
                            button.setMinimumWidth(button.minimumSizeHint().width())
                        actions_widget.setMinimumWidth(sum(button.minimumWidth() for button in (restore_btn, open_btn, delete_btn)) + 2 * spacing.XSMALL + 16)
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

    def _action_error(self, message):
        # Keep the rows available after a recoverable operation failure.
        self.error_label.setText(message)
        self.error_label.show()
        self.status_label.setText(message)

    def open_backup(self, folder_id, archive_path):
        if self._thread is not None:
            return
        try:
            archive = self.backup_service.get_archive_path(folder_id, archive_path)
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(archive.parent))):
                raise RuntimeError("The backup directory could not be opened")
            self.error_label.hide()
            self.status_label.setText(f"Opened {archive.parent}")
        except Exception as exc:
            self._action_error(f"Unable to open backup: {exc}")

    def delete_backup(self, folder_id, archive_path):
        if self._thread is not None:
            return
        try:
            archive = self.backup_service.get_archive_path(folder_id, archive_path)
            answer = QMessageBox.question(
                self, "Delete backup", f"Permanently delete this backup archive?\n\n{archive}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
            self.backup_service.delete_backup(folder_id, archive)
            self.load_configuration_data()
            self.status_label.setText(f"Deleted {archive.name}")
        except Exception as exc:
            self._action_error(f"Unable to delete backup: {exc}")

    def restore_backup(self, folder_id, archive_path):
        if self._thread is not None:
            return
        try:
            archive = self.backup_service.get_archive_path(folder_id, archive_path)
            target = QFileDialog.getExistingDirectory(self, "Choose restore directory")
            if not target:
                return
            answer = QMessageBox.question(
                self, "Restore backup",
                f"Restore {archive.name} into:\n{target}\n\n"
                "Existing files with matching names will be overwritten. Other files will be retained.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
            self.error_label.hide()
            self.status_label.setText(f"Restoring {archive.name}…")
            self.refresh_btn.setEnabled(False)
            self.table.setEnabled(False)
            self._operation_result = None
            # Application ownership also protects against page removal during a restore.
            self._thread = QThread(QApplication.instance())
            self._worker = BackupWorker(self.backup_service, folder_id, str(archive), target)
            self._worker.moveToThread(self._thread)
            self._thread.started.connect(self._worker.run)
            self._worker.completed.connect(self._restore_completed)
            self._worker.failed.connect(self._restore_failed)
            self._worker.finished.connect(self._thread.quit, Qt.ConnectionType.DirectConnection)
            self._worker.finished.connect(self._worker.deleteLater)
            self._thread.finished.connect(self._restore_finished)
            self._thread.finished.connect(self._thread.deleteLater)
            # A page can be disposed before QApplication exits. The closure
            # remains connected independently of the page's QObject lifetime.
            thread = self._thread
            self._thread_cleanup = lambda: thread.wait() if isValid(thread) and thread.isRunning() else None
            self.destroyed.connect(self._thread_cleanup)
            self._thread.start()
        except Exception as exc:
            self.refresh_btn.setEnabled(True)
            self.table.setEnabled(True)
            self._action_error(f"Unable to restore backup: {exc}")

    @Slot(int)
    def _restore_completed(self, count):
        self._operation_result = (True, f"Restored {count} file(s)")

    @Slot(str)
    def _restore_failed(self, message):
        self._operation_result = (False, f"Unable to restore backup: {message}")

    @Slot()
    def _restore_finished(self):
        if self._thread_cleanup is not None:
            self.destroyed.disconnect(self._thread_cleanup)
            self._thread_cleanup = None
        self._worker = None
        self._thread = None
        self.refresh_btn.setEnabled(True)
        self.table.setEnabled(True)
        self.load_configuration_data()
        if self._operation_result:
            success, message = self._operation_result
            if success:
                self.status_label.setText(message)
            else:
                self._action_error(message)

    @Slot()
    def wait_for_finished(self):
        if self._thread is not None:
            self._thread.wait()

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
