from dataclasses import replace

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QGroupBox,
    QFormLayout,
    QSpinBox,
    QCheckBox,
    QComboBox,
    QPushButton,
    QHBoxLayout,
    QFrame,
    QScrollArea,
    QMessageBox,
)
from PySide6.QtCore import Qt
from ..themes import spacing
from backend.services.configuration_service import ConfigurationService
from backend.services.app_startup_service import AppStartupService
from src.config import AppConfig, GeneralSettings, SyncSettings, CopyEngineSettings, BackupSettings, SyncDirection, LogLevel, SyncTriggerSettings


class SettingsPage(QWidget):
    def __init__(self, config_service: ConfigurationService, parent=None, startup_service=None):
        super().__init__(parent)
        self.config_service = config_service
        self.startup_service = startup_service if startup_service is not None else AppStartupService()
        self._startup_enabled = False
        self._original_app_config: Optional[AppConfig] = None
        self._dirty = False
        self.setup_ui()
        # Load configuration data if backend is available
        app_config = self.config_service.get_app_config()
        if app_config:
            self._original_app_config = app_config
            self.load_configuration_data(app_config)
        else:
            self.show_no_config_message()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(spacing.LARGE, spacing.LARGE, spacing.LARGE, spacing.LARGE)
        layout.setSpacing(spacing.MEDIUM)

        startup_group = QGroupBox("App startup")
        startup_group.setProperty("card", "true")
        startup_layout = QVBoxLayout(startup_group)
        self.run_at_startup_check = QCheckBox("Run at startup")
        self.run_at_startup_check.setAccessibleName("Run at startup")
        self.run_at_startup_check.setToolTip("Open the desktop app when you sign in to Windows.")
        startup_layout.addWidget(self.run_at_startup_check)
        hint = QLabel("Open the app when you sign in to Windows. This choice is saved immediately. "
                      "Scheduled synchronization is configured separately.")
        hint.setWordWrap(True)
        hint.setProperty("description", "true")
        startup_layout.addWidget(hint)
        self.startup_status = QLabel()
        self.startup_status.setTextFormat(Qt.TextFormat.PlainText)
        self.startup_status.setWordWrap(True)
        startup_layout.addWidget(self.startup_status)
        self.startup_retry_button = QPushButton("Retry")
        self.startup_retry_button.clicked.connect(self.refresh_startup)
        startup_layout.addWidget(self.startup_retry_button)
        layout.addWidget(startup_group)
        self.run_at_startup_check.toggled.connect(self.set_run_at_startup)
        self.refresh_startup()

        # Scroll area for settings
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        self.settings_container = QWidget()
        self.settings_layout = QVBoxLayout(self.settings_container)
        self.settings_layout.setContentsMargins(0, 0, 0, 0)
        self.settings_layout.setSpacing(spacing.SMALL)
        scroll_area.setWidget(self.settings_container)
        layout.addWidget(scroll_area, 1)  # stretch factor 1

        # Button layout
        button_layout = QHBoxLayout()
        button_layout.setSpacing(spacing.SMALL)
        self.apply_button = QPushButton("Apply")
        self.apply_button.setProperty("primary", "true")
        self.apply_button.setToolTip("Apply changes")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setToolTip("Cancel changes")
        self.reset_button = QPushButton("Reset")
        self.reset_button.setToolTip("Reset to last saved state")
        button_layout.addWidget(self.apply_button)
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.reset_button)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Connect buttons
        self.apply_button.clicked.connect(self.on_apply_clicked)
        self.cancel_button.clicked.connect(self.on_cancel_clicked)
        self.reset_button.clicked.connect(self.on_reset_clicked)

        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setProperty("description", "true")
        layout.addWidget(self.status_label)

    def showEvent(self, event):
        self.refresh_startup()
        super().showEvent(event)

    def refresh_startup(self):
        supported = self.startup_service.supported
        self.run_at_startup_check.setEnabled(supported)
        self.startup_retry_button.hide()
        if not supported:
            self.startup_status.setText("Available in the installed Windows app.")
            return
        try:
            self._startup_enabled = self.startup_service.is_enabled()
            self._set_startup_checked(self._startup_enabled)
            self.startup_status.setText("Startup is enabled." if self._startup_enabled else "Startup is disabled.")
        except Exception as exc:
            self.run_at_startup_check.setEnabled(False)
            self.startup_status.setText(f"Cannot read the startup setting: {exc}")
            self.startup_retry_button.show()

    def _set_startup_checked(self, enabled):
        self.run_at_startup_check.blockSignals(True)
        self.run_at_startup_check.setChecked(enabled)
        self.run_at_startup_check.blockSignals(False)

    def set_run_at_startup(self, enabled):
        try:
            self.startup_service.set_enabled(enabled)
        except Exception as exc:
            self._set_startup_checked(self._startup_enabled)
            self.startup_status.setText(f"Could not change startup: {exc}")
            self.startup_retry_button.show()
            return
        self.refresh_startup()

    def load_configuration_data(self, app_config: AppConfig):
        """Load and display settings from the configuration."""
        try:
            self.clear_settings()

            general = app_config.general
            sync = app_config.sync
            copy_engine = app_config.copy_engine

            # General Settings
            general_group = QGroupBox("General Settings")
            general_group.setProperty("card", "true")
            general_layout = QFormLayout()
            general_group.setLayout(general_layout)

            # Log level
            self.log_level_combo = QComboBox()
            self.log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
            self.log_level_combo.setCurrentText(general.log_level.value)
            self.log_level_combo.setEnabled(True)
            self.log_level_combo.setProperty("value", "true")
            log_level_label = QLabel("Log Level:")
            log_level_label.setProperty("title", "true")
            general_layout.addRow(log_level_label, self.log_level_combo)

            # Dry run
            self.dry_run_check = QCheckBox()
            self.dry_run_check.setChecked(general.dry_run)
            self.dry_run_check.setEnabled(True)
            self.dry_run_check.setProperty("value", "true")
            dry_run_label = QLabel("Dry Run:")
            dry_run_label.setProperty("title", "true")
            general_layout.addRow(dry_run_label, self.dry_run_check)

            # Verify after sync
            self.verify_after_sync_check = QCheckBox()
            self.verify_after_sync_check.setChecked(general.verify_after_sync)
            self.verify_after_sync_check.setEnabled(True)
            self.verify_after_sync_check.setProperty("value", "true")
            verify_after_sync_label = QLabel("Verify After Sync:")
            verify_after_sync_label.setProperty("title", "true")
            general_layout.addRow(verify_after_sync_label, self.verify_after_sync_check)

            # Create destination
            self.create_destination_check = QCheckBox()
            self.create_destination_check.setChecked(general.create_destination)
            self.create_destination_check.setEnabled(True)
            self.create_destination_check.setProperty("value", "true")
            create_destination_label = QLabel("Create Destination:")
            create_destination_label.setProperty("title", "true")
            general_layout.addRow(create_destination_label, self.create_destination_check)

            # Max parallel jobs
            self.max_parallel_jobs_spin = QSpinBox()
            self.max_parallel_jobs_spin.setRange(1, 16)
            self.max_parallel_jobs_spin.setValue(general.max_parallel_jobs)
            self.max_parallel_jobs_spin.setEnabled(True)
            self.max_parallel_jobs_spin.setProperty("value", "true")
            max_parallel_jobs_label = QLabel("Max Parallel Jobs:")
            max_parallel_jobs_label.setProperty("title", "true")
            general_layout.addRow(max_parallel_jobs_label, self.max_parallel_jobs_spin)

            self.settings_layout.addWidget(general_group)

            # Synchronization Settings
            sync_group = QGroupBox("Synchronization Settings")
            sync_group.setProperty("card", "true")
            sync_layout = QFormLayout()
            sync_group.setLayout(sync_layout)

            # Startup sync
            self.startup_enabled_check = QCheckBox()
            self.startup_enabled_check.setChecked(sync.startup.enabled)
            self.startup_enabled_check.setEnabled(True)
            self.startup_enabled_check.setProperty("value", "true")
            startup_enabled_label = QLabel("Startup Sync Enabled:")
            startup_enabled_label.setProperty("title", "true")
            sync_layout.addRow(startup_enabled_label, self.startup_enabled_check)

            self.startup_direction_combo = QComboBox()
            self.startup_direction_combo.addItems(["Download", "Upload"])
            self.startup_direction_combo.setCurrentText(sync.startup.direction.value.capitalize())
            self.startup_direction_combo.setEnabled(True)
            self.startup_direction_combo.setProperty("value", "true")
            startup_direction_label = QLabel("Startup Sync Direction:")
            startup_direction_label.setProperty("title", "true")
            sync_layout.addRow(startup_direction_label, self.startup_direction_combo)

            # Shutdown sync
            self.shutdown_enabled_check = QCheckBox()
            self.shutdown_enabled_check.setChecked(sync.shutdown.enabled)
            self.shutdown_enabled_check.setEnabled(True)
            self.shutdown_enabled_check.setProperty("value", "true")
            shutdown_enabled_label = QLabel("Shutdown Sync Enabled:")
            shutdown_enabled_label.setProperty("title", "true")
            sync_layout.addRow(shutdown_enabled_label, self.shutdown_enabled_check)

            self.shutdown_direction_combo = QComboBox()
            self.shutdown_direction_combo.addItems(["Download", "Upload"])
            self.shutdown_direction_combo.setCurrentText(sync.shutdown.direction.value.capitalize())
            self.shutdown_direction_combo.setEnabled(True)
            self.shutdown_direction_combo.setProperty("value", "true")
            shutdown_direction_label = QLabel("Shutdown Sync Direction:")
            shutdown_direction_label.setProperty("title", "true")
            sync_layout.addRow(shutdown_direction_label, self.shutdown_direction_combo)

            self.settings_layout.addWidget(sync_group)

            # Copy Engine Settings
            copy_group = QGroupBox("Copy Engine Settings")
            copy_group.setProperty("card", "true")
            copy_layout = QFormLayout()
            copy_group.setLayout(copy_layout)

            # Retry count
            self.retry_spin = QSpinBox()
            self.retry_spin.setRange(0, 10)
            self.retry_spin.setValue(copy_engine.retry_count)
            self.retry_spin.setEnabled(True)
            self.retry_spin.setProperty("value", "true")
            retry_label = QLabel("Retry Count:")
            retry_label.setProperty("title", "true")
            copy_layout.addRow(retry_label, self.retry_spin)

            # Retry wait seconds
            self.retry_wait_spin = QSpinBox()
            self.retry_wait_spin.setRange(0, 60)
            self.retry_wait_spin.setValue(copy_engine.retry_wait_seconds)
            self.retry_wait_spin.setEnabled(True)
            self.retry_wait_spin.setProperty("value", "true")
            retry_wait_label = QLabel("Retry Wait (seconds):")
            retry_wait_label.setProperty("title", "true")
            copy_layout.addRow(retry_wait_label, self.retry_wait_spin)

            # Multithreading
            self.multi_spin = QSpinBox()
            self.multi_spin.setRange(1, 32)
            self.multi_spin.setValue(copy_engine.multithreading)
            self.multi_spin.setEnabled(True)
            self.multi_spin.setProperty("value", "true")
            multi_label = QLabel("Multithreading:")
            multi_label.setProperty("title", "true")
            copy_layout.addRow(multi_label, self.multi_spin)

            # Copy subdirectories
            self.subdir_check = QCheckBox()
            self.subdir_check.setChecked(copy_engine.copy_subdirectories)
            self.subdir_check.setEnabled(True)
            self.subdir_check.setProperty("value", "true")
            subdir_label = QLabel("Copy Subdirectories:")
            subdir_label.setProperty("title", "true")
            copy_layout.addRow(subdir_label, self.subdir_check)

            # Copy empty directories
            self.empty_dir_check = QCheckBox()
            self.empty_dir_check.setChecked(copy_engine.copy_empty_directories)
            self.empty_dir_check.setEnabled(True)
            self.empty_dir_check.setProperty("value", "true")
            empty_dir_label = QLabel("Copy Empty Directories:")
            empty_dir_label.setProperty("title", "true")
            copy_layout.addRow(empty_dir_label, self.empty_dir_check)

            # Exclude junctions
            self.exclude_junc_check = QCheckBox()
            self.exclude_junc_check.setChecked(copy_engine.exclude_junctions)
            self.exclude_junc_check.setEnabled(True)
            self.exclude_junc_check.setProperty("value", "true")
            exclude_junc_label = QLabel("Exclude Junctions:")
            exclude_junc_label.setProperty("title", "true")
            copy_layout.addRow(exclude_junc_label, self.exclude_junc_check)

            # FAT file times
            self.fat_time_check = QCheckBox()
            self.fat_time_check.setChecked(copy_engine.fat_file_times)
            self.fat_time_check.setEnabled(True)
            self.fat_time_check.setProperty("value", "true")
            fat_time_label = QLabel("FAT File Times:")
            fat_time_label.setProperty("title", "true")
            copy_layout.addRow(fat_time_label, self.fat_time_check)

            # Monitor mode
            self.monitor_check = QCheckBox()
            self.monitor_check.setChecked(copy_engine.monitor_mode)
            self.monitor_check.setEnabled(True)
            self.monitor_check.setProperty("value", "true")
            self.monitor_check.setToolTip("While the app is open, changes trigger the configured shutdown sync. Pause UI Sync postpones monitored runs.")
            self.exclude_junc_check.setToolTip("When disabled, links within the source tree are followed once. Links outside the source remain excluded for safety.")
            monitor_label = QLabel("Monitor Changes:")
            monitor_label.setProperty("title", "true")
            copy_layout.addRow(monitor_label, self.monitor_check)

            self.settings_layout.addWidget(copy_group)

            # Backup Settings (global note)
            backup_group = QGroupBox("Backup Settings")
            backup_group.setProperty("card", "true")
            backup_layout = QVBoxLayout()
            backup_group.setLayout(backup_layout)

            backup_note = QLabel("Backup settings are configured per folder in the Folders page.")
            backup_note.setWordWrap(True)
            backup_note.setProperty("description", "true")
            backup_layout.addWidget(backup_note)

            self.settings_layout.addWidget(backup_group)

            self.settings_layout.addStretch()

            self.status_label.setText("Settings loaded successfully")
        except Exception as e:
            self.show_error(f"Error loading settings data: {e}")

    def clear_settings(self):
        """Clear all settings widgets from the layout."""
        while self.settings_layout.count():
            item = self.settings_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        # Clear widget references for settings (not buttons)
        self.log_level_combo = None
        self.dry_run_check = None
        self.verify_after_sync_check = None
        self.create_destination_check = None
        self.max_parallel_jobs_spin = None
        self.startup_enabled_check = None
        self.startup_direction_combo = None
        self.shutdown_enabled_check = None
        self.shutdown_direction_combo = None
        self.retry_spin = None
        self.retry_wait_spin = None
        self.multi_spin = None
        self.subdir_check = None
        self.empty_dir_check = None
        self.exclude_junc_check = None
        self.fat_time_check = None
        self.monitor_check = None

    def show_no_config_message(self):
        """Show a message when no configuration is available."""
        self.clear_settings()
        label = QLabel("No configuration available.\n"
                       "Settings cannot be displayed.")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        self.settings_layout.addWidget(label)

    def on_apply_clicked(self):
        """Handle the Apply button click."""
        # If there's no original config, we cannot apply changes.
        if self._original_app_config is None:
            QMessageBox.warning(
                self,
                "No Configuration",
                "Cannot apply changes because no configuration is loaded.",
                QMessageBox.StandardButton.Ok,
            )
            return

        try:
            # Collect values from widgets
            log_level = LogLevel(self.log_level_combo.currentText())
            dry_run = self.dry_run_check.isChecked()
            verify_after_sync = self.verify_after_sync_check.isChecked()
            create_destination = self.create_destination_check.isChecked()
            max_parallel_jobs = self.max_parallel_jobs_spin.value()

            startup_enabled = self.startup_enabled_check.isChecked()
            startup_direction = SyncDirection(
                self.startup_direction_combo.currentText().lower()
            )
            shutdown_enabled = self.shutdown_enabled_check.isChecked()
            shutdown_direction = SyncDirection(
                self.shutdown_direction_combo.currentText().lower()
            )

            retry_count = self.retry_spin.value()
            retry_wait_seconds = self.retry_wait_spin.value()
            multithreading = self.multi_spin.value()
            copy_subdirectories = self.subdir_check.isChecked()
            copy_empty_directories = self.empty_dir_check.isChecked()
            exclude_junctions = self.exclude_junc_check.isChecked()
            fat_file_times = self.fat_time_check.isChecked()
            monitor_mode = self.monitor_check.isChecked()

            # Preserve current folders and connections changed on other pages.
            new_app_config = replace(
                self.config_service.get_app_config(),
                general=GeneralSettings(
                    log_level=log_level,
                    dry_run=dry_run,
                    verify_after_sync=verify_after_sync,
                    create_destination=create_destination,
                    max_parallel_jobs=max_parallel_jobs,
                ),
                sync=SyncSettings(
                    startup=SyncTriggerSettings(
                        enabled=startup_enabled,
                        direction=startup_direction,
                    ),
                    shutdown=SyncTriggerSettings(
                        enabled=shutdown_enabled,
                        direction=shutdown_direction,
                    ),
                ),
                copy_engine=CopyEngineSettings(
                    retry_count=retry_count,
                    retry_wait_seconds=retry_wait_seconds,
                    multithreading=multithreading,
                    copy_subdirectories=copy_subdirectories,
                    copy_empty_directories=copy_empty_directories,
                    exclude_junctions=exclude_junctions,
                    fat_file_times=fat_file_times,
                    monitor_mode=monitor_mode,
                ),
            )

            # Save the new configuration
            self.config_service.save(new_app_config)

            # Update the original config and reset dirty state
            self._original_app_config = new_app_config
            self._dirty = False
            self.status_label.setText("Settings saved successfully")

            # Show success message
            QMessageBox.information(
                self,
                "Settings Saved",
                "Your settings have been saved successfully.",
                QMessageBox.StandardButton.Ok,
            )

        except Exception as e:
            QMessageBox.warning(
                self,
                "Failed to Apply Changes",
                f"An error occurred while applying changes: {e}",
                QMessageBox.StandardButton.Ok,
            )
            self.status_label.setText(f"Error: {e}")

    def on_cancel_clicked(self):
        """Handle the Cancel button click - discard changes."""
        if self._original_app_config is None:
            # If there's no original config, show the no config message
            self.show_no_config_message()
            self._dirty = False
            self.status_label.setText("No configuration available")
            return

        # Reload the original configuration
        self.load_configuration_data(self._original_app_config)
        self._dirty = False
        self.status_label.setText("Changes discarded")

    def on_reset_clicked(self):
        """Handle the Reset button click - reset to last saved state."""
        # In this implementation, Reset is the same as Cancel
        self.on_cancel_clicked()

    def show_error(self, message):
        """Show an error message."""
        self.clear_settings()
        label = QLabel(f"Error:\n{message}")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        self.settings_layout.addWidget(label)

    # For compatibility with the existing MainWindow, we keep the config_backend argument
    # even though we don't use it.
