from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QLabel,
    QStatusBar,
    QFrame,
)
from PySide6.QtCore import Qt, QSize
from .pages.dashboard import DashboardPage
from .pages.folders import FoldersPage
from .pages.backups import BackupsPage
from .pages.scheduler import SchedulerPage
from .pages.logs import LogsPage
from .pages.settings import SettingsPage
from .pages.about import AboutPage
from .themes.theme import get_dark_theme, get_sidebar_stylesheet
from .themes import spacing
from .resources.icons import get_icon


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OneDrive PC Sync")
        self.setMinimumSize(1000, 600)
        self.setup_ui()

    def setup_ui(self):
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Left sidebar
        sidebar = self.create_sidebar()
        main_layout.addWidget(sidebar)

        # Central content area (stacked widget)
        self.content_stack = QStackedWidget()
        main_layout.addWidget(self.content_stack, 1)  # stretch factor 1

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

        # Add pages
        self.add_pages()

    def create_sidebar(self):
        sidebar_frame = QFrame()
        sidebar_frame.setObjectName("sidebar")
        sidebar_frame.setFixedWidth(spacing.SIDEBAR_WIDTH)
        sidebar_frame.setStyleSheet(get_sidebar_stylesheet())

        sidebar_layout = QVBoxLayout(sidebar_frame)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        # Sidebar title
        title_label = QLabel("OneDrive PC Sync")
        title_label.setObjectName("sidebarTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sidebar_layout.addWidget(title_label)

        # Navigation list
        self.nav_list = QListWidget()
        self.nav_list.setIconSize(QSize(20, 20))
        self.nav_list.setSpacing(0)
        self.nav_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)

        # Add sidebar entries
        entries = [
            ("Dashboard", "dashboard"),
            ("Folders", "folders"),
            ("Backups", "backups"),
            ("Scheduler", "scheduler"),
            ("Logs", "logs"),
            ("Settings", "settings"),
            ("About", "about"),
        ]

        for text, icon_name in entries:
            item = QListWidgetItem(text)
            item.setIcon(get_icon(icon_name))
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.nav_list.addItem(item)

        # Select first item by default
        self.nav_list.setCurrentRow(0)

        sidebar_layout.addWidget(self.nav_list)
        sidebar_layout.addStretch()

        # Connect navigation
        self.nav_list.currentItemChanged.connect(self.change_page)

        return sidebar_frame

    def add_pages(self):
        # Map page names to their classes
        page_classes = {
            "Dashboard": DashboardPage,
            "Folders": FoldersPage,
            "Backups": BackupsPage,
            "Scheduler": SchedulerPage,
            "Logs": LogsPage,
            "Settings": SettingsPage,
            "About": AboutPage,
        }

        page_names = [
            "Dashboard",
            "Folders",
            "Backups",
            "Scheduler",
            "Logs",
            "Settings",
            "About",
        ]

        for name in page_names:
            page_class = page_classes[name]
            page = page_class()
            self.content_stack.addWidget(page)

    def change_page(self, current, previous):
        if current is None:
            current = previous
        if current:
            index = self.nav_list.row(current)
            self.content_stack.setCurrentIndex(index)