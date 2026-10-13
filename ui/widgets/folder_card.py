from PySide6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFormLayout,
    QSizePolicy,
)
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QFont
from ..themes.theme import get_card_stylesheet
from ..themes import spacing, colors
from ..resources.icons import get_icon


class FolderCard(QFrame):
    """
    A reusable card widget displaying folder synchronization information and actions.
    Emits signals for actions (Sync Now, Edit, Enable/Disable) without executing synchronization.
    """
    sync_now_clicked = Signal()
    force_sync_clicked = Signal()
    edit_clicked = Signal()
    enabled_toggled = Signal(bool)  # True for enabled, False for disabled

    def __init__(self, folder_data=None, parent=None):
        super().__init__(parent)
        self.setProperty("card", "true")
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        # Store folder data
        self.folder_data = folder_data or {}

        self.setup_ui()

    def setup_ui(self):
        """Set up the user interface for the folder card."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(
            spacing.SMALL, spacing.SMALL, spacing.SMALL, spacing.SMALL
        )
        main_layout.setSpacing(spacing.XSMALL)

        # Header: icon, folder name, enabled status
        header_layout = QHBoxLayout()
        # Folder icon
        icon_name = self.folder_data.get('icon', 'folder')
        icon = get_icon(icon_name)
        pixmap = icon.pixmap(QSize(24, 24))
        icon_label = QLabel()
        icon_label.setPixmap(pixmap)
        header_layout.addWidget(icon_label)

        # Folder name
        name_label = QLabel(self.folder_data.get('name', ''))
        name_label.setProperty("h3", "true")
        name_label.setWordWrap(True)
        header_layout.addWidget(name_label)
        header_layout.addStretch()

        # Enabled/Disabled status indicator
        self.enabled_indicator = QLabel()
        self.enabled_indicator.setProperty("statusSuccess" if self.folder_data.get('enabled', False) else "statusError", "true")
        self.enabled_indicator.setProperty("enabledState", "true" if self.folder_data.get('enabled', False) else "false")
        self.enabled_indicator.setProperty("badge", "true")
        self.enabled_indicator.setText("Enabled" if self.folder_data.get('enabled', False) else "Disabled")
        self.enabled_indicator.setToolTip("Enabled" if self.folder_data.get('enabled', False) else "Disabled")
        self.enabled_indicator.setStyleSheet(f"""
            QLabel[enabledState="true"] {{
                color: {colors.SUCCESS}; background-color: {colors.INPUT_BACKGROUND};
                border-radius: 6px; padding: 5px 10px;
            }}
            QLabel[enabledState="false"] {{
                color: {colors.TEXT_SECONDARY}; background-color: {colors.INPUT_BACKGROUND};
                border-radius: 6px; padding: 5px 10px;
            }}
        """)
        header_layout.addWidget(self.enabled_indicator)

        main_layout.addLayout(header_layout)

        # Details section: key-value pairs
        details_layout = QFormLayout()
        details_layout.setLabelAlignment(Qt.AlignLeft)
        details_layout.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(spacing.XSMALL)

        # Sync Direction
        direction_label = QLabel("Sync Direction:")
        direction_label.setProperty("title", "true")
        direction_value = QLabel(self.folder_data.get('direction', ''))
        direction_value.setProperty("value", "true")
        details_layout.addRow(direction_label, direction_value)

        # Local Path
        local_path_label = QLabel("Local Path:")
        local_path_label.setProperty("title", "true")
        local_path_value = QLabel(self.folder_data.get('local_path', ''))
        local_path_value.setProperty("value", "true")
        local_path_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        local_path_value.setWordWrap(True)
        local_path_value.setMinimumWidth(0)
        local_path_value.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        local_path_value.setToolTip(local_path_value.text())
        details_layout.addRow(local_path_label, local_path_value)

        # OneDrive Path
        onedrive_path_label = QLabel("OneDrive Path:")
        onedrive_path_label.setProperty("title", "true")
        onedrive_path_value = QLabel(self.folder_data.get('onedrive_path', ''))
        onedrive_path_value.setProperty("value", "true")
        onedrive_path_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        onedrive_path_value.setWordWrap(True)
        onedrive_path_value.setMinimumWidth(0)
        onedrive_path_value.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        onedrive_path_value.setToolTip(onedrive_path_value.text())
        details_layout.addRow(onedrive_path_label, onedrive_path_value)

        # Safety Threshold
        safety_label = QLabel("Safety Threshold:")
        safety_label.setProperty("title", "true")
        safety_value = QLabel(f"{self.folder_data.get('safety_threshold', 0)}%")
        safety_value.setProperty("value", "true")
        details_layout.addRow(safety_label, safety_value)

        # Backup Status
        backup_label = QLabel("Backup Status:")
        backup_label.setProperty("title", "true")
        backup_value = QLabel(self.folder_data.get('backup_status', ''))
        backup_value.setProperty("value", "true")
        details_layout.addRow(backup_label, backup_value)

        # Last Sync
        last_sync_label = QLabel("Last Sync:")
        last_sync_label.setProperty("title", "true")
        last_sync_value = QLabel(self.folder_data.get('last_sync', ''))
        last_sync_value.setProperty("value", "true")
        details_layout.addRow(last_sync_label, last_sync_value)

        # Sync Status
        sync_status_label = QLabel("Sync Status:")
        sync_status_label.setProperty("title", "true")
        sync_status_value = QLabel(self.folder_data.get('sync_status', ''))
        sync_status_value.setProperty("value", "true")
        # Set color based on sync status
        status = self.folder_data.get('sync_status', '').lower()
        if 'success' in status or 'synced' in status:
            sync_status_value.setProperty("statusSuccess", "true")
        elif 'error' in status or 'failed' in status:
            sync_status_value.setProperty("statusError", "true")
        elif 'warning' in status:
            sync_status_value.setProperty("statusWarning", "true")
        elif 'paused' in status:
            sync_status_value.setProperty("statusPaused", "true")
        else:
            sync_status_value.setProperty("statusInfo", "true")
        details_layout.addRow(sync_status_label, sync_status_value)

        main_layout.addLayout(details_layout)

        # Actions section
        actions_layout = QHBoxLayout()
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(spacing.SMALL)

        # Sync Now button
        self.sync_now_button = QPushButton("Sync Now")
        self.sync_now_button.setIcon(get_icon("sync"))
        self.sync_now_button.setProperty("primary", "true")
        self.sync_now_button.clicked.connect(self.sync_now_clicked.emit)
        actions_layout.addWidget(self.sync_now_button)

        self.force_sync_button = QPushButton("Force sync")
        self.force_sync_button.setToolTip("Sync this folder once without the percentage threshold. Other safety checks remain active.")
        self.force_sync_button.clicked.connect(self.force_sync_clicked.emit)
        actions_layout.addWidget(self.force_sync_button)

        # Edit button
        self.edit_button = QPushButton("Edit")
        self.edit_button.setIcon(get_icon("edit"))
        self.edit_button.clicked.connect(self.edit_clicked.emit)
        actions_layout.addWidget(self.edit_button)

        # Enable/Disable toggle button
        self.toggle_enabled_button = QPushButton()
        self.update_toggle_button()
        self.toggle_enabled_button.clicked.connect(self.toggle_enabled)
        actions_layout.addWidget(self.toggle_enabled_button)
        actions_layout.addStretch()

        main_layout.addLayout(actions_layout)

        main_layout.addStretch()

    def update_toggle_button(self):
        """Update the enable/disable button based on current state."""
        enabled = self.folder_data.get('enabled', False)
        if enabled:
            self.toggle_enabled_button.setText("Disable")
            self.toggle_enabled_button.setIcon(get_icon("toggle-off"))
        else:
            self.toggle_enabled_button.setText("Enable")
            self.toggle_enabled_button.setIcon(get_icon("toggle-on"))

    def toggle_enabled(self):
        """Toggle the enabled state and emit signal."""
        current = self.folder_data.get('enabled', False)
        self.folder_data['enabled'] = not current
        self.enabled_indicator.setProperty("enabledState", "true" if not current else "false")
        self.enabled_indicator.setText("Enabled" if not current else "Disabled")
        self.enabled_indicator.setProperty("statusSuccess", "true" if not current else "false")
        self.enabled_indicator.setProperty("statusError", "true" if current else "false")
        self.enabled_indicator.setToolTip("Enabled" if not current else "Disabled")
        # Force style update
        self.enabled_indicator.style().unpolish(self.enabled_indicator)
        self.enabled_indicator.style().polish(self.enabled_indicator)
        self.update_toggle_button()
        # Emit the toggled state
        self.enabled_toggled.emit(not current)

    # Optional: method to update folder data (not required for basic use)
    def update_folder_data(self, folder_data):
        """Update the card with new folder data."""
        self.folder_data = folder_data
        # In a full implementation, we would update all UI elements here.
        # For simplicity, we rely on the constructor setting the data.
        # A proper implementation would refresh the UI components.
        pass
