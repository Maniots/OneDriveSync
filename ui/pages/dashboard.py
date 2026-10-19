from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QSizePolicy,
    QGridLayout,
    QPushButton,
    QScrollArea,
)
from PySide6.QtCore import Qt, QTimer, QSize, Slot
from backend.services.configuration_service import ConfigurationService
from backend.services.sync_service import SyncService
from backend.services.backup_service import BackupService
from backend.services.scheduler_service import SchedulerService
from backend.services.monitor_service import MonitorService
from backend.services.log_service import LogService
from ..widgets.sync_chart import SyncChartWidget
import time
from datetime import datetime
import shutil
from ..themes import spacing
from ..resources.icons import get_icon
from ..models.synchronization_results import activity_results


class DashboardPage(QWidget):
    def __init__(self, config_service: ConfigurationService, sync_service: SyncService, backup_service: BackupService, scheduler_service: SchedulerService, monitor_service: MonitorService, log_service: LogService, parent=None):
        super().__init__(parent)
        self.config_service = config_service
        self.sync_service = sync_service
        self.backup_service = backup_service
        self.scheduler_service = scheduler_service
        self.monitor_service = monitor_service
        self.log_service = log_service
        if hasattr(self.scheduler_service, "updated"):
            self.scheduler_service.updated.connect(self.on_scheduler_updated)
            self.destroyed.connect(self.scheduler_service.wait_for_finished)
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
        layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        body = QVBoxLayout(content)
        body.setContentsMargins(spacing.LARGE, spacing.MEDIUM, spacing.LARGE, spacing.LARGE)
        body.setSpacing(spacing.MEDIUM)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        # Existing actions and signal connections, surfaced above the details.
        hero = QFrame()
        hero.setProperty("card", "true")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(24, 22, 24, 22)
        hero_layout.setSpacing(12)
        eyebrow = QLabel("SYNC CONTROL")
        eyebrow.setProperty("eyebrow", "true")
        hero_layout.addWidget(eyebrow)
        self.status_label = QLabel("Idle")
        self.status_label.setProperty("h2", "true")
        self.status_label.setWordWrap(True)
        hero_layout.addWidget(self.status_label)
        hint = QLabel("Run your configured startup or shutdown sync without leaving your desktop.")
        hint.setProperty("description", "true")
        hint.setWordWrap(True)
        hero_layout.addWidget(hint)
        actions = QHBoxLayout()
        actions.setSpacing(12)
        self.startup_button = QPushButton("Run startup sync")
        self.startup_button.setIcon(get_icon("download"))
        self.startup_button.setToolTip("Run the startup synchronization with its configured direction.")
        self.startup_button.clicked.connect(self.start_startup_sync)
        self.shutdown_button = QPushButton("Run shutdown sync")
        self.shutdown_button.setIcon(get_icon("upload"))
        self.shutdown_button.setProperty("primary", "true")
        self.shutdown_button.setToolTip("Run the shutdown synchronization with its configured direction.")
        self.shutdown_button.clicked.connect(self.start_shutdown_sync)
        actions.addWidget(self.startup_button)
        actions.addWidget(self.shutdown_button)
        actions.addStretch()
        hero_layout.addLayout(actions)
        body.addWidget(hero)

        # Keep the original label attributes so service updates remain intact.
        summary = QHBoxLayout()
        summary.setSpacing(16)
        for title, attribute, initial, icon in [
            ("Last sync", "last_sync_label", "Never", "sync"),
            ("Next sync", "next_sync_label", "N/A", "scheduler"),
            ("Backups", "backup_status_label", "No backups", "backups"),
        ]:
            card = QFrame()
            card.setProperty("card", "true")
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(18, 16, 18, 16)
            card_layout.setSpacing(10)
            caption_row = QHBoxLayout()
            caption = QLabel(title)
            caption.setProperty("title", "true")
            caption_row.addWidget(caption)
            caption_row.addStretch()
            icon_label = QLabel()
            icon_label.setPixmap(get_icon(icon).pixmap(QSize(16, 16)))
            caption_row.addWidget(icon_label)
            card_layout.addLayout(caption_row)
            value = QLabel(initial)
            value.setProperty("value", "true")
            value.setWordWrap(True)
            setattr(self, attribute, value)
            card_layout.addWidget(value)
            summary.addWidget(card, 1)
        body.addLayout(summary)

        activity = QFrame()
        activity.setProperty("card", "true")
        activity_layout = QVBoxLayout(activity)
        activity_layout.setContentsMargins(20, 18, 20, 16)
        activity_layout.setSpacing(8)
        activity_title = QLabel("Sync activity")
        activity_title.setProperty("h3", "true")
        activity_layout.addWidget(activity_title)
        activity_hint = QLabel("Successful folders per run · recent history")
        activity_hint.setProperty("description", "true")
        activity_layout.addWidget(activity_hint)
        self.chart_widget = SyncChartWidget()
        activity_layout.addWidget(self.chart_widget)
        body.addWidget(activity)

        details = QFrame()
        details.setProperty("card", "true")
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(20, 18, 20, 20)
        details_layout.setSpacing(16)
        details_title = QLabel("Run details")
        details_title.setProperty("h3", "true")
        details_layout.addWidget(details_title)
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(12)
        fields = [
            ("Operation", "current_operation_label", "None"),
            ("Current folder", "current_folder_label", "N/A"),
            ("Direction", "direction_label", "N/A"),
            ("Elapsed time", "elapsed_time_label", "00:00:00"),
            ("Result", "result_label", "N/A"),
            ("OneDrive disk", "storage_label", "N/A"),
            ("Last successful folder", "last_successful_label", "None"),
            ("Last failed folder", "last_failed_label", "None"),
        ]
        for index, (title, attribute, initial) in enumerate(fields):
            row, column = divmod(index, 2)
            field = QVBoxLayout()
            field.setSpacing(4)
            caption = QLabel(title)
            caption.setProperty("title", "true")
            value = QLabel(initial)
            value.setProperty("value", "true")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            setattr(self, attribute, value)
            field.addWidget(caption)
            field.addWidget(value)
            grid.addLayout(field, row, column)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        details_layout.addLayout(grid)
        body.addWidget(details)
        body.addStretch()

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
            active_direction = getattr(self.sync_service, "active_direction", None)
            if active_direction is not None:
                direction = active_direction.value
            elif operation == "startup":
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
        outcomes = activity_results(outcomes, self.config_service.get_app_config())
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

    @Slot(object)
    def on_scheduler_updated(self, summary):
        self.update_data()

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
                history = self.sync_service.get_history() if hasattr(self.sync_service, "get_history") else []
                if getattr(self.sync_service, "history_error", None):
                    self.last_sync_label.setText("History unavailable")
                    self.last_sync_label.setToolTip(self.sync_service.history_error)
                if history:
                    latest = history[0]
                    self.last_sync_label.setText(datetime.fromisoformat(latest["timestamp"]).astimezone().strftime("%Y-%m-%d %H:%M:%S"))
                    self.chart_data = [sum(o["succeeded"] for o in activity_results(run["outcomes"], app_config)) for run in reversed(history)]
                    self.chart_widget.set_data(list(range(len(self.chart_data))), self.chart_data)
                    if not self.sync_service.is_syncing:
                        outcomes = activity_results(latest["outcomes"], app_config)
                        successes = [o["folder_name"] for o in outcomes if o["succeeded"]]
                        failures = [o["folder_name"] for o in outcomes if not o["succeeded"]]
                        self.result_label.setText(f"Succeeded: {len(successes)}, Failed: {len(failures)}" + (" (dry run)" if latest["dry_run"] else ""))
                        self.last_successful_label.setText(successes[-1] if successes else "None")
                        self.last_failed_label.setText(failures[-1] if failures else "None")
                        self.current_operation_label.setText(latest["mode"].capitalize())
                        self.direction_label.setText(outcomes[0]["direction"].capitalize() if outcomes else "N/A")
                if self.scheduler_service and hasattr(self.scheduler_service, "request_refresh"):
                    self.scheduler_service.request_refresh()
                    summary = self.scheduler_service.cached_summary
                else:
                    summary = self.scheduler_service.get_scheduler_summary() if self.scheduler_service else None
                tasks = list((summary or {}).values())
                times = [datetime.fromisoformat(t["next_run_time"]).astimezone() for t in tasks if t and t.get("enabled") == "Enabled" and t.get("next_run_time")]
                if times:
                    self.next_sync_label.setText(min(times).strftime("%d %b %H:%M"))
                elif any(t and t.get("enabled") == "Enabled" for t in tasks):
                    self.next_sync_label.setText("On logon / lock")
                else:
                    self.next_sync_label.setText("No scheduled sync" if summary and all(t and t.get("enabled") != "Unknown" for t in tasks) else "Unavailable")
                if app_config.folders:
                    disk_path = app_config.folders[0].onedrive_path_resolved
                    while not disk_path.exists() and disk_path != disk_path.parent:
                        disk_path = disk_path.parent
                    disk = shutil.disk_usage(disk_path)
                    self.storage_label.setText(f"{disk.free / 1024**3:.1f} GB free")
                    self.storage_label.setToolTip(f"Free space on the disk containing {disk_path}")
                else:
                    self.storage_label.setText("No folders configured")
                # We'll check if there are any backups for any folder
                has_backups = False
                backups_configured = False
                for folder in app_config.folders:
                    if folder.backup and folder.backup.enabled:
                        backups_configured = True
                        backup_info = self.backup_service.get_backup_info(folder.id)
                        if backup_info:
                            has_backups = True
                            break
                if has_backups:
                    self.backup_status_label.setText("Backups available")
                elif backups_configured:
                    self.backup_status_label.setText("No archives yet")
                else:
                    self.backup_status_label.setText("No backups configured")
            else:
                self.backup_status_label.setText("Configuration not available")

        except Exception as e:
            # In case of error, we don't want to crash the dashboard
            self.backup_status_label.setText("Status unavailable")
            self.backup_status_label.setToolTip(str(e))
