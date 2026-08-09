from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QScrollArea,
    QGridLayout,
    QSizePolicy,
    QFrame,
    QSpacerItem,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont
from ..widgets.folder_card import FolderCard
from ..themes import spacing
from ..resources.icons import get_icon
from ..models.folder_model import FolderModel
from backend.services.configuration_service import ConfigurationService
from src.config import AppConfig


class FoldersPage(QWidget):
    # Signals for toolbar actions (to be implemented by the parent or controller)
    add_folder_requested = Signal()
    refresh_requested = Signal()
    search_text_changed = Signal(str)
    filter_changed = Signal(str)

    def __init__(self, config_service: ConfigurationService, parent=None):
        super().__init__(parent)
        self.config_service = config_service
        self.folders = []  # List of FolderModel
        self.setup_ui()
        # Load data from configuration if backend is available, otherwise use mock data
        app_config = self.config_service.get_app_config()
        if app_config:
            self.load_configuration_data(app_config)
        else:
            self.show_no_config_message()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(spacing.MEDIUM, spacing.MEDIUM, spacing.MEDIUM, spacing.MEDIUM)
        layout.setSpacing(spacing.SMALL)

        # Toolbar
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(spacing.XSMALL)

        # Search
        search_label = QLabel("Search:")
        search_label.setProperty("title", "true")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search folders...")
        self.search_input.textChanged.connect(self.on_search_text_changed)
        toolbar_layout.addWidget(search_label)
        toolbar_layout.addWidget(self.search_input)

        # Filter
        filter_label = QLabel("Filter:")
        filter_label.setProperty("title", "true")
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All", "Enabled", "Disabled"])
        self.filter_combo.setCurrentText("All")
        self.filter_combo.currentTextChanged.connect(self.on_filter_changed)
        toolbar_layout.addWidget(filter_label)
        toolbar_layout.addWidget(self.filter_combo)

        toolbar_layout.addStretch()

        # Add Folder button
        self.add_folder_btn = QPushButton("Add Folder")
        self.add_folder_btn.setIcon(get_icon("folder-plus"))
        self.add_folder_btn.clicked.connect(self.on_add_folder_requested)
        toolbar_layout.addWidget(self.add_folder_btn)

        # Refresh button
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setIcon(get_icon("refresh"))
        self.refresh_btn.clicked.connect(self.on_refresh_requested)
        toolbar_layout.addWidget(self.refresh_btn)

        layout.addLayout(toolbar_layout)

        # Scroll area for folders
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        self.folders_container = QWidget()
        self.folders_layout = QGridLayout(self.folders_container)
        self.folders_layout.setContentsMargins(spacing.SMALL, spacing.SMALL, spacing.SMALL, spacing.SMALL)
        self.folders_layout.setHorizontalSpacing(spacing.SMALL)
        self.folders_layout.setVerticalSpacing(spacing.SMALL)
        scroll_area.setWidget(self.folders_container)
        layout.addWidget(scroll_area, 1)  # stretch factor 1

        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setProperty("value", "true")
        layout.addWidget(self.status_label)

    def load_configuration_data(self, app_config: AppConfig):
        """Load and display folder data from the configuration."""
        try:
            self.clear_folders()

            # Convert each folder config to a UI model
            folder_models = []
            for folder_config in app_config.folders:
                folder_model = self.convert_folder_to_ui_model(folder_config)
                folder_models.append(folder_model)

            self.folders = folder_models
            self.display_folders()
            self.status_label.setText(f"Loaded {len(self.folders)} folder(s)")
        except Exception as e:
            self.show_error(f"Error loading folder data: {e}")

    def convert_folder_to_ui_model(self, folder_config) -> FolderModel:
        """Convert a backend FolderSyncConfig to a UI FolderModel.
        This is a simplified version - in a full implementation, we might want to
        get additional data from sync status and backup services.
        """
        # Convert Path objects to strings with environment variables unexpanded for display
        local_path_str = str(folder_config.local_path)
        onedrive_path_str = str(folder_config.onedrive_path)

        # Try to convert back to environment variable format for display if possible
        # This is a simplified approach - in practice, we might want to store the original
        # or have a setting for how to display paths
        try:
            # Try to convert common environment variables back
            import os
            appdata = os.getenv("APPDATA", "")
            userprofile = os.getenv("USERPROFILE", "")
            onedrive = os.getenv("OneDrive", "")

            if appdata and local_path_str.startswith(appdata):
                local_path_str = local_path_str.replace(appdata, "%APPDATA%", 1)
            if userprofile and local_path_str.startswith(userprofile):
                local_path_str = local_path_str.replace(userprofile, "%USERPROFILE%", 1)
            if onedrive and onedrive_path_str.startswith(onedrive):
                onedrive_path_str = onedrive_path_str.replace(onedrive, "%OneDrive%", 1)
        except:
            # If anything goes wrong, just use the expanded paths
            pass

        return FolderModel(
            id=folder_config.id,
            name=folder_config.name,
            enabled=folder_config.enabled,
            local_path=local_path_str,
            onedrive_path=onedrive_path_str,
            minimum_sync_percentage=int(folder_config.minimum_sync_percentage),
            verify_after_sync=folder_config.verify_after_sync,
            create_destination=folder_config.create_destination,
            # UI-specific fields - these would normally come from a sync status service
            last_sync_status=None,
            last_sync_time=None,
            backup_enabled=folder_config.backup is not None and folder_config.backup.enabled,
            backup_retention_days=folder_config.backup.retention_days if folder_config.backup else 0
        )

    def display_folders(self):
        """Display the folders in the grid layout."""
        # Clear existing cards
        self.clear_folders()

        # Add folder cards
        for i, folder_model in enumerate(self.folders):
            # Convert FolderModel to dict for FolderCard
            folder_data = {
                'icon': 'folder',
                'name': folder_model.name,
                'enabled': folder_model.enabled,
                'direction': 'Upload',  # Default direction since not in FolderModel
                'local_path': folder_model.local_path,
                'onedrive_path': folder_model.onedrive_path,
                'safety_threshold': folder_model.minimum_sync_percentage,
                'backup_status': 'Enabled' if folder_model.backup_enabled else 'Disabled',
                'last_sync': folder_model.last_sync_time if folder_model.last_sync_time else 'Never',
                'sync_status': folder_model.last_sync_status if folder_model.last_sync_status else 'Unknown'
            }
            card = FolderCard(folder_data)
            # Connect card signals to page signals (if needed)
            card.edit_clicked.connect(lambda f_id=folder_model.id: self.on_folder_edit_requested(f_id))
            card.enabled_toggled.connect(lambda enabled, f_id=folder_model.id: self.on_folder_toggle_requested(f_id, enabled))
            row = i // 3  # 3 columns
            col = i % 3
            self.folders_layout.addWidget(card, row, col)

    def clear_folders(self):
        """Clear all folder cards from the layout."""
        while self.folders_layout.count():
            item = self.folders_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def show_no_config_message(self):
        """Show a message when no configuration is available."""
        self.clear_folders()
        label = QLabel("No configuration available.\n"
                       "Folder information cannot be displayed.")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        self.folders_layout.addWidget(label)

    def show_error(self, message):
        """Show an error message."""
        self.clear_folders()
        label = QLabel(f"Error:\n{message}")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        self.folders_layout.addWidget(label)

    # Signal handlers (to be connected by parent/controller)
    def on_add_folder_requested(self):
        self.add_folder_requested.emit()

    def on_refresh_requested(self):
        self.refresh_requested.emit()

    def on_search_text_changed(self, text):
        self.search_text_changed.emit(text)

    def on_filter_changed(self, text):
        self.filter_changed.emit(text)

    # Folder card signal handlers (can be overridden by parent)
    def on_folder_edit_requested(self, folder_id):
        pass  # To be implemented by parent if needed

    def on_folder_toggle_requested(self, folder_id, enabled):
        pass  # To be implemented by parent if needed