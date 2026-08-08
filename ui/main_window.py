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
    QMessageBox,
)
from PySide6.QtCore import Qt, QSize, QTimer
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
from .config import get_config_path
from backend.configuration import ConfigurationBackend
from src.exceptions import ConfigurationError, PathValidationError


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OneDrive PC Sync")
        self.setMinimumSize(1100, 700)
        self.config_backend = None
        self.config_error = None
        self.setup_ui()
        self.load_configuration()

    def setup_ui(self):
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main vertical layout: header + content area
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header bar
        self.header = self.create_header()
        main_layout.addWidget(self.header)

        # Content area: sidebar + stacked widget
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Left sidebar
        self.sidebar = self.create_sidebar()
        content_layout.addWidget(self.sidebar)

        # Central content area (stacked widget)
        self.content_stack = QStackedWidget()
        content_layout.addWidget(self.content_stack, 1)  # stretch factor 1

        main_layout.addLayout(content_layout, 1)  # stretch factor 1

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def load_configuration(self):
        """Load configuration from file and handle any errors."""
        try:
            config_path = get_config_path()
            self.config_backend = ConfigurationBackend(str(config_path))
            self.config_error = None
            # Configuration loaded successfully, now add pages
            self.add_pages()
            # Set initial header text
            self.update_header("Dashboard", "Overview of sync status")
            self.status_bar.showMessage("Configuration loaded successfully")
        except (ConfigurationError, PathValidationError, FileNotFoundError) as e:
            self.config_error = str(e)
            self.config_backend = None
            # Show error state
            self.add_error_page()
            self.status_bar.showMessage(f"Configuration error: {e}")
        except Exception as e:
            self.config_error = f"Unexpected error loading configuration: {e}"
            self.config_backend = None
            # Show error state
            self.add_error_page()
            self.status_bar.showMessage(f"Configuration error: {e}")

    def add_pages(self):
        """Add pages to the stacked widget, passing configuration backend to pages that need it."""
        # Clear existing pages
        while self.content_stack.count():
            widget = self.content_stack.widget(0)
            self.content_stack.removeWidget(widget)
            widget.deleteLater()

        # Map page names to their classes
        page_classes = {
            "Dashboard": lambda: DashboardPage(self.config_backend),
            "Folders": lambda: FoldersPage(self.config_backend),
            "Backups": lambda: BackupsPage(self.config_backend),
            "Scheduler": lambda: SchedulerPage(self.config_backend),
            "Logs": lambda: LogsPage(self.config_backend),
            "Settings": lambda: SettingsPage(self.config_backend),
            "About": lambda: AboutPage(self.config_backend),
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

    def add_error_page(self):
        """Add an error page to show configuration issues."""
        # Clear existing pages
        while self.content_stack.count():
            widget = self.content_stack.widget(0)
            self.content_stack.removeWidget(widget)
            widget.deleteLater()

        # Create error widget
        from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget
        error_widget = QWidget()
        error_layout = QVBoxLayout(error_widget)
        error_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        error_label = QLabel(
            f"Configuration Error\n\n{self.config_error}\n\n"
            "Please check that config.json exists and is valid.\n"
            "See the documentation for configuration requirements."
        )
        error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        error_label.setWordWrap(True)
        error_label.setProperty("h2", "true")
        error_layout.addWidget(error_label)

        self.content_stack.addWidget(error_widget)

        # Update header to show error state
        self.update_header("Configuration Error", "Please fix config.json")

    # Keep the rest of the methods unchanged

    def create_header(self):
        header_frame = QFrame()
        header_frame.setObjectName("header")
        header_frame.setMinimumHeight(spacing.LARGE * 2)  # 64px minimum
        header_frame.setMaximumHeight(spacing.LARGE * 4)   # Allow up to 256px
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(spacing.LARGE, spacing.MEDIUM, spacing.LARGE, spacing.MEDIUM)
        header_layout.setSpacing(spacing.XSMALL)
        header_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)  # Align vertically center
        # Transparent background, no border
        header_frame.setStyleSheet("""
            QFrame#header {
                background: transparent;
                border: none;
            }
        """)

        self.header_title = QLabel()
        self.header_title.setProperty("h1", "true")
        header_layout.addWidget(self.header_title)

        self.header_subtitle = QLabel()
        self.header_subtitle.setProperty("h2", "true")
        self.header_subtitle.setProperty("class", "subtitle")
        header_layout.addWidget(self.header_subtitle)

        return header_frame

    def create_sidebar(self):
        sidebar_frame = QFrame()
        sidebar_frame.setObjectName("sidebar")
        sidebar_frame.setFixedWidth(spacing.SIDEBAR_WIDTH)
        base_style = get_sidebar_stylesheet()
        # Remove right border to avoid unnecessary border
        sidebar_frame.setStyleSheet(base_style + "\nQFrame#sidebar { border-right: none; }")

        sidebar_layout = QVBoxLayout(sidebar_frame)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        # Sidebar title (logo/name)
        title_label = QLabel("OneDrive PC Sync")
        title_label.setObjectName("sidebarTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sidebar_layout.addWidget(title_label)

        # Navigation list
        self.nav_list = QListWidget()
        self.nav_list.setIconSize(QSize(20, 20))
        self.nav_list.setSpacing(0)
        self.nav_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.nav_list.setProperty("class", "nav-list")

        # Add sidebar entries (top section)
        nav_entries = [
            ("Dashboard", "dashboard"),
            ("Folders", "folders"),
            ("Backups", "backups"),
            ("Scheduler", "scheduler"),
            ("Logs", "logs"),
        ]

        for text, icon_name in nav_entries:
            item = QListWidgetItem(text)
            item.setIcon(get_icon(icon_name))
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.nav_list.addItem(item)

        # Separator line
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setProperty("class", "separator")
        sidebar_layout.addWidget(separator)

        # Bottom section (Settings, About)
        bottom_entries = [
            ("Settings", "settings"),
            ("About", "about"),
        ]

        for text, icon_name in bottom_entries:
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

    def change_page(self, current, previous):
        if current is None:
            current = previous
        if current:
            index = self.nav_list.row(current)
            self.content_stack.setCurrentIndex(index)

            # Update header based on page
            page_titles = {
                "Dashboard": ("Dashboard", "Overview of sync status"),
                "Folders": ("Folders", "Manage synchronized folders"),
                "Backups": ("Backups", "View and manage backups"),
                "Scheduler": ("Scheduler", "View scheduled tasks"),
                "Logs": ("Logs", "View application logs"),
                "Settings": ("Settings", "Configure application settings"),
                "About": ("About", "About OneDrive PC Sync"),
            }
            title, subtitle = page_titles.get(current.text(), ("", ""))
            self.update_header(title, subtitle)

    def update_header(self, title: str, subtitle: str = ""):
        self.header_title.setText(title)
        self.header_subtitle.setText(subtitle)
        # Show/hide subtitle if empty
        self.header_subtitle.setVisible(bool(subtitle))