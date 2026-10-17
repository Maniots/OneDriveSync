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
    QMessageBox,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont
from ..widgets.folder_card import FolderCard
from ..themes import spacing
from ..resources.icons import get_icon
from ..models.folder_model import FolderModel
from backend.services.configuration_service import ConfigurationService
from src.config import AppConfig, BackupSettings, FolderSyncConfig, SyncDirection
from dataclasses import asdict, replace
from datetime import datetime
from ..widgets.add_folder_wizard import AddFolderWizard


class FoldersPage(QWidget):
    # Signals for toolbar actions (to be implemented by the parent or controller)
    add_folder_requested = Signal()
    refresh_requested = Signal()
    search_text_changed = Signal(str)
    filter_changed = Signal(str)

    def __init__(self, config_service: ConfigurationService, parent=None, sync_service=None):
        super().__init__(parent)
        self.config_service = config_service
        self.sync_service = sync_service
        self._wizard = None
        self.folders = []  # List of FolderModel
        self._folder_history = {}
        self.setup_ui()
        self.add_folder_requested.connect(self.open_add_folder_wizard)
        self.refresh_requested.connect(self.refresh_configuration)
        self.search_text_changed.connect(lambda text: self.display_folders())
        self.filter_changed.connect(lambda text: self.display_folders())
        if hasattr(self.config_service, "changed"):
            self.config_service.changed.connect(self.load_configuration_data)
        if self.sync_service is not None:
            self.sync_service.completed.connect(lambda outcomes: self.load_configuration_data(self.config_service.get_app_config()))
            self.sync_service.state_changed.connect(self.update_sync_buttons)
        self.history_timer = QTimer(self)
        self.history_timer.timeout.connect(self.refresh_history)
        self.history_timer.start(10000)
        # Load data from configuration if backend is available, otherwise use mock data
        app_config = self.config_service.get_app_config()
        if app_config:
            self.load_configuration_data(app_config)
        else:
            self.show_no_config_message()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(spacing.LARGE, spacing.MEDIUM, spacing.LARGE, spacing.MEDIUM)
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
        self.search_input.setAccessibleName("Search folders")
        search_label.setBuddy(self.search_input)
        self.search_input.textChanged.connect(self.on_search_text_changed)
        toolbar_layout.addWidget(search_label)
        toolbar_layout.addWidget(self.search_input)

        # Filter
        filter_label = QLabel("Filter:")
        filter_label.setProperty("title", "true")
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All", "Enabled", "Disabled"])
        self.filter_combo.setCurrentText("All")
        self.filter_combo.setAccessibleName("Filter folders by enabled status")
        filter_label.setBuddy(self.filter_combo)
        self.filter_combo.currentTextChanged.connect(self.on_filter_changed)
        toolbar_layout.addWidget(filter_label)
        toolbar_layout.addWidget(self.filter_combo)

        toolbar_layout.addStretch()

        # Add Folder button
        self.add_folder_btn = QPushButton("Add Folder")
        self.add_folder_btn.setIcon(get_icon("folder-plus"))
        self.add_folder_btn.setProperty("primary", "true")
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
        self.folders_layout.setContentsMargins(0, 0, 8, 0)
        self.folders_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.folders_layout.setHorizontalSpacing(spacing.SMALL)
        self.folders_layout.setVerticalSpacing(spacing.SMALL)
        scroll_area.setWidget(self.folders_container)
        layout.addWidget(scroll_area, 1)  # stretch factor 1

        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setProperty("description", "true")
        layout.addWidget(self.status_label)

    def load_configuration_data(self, app_config: AppConfig):
        """Load and display folder data from the configuration."""
        try:
            self.clear_folders()

            if app_config is None:
                self.folders = []
                self.show_no_config_message()
                return
            # Convert each folder config to a UI model
            self._folder_history = self.sync_service.get_folder_history() if self.sync_service else {}
            folder_models = []
            for folder_config in app_config.folders:
                folder_model = self.convert_folder_to_ui_model(folder_config)
                folder_models.append(folder_model)

            self.folders = folder_models
            self.display_folders()
            self.status_label.setText(f"Loaded {len(self.folders)} folder(s)")
            if self.sync_service and self.sync_service.history_error:
                self.status_label.setText(f"Loaded {len(self.folders)} folder(s). Sync history unavailable.")
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

        history = self._folder_history.get(folder_config.id, {})
        sync_status = (("Dry run" if history.get("dry_run") else "Success") if history.get("succeeded")
                       else ("Failed (dry run)" if history.get("dry_run") else "Failed")) if history else None
        if history.get("threshold_bypassed"):
            sync_status = f"Forced {sync_status}"
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
            last_sync_status=sync_status,
            last_sync_time=datetime.fromisoformat(history["timestamp"]).astimezone().strftime("%Y-%m-%d %H:%M:%S") if history else None,
            backup_enabled=folder_config.backup is not None and folder_config.backup.enabled,
            backup_retention_days=folder_config.backup.retention_days if folder_config.backup else 0
        )

    def display_folders(self):
        """Display the folders in the grid layout."""
        # Clear existing cards
        self.clear_folders()

        # Add folder cards
        search = self.search_input.text().casefold()
        selected_filter = self.filter_combo.currentText()
        visible_folders = [folder for folder in self.folders
                           if search in f"{folder.name} {folder.local_path} {folder.onedrive_path}".casefold()
                           and (selected_filter == "All" or folder.enabled == (selected_filter == "Enabled"))]
        for i, folder_model in enumerate(visible_folders):
            # Convert FolderModel to dict for FolderCard
            folder_data = {
                'icon': 'folder',
                'name': folder_model.name,
                'enabled': folder_model.enabled,
                'direction': self.config_service.get_app_config().sync.shutdown.direction.value.capitalize(),
                'local_path': folder_model.local_path,
                'onedrive_path': folder_model.onedrive_path,
                'safety_threshold': folder_model.minimum_sync_percentage,
                'backup_status': 'Enabled' if folder_model.backup_enabled else 'Disabled',
                'last_sync': folder_model.last_sync_time if folder_model.last_sync_time else 'Never',
                'sync_status': folder_model.last_sync_status if folder_model.last_sync_status else 'Unknown'
            }
            card = FolderCard(folder_data)
            # Connect card signals to page signals (if needed)
            card.sync_now_clicked.connect(lambda f_id=folder_model.id: self.on_folder_sync_requested(f_id))
            card.force_sync_clicked.connect(lambda f_id=folder_model.id: self.on_folder_force_sync_requested(f_id))
            card.edit_clicked.connect(lambda f_id=folder_model.id: self.on_folder_edit_requested(f_id))
            card.delete_clicked.connect(lambda f_id=folder_model.id: self.on_folder_delete_requested(f_id))
            card.enabled_toggled.connect(lambda enabled, f_id=folder_model.id: self.on_folder_toggle_requested(f_id, enabled))
            # A full-width row keeps paths readable at the minimum window size.
            self.folders_layout.addWidget(card, i, 0)
        self.update_sync_buttons()

    def update_sync_buttons(self):
        if self.sync_service is None:
            for card in self.findChildren(FolderCard):
                card.force_sync_button.setEnabled(False)
            return
        available = not self.sync_service.is_syncing and not self.sync_service.is_paused and self.sync_service.is_shutdown_sync_enabled()
        for card in self.findChildren(FolderCard):
            card.delete_button.setEnabled(not self.sync_service.is_syncing)
            card.sync_now_button.setEnabled(available and card.folder_data.get("enabled", False))
            card.force_sync_button.setEnabled(available and card.folder_data.get("enabled", False))

    def refresh_history(self):
        if self.sync_service and self.sync_service.get_folder_history() != self._folder_history:
            self.load_configuration_data(self.config_service.get_app_config())

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
    def refresh_configuration(self):
        self.config_service.reload()
        self.load_configuration_data(self.config_service.get_app_config())

    def open_add_folder_wizard(self):
        self._open_wizard()

    def on_folder_edit_requested(self, folder_id):
        config = self.config_service.get_app_config()
        folder = next((f for f in config.folders if f.id == folder_id), None)
        if folder is None:
            return
        data = asdict(folder)
        if folder.backup is not None:
            data.update(backup_enabled=folder.backup.enabled,
                        backup_path=str(folder.backup.backup_path),
                        backup_retention_days=folder.backup.retention_days)
        data["local_path"] = str(folder.local_path)
        data["onedrive_path"] = str(folder.onedrive_path)
        self._open_wizard(data, folder_id)

    def _open_wizard(self, data=None, original_id=None):
        self._wizard = AddFolderWizard(self, folder_data=data)
        self._wizard.folderDataCollected.connect(lambda values: self.save_folder_data(values, original_id))
        self._wizard.open()

    def save_folder_data(self, data, original_id=None):
        """Apply a wizard result through validated, atomic configuration saving."""
        try:
            config = self.config_service.get_app_config()
            backup = None
            if data.get("backup_enabled", False):
                backup = BackupSettings(enabled=True, backup_path=data["backup_path"],
                                        retention_days=data["backup_retention_days"])
            folder = FolderSyncConfig(
                id=data["id"], name=data["name"], enabled=data.get("enabled", True),
                local_path=data["local_path"], onedrive_path=data["onedrive_path"],
                minimum_sync_percentage=data.get("minimum_sync_percentage", 80),
                verify_after_sync=data.get("verify_after_sync", True),
                create_destination=data.get("create_destination", True), backup=backup,
            )
            if original_id is None:
                folders = [*config.folders, folder]
            else:
                if not any(f.id == original_id for f in config.folders):
                    raise ValueError("The folder being edited no longer exists")
                folders = [folder if f.id == original_id else f for f in config.folders]
            self.config_service.save(replace(config, folders=folders))
            self.status_label.setText("Folder saved successfully")
        except Exception as exc:
            QMessageBox.warning(self, "Cannot Save Folder", str(exc))

    def on_folder_toggle_requested(self, folder_id, enabled):
        try:
            config = self.config_service.get_app_config()
            folders = [replace(folder, enabled=enabled) if folder.id == folder_id else folder
                       for folder in config.folders]
            self.config_service.save(replace(config, folders=folders))
        except Exception as exc:
            QMessageBox.warning(self, "Cannot Update Folder", str(exc))
            self.load_configuration_data(self.config_service.get_app_config())

    def on_folder_sync_requested(self, folder_id):
        if self.sync_service is not None:
            self.sync_service.request_sync("shutdown", folder_id=folder_id)

    def on_folder_delete_requested(self, folder_id):
        if self.sync_service is not None and self.sync_service.is_syncing:
            return
        config = self.config_service.get_app_config()
        if config is None:
            return
        folder = next((folder for folder in config.folders if folder.id == folder_id), None)
        if folder is None:
            return
        answer = QMessageBox.question(
            self, "Remove folder from synchronization?",
            f'Remove "{folder.name}" from the configured folders?\n\n'
            "Local files, OneDrive files and existing backups will be kept.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if self.sync_service is not None and self.sync_service.is_syncing:
            return
        # Modal dialogs process events; use the latest configuration when saving.
        config = self.config_service.get_app_config()
        if config is None or not any(folder.id == folder_id for folder in config.folders):
            return
        try:
            self.config_service.save(replace(
                config, folders=[folder for folder in config.folders if folder.id != folder_id],
            ))
            self.status_label.setText("Folder removed from configuration. Files were kept.")
        except Exception as exc:
            QMessageBox.warning(self, "Cannot Remove Folder", str(exc))

    def on_folder_force_sync_requested(self, folder_id):
        if self.sync_service is None or self.sync_service.is_syncing or self.sync_service.is_paused:
            return
        config = self.config_service.get_app_config()
        if config is None or not config.sync.shutdown.enabled:
            return
        folder = next((f for f in config.enabled_folders() if f.id == folder_id), None)
        if folder is None:
            return
        source, destination = (folder.local_path_resolved, folder.onedrive_path_resolved)
        if config.sync.shutdown.direction == SyncDirection.DOWNLOAD:
            source, destination = destination, source
        answer = QMessageBox.question(
            self, "Force sync without threshold?",
            f"Folder: {folder.name}\nDirection: {config.sync.shutdown.direction.value.capitalize()}\n"
            f"From: {source}\nTo: {destination}\n\n"
            f"Ignore the {folder.minimum_sync_percentage:g}% safety threshold for this run only?\n"
            "Files at the destination can be updated. Backups, path checks, dry run and verification remain active.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.sync_service.request_sync("shutdown", folder_id=folder_id, ignore_threshold=True)
