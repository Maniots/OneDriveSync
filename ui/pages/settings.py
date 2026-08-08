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
from ..config import convert_to_ui_models


class SettingsPage(QWidget):
    def __init__(self, config_backend=None, parent=None):
        super().__init__(parent)
        self.config_backend = config_backend
        self.setup_ui()
        # Load configuration data if backend is available
        if self.config_backend:
            self.load_configuration_data()
        else:
            self.show_no_config_message()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Title
        title = QLabel("Settings")
        title.setProperty("h2", "true")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Create a scroll area for the settings content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        layout.addWidget(scroll_area, 1)

        # Content widget inside scroll area
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(24, 24, 24, 24)
        self.content_layout.setSpacing(24)
        scroll_area.setWidget(self.content_widget)

        # Initially show loading state
        self.show_loading("Loading settings...")

    def load_configuration_data(self):
        """Load and display configuration data."""
        try:
            if not self.config_backend:
                self.show_error("No configuration backend available")
                return

            # Clear existing content
            self.clear_content()

            # Get the configuration
            config = self.config_backend.config

            # General Settings Group
            general_group = QGroupBox("General")
            general_layout = QFormLayout()
            general_group.setLayout(general_layout)

            # Log Level
            log_level_combo = QComboBox()
            log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
            log_level_combo.setCurrentText(config.general.log_level.value)
            log_level_combo.setEnabled(False)
            general_layout.addRow("Log Level:", log_level_combo)

            # Dry Run
            dry_run_switch = QCheckBox()
            dry_run_switch.setChecked(config.general.dry_run)
            dry_run_switch.setEnabled(False)
            general_layout.addRow("Dry Run:", dry_run_switch)

            # Verify After Sync
            verify_switch = QCheckBox()
            verify_switch.setChecked(config.general.verify_after_sync)
            verify_switch.setEnabled(False)
            general_layout.addRow("Verify After Sync:", verify_switch)

            # Create Destination
            create_dest_switch = QCheckBox()
            create_dest_switch.setChecked(config.general.create_destination)
            create_dest_switch.setEnabled(False)
            general_layout.addRow("Create Destination:", create_dest_switch)

            # Max Parallel Jobs
            max_jobs_spin = QSpinBox()
            max_jobs_spin.setRange(1, 16)
            max_jobs_spin.setValue(config.general.max_parallel_jobs)
            max_jobs_spin.setEnabled(False)
            general_layout.addRow("Max Parallel Jobs:", max_jobs_spin)

            self.content_layout.addWidget(general_group)

            # Synchronization Settings Group
            sync_group = QGroupBox("Synchronization")
            sync_layout = QFormLayout()
            sync_group.setLayout(sync_layout)

            # Startup Sync
            startup_enabled_switch = QCheckBox()
            startup_enabled_switch.setChecked(config.sync.startup.enabled)
            startup_enabled_switch.setEnabled(False)
            sync_layout.addRow("Startup Sync Enabled:", startup_enabled_switch)

            # Startup Direction
            startup_direction_combo = QComboBox()
            startup_direction_combo.addItems(["Download", "Upload"])
            startup_direction_combo.setCurrentText(config.sync.startup.direction.value.upper())
            startup_direction_combo.setEnabled(False)
            sync_layout.addRow("Startup Sync Direction:", startup_direction_combo)

            # Shutdown Sync
            shutdown_enabled_switch = QCheckBox()
            shutdown_enabled_switch.setChecked(config.sync.shutdown.enabled)
            shutdown_enabled_switch.setEnabled(False)
            sync_layout.addRow("Shutdown Sync Enabled:", shutdown_enabled_switch)

            # Shutdown Direction
            shutdown_direction_combo = QComboBox()
            shutdown_direction_combo.addItems(["Download", "Upload"])
            shutdown_direction_combo.setCurrentText(config.sync.shutdown.direction.value.upper())
            shutdown_direction_combo.setEnabled(False)
            sync_layout.addRow("Shutdown Sync Direction:", shutdown_direction_combo)

            self.content_layout.addWidget(sync_group)

            # Copy Engine Settings Group
            copy_group = QGroupBox("Copy Engine")
            copy_layout = QFormLayout()
            copy_group.setLayout(copy_layout)

            # Retry Count
            retry_spin = QSpinBox()
            retry_spin.setRange(0, 10)
            retry_spin.setValue(config.copy_engine.retry_count)
            retry_spin.setEnabled(False)
            copy_layout.addRow("Retry Count:", retry_spin)

            # Retry Wait (seconds)
            wait_spin = QSpinBox()
            wait_spin.setRange(0, 30)
            wait_spin.setValue(config.copy_engine.retry_wait_seconds)
            wait_spin.setEnabled(False)
            copy_layout.addRow("Retry Wait (seconds):", wait_spin)

            # Multithreading
            multi_spin = QSpinBox()
            multi_spin.setRange(1, 32)
            multi_spin.setValue(config.copy_engine.multithreading)
            multi_spin.setEnabled(False)
            copy_layout.addRow("Multithreading:", multi_spin)

            # Copy Subdirectories
            subdir_switch = QCheckBox()
            subdir_switch.setChecked(config.copy_engine.copy_subdirectories)
            subdir_switch.setEnabled(False)
            copy_layout.addRow("Copy Subdirectories:", subdir_switch)

            # Copy Empty Directories
            empty_switch = QCheckBox()
            empty_switch.setChecked(config.copy_engine.copy_empty_directories)
            empty_switch.setEnabled(False)
            copy_layout.addRow("Copy Empty Directories:", empty_switch)

            # Exclude Junctions
            junction_switch = QCheckBox()
            junction_switch.setChecked(config.copy_engine.exclude_junctions)
            junction_switch.setEnabled(False)
            copy_layout.addRow("Exclude Junctions:", junction_switch)

            # FAT File Times
            fat_switch = QCheckBox()
            fat_switch.setChecked(config.copy_engine.fat_file_times)
            fat_switch.setEnabled(False)
            copy_layout.addRow("FAT File Times:", fat_switch)

            # Monitor Mode
            monitor_switch = QCheckBox()
            monitor_switch.setChecked(config.copy_engine.monitor_mode)
            monitor_switch.setEnabled(False)
            copy_layout.addRow("Monitor Mode:", monitor_switch)

            self.content_layout.addWidget(copy_group)

            # Safety Settings Group
            safety_group = QGroupBox("Safety")
            safety_layout = QFormLayout()
            safety_group.setLayout(safety_layout)

            # Verify After Sync (from general)
            safety_verify_switch = QCheckBox()
            safety_verify_switch.setChecked(config.general.verify_after_sync)
            safety_verify_switch.setEnabled(False)
            safety_layout.addRow("Verify After Sync:", safety_verify_switch)

            # Create Destination (from general)
            safety_create_dest_switch = QCheckBox()
            safety_create_dest_switch.setChecked(config.general.create_destination)
            safety_create_dest_switch.setEnabled(False)
            safety_layout.addRow("Create Destination:", safety_create_dest_switch)

            # Minimum Sync Percentage (from first folder, if available)
            min_sync_label = QLabel("N/A")
            if config.folders:
                # Show the minimum sync percentage of the first folder as an example
                min_sync_label.setText(f"{int(config.folders[0].minimum_sync_percentage)}% (per folder)")
            min_sync_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            safety_layout.addRow("Minimum Sync Percentage:", min_sync_label)

            self.content_layout.addWidget(safety_group)

            # Notifications Group
            notifications_group = QGroupBox("Notifications")
            notifications_layout = QFormLayout()
            notifications_group.setLayout(notifications_layout)

            # Desktop Notifications (always enabled, best-effort)
            notifications_switch = QCheckBox()
            notifications_switch.setChecked(True)  # We don't have a setting, but notifications are enabled by design
            notifications_switch.setEnabled(False)
            notifications_layout.addRow("Desktop Notifications:", notifications_switch)

            self.content_layout.addWidget(notifications_group)

            # Backups Group
            backups_group = QGroupBox("Backups")
            backups_layout = QFormLayout()
            backups_group.setLayout(backups_layout)

            # Backup Enabled (from first folder, if available)
            backup_enabled_label = QLabel("N/A")
            if config.folders and config.folders[0].backup:
                backup_enabled_label.setText("Yes" if config.folders[0].backup.enabled else "No")
            backup_enabled_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            backups_layout.addRow("Backup Enabled:", backup_enabled_label)

            # Backup Path (from first folder, if available)
            backup_path_label = QLabel("N/A")
            if config.folders and config.folders[0].backup:
                backup_path_label.setText(str(config.folders[0].backup.backup_path))
            backup_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            backups_layout.addRow("Backup Path:", backup_path_label)

            # Retention Days (from first folder, if available)
            retention_label = QLabel("N/A")
            if config.folders and config.folders[0].backup:
                retention_label.setText(f"{config.folders[0].backup.retention_days} days")
            retention_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            backups_layout.addRow("Retention Days:", retention_label)

            self.content_layout.addWidget(backups_group)

            # Add stretch to push content to top
            self.content_layout.addStretch()

            # Edit Settings Button
            edit_button_layout = QHBoxLayout()
            edit_button_layout.addStretch()
            edit_button = QPushButton("Edit Settings")
            edit_button.setProperty("class", "primary")
            edit_button.clicked.connect(self.on_edit_settings_clicked)
            edit_button_layout.addWidget(edit_button)
            edit_button_layout.addStretch()
            self.content_layout.addLayout(edit_button_layout)

        except Exception as e:
            self.show_error(f"Error loading configuration data: {e}")

    def show_no_config_message(self):
        """Show a message when no configuration backend is available."""
        self.clear_content()
        label = QLabel("No configuration backend available.\n"
                      "Settings cannot be displayed.")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        self.content_layout.addWidget(label)

    def show_loading(self, message="Loading..."):
        """Show a loading state."""
        self.clear_content()
        label = QLabel(message)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content_layout.addWidget(label)

    def show_error(self, message="An error occurred"):
        """Show an error state."""
        self.clear_content()
        label = QLabel(f"Error:\n{message}")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        self.content_layout.addWidget(label)

    def clear_content(self):
        """Clear all content from the content layout."""
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def on_edit_settings_clicked(self):
        """Handle the Edit Settings button click."""
        QMessageBox.information(
            self,
            "Edit Settings",
            "Settings editing is not implemented in this version.\n"
            "Persistence to config.json is disabled for this task."
        )