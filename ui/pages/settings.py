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
from backend.services.configuration_service import ConfigurationService
from src.config import AppConfig, GeneralSettings, SyncSettings, CopyEngineSettings, BackupSettings, SyncDirection


class SettingsPage(QWidget):
    def __init__(self, config_service: ConfigurationService, parent=None):
        super().__init__(parent)
        self.config_service = config_service
        self.setup_ui()
        # Load configuration data if backend is available
        app_config = self.config_service.get_app_config()
        if app_config:
            self.load_configuration_data(app_config)
        else:
            self.show_no_config_message()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # Scroll area for settings
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        self.settings_container = QWidget()
        self.settings_layout = QVBoxLayout(self.settings_container)
        self.settings_layout.setContentsMargins(0, 0, 0, 0)
        self.settings_layout.setSpacing(12)
        scroll_area.setWidget(self.settings_container)
        layout.addWidget(scroll_area, 1)  # stretch factor 1

        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

    def load_configuration_data(self, app_config: AppConfig):
        """Load and display settings from the configuration."""
        try:
            self.clear_settings()

            general = app_config.general
            sync = app_config.sync
            copy_engine = app_config.copy_engine

            # General Settings
            general_group = QGroupBox("General Settings")
            general_layout = QFormLayout()
            general_group.setLayout(general_layout)

            # Log level
            log_level_combo = QComboBox()
            log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
            log_level_combo.setCurrentText(general.log_level.value)
            log_level_combo.setEnabled(False)  # Read-only as per requirements
            general_layout.addRow("Log Level:", log_level_combo)

            # Dry run
            dry_run_check = QCheckBox()
            dry_run_check.setChecked(general.dry_run)
            dry_run_check.setEnabled(False)
            general_layout.addRow("Dry Run:", dry_run_check)

            # Verify after sync
            verify_check = QCheckBox()
            verify_check.setChecked(general.verify_after_sync)
            verify_check.setEnabled(False)
            general_layout.addRow("Verify After Sync:", verify_check)

            # Create destination
            create_dest_check = QCheckBox()
            create_dest_check.setChecked(general.create_destination)
            create_dest_check.setEnabled(False)
            general_layout.addRow("Create Destination:", create_dest_check)

            # Max parallel jobs
            max_jobs_spin = QSpinBox()
            max_jobs_spin.setRange(1, 16)
            max_jobs_spin.setValue(general.max_parallel_jobs)
            max_jobs_spin.setEnabled(False)
            general_layout.addRow("Max Parallel Jobs:", max_jobs_spin)

            self.settings_layout.addWidget(general_group)

            # Synchronization Settings
            sync_group = QGroupBox("Synchronization Settings")
            sync_layout = QFormLayout()
            sync_group.setLayout(sync_layout)

            # Startup sync
            startup_enabled_check = QCheckBox()
            startup_enabled_check.setChecked(sync.startup.enabled)
            startup_enabled_check.setEnabled(False)
            sync_layout.addRow("Startup Sync Enabled:", startup_enabled_check)

            startup_direction_combo = QComboBox()
            startup_direction_combo.addItems(["Download", "Upload"])
            startup_direction_combo.setCurrentText(sync.startup.direction.value.capitalize())
            startup_direction_combo.setEnabled(False)
            sync_layout.addRow("Startup Sync Direction:", startup_direction_combo)

            # Shutdown sync
            shutdown_enabled_check = QCheckBox()
            shutdown_enabled_check.setChecked(sync.shutdown.enabled)
            shutdown_enabled_check.setEnabled(False)
            sync_layout.addRow("Shutdown Sync Enabled:", shutdown_enabled_check)

            shutdown_direction_combo = QComboBox()
            shutdown_direction_combo.addItems(["Download", "Upload"])
            shutdown_direction_combo.setCurrentText(sync.shutdown.direction.value.capitalize())
            shutdown_direction_combo.setEnabled(False)
            sync_layout.addRow("Shutdown Sync Direction:", shutdown_direction_combo)

            self.settings_layout.addWidget(sync_group)

            # Copy Engine Settings
            copy_group = QGroupBox("Copy Engine Settings")
            copy_layout = QFormLayout()
            copy_group.setLayout(copy_layout)

            # Retry count
            retry_spin = QSpinBox()
            retry_spin.setRange(0, 10)
            retry_spin.setValue(copy_engine.retry_count)
            retry_spin.setEnabled(False)
            copy_layout.addRow("Retry Count:", retry_spin)

            # Retry wait seconds
            retry_wait_spin = QSpinBox()
            retry_wait_spin.setRange(0, 60)
            retry_wait_spin.setValue(copy_engine.retry_wait_seconds)
            retry_wait_spin.setEnabled(False)
            copy_layout.addRow("Retry Wait (seconds):", retry_wait_spin)

            # Multithreading
            multi_spin = QSpinBox()
            multi_spin.setRange(1, 32)
            multi_spin.setValue(copy_engine.multithreading)
            multi_spin.setEnabled(False)
            copy_layout.addRow("Multithreading:", multi_spin)

            # Copy subdirectories
            subdir_check = QCheckBox()
            subdir_check.setChecked(copy_engine.copy_subdirectories)
            subdir_check.setEnabled(False)
            copy_layout.addRow("Copy Subdirectories:", subdir_check)

            # Copy empty directories
            empty_dir_check = QCheckBox()
            empty_dir_check.setChecked(copy_engine.copy_empty_directories)
            empty_dir_check.setEnabled(False)
            copy_layout.addRow("Copy Empty Directories:", empty_dir_check)

            # Exclude junctions
            exclude_junc_check = QCheckBox()
            exclude_junc_check.setChecked(copy_engine.exclude_junctions)
            exclude_junc_check.setEnabled(False)
            copy_layout.addRow("Exclude Junctions:", exclude_junc_check)

            # FAT file times
            fat_time_check = QCheckBox()
            fat_time_check.setChecked(copy_engine.fat_file_times)
            fat_time_check.setEnabled(False)
            copy_layout.addRow("FAT File Times:", fat_time_check)

            # Monitor mode
            monitor_check = QCheckBox()
            monitor_check.setChecked(copy_engine.monitor_mode)
            monitor_check.setEnabled(False)
            copy_layout.addRow("Monitor Mode:", monitor_check)

            self.settings_layout.addWidget(copy_group)

            # Backup Settings (global note)
            backup_group = QGroupBox("Backup Settings")
            backup_layout = QVBoxLayout()
            backup_group.setLayout(backup_layout)

            backup_note = QLabel("Backup settings are configured per folder in the Folders page.")
            backup_note.setWordWrap(True)
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

    def show_no_config_message(self):
        """Show a message when no configuration is available."""
        self.clear_settings()
        label = QLabel("No configuration available.\n"
                       "Settings cannot be displayed.")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        self.settings_layout.addWidget(label)

    def show_error(self, message):
        """Show an error message."""
        self.clear_settings()
        label = QLabel(f"Error:\n{message}")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        self.settings_layout.addWidget(label)

    # For compatibility with the existing MainWindow, we keep the config_backend argument
    # even though we don't use it.