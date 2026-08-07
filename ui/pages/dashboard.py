from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel
from PySide6.QtCore import Qt
from ..widgets.card import Card


class DashboardPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)

        # Title
        title_label = QLabel("Dashboard")
        title_label.setProperty("h1", "true")
        layout.addWidget(title_label)

        # Stats cards grid
        grid_layout = QGridLayout()
        grid_layout.setSpacing(16)

        # Card data: (title, value, icon_name)
        cards_data = [
            ("Service Status", "Running", "running"),
            ("Last Sync", "2 minutes ago", "sync"),
            ("Next Scheduled Upload", "In 13 minutes", "upload"),
            ("Synced Folders", "3/5", "folders"),
            ("Backup Status", "Healthy", "backup"),
        ]

        # Create cards and add to grid (2 columns)
        for i, (title, value, icon) in enumerate(cards_data):
            card = Card(title, value, icon)
            row = i // 2
            col = i % 2
            grid_layout.addWidget(card, row, col)

        layout.addLayout(grid_layout)
        layout.addStretch()