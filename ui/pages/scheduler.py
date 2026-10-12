from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QGroupBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QCheckBox,
    QPushButton,
    QMessageBox,
)
from PySide6.QtCore import Qt, QTimer, QSignalBlocker
from ..themes import spacing
from typing import Optional, Dict
from backend.services.configuration_service import ConfigurationService
from backend.services.scheduler_service import SchedulerService
from backend.services.monitor_service import MonitorService


class SchedulerPage(QWidget):
    def __init__(self, config_service: ConfigurationService, scheduler_service: SchedulerService, monitor_service: MonitorService, parent=None):
        super().__init__(parent)
        self.config_service = config_service
        self.scheduler_service = scheduler_service
        self.monitor_service = monitor_service
        self.scheduler_data: Optional[Dict] = None
        self.monitor_status: Optional[Dict] = None
        self.setup_ui()
        self.error_label = QLabel(self)
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        self.layout().insertWidget(0, self.error_label)
        # Timer for updating shutdown monitor status
        self.shutdown_timer = QTimer(self)
        self.shutdown_timer.timeout.connect(self.update_shutdown_monitor_status)
        self.shutdown_timer.start(5000)  # update every 5 seconds
        # Load initial data
        self.load_scheduler_data()
        self.update_shutdown_monitor_status()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(spacing.LARGE, spacing.LARGE, spacing.LARGE, spacing.LARGE)
        layout.setSpacing(spacing.MEDIUM)

        # Title and refresh button
        title_layout = QHBoxLayout()
        title_layout.setSpacing(spacing.SMALL)
        title = QLabel("Scheduler")
        title.setProperty("h2", "true")
        title_layout.addWidget(title)
        title_layout.addStretch()
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setToolTip("Refresh scheduler status")
        self.refresh_button.clicked.connect(self.on_refresh_clicked)
        title_layout.addWidget(self.refresh_button)
        layout.addLayout(title_layout)

        # Visual timeline
        timeline_frame = QFrame()
        timeline_frame.setProperty("card", "true")
        timeline_layout = QVBoxLayout(timeline_frame)
        timeline_layout.setContentsMargins(spacing.MEDIUM, spacing.MEDIUM, spacing.MEDIUM, spacing.MEDIUM)
        timeline_layout.setSpacing(spacing.SMALL)

        timeline_label = QLabel(
            "Logon\n"
            "   ������� ����� ����� ��� ����� ��� ��� � ����� ��� ��� � ��� � � ↓ (2 min delay)\n"
            "Startup Download\n\n"
            "Lock\n"
            "   ������� ����� ����� ��� ����� ��� ��� � ����� ��� ��� � ��� � � ↓\n"
            "Upload\n\n"
            "Every 15 minutes\n"
            "   ������� ����� ����� ��� ����� ��� ��� � ����� ��� ��� � ��� � � ↓\n"
            "Upload\n\n"
            "Shutdown\n"
            "   ������� ����� ����� ��� ����� ��� ��� � ����� ��� ��� � ��� � � ↓\n"
            "Monitor\n"
            "   ������� ����� ����� ��� ����� ��� ��� � ����� ��� ��� � ��� � � ↓\n"
            "Upload"
        )
        timeline_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        timeline_label.setProperty("value", "true")
        timeline_label.setProperty("class", "monospace")
        timeline_layout.addWidget(timeline_label)
        layout.addWidget(timeline_frame)

        # Sections
        sections_layout = QVBoxLayout()
        sections_layout.setSpacing(spacing.SMALL)

        # Startup Sync Section
        startup_group = QGroupBox("Startup Sync")
        startup_group.setProperty("card", "true")
        startup_layout = QFormLayout()
        startup_group.setLayout(startup_layout)

        self.startup_trigger_label = QLabel()
        self.startup_delay_label = QLabel()
        self.startup_direction_label = QLabel()
        self.startup_enabled_checkbox = QCheckBox()
        self.startup_enabled_checkbox.stateChanged.connect(lambda state: self.on_startup_enabled_changed(state))
        self.startup_last_run_label = QLabel()
        self.startup_next_run_label = QLabel()

        self.startup_trigger_label.setProperty("value", "true")
        self.startup_delay_label.setProperty("value", "true")
        self.startup_direction_label.setProperty("value", "true")
        self.startup_enabled_checkbox.setProperty("value", "true")
        self.startup_last_run_label.setProperty("value", "true")
        self.startup_next_run_label.setProperty("value", "true")

        trigger_label = QLabel("Trigger:")
        trigger_label.setProperty("title", "true")
        startup_layout.addRow(trigger_label, self.startup_trigger_label)
        delay_label = QLabel("Delay:")
        delay_label.setProperty("title", "true")
        startup_layout.addRow(delay_label, self.startup_delay_label)
        direction_label = QLabel("Direction:")
        direction_label.setProperty("title", "true")
        startup_layout.addRow(direction_label, self.startup_direction_label)
        enabled_label = QLabel("Enabled:")
        enabled_label.setProperty("title", "true")
        startup_layout.addRow(enabled_label, self.startup_enabled_checkbox)
        last_run_label = QLabel("Last Run:")
        last_run_label.setProperty("title", "true")
        startup_layout.addRow(last_run_label, self.startup_last_run_label)
        next_run_label = QLabel("Next Run:")
        next_run_label.setProperty("title", "true")
        startup_layout.addRow(next_run_label, self.startup_next_run_label)

        sections_layout.addWidget(startup_group)

        # Periodic Sync Section
        periodic_group = QGroupBox("Periodic Sync")
        periodic_group.setProperty("card", "true")
        periodic_layout = QFormLayout()
        periodic_group.setLayout(periodic_layout)

        self.periodic_interval_label = QLabel()
        self.periodic_direction_label = QLabel()
        self.periodic_enabled_checkbox = QCheckBox()
        self.periodic_enabled_checkbox.stateChanged.connect(lambda state: self.on_periodic_enabled_changed(state))
        self.periodic_last_run_label = QLabel()
        self.periodic_next_run_label = QLabel()

        self.periodic_interval_label.setProperty("value", "true")
        self.periodic_direction_label.setProperty("value", "true")
        self.periodic_enabled_checkbox.setProperty("value", "true")
        self.periodic_last_run_label.setProperty("value", "true")
        self.periodic_next_run_label.setProperty("value", "true")

        interval_label = QLabel("Interval:")
        interval_label.setProperty("title", "true")
        periodic_layout.addRow(interval_label, self.periodic_interval_label)
        direction_label = QLabel("Direction:")
        direction_label.setProperty("title", "true")
        periodic_layout.addRow(direction_label, self.periodic_direction_label)
        enabled_label = QLabel("Enabled:")
        enabled_label.setProperty("title", "true")
        periodic_layout.addRow(enabled_label, self.periodic_enabled_checkbox)
        last_run_label = QLabel("Last Run:")
        last_run_label.setProperty("title", "true")
        periodic_layout.addRow(last_run_label, self.periodic_last_run_label)
        next_run_label = QLabel("Next Run:")
        next_run_label.setProperty("title", "true")
        periodic_layout.addRow(next_run_label, self.periodic_next_run_label)

        sections_layout.addWidget(periodic_group)

        # Workstation Lock Section
        workstation_group = QGroupBox("Workstation Lock")
        workstation_group.setProperty("card", "true")
        workstation_layout = QFormLayout()
        workstation_group.setLayout(workstation_layout)

        self.workstation_trigger_label = QLabel()
        self.workstation_direction_label = QLabel()
        self.workstation_enabled_checkbox = QCheckBox()
        self.workstation_enabled_checkbox.stateChanged.connect(lambda state: self.on_workstation_enabled_changed(state))
        self.workstation_last_run_label = QLabel()
        self.workstation_next_run_label = QLabel()

        self.workstation_trigger_label.setProperty("value", "true")
        self.workstation_direction_label.setProperty("value", "true")
        self.workstation_enabled_checkbox.setProperty("value", "true")
        self.workstation_last_run_label.setProperty("value", "true")
        self.workstation_next_run_label.setProperty("value", "true")

        trigger_label = QLabel("Trigger:")
        trigger_label.setProperty("title", "true")
        workstation_layout.addRow(trigger_label, self.workstation_trigger_label)
        direction_label = QLabel("Direction:")
        direction_label.setProperty("title", "true")
        workstation_layout.addRow(direction_label, self.workstation_direction_label)
        enabled_label = QLabel("Enabled:")
        enabled_label.setProperty("title", "true")
        workstation_layout.addRow(enabled_label, self.workstation_enabled_checkbox)
        last_run_label = QLabel("Last Run:")
        last_run_label.setProperty("title", "true")
        workstation_layout.addRow(last_run_label, self.workstation_last_run_label)
        next_run_label = QLabel("Next Run:")
        next_run_label.setProperty("title", "true")
        workstation_layout.addRow(next_run_label, self.workstation_next_run_label)

        sections_layout.addWidget(workstation_group)

        # Shutdown Monitor Section
        monitor_group = QGroupBox("Shutdown Monitor")
        monitor_group.setProperty("card", "true")
        monitor_layout = QFormLayout()
        monitor_group.setLayout(monitor_layout)

        self.monitor_status_label = QLabel()
        self.last_detected_event_label = QLabel()
        self.last_shutdown_sync_label = QLabel()
        self.pid_label = QLabel()
        self.startup_time_label = QLabel()
        self.last_error_label = QLabel()

        self.monitor_status_label.setProperty("value", "true")
        self.last_detected_event_label.setProperty("value", "true")
        self.last_shutdown_sync_label.setProperty("value", "true")
        self.pid_label.setProperty("value", "true")
        self.startup_time_label.setProperty("value", "true")
        self.last_error_label.setProperty("value", "true")

        monitor_status_label = QLabel("Monitor Status:")
        monitor_status_label.setProperty("title", "true")
        monitor_layout.addRow(monitor_status_label, self.monitor_status_label)
        last_detected_event_label = QLabel("Last Detected Event:")
        last_detected_event_label.setProperty("title", "true")
        monitor_layout.addRow(last_detected_event_label, self.last_detected_event_label)
        last_shutdown_sync_label = QLabel("Last Shutdown Sync:")
        last_shutdown_sync_label.setProperty("title", "true")
        monitor_layout.addRow(last_shutdown_sync_label, self.last_shutdown_sync_label)
        pid_label = QLabel("PID:")
        pid_label.setProperty("title", "true")
        monitor_layout.addRow(pid_label, self.pid_label)
        startup_time_label = QLabel("Startup Time:")
        startup_time_label.setProperty("title", "true")
        monitor_layout.addRow(startup_time_label, self.startup_time_label)
        last_error_label = QLabel("Last Error:")
        last_error_label.setProperty("title", "true")
        monitor_layout.addRow(last_error_label, self.last_error_label)

        sections_layout.addWidget(monitor_group)

        layout.addLayout(sections_layout)

    def on_refresh_clicked(self):
        """Refresh the scheduler data by reloading from the service."""
        self.load_scheduler_data()

    def load_scheduler_data(self):
        """Load and display scheduler data from the scheduler service."""
        try:
            if not self.config_service:
                self.show_error("Configuration service not available")
                return

            # Get scheduler summary from the scheduler service
            scheduler_summary = self.scheduler_service.get_scheduler_summary()
            if scheduler_summary is None:
                self.show_error("Scheduler information not available")
                return

            self.error_label.hide()
            self.scheduler_data = scheduler_summary
            self.update_ui_from_scheduler_data()

        except Exception as e:
            self.show_error(f"Error loading scheduler data: {e}")

    def update_ui_from_scheduler_data(self):
        """Update the UI with the scheduler data from the scheduler service."""
        if not self.scheduler_data:
            return

        # Startup Sync
        startup_info = self.scheduler_data.get("startup")
        if startup_info:
            self.startup_trigger_label.setText(startup_info.get("trigger", "N/A"))
            self.startup_delay_label.setText(startup_info.get("delay", "N/A"))
            self.startup_direction_label.setText(startup_info.get("direction", "N/A"))
            enabled_str = startup_info.get("enabled", "Disabled")
            self._set_checked(self.startup_enabled_checkbox, enabled_str == "Enabled")
            self.startup_enabled_checkbox.setEnabled(startup_info.get("exists", False))
            self.startup_last_run_label.setText(startup_info.get("last_run_time") or "N/A")
            self.startup_next_run_label.setText(startup_info.get("next_run_time") or "N/A")

        # Periodic Sync
        periodic_info = self.scheduler_data.get("periodic")
        if periodic_info:
            self.periodic_interval_label.setText(periodic_info.get("interval", "N/A"))
            self.periodic_direction_label.setText(periodic_info.get("direction", "N/A"))
            enabled_str = periodic_info.get("enabled", "Disabled")
            self._set_checked(self.periodic_enabled_checkbox, enabled_str == "Enabled")
            self.periodic_enabled_checkbox.setEnabled(periodic_info.get("exists", False))
            self.periodic_last_run_label.setText(periodic_info.get("last_run_time") or "N/A")
            self.periodic_next_run_label.setText(periodic_info.get("next_run_time") or "N/A")

        # Workstation Lock
        workstation_info = self.scheduler_data.get("workstation_lock")
        if workstation_info:
            self.workstation_trigger_label.setText(workstation_info.get("trigger", "N/A"))
            self.workstation_direction_label.setText(workstation_info.get("direction", "N/A"))
            enabled_str = workstation_info.get("enabled", "Disabled")
            self._set_checked(self.workstation_enabled_checkbox, enabled_str == "Enabled")
            self.workstation_enabled_checkbox.setEnabled(workstation_info.get("exists", False))
            self.workstation_last_run_label.setText(workstation_info.get("last_run_time") or "N/A")
            self.workstation_next_run_label.setText(workstation_info.get("next_run_time") or "N/A")

    def update_shutdown_monitor_status(self):
        """Update the shutdown monitor status labels using the monitor service."""
        if not self.monitor_service:
            # No monitor service, show unknown
            self.monitor_status_label.setText("Unknown")
            self.last_detected_event_label.setText("N/A")
            self.last_shutdown_sync_label.setText("N/A")
            self.pid_label.setText("N/A")
            self.startup_time_label.setText("N/A")
            self.last_error_label.setText("N/A")
            return

        try:
            status = self.monitor_service.get_status()
            # Map status to display text
            monitor_status = status.get("status", "unknown")
            # Capitalize first letter for display
            if monitor_status == "running":
                display_status = "Running"
            elif monitor_status == "stopped":
                display_status = "Stopped"
            elif monitor_status == "error":
                display_status = "Error"
            else:
                display_status = "Unknown"
            self.monitor_status_label.setText(display_status)

            last_detected = status.get("last_detected_event")
            self.last_detected_event_label.setText(last_detected if last_detected else "N/A")

            last_sync = status.get("last_shutdown_sync")
            self.last_shutdown_sync_label.setText(last_sync if last_sync else "N/A")

            pid = status.get("pid")
            self.pid_label.setText(str(pid) if pid is not None else "N/A")

            startup_time = status.get("startup_time")
            self.startup_time_label.setText(startup_time if startup_time else "N/A")

            last_error = status.get("last_error")
            self.last_error_label.setText(last_error if last_error else "N/A")
        except Exception:
            # In case of any error, show unknown
            self.monitor_status_label.setText("Unknown")
            self.last_detected_event_label.setText("N/A")
            self.last_shutdown_sync_label.setText("N/A")
            self.pid_label.setText("N/A")
            self.startup_time_label.setText("N/A")
            self.last_error_label.setText("N/A")

    def on_startup_enabled_changed(self, state):
        """Handle startup enabled checkbox state change."""
        from PySide6.QtWidgets import QMessageBox
        enabled = state == 2  # Qt.Checked is 2
        task_name = "Startup Sync"
        display_name = self.scheduler_service._TASK_NAMES["startup"]

        # Show confirmation dialog
        reply = QMessageBox.question(
            self,
            f"Confirm {task_name} Change",
            f"Are you sure you want to {'enable' if enabled else 'disable'} {task_name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Try to change the task status
            success = self.scheduler_service.set_task_enabled("startup", enabled)
            if success:
                # Refresh to update the UI with the actual status
                self.load_scheduler_data()
            else:
                # Show error and revert checkbox
                QMessageBox.warning(
                    self,
                    "Operation Failed",
                    f"Failed to {'enable' if enabled else 'disable'} {task_name}.",
                    QMessageBox.StandardButton.Ok
                )
                self._set_checked(self.startup_enabled_checkbox, not enabled)
        else:
            # User cancelled, revert checkbox
            self._set_checked(self.startup_enabled_checkbox, not enabled)

    def on_periodic_enabled_changed(self, state):
        """Handle periodic enabled checkbox state change."""
        from PySide6.QtWidgets import QMessageBox
        enabled = state == 2  # Qt.Checked is 2
        task_name = "Periodic Sync"
        display_name = self.scheduler_service._TASK_NAMES["periodic"]

        # Show confirmation dialog
        reply = QMessageBox.question(
            self,
            f"Confirm {task_name} Change",
            f"Are you sure you want to {'enable' if enabled else 'disable'} {task_name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Try to change the task status
            success = self.scheduler_service.set_task_enabled("periodic", enabled)
            if success:
                # Refresh to update the UI with the actual status
                self.load_scheduler_data()
            else:
                # Show error and revert checkbox
                QMessageBox.warning(
                    self,
                    "Operation Failed",
                    f"Failed to {'enable' if enabled else 'disable'} {task_name}.",
                    QMessageBox.StandardButton.Ok
                )
                self._set_checked(self.periodic_enabled_checkbox, not enabled)
        else:
            # User cancelled, revert checkbox
            self._set_checked(self.periodic_enabled_checkbox, not enabled)

    def on_workstation_enabled_changed(self, state):
        """Handle workstation lock enabled checkbox state change."""
        from PySide6.QtWidgets import QMessageBox
        enabled = state == 2  # Qt.Checked is 2
        task_name = "Workstation Lock Sync"
        display_name = self.scheduler_service._TASK_NAMES["workstation_lock"]

        # Show confirmation dialog
        reply = QMessageBox.question(
            self,
            f"Confirm {task_name} Change",
            f"Are you sure you want to {'enable' if enabled else 'disable'} {task_name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Try to change the task status
            success = self.scheduler_service.set_task_enabled("workstation_lock", enabled)
            if success:
                # Refresh to update the UI with the actual status
                self.load_scheduler_data()
            else:
                # Show error and revert checkbox
                QMessageBox.warning(
                    self,
                    "Operation Failed",
                    f"Failed to {'enable' if enabled else 'disable'} {task_name}.",
                    QMessageBox.StandardButton.Ok
                )
                self._set_checked(self.workstation_enabled_checkbox, not enabled)
        else:
            # User cancelled, revert checkbox
            self._set_checked(self.workstation_enabled_checkbox, not enabled)

    @staticmethod
    def _set_checked(checkbox, checked):
        # Loading or reverting state must never trigger a scheduler write/dialog.
        with QSignalBlocker(checkbox):
            checkbox.setChecked(checked)

    def show_no_config_message(self):
        self.show_error("Configuration service not available.")

    def show_error(self, message):
        """Keep monitor widgets alive so timer updates and recovery remain safe."""
        self.error_label.setText(f"Error: {message}")
        self.error_label.show()
