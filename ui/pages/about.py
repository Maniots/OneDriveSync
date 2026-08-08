from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt


class AboutPage(QWidget):
    def __init__(self, config_backend=None, parent=None):
        super().__init__(parent)
        self.config_backend = config_backend  # Store for potential future use
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        label = QLabel("About")
        label.setProperty("h2", "true")
        layout.addWidget(label)