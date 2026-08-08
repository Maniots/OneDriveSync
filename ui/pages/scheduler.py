from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QGroupBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
)
from PySide6.QtCore import Qt, QTimer
from typing import Optional
from ..config import convert_to_ui_models
from ..models.scheduler_model import SchedulerModel


class SchedulerPage(QWidget):
    def __init__(self, config_backend=None, parent=None):
        super().__init__(parent)
        self.config_backend = config_backend
        self.scheduler_data: Optional[SchedulerModel] = None
        self.setup_ui()
        # Timer for updating shutdown monitor status
        self.shutdown_timer = QTimer(self)
        self.shutdown_timer.timeout.connect(self.update_shutdown_monitor_status)
        self.shutdown_timer.start(5000)  # update every 5 seconds
        # Load configuration data if backend is available
        if self.config_backend:
            self.load_scheduler_data()
            self.update_shutdown_monitor_status()
        else:
            self.show_no_config_message()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Title
        title = QLabel("Scheduler")
        title.setProperty("h2", "true")
        layout.addWidget(title)

        # Visual timeline
        timeline_frame = QFrame()
        timeline_frame.setFrameShape(QFrame.StyledPanel)
        timeline_layout = QVBoxLayout(timeline_frame)
        timeline_layout.setContentsMargins(16, 16, 16, 16)
        timeline_layout.setSpacing(8)

        timeline_label = QLabel(
            "Logon\n"
            "   � ↓ (2 min delay)\n"
            "Startup Download\n\n"
            "Lock\n"
            "   � ↓\n"
            "Upload\n\n"
            "Every 15 minutes\n"
            "   � ↓\n"
            "Upload\n\n"
            "Shutdown\n"
            "   � ↓\n"
            "Monitor\n"
            "   � ↓\n"
            "Upload"
        )
        timeline_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        timeline_label.setStyleSheet("""
            QLabel {
                font-family: monospace;
                font-size: 12pt;
                color: palette(text);
            }
        """)
        timeline_layout.addWidget(timeline_label)
        layout.addWidget(timeline_frame)

        # Sections
        sections_layout = QVBoxLayout()
        sections_layout.setSpacing(12)

        # Startup Sync Section
        startup_group = QGroupBox("Startup Sync")
        startup_layout = QFormLayout()
        startup_group.setLayout(startup_layout)

        self.startup_trigger_label = QLabel()
        self.startup_delay_label = QLabel()
        self.startup_direction_label = QLabel()
        self.startup_status_label = QLabel()

        startup_layout.addRow("Trigger:", self.startup_trigger_label)
        startup_layout.addRow("Delay:", self.startup_delay_label)
        startup_layout.addRow("Direction:", self.startup_direction_label)
        startup_layout.addRow("Status:", self.startup_status_label)

        sections_layout.addWidget(startup_group)

        # Periodic Sync Section
        periodic_group = QGroupBox("Periodic Sync")
        periodic_layout = QFormLayout()
        periodic_group.setLayout(periodic_layout)

        self.periodic_interval_label = QLabel()
        self.periodic_direction_label = QLabel()
        self.periodic_status_label = QLabel()

        periodic_layout.addRow("Interval:", self.periodic_interval_label)
        periodic_layout.addRow("Direction:", self.periodic_direction_label)
        periodic_layout.addRow("Status:", self.periodic_status_label)

        sections_layout.addWidget(periodic_group)

        # Workstation Lock Section
        workstation_group = QGroupBox("Workstation Lock")
        workstation_layout = QFormLayout()
        workstation_group.setLayout(workstation_layout)

        self.workstation_trigger_label = QLabel()
        self.workstation_direction_label = QLabel()
        self.workstation_status_label = QLabel()

        workstation_layout.addRow("Trigger:", self.workstation_trigger_label)
        workstation_layout.addRow("Direction:", self.workstation_direction_label)
        workstation_layout.addRow("Status:", self.workstation_status_label)

        sections_layout.addWidget(workstation_group)

        # Shutdown Monitor Section
        monitor_group = QGroupBox("Shutdown Monitor")
        monitor_layout = QFormLayout()
        monitor_group.setLayout(monitor_layout)

        self.monitor_status_label = QLabel()
        self.last_detected_event_label = QLabel()
        self.last_shutdown_sync_label = QLabel()
        self.pid_label = QLabel()
        self.startup_time_label = QLabel()
        self.last_error_label = QLabel()

        monitor_layout.addRow("Monitor Status:", self.monitor_status_label)
        monitor_layout.addRow("Last Detected Event:", self.last_detected_event_label)
        monitor_layout.addRow("Last Shutdown Sync:", self.last_shutdown_sync_label)
        monitor_layout.addRow("PID:", self.pid_label)
        monitor_layout.addRow("Startup Time:", self.startup_time_label)
        monitor_layout.addRow("Last Error:", self.last_error_label)

        sections_layout.addWidget(monitor_group)

        layout.addLayout(sections_layout)

        # Add stretch to push everything to the top
        layout.addStretch()

    def load_scheduler_data(self):
        """Load and display scheduler data."""
        try:
            if not self.config_backend:
                self.show_error("No configuration backend available")
                return

            # Get the configuration
            config = self.config_backend.config

            # Convert to UI models to get the scheduler model
            _, _, _, scheduler_model = convert_to_ui_models(config)
            self.scheduler_data = scheduler_model

            # Update the UI
            self.update_ui()

        except Exception as e:
            self.show_error(f"Error loading scheduler data: {e}")

    def update_ui(self):
        """Update the UI with the scheduler data."""
        if not self.scheduler_data:
            return

        # Startup Sync
        self.startup_trigger_label.setText(self.scheduler_data.startup_trigger)
        self.startup_delay_label.setText(f"{self.scheduler_data.startup_delay} minutes")
        self.startup_direction_label.setText(self.scheduler_data.startup_direction.capitalize())
        startup_status = "Enabled" if self.scheduler_data.startup_enabled else "Disabled"
        if self.scheduler_data.startup_next_run:
            startup_status += f" (Next: {self.scheduler_data.startup_next_run})"
        self.startup_status_label.setText(startup_status)

        # Periodic Sync
        self.periodic_interval_label.setText(f"{self.scheduler_data.periodic_interval} minutes")
        self.periodic_direction_label.setText(self.scheduler_data.periodic_direction.capitalize())
        periodic_status = "Enabled" if self.scheduler_data.periodic_enabled else "Disabled"
        if self.scheduler_data.periodic_next_run:
            periodic_status += f" (Next: {self.scheduler_data.periodic_next_run})"
        self.periodic_status_label.setText(periodic_status)

        # Workstation Lock
        self.workstation_trigger_label.setText(self.scheduler_data.workstation_trigger)
        self.workstation_direction_label.setText(self.scheduler_data.workstation_direction.capitalize())
        workstation_status = "Enabled" if self.scheduler_data.workstation_enabled else "Disabled"
        if self.scheduler_data.workstation_next_run:
            workstation_status += f" (Next: {self.scheduler_data.workstation_next_run})"
        self.workstation_status_label.setText(workstation_status)

        # Shutdown Monitor
        self.monitor_status_label.setText(self.scheduler_data.monitor_status)
        self.last_detected_event_label.setText(self.scheduler_data.last_detected_event)
        last_sync = self.scheduler_data.last_shutdown_sync or "Never"
        self.last_shutdown_sync_label.setText(last_sync)

    def show_no_config_message(self):
        """Show a message when no configuration backend is available."""
        self.clear_layout()
        label = QLabel("No configuration backend available.\n"
                       "Scheduler information cannot be displayed.")
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

    def update_shutdown_monitor_status(self):
        """Update the shutdown monitor status labels."""
        if not self.config_backend:
            # No backend, show unknown
            self.monitor_status_label.setText("Unknown")
            self.last_detected_event_label.setText("N/A")
            self.last_shutdown_sync_label.setText("N/A")
            self.pid_label.setText("N/A")
            self.startup_time_label.setText("N/A")
            self.last_error_label.setText("N/A")
            return

        try:
            status = self.config_backend.get_shutdown_monitor_status()
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

    def clear_layout(self):
        """Clear the layout."""
        while self.layout().count():
            item = self.layout().takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()