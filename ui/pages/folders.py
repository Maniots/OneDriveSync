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
from ..config import convert_folder_to_ui_model


class FoldersPage(QWidget):
    # Signals for toolbar actions (to be implemented by the parent or controller)
    add_folder_requested = Signal()
    refresh_requested = Signal()
    search_text_changed = Signal(str)
    filter_changed = Signal(str)

    def __init__(self, config_backend=None, parent=None):
        super().__init__(parent)
        self.config_backend = config_backend
        self.folders = []  # List of FolderModel
        self.setup_ui()
        # Load data from configuration if backend is available, otherwise use mock data
        if self.config_backend:
            self.load_configuration_data()
        else:
            self.load_mock_data()  # Load mock data for demonstration

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(spacing.LARGE, spacing.LARGE, spacing.LARGE, spacing.LARGE)
        layout.setSpacing(spacing.LARGE)

        # Top toolbar
        layout.addWidget(self._create_toolbar())

        # Status widget (for loading, error, empty)
        self.status_widget = QWidget()
        self.status_widget.setObjectName("statusWidget")
        status_layout = QVBoxLayout(self.status_widget)
        status_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_icon = QLabel()
        self.status_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_layout.addWidget(self.status_icon)
        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)
        status_layout.addWidget(self.status_label)
        layout.addWidget(self.status_widget)

        # Grid widget for cards
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(spacing.MEDIUM)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        # Scroll area for the grid
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self.grid_widget)
        scroll_area.setFrameShape(QFrame.NoFrame)
        layout.addWidget(scroll_area, 1)  # stretch factor 1

        # Initially show loading state
        self.show_loading("Loading folders...")

    def _create_toolbar(self):
        toolbar = QFrame()
        toolbar.setFrameShape(QFrame.NoFrame)
        toolbar.setStyleSheet("""
            QFrame {
                background-color: transparent;
            }
        """)
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing.MEDIUM)

        # Search folders
        search_label = QLabel("Search:")
        search_label.setProperty("class", "toolbar-label")
        layout.addWidget(search_label)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search folders...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self.search_text_changed.emit)
        layout.addWidget(self.search_input, 1)  # stretch factor 1

        # Filter
        filter_label = QLabel("Filter:")
        filter_label.setProperty("class", "toolbar-label")
        layout.addWidget(filter_label)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All", "Enabled", "Disabled"])
        self.filter_combo.currentTextChanged.connect(self.filter_changed.emit)
        layout.addWidget(self.filter_combo)

        # Add Folder button
        self.add_button = QPushButton("Add Folder")
        self.add_button.setIcon(get_icon("plus"))
        self.add_button.setProperty("class", "toolbar-button")
        self.add_button.clicked.connect(self.add_folder_requested.emit)
        layout.addWidget(self.add_button)

        # Refresh button
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setIcon(get_icon("refresh"))
        self.refresh_button.setProperty("class", "toolbar-button")
        self.refresh_button.clicked.connect(self.refresh_requested.emit)
        layout.addWidget(self.refresh_button)

        return toolbar

    def show_loading(self, message="Loading..."):
        self.status_icon.clear()
        self.status_icon.setPixmap(get_icon("hourglass").pixmap(32, 32))
        self.status_label.setText(message)
        self.status_widget.show()
        self.grid_widget.hide()

    def show_error(self, message="An error occurred while loading folders."):
        self.status_icon.clear()
        self.status_icon.setPixmap(get_icon("alert-circle").pixmap(32, 32))
        self.status_label.setText(message)
        self.status_widget.show()
        self.grid_widget.hide()

    def show_empty(self, message="No folders to display."):
        self.status_icon.clear()
        self.status_icon.setPixmap(get_icon("folder").pixmap(32, 32))
        self.status_label.setText(message)
        self.status_widget.show()
        self.grid_widget.hide()

    def show_folders(self):
        self.status_widget.hide()
        self.grid_widget.show()
        self.populate_grid()

    def populate_grid(self):
        # Clear the grid
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        # Apply filters and search
        filtered_folders = self._filter_folders(self.folders)

        if not filtered_folders:
            self.show_empty("No folders match the current filter.")
            return

        # Add cards to the grid (3 columns)
        column_count = 3
        for index, folder in enumerate(filtered_folders):
            row = index // column_count
            col = index % column_count
            card = FolderCard(folder.__dict__)  # Convert FolderModel to dict
            # Connect card signals (optional, for now just emit)
            card.sync_now_clicked.connect(lambda _, f=folder: self.sync_folder(f))
            card.edit_clicked.connect(lambda _, f=folder: self.edit_folder(f))
            card.enabled_toggled.connect(lambda enabled, f=folder: self.toggle_folder_enabled(f, enabled))
            self.grid_layout.addWidget(card, row, col)

    def _filter_folders(self, folders):
        search_text = self.search_input.text().lower().strip()
        filter_text = self.filter_combo.currentText()

        filtered = []
        for folder in folders:
            # Search in folder name and id
            if search_text and search_text not in folder.name.lower() and search_text not in folder.id.lower():
                continue
            # Filter by enabled status
            if filter_text == "Enabled" and not folder.enabled:
                continue
            if filter_text == "Disabled" and folder.enabled:
                continue
            filtered.append(folder)
        return filtered

    # Mock data loading
    def load_mock_data(self):
        # In a real application, this would come from a service or model
        mock_folders = [
            FolderModel(
                id="elden_ring",
                name="Elden Ring Save",
                enabled=True,
                local_path="%APPDATA%\\EldenRing",
                onedrive_path="%OneDrive%\\PCSync\\AppData\\Roaming\\EldenRing",
                minimum_sync_percentage=80,
                verify_after_sync=True,
                create_destination=True,
                last_sync_status="Success",
                last_sync_time="Today, 10:30 AM",
                backup_enabled=True,
                backup_retention_days=7,
            ),
            FolderModel(
                id="cyberpunk",
                name="Cyberpunk 2077",
                enabled=False,
                local_path="%APPDATA%\\Cyberpunk 2077",
                onedrive_path="%OneDrive%\\PCSync\\AppData\\Roaming\\Cyberpunk 2077",
                minimum_sync_percentage=80,
                verify_after_sync=True,
                create_destination=True,
                last_sync_status="Failed",
                last_sync_time="Yesterday, 4:20 PM",
                backup_enabled=True,
                backup_retention_days=7,
            ),
            FolderModel(
                id="witcher3",
                name="The Witcher 3",
                enabled=True,
                local_path="%APPDATA%\\TheWitcher3",
                onedrive_path="%OneDrive%\\PCSync\\AppData\\Roaming\\TheWitcher3",
                minimum_sync_percentage=80,
                verify_after_sync=True,
                create_destination=True,
                last_sync_status="Success",
                last_sync_time="Today, 9:15 AM",
                backup_enabled=False,
                backup_retention_days=0,
            ),
            FolderModel(
                id="stardew",
                name="Stardew Valley",
                enabled=True,
                local_path="%APPDATA%\\StardewValley",
                onedrive_path="%OneDrive%\\PCSync\\AppData\\Roaming\\StardewValley",
                minimum_sync_percentage=80,
                verify_after_sync=True,
                create_destination=True,
                last_sync_status="Paused",
                last_sync_time="Today, 8:00 AM",
                backup_enabled=True,
                backup_retention_days=7,
            ),
            FolderModel(
                id="cuphead",
                name="Cuphead Save",
                enabled=True,
                local_path="%APPDATA%\\Cuphead",
                onedrive_path="%OneDrive%\\PCSync\\AppData\\Roaming\\Cuphead",
                minimum_sync_percentage=80,
                verify_after_sync=True,
                create_destination=True,
                last_sync_status="Success",
                last_sync_time="Today, 10:11 AM",
                backup_enabled=False,
                backup_retention_days=0,
            ),
            FolderModel(
                id="rainworld",
                name="Rain World Save",
                enabled=True,
                local_path="%APPDATA%\\RainWorld",
                onedrive_path="%OneDrive%\\PCSync\\AppData\\Roaming\\RainWorld",
                minimum_sync_percentage=80,
                verify_after_sync=True,
                create_destination=True,
                last_sync_status="Success",
                last_sync_time="Today, 10:11 AM",
                backup_enabled=True,
                backup_retention_days=7,
            ),
        ]
        self.folders = mock_folders
        # Simulate loading delay
        self.show_loading()
        # In a real app, we would use a QTimer or async call, but for now we'll show folders after a short delay via a timer
        from PySide6.QtCore import QTimer
        QTimer.singleShot(500, self._finish_loading)

    def load_configuration_data(self):
        """Load folder data from the configuration backend."""
        try:
            if not self.config_backend:
                self.show_error("No configuration backend available")
                return

            # Get folders from backend
            backend_folders = self.config_backend.get_folders()

            # Convert to UI models
            self.folders = [
                convert_folder_to_ui_model(folder)
                for folder in backend_folders
            ]

            # Simulate loading delay for consistency with mock data
            self.show_loading()
            from PySide6.QtCore import QTimer
            QTimer.singleShot(500, self._finish_loading)

        except Exception as e:
            self.show_error(f"Error loading configuration data: {e}")

    def _finish_loading(self):
        self.show_folders()

    # Placeholder slots for card actions (to be connected by parent/controller)
    def sync_folder(self, folder):
        print(f"Sync requested for folder: {folder.name}")

    def edit_folder(self, folder):
        print(f"Edit requested for folder: {folder.name}")

    def toggle_folder_enabled(self, folder, enabled):
        print(f"Toggle folder {folder.name} enabled to {enabled}")
        # Update the folder model in our list
        for f in self.folders:
            if f.id == folder.id:
                f.enabled = enabled
                break


if __name__ == "__main__":
    # For testing the widget standalone
    from PySide6.QtWidgets import QApplication
    import sys
    app = QApplication(sys.argv)
    window = FoldersPage()
    window.resize(800, 600)
    window.show()
    sys.exit(app.exec())