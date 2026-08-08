from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QSizePolicy,
    QGridLayout,
    QSpacerItem,
)
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QFont
from ..widgets.card import Card
from ..widgets.sync_chart import SyncChartWidget
from ..themes import spacing
from ..resources.icons import get_icon
from ..config import convert_to_ui_models


class DashboardPage(QWidget):
    def __init__(self, config_backend=None, parent=None):
        super().__init__(parent)
        self.config_backend = config_backend
        self.folder_models = []
        self.sync_status_model = None
        self.backup_models = []
        self.setup_ui()
        # Load configuration data if backend is available
        if self.config_backend:
            self.load_configuration_data()
        else:
            # Show error state
            self.show_configuration_error()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            spacing.LARGE, spacing.LARGE, spacing.LARGE, spacing.LARGE
        )
        layout.setSpacing(spacing.LARGE)

        # Top bar
        layout.addWidget(self._create_top_bar())

        # Status area (4 cards)
        self.status_area_widget = self._create_status_area()
        layout.addWidget(self.status_area_widget)

        # Main area (chart and side panels)
        self.main_area_widget = self._create_main_area()
        layout.addWidget(self.main_area_widget, 1)  # stretch factor 1

        # Recent activity
        self.recent_activity_widget = self._create_recent_activity()
        layout.addWidget(self.recent_activity_widget)

    def load_configuration_data(self):
        """Load and process configuration data to update the UI."""
        try:
            if not self.config_backend:
                self.show_configuration_error("No configuration backend available")
                return

            # Convert backend config to UI models
            folder_models, sync_status_model, backup_models, scheduler_model = \
                convert_to_ui_models(self.config_backend.config)

            self.folder_models = folder_models
            self.sync_status_model = sync_status_model
            self.backup_models = backup_models
            # scheduler_model would be used by the SchedulerPage

            # Update UI components with the data
            self.update_status_area()
            self.update_main_area()
            self.update_recent_activity()

        except Exception as e:
            self.show_configuration_error(f"Error loading configuration data: {e}")

    def show_configuration_error(self, message="Configuration error"):
        """Show an error state in the dashboard."""
        # Update status area to show error
        if hasattr(self, 'status_area_widget'):
            # Replace the status area with an error message
            error_frame = QFrame()
            error_frame.setFrameStyle(QFrame.NoFrame)
            error_layout = QVBoxLayout(error_frame)
            error_layout.setContentsMargins(0, 0, 0, 0)
            error_layout.setSpacing(spacing.MEDIUM)

            error_label = QLabel(f"Configuration Error\n\n{message}")
            error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            error_label.setWordWrap(True)
            error_label.setProperty("h2", "true")
            error_layout.addWidget(error_label)

            # Replace in layout
            layout = self.layout()
            if layout:
                layout.replaceWidget(self.status_area_widget, error_frame)
                self.status_area_widget.hide()
                self.status_area_widget.deleteLater()
                self.status_area_widget = error_frame

    def update_status_area(self):
        """Update the status area cards with real data."""
        # This would update the status cards with real data from sync_status_model
        # For now, we'll keep the mock data but in a real implementation,
        # we would update the cards based on the actual sync status
        pass

    def update_main_area(self):
        """Update the main area with real folder and backup data."""
        # Update folder overview
        if hasattr(self, 'main_area_widget'):
            # Find the folder overview and backup status frames and update them
            # This is simplified - in practice we'd need to traverse the layout
            # or store references to the specific widgets we want to update
            pass

    def update_recent_activity(self):
        """Update the recent activity with real data."""
        # This would update the recent activity with real sync events
        # For now, we'll keep the mock data
        pass

    # Keep the existing UI creation methods but modify them to use stored references
    def _create_top_bar(self):
        frame = QFrame()
        frame.setFrameStyle(QFrame.NoFrame)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing.MEDIUM)

        # Title
        title = QLabel("Dashboard")
        title.setProperty("h1", "true")
        layout.addWidget(title)

        # Subtitle
        subtitle = QLabel("Overview of sync status")
        subtitle.setProperty("h2", "true")
        subtitle.setProperty("class", "subtitle")
        layout.addWidget(subtitle)

        layout.addStretch()

        # Sync Now button
        sync_button = QPushButton("Sync Now")
        sync_button.setIcon(get_icon("sync"))
        sync_button.setProperty("class", "primary")
        layout.addWidget(sync_button)

        return frame

    def _create_status_area(self):
        frame = QFrame()
        frame.setFrameStyle(QFrame.NoFrame)
        layout = QGridLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing.MEDIUM)

        # Status cards data: (title, value, icon_name, description)
        # Using mock data for now - in a real implementation, this would come from
        # the sync_status_model and other sources
        cards_data = [
            ("Service Status", "Running", "running", "Service is active"),
            ("Current Sync", "Idle", "sync-arrow", "No active sync"),
            ("Last Sync", "Today, 10:30 AM", "history", "Last successful sync"),
            ("Next Sync", "In 15 minutes", "schedule", "Next scheduled upload"),
        ]

        for i, (title, value, icon, desc) in enumerate(cards_data):
            card = Card(title, value, icon, desc)
            row = i // 2
            col = i % 2
            layout.addWidget(card, row, col)

        return frame

    def _create_main_area(self):
        frame = QFrame()
        frame.setFrameStyle(QFrame.NoFrame)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing.LARGE)

        # Left: Sync activity chart
        layout.addWidget(self._create_chart(), 2)  # chart takes 2/3 width

        # Right: Folder overview and backup status (vertical stack)
        right_layout = QVBoxLayout()
        right_layout.setSpacing(spacing.MEDIUM)

        # Folder overview
        right_layout.addWidget(self._create_folder_overview())

        # Backup status
        right_layout.addWidget(self._create_backup_status())

        layout.addLayout(right_layout, 1)  # right takes 1/3 width

        return frame

    def _create_chart(self):
        frame = QFrame()
        frame.setFrameStyle(QFrame.StyledPanel)
        frame.setLineWidth(1)
        frame.setStyleSheet("""
            QFrame {
                background-color: #252525;
                border-radius: 8px;
            }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(
            spacing.MEDIUM, spacing.MEDIUM, spacing.MEDIUM, spacing.MEDIUM
        )

        # Chart title
        title = QLabel("Sync Activity")
        title.setProperty("h2", "true")
        layout.addWidget(title)

        # Create and configure the sync chart widget
        chart_widget = SyncChartWidget()
        # Mock data: last 10 hours - in a real app, this would come from sync history
        hours = list(range(10))
        # Mock sync counts (random-ish)
        sync_counts = [5, 3, 0, 12, 7, 0, 0, 4, 9, 2]
        chart_widget.set_data(hours, sync_counts)
        layout.addWidget(chart_widget)

        return frame

    def _create_folder_overview(self):
        frame = QFrame()
        frame.setFrameStyle(QFrame.StyledPanel)
        frame.setLineWidth(1)
        frame.setStyleSheet("""
            QFrame {
                background-color: #252525;
                border-radius: 8px;
            }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(
            spacing.MEDIUM, spacing.MEDIUM, spacing.MEDIUM, spacing.MEDIUM
        )

        # Title
        title = QLabel("Folder Overview")
        title.setProperty("h2", "true")
        layout.addWidget(title)

        # Folder data - in a real implementation, this would come from folder_models
        folders = [
            ("Elden Ring", "Synced", "check-circle"),
            ("Cyberpunk 2077", "Sync Needed", "sync-alert"),
            ("The Witcher 3", "Up to Date", "check-circle"),
            ("Stardew Valley", "Paused", "pause-circle"),
        ]

        for name, status, icon_name in folders:
            item_layout = QHBoxLayout()
            item_layout.setContentsMargins(0, 0, 0, 0)
            item_layout.setSpacing(spacing.SMALL)

            # Icon
            if icon_name:
                icon = get_icon(icon_name)
                pixmap = icon.pixmap(QSize(16, 16))
                icon_label = QLabel()
                icon_label.setPixmap(pixmap)
                item_layout.addWidget(icon_label)

            # Folder name
            name_label = QLabel(name)
            name_label.setProperty("class", "folder-name")
            item_layout.addWidget(name_label)

            item_layout.addStretch()

            # Status
            status_label = QLabel(status)
            if status == "Synced":
                status_label.setProperty("class", "status-success")
            elif status == "Sync Needed":
                status_label.setProperty("class", "status-warning")
            elif status == "Paused":
                status_label.setProperty("class", "status-paused")
            else:
                status_label.setProperty("class", "status-info")
            item_layout.addWidget(status_label)

            layout.addLayout(item_layout)

        layout.addStretch()
        return frame

    def _create_backup_status(self):
        frame = QFrame()
        frame.setFrameStyle(QFrame.StyledPanel)
        frame.setLineWidth(1)
        frame.setStyleSheet("""
            QFrame {
                background-color: #252525;
                border-radius: 8px;
            }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(
            spacing.MEDIUM, spacing.MEDIUM, spacing.MEDIUM, spacing.MEDIUM
        )

        # Title
        title = QLabel("Backup Status")
        title.setProperty("h2", "true")
        layout.addWidget(title)

        # Backup info - in a real implementation, this would come from backup_models
        backup_data = [
            ("Last Backup", "Today, 9:15 AM"),
            ("Backup Size", "2.4 GB"),
            ("Retention", "7 days"),
            ("Location", "OneDrive/PCSync/Backups"),
        ]

        for label, value in backup_data:
            item_layout = QHBoxLayout()
            item_layout.setContentsMargins(0, 0, 0, 0)
            item_layout.setSpacing(spacing.SMALL)

            label_widget = QLabel(label)
            label_widget.setProperty("class", "backup-label")
            item_layout.addWidget(label_widget)

            item_layout.addStretch()

            value_widget = QLabel(value)
            value_widget.setProperty("class", "backup-value")
            item_layout.addWidget(value_widget)

            layout.addLayout(item_layout)

        layout.addStretch()
        return frame

    def _create_recent_activity(self):
        frame = QFrame()
        frame.setFrameStyle(QFrame.StyledPanel)
        frame.setLineWidth(1)
        frame.setStyleSheet("""
            QFrame {
                background-color: #252525;
                border-radius: 8px;
            }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(
            spacing.MEDIUM, spacing.MEDIUM, spacing.MEDIUM, spacing.MEDIUM
        )

        # Title
        title = QLabel("Recent Activity")
        title.setProperty("h2", "true")
        layout.addWidget(title)

        # Mock recent events - in a real implementation, this would come from sync history
        events = [
            ("Today, 10:30 AM", "Sync completed", "Elden Ring", "success"),
            ("Today, 10:15 AM", "Backup created", "Cyberpunk 2077", "info"),
            ("Today, 9:45 AM", "Sync started", "The Witcher 3", "info"),
            ("Yesterday, 4:20 PM", "Sync failed", "Stardew Valley", "error"),
            ("Yesterday, 3:00 PM", "Sync completed", "Elden Ring", "success"),
        ]

        for time, action, folder, status in events:
            event_layout = QHBoxLayout()
            event_layout.setContentsMargins(0, 0, 0, 0)
            event_layout.setSpacing(spacing.SMALL)

            # Time
            time_label = QLabel(time)
            time_label.setProperty("class", "event-time")
            event_layout.addWidget(time_label)

            # Action and folder
            text_label = QLabel(f"{action} <b>{folder}</b>")
            text_label.setProperty("class", "event-text")
            text_label.setTextFormat(Qt.RichText)
            event_layout.addWidget(text_label)

            event_layout.addStretch()

            # Status indicator
            status_label = QLabel("●")
            status_label.setProperty("class", f"event-status-{status}")
            event_layout.addWidget(status_label)

            layout.addLayout(event_layout)

        layout.addStretch()
        return frame

    def _create_top_bar(self):
        frame = QFrame()
        frame.setFrameStyle(QFrame.NoFrame)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing.MEDIUM)

        # Title
        title = QLabel("Dashboard")
        title.setProperty("h1", "true")
        layout.addWidget(title)

        # Subtitle
        subtitle = QLabel("Overview of sync status")
        subtitle.setProperty("h2", "true")
        subtitle.setProperty("class", "subtitle")
        layout.addWidget(subtitle)

        layout.addStretch()

        # Sync Now button
        sync_button = QPushButton("Sync Now")
        sync_button.setIcon(get_icon("sync"))
        sync_button.setProperty("class", "primary")
        layout.addWidget(sync_button)

        return frame

    def _create_status_area(self):
        frame = QFrame()
        frame.setFrameStyle(QFrame.NoFrame)
        layout = QGridLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing.MEDIUM)

        # Status cards data: (title, value, icon_name, description)
        cards_data = [
            ("Service Status", "Running", "running", "Service is active"),
            ("Current Sync", "Idle", "sync-arrow", "No active sync"),
            ("Last Sync", "Today, 10:30 AM", "history", "Last successful sync"),
            ("Next Sync", "In 15 minutes", "schedule", "Next scheduled upload"),
        ]

        for i, (title, value, icon, desc) in enumerate(cards_data):
            card = Card(title, value, icon, desc)
            row = i // 2
            col = i % 2
            layout.addWidget(card, row, col)

        return frame

    def _create_main_area(self):
        frame = QFrame()
        frame.setFrameStyle(QFrame.NoFrame)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing.LARGE)

        # Left: Sync activity chart
        layout.addWidget(self._create_chart(), 2)  # chart takes 2/3 width

        # Right: Folder overview and backup status (vertical stack)
        right_layout = QVBoxLayout()
        right_layout.setSpacing(spacing.MEDIUM)

        # Folder overview
        right_layout.addWidget(self._create_folder_overview())

        # Backup status
        right_layout.addWidget(self._create_backup_status())

        layout.addLayout(right_layout, 1)  # right takes 1/3 width

        return frame

    def _create_chart(self):
        frame = QFrame()
        frame.setFrameStyle(QFrame.StyledPanel)
        frame.setLineWidth(1)
        frame.setStyleSheet("""
            QFrame {
                background-color: #252525;
                border-radius: 8px;
            }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(
            spacing.MEDIUM, spacing.MEDIUM, spacing.MEDIUM, spacing.MEDIUM
        )

        # Chart title
        title = QLabel("Sync Activity")
        title.setProperty("h2", "true")
        layout.addWidget(title)

        # Create and configure the sync chart widget
        chart_widget = SyncChartWidget()
        # Mock data: last 10 hours
        hours = list(range(10))
        # Mock sync counts (random-ish)
        sync_counts = [5, 3, 0, 12, 7, 0, 0, 4, 9, 2]
        chart_widget.set_data(hours, sync_counts)
        layout.addWidget(chart_widget)

        return frame

    def _create_folder_overview(self):
        frame = QFrame()
        frame.setFrameStyle(QFrame.StyledPanel)
        frame.setLineWidth(1)
        frame.setStyleSheet("""
            QFrame {
                background-color: #252525;
                border-radius: 8px;
            }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(
            spacing.MEDIUM, spacing.MEDIUM, spacing.MEDIUM, spacing.MEDIUM
        )

        # Title
        title = QLabel("Folder Overview")
        title.setProperty("h2", "true")
        layout.addWidget(title)

        # Mock folder data
        folders = [
            ("Elden Ring", "Synced", "check-circle"),
            ("Cyberpunk 2077", "Sync Needed", "sync-alert"),
            ("The Witcher 3", "Up to Date", "check-circle"),
            ("Stardew Valley", "Paused", "pause-circle"),
        ]

        for name, status, icon_name in folders:
            item_layout = QHBoxLayout()
            item_layout.setContentsMargins(0, 0, 0, 0)
            item_layout.setSpacing(spacing.SMALL)

            # Icon
            if icon_name:
                icon = get_icon(icon_name)
                pixmap = icon.pixmap(QSize(16, 16))
                icon_label = QLabel()
                icon_label.setPixmap(pixmap)
                item_layout.addWidget(icon_label)

            # Folder name
            name_label = QLabel(name)
            name_label.setProperty("class", "folder-name")
            item_layout.addWidget(name_label)

            item_layout.addStretch()

            # Status
            status_label = QLabel(status)
            if status == "Synced":
                status_label.setProperty("class", "status-success")
            elif status == "Sync Needed":
                status_label.setProperty("class", "status-warning")
            elif status == "Paused":
                status_label.setProperty("class", "status-paused")
            else:
                status_label.setProperty("class", "status-info")
            item_layout.addWidget(status_label)

            layout.addLayout(item_layout)

        layout.addStretch()
        return frame

    def _create_backup_status(self):
        frame = QFrame()
        frame.setFrameStyle(QFrame.StyledPanel)
        frame.setLineWidth(1)
        frame.setStyleSheet("""
            QFrame {
                background-color: #252525;
                border-radius: 8px;
            }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(
            spacing.MEDIUM, spacing.MEDIUM, spacing.MEDIUM, spacing.MEDIUM
        )

        # Title
        title = QLabel("Backup Status")
        title.setProperty("h2", "true")
        layout.addWidget(title)

        # Backup info
        backup_data = [
            ("Last Backup", "Today, 9:15 AM"),
            ("Backup Size", "2.4 GB"),
            ("Retention", "7 days"),
            ("Location", "OneDrive/PCSync/Backups"),
        ]

        for label, value in backup_data:
            item_layout = QHBoxLayout()
            item_layout.setContentsMargins(0, 0, 0, 0)
            item_layout.setSpacing(spacing.SMALL)

            label_widget = QLabel(label)
            label_widget.setProperty("class", "backup-label")
            item_layout.addWidget(label_widget)

            item_layout.addStretch()

            value_widget = QLabel(value)
            value_widget.setProperty("class", "backup-value")
            item_layout.addWidget(value_widget)

            layout.addLayout(item_layout)

        layout.addStretch()
        return frame

    def _create_recent_activity(self):
        frame = QFrame()
        frame.setFrameStyle(QFrame.StyledPanel)
        frame.setLineWidth(1)
        frame.setStyleSheet("""
            QFrame {
                background-color: #252525;
                border-radius: 8px;
            }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(
            spacing.MEDIUM, spacing.MEDIUM, spacing.MEDIUM, spacing.MEDIUM
        )

        # Title
        title = QLabel("Recent Activity")
        title.setProperty("h2", "true")
        layout.addWidget(title)

        # Mock recent events
        events = [
            ("Today, 10:30 AM", "Sync completed", "Elden Ring", "success"),
            ("Today, 10:15 AM", "Backup created", "Cyberpunk 2077", "info"),
            ("Today, 9:45 AM", "Sync started", "The Witcher 3", "info"),
            ("Yesterday, 4:20 PM", "Sync failed", "Stardew Valley", "error"),
            ("Yesterday, 3:00 PM", "Sync completed", "Elden Ring", "success"),
        ]

        for time, action, folder, status in events:
            event_layout = QHBoxLayout()
            event_layout.setContentsMargins(0, 0, 0, 0)
            event_layout.setSpacing(spacing.SMALL)

            # Time
            time_label = QLabel(time)
            time_label.setProperty("class", "event-time")
            event_layout.addWidget(time_label)

            # Action and folder
            text_label = QLabel(f"{action} <b>{folder}</b>")
            text_label.setProperty("class", "event-text")
            text_label.setTextFormat(Qt.RichText)
            event_layout.addWidget(text_label)

            event_layout.addStretch()

            # Status indicator
            status_label = QLabel("●")
            status_label.setProperty("class", f"event-status-{status}")
            event_layout.addWidget(status_label)

            layout.addLayout(event_layout)

        layout.addStretch()
        return frame