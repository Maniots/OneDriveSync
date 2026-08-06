from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt


class OneDrivePCSyncApp(QApplication):
    """Main application class for OneDrive PC Sync desktop UI."""

    def __init__(self, argv):
        super().__init__(argv)
        # Set application properties
        self.setApplicationName("OneDrive PC Sync")
        self.setApplicationDisplayName("OneDrive PC Sync")
        self.setOrganizationName("OneDrivePCSync")
        self.setOrganizationDomain("onedrivepcsync.example.com")

        # TODO: Initialize UI components (main window, etc.)


if __name__ == "__main__":
    import sys
    app = OneDrivePCSyncApp(sys.argv)
    # TODO: Show main window
    sys.exit(app.exec())