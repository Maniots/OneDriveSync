from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QSizePolicy,
    QSpacerItem,
    QGridLayout,
    QPushButton,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QColor, QPen, QBrush
from backend.services.configuration_service import ConfigurationService
from backend.services.sync_service import SyncService
from backend.services.backup_service import BackupService
from backend.services.scheduler_service import SchedulerService
from backend.services.monitor_service import MonitorService
from backend.services.log_service import LogService
from ..widgets.sync_chart import SyncChartWidget
import time
from datetime import datetime
from ..themes import spacing


class DashboardPage(QWidget):
    def __init__(self, config_service: ConfigurationService, sync_service: SyncService, backup_service: BackupService, scheduler_service: SchedulerService, monitor_service: MonitorService, log_service: LogService, parent=None):
        super().__init__(parent)
        self.config_service = config_service
        self.sync_service = sync_service
        self.backup_service = backup_service
        self.scheduler_service = scheduler_service
        self.monitor_service = monitor_service
        self.log_service = log_service
        self.chart_data = []  # For the sync chart
        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.timeout.connect(self.update_elapsed_time)
        self.sync_start_time = 0
        self.setup_ui()
        if isinstance(self.sync_service, SyncService):
            self.sync_service.started.connect(self.on_sync_started)
            self.sync_service.progress.connect(self.on_sync_progress)
            self.sync_service.completed.connect(self.on_sync_completed)
            self.sync_service.failed.connect(self.on_sync_failed)
            self.sync_service.finished.connect(self.on_sync_finished)
            self.sync_service.state_changed.connect(self.update_sync_controls)
            self.update_sync_controls()
        # Timer for updating data (backup status, etc.)
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_data)
        self.update_timer.start(5000)  # update every 5 seconds
        # Initial update
        self.update_data()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(spacing.LARGE, spacing.LARGE, spacing.LARGE, spacing.LARGE)
        layout.setSpacing(spacing.MEDIUM)

        # Title
        title = QLabel("Dashboard")
        title.setProperty("h2", "true")
        layout.addWidget(title)

        # Sync Chart
        self.chart_widget = SyncChartWidget()
        layout.addWidget(self.chart_widget, 1)  # stretch factor 1

        # Stats grid
        stats_frame = QFrame()
        stats_frame.setProperty("card", "true")
        stats_layout = QGridLayout(stats_frame)
        stats_layout.setContentsMargins(spacing.MEDIUM, spacing.MEDIUM, spacing.MEDIUM, spacing.MEDIUM)
        stats_layout.setSpacing(spacing.SMALL)

        # Status
        status_label_text = QLabel("Sync Status:")
        status_label_text.setProperty("title", "true")
        stats_layout.addWidget(status_label_text, 0, 0)
        self.status_label = QLabel("Idle")
        self.status_label.setProperty("value", "true")
        stats_layout.addWidget(self.status_label, 0, 1)

        # Last Sync
        last_sync_label_text = QLabel("Last Sync:")
        last_sync_label_text.setProperty("title", "true")
        stats_layout.addWidget(last_sync_label_text, 0, 2)
        self.last_sync_label = QLabel("Never")
        self.last_sync_label.setProperty("value", "true")
        stats_layout.addWidget(self.last_sync_label, 0, 3)

        # Next Sync
        next_sync_label_text = QLabel("Next Sync:")
        next_sync_label_text.setProperty("title", "true")
        stats_layout.addWidget(next_sync_label_text, 1, 0)
        self.next_sync_label = QLabel("N/A")
        self.next_sync_label.setProperty("value", "true")
        stats_layout.addWidget(self.next_sync_label, 1, 1)

        # Storage
        storage_label_text = QLabel("Storage:")
        storage_label_text.setProperty("title", "true")
        stats_layout.addWidget(storage_label_text, 1, 2)
        self.storage_label = QLabel("N/A")
        self.storage_label.setProperty("value", "true")
        stats_layout.addWidget(self.storage_label, 1, 3)

        # Backup Status
        backup_status_label_text = QLabel("Backup Status:")
        backup_status_label_text.setProperty("title", "true")
        stats_layout.addWidget(backup_status_label_text, 2, 0)
        self.backup_status_label = QLabel("No backups")
        self.backup_status_label.setProperty("value", "true")
        stats_layout.addWidget(self.backup_status_label, 2, 1)

        # New fields for sync state
        current_operation_label_text = QLabel("Current Operation:")
        current_operation_label_text.setProperty("title", "true")
        stats_layout.addWidget(current_operation_label_text, 3, 0)
        self.current_operation_label = QLabel("None")
        self.current_operation_label.setProperty("value", "true")
        stats_layout.addWidget(self.current_operation_label, 3, 1)

        current_folder_label_text = QLabel("Current Folder:")
        current_folder_label_text.setProperty("title", "true")
        stats_layout.addWidget(current_folder_label_text, 3, 2)
        self.current_folder_label = QLabel("N/A")
        self.current_folder_label.setProperty("value", "true")
        stats_layout.addWidget(self.current_folder_label, 3, 3)

        direction_label_text = QLabel("Direction:")
        direction_label_text.setProperty("title", "true")
        stats_layout.addWidget(direction_label_text, 4, 0)
        self.direction_label = QLabel("N/A")
        self.direction_label.setProperty("value", "true")
        stats_layout.addWidget(self.direction_label, 4, 1)

        elapsed_time_label_text = QLabel("Elapsed Time:")
        elapsed_time_label_text.setProperty("title", "true")
        stats_layout.addWidget(elapsed_time_label_text, 4, 2)
        self.elapsed_time_label = QLabel("00:00:00")
        self.elapsed_time_label.setProperty("value", "true")
        stats_layout.addWidget(self.elapsed_time_label, 4, 3)

        result_label_text = QLabel("Result:")
        result_label_text.setProperty("title", "true")
        stats_layout.addWidget(result_label_text, 5, 0)
        self.result_label = QLabel("N/A")
        self.result_label.setProperty("value", "true")
        stats_layout.addWidget(self.result_label, 5, 1)

        last_successful_label_text = QLabel("Last Successful Sync:")
        last_successful_label_text.setProperty("title", "true")
        stats_layout.addWidget(last_successful_label_text, 5, 2)
        self.last_successful_label = QLabel("None")
        self.last_successful_label.setProperty("value", "true")
        stats_layout.addWidget(self.last_successful_label, 5, 3)

        last_failed_label_text = QLabel("Last Failed Sync:")
        last_failed_label_text.setProperty("title", "true")
        stats_layout.addWidget(last_failed_label_text, 6, 0)
        self.last_failed_label = QLabel("None")
        self.last_failed_label.setProperty("value", "true")
        stats_layout.addWidget(self.last_failed_label, 6, 1)

        # Buttons to start sync (for demonstration)
        button_layout = QHBoxLayout()
        button_layout.setSpacing(spacing.SMALL)
        self.startup_button = QPushButton("Start Startup Sync")
        self.startup_button.clicked.connect(self.start_startup_sync)
        button_layout.addWidget(self.startup_button)

        self.shutdown_button = QPushButton("Start Shutdown Sync")
        self.shutdown_button.clicked.connect(self.start_shutdown_sync)
        button_layout.addWidget(self.shutdown_button)

        stats_layout.addLayout(button_layout, 7, 0, 1, 4)

        layout.addWidget(stats_frame)

    def start_startup_sync(self):
        self.sync_service.request_sync("startup")

    def start_shutdown_sync(self):
        self.sync_service.request_sync("shutdown")

    def update_sync_controls(self):
        available = not self.sync_service.is_syncing and not self.sync_service.is_paused
        self.startup_button.setEnabled(available and self.sync_service.is_startup_sync_enabled())
        self.shutdown_button.setEnabled(available and self.sync_service.is_shutdown_sync_enabled())

    def on_sync_started(self, operation: str):
        """Handle the sync started signal."""
        self.sync_start_time = time.monotonic()
        self.elapsed_time_label.setText("00:00:00")
        self.elapsed_timer.start(1000)
        self.status_label.setText(f"{operation.capitalize()} synchronization in progress...")
        self.current_operation_label.setText(operation.capitalize())
        # Reset current folder
        self.current_folder_label.setText("Processing...")
        # Get direction from config
        app_config = self.config_service.get_app_config()
        if app_config:
            if operation == "startup":
                direction = app_config.sync.startup.direction.value
            else:
                direction = app_config.sync.shutdown.direction.value
            self.direction_label.setText(direction)
        else:
            self.direction_label.setText("N/A")

    def on_sync_progress(self, percentage: int, message: str):
        """Handle the sync progress signal."""
        # Update current folder label with progress message
        self.current_folder_label.setText(message)

    def on_sync_completed(self, outcomes):
        """Handle the sync completed signal."""
        failed_count = sum(1 for o in outcomes if not o.succeeded)
        self.status_label.setText("Sync completed with errors" if failed_count else "Sync completed successfully")
        self.last_sync_label.setText(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self.chart_data.append(sum(1 for o in outcomes if o.succeeded))
        self.chart_widget.set_data(list(range(len(self.chart_data))), self.chart_data)
        self.result_label.setText(f"Succeeded: {sum(1 for o in outcomes if o.succeeded)}, Failed: {sum(1 for o in outcomes if not o.succeeded)}")
        # Determine last successful and failed folder (by order in outcomes)
        last_successful = "None"
        last_failed = "None"
        # We'll go through the outcomes in reverse to get the last one that succeeded/failed
        for outcome in reversed(outcomes):
            if outcome.succeeded and last_successful == "None":
                last_successful = outcome.folder_name
            if not outcome.succeeded and last_failed == "None":
                last_failed = outcome.folder_name
            if last_successful != "None" and last_failed != "None":
                break
        self.last_successful_label.setText(last_successful)
        self.last_failed_label.setText(last_failed)


    def on_sync_failed(self, error_message: str):
        """Handle the sync failed signal."""
        self.status_label.setText(f"Sync failed: {error_message}")
        self.result_label.setText("Failed")
        self.last_failed_label.setText("Error")
        self.last_successful_label.setText("None")

    def on_sync_finished(self):
        """Common cleanup after sync finishes (success or failed)."""
        # Re-enable buttons
        self.update_elapsed_time()
        self.update_sync_controls()
        # Stop the elapsed time timer
        self.elapsed_timer.stop()
        # SyncService owns and disposes the background worker and thread.

    def update_elapsed_time(self):
        """Update the elapsed time label."""
        if self.sync_start_time == 0:
            # If not started, show 00:00:00
            self.elapsed_time_label.setText("00:00:00")
            return
        elapsed_seconds = int(time.monotonic() - self.sync_start_time)
        hours = elapsed_seconds // 3600
        minutes = (elapsed_seconds % 3600) // 60
        seconds = elapsed_seconds % 60
        self.elapsed_time_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

    def update_data(self):
        """Update all dashboard data from the services."""
        try:
            if isinstance(self.sync_service, SyncService):
                self.update_sync_controls()

            # Update backup status from backup service
            # We'll get the backup information for the first folder? Or we can show a summary.
            # We'll get the backup information for all folders and show if there are any backups.
            app_config = self.config_service.get_app_config()
            if app_config:
                # We'll check if there are any backups for any folder
                has_backups = False
                for folder in app_config.folders:
                    if folder.backup and folder.backup.enabled:
                        backup_info = self.backup_service.get_backup_info(folder.id)
                        if backup_info:
                            has_backups = True
                            break
                if has_backups:
                    self.backup_status_label.setText("Backups available")
                else:
                    self.backup_status_label.setText("No backups configured")
            else:
                self.backup_status_label.setText("Configuration not available")

        except Exception as e:
            # In case of error, we don't want to crash the dashboard
            pass