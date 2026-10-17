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
    QSystemTrayIcon,
    QMenu,
    QApplication,
    QSizePolicy,
)
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt, QSize, QTimer, QObject, QEvent
from .pages.dashboard import DashboardPage
from .pages.folders import FoldersPage
from .pages.backups import BackupsPage
from .pages.scheduler import SchedulerPage
from .pages.logs import LogsPage
from .pages.settings import SettingsPage
from .pages.about import AboutPage
from .themes.theme import get_dark_theme, get_sidebar_stylesheet
from .themes import spacing
from .resources.icons import get_icon, get_app_icon
from src.app_info import APP_NAME
from backend.services.configuration_service import ConfigurationService
from backend.services.sync_service import SyncService
from backend.services.backup_service import BackupService
from backend.services.scheduler_service import SchedulerService
from backend.services.monitor_service import MonitorService
from backend.services.log_service import LogService
from backend.services.update_service import UpdateService


class MainWindow(QMainWindow):
    def __init__(self, configuration_service=None, sync_service=None, backup_service=None, scheduler_service=None, monitor_service=None, log_service=None, update_service=None):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1100, 700)
        self.resize(1360, 900)
        self.setWindowIcon(get_app_icon())
        # Services
        self.configuration_service = configuration_service if configuration_service is not None else ConfigurationService()
        self.sync_service = sync_service if sync_service is not None else SyncService(self.configuration_service)
        self.backup_service = backup_service if backup_service is not None else BackupService(self.configuration_service)
        self.scheduler_service = scheduler_service if scheduler_service is not None else SchedulerService(self.configuration_service)
        self.monitor_service = monitor_service if monitor_service is not None else MonitorService(self.configuration_service)
        self.log_service = log_service if log_service is not None else LogService()
        self.update_service = update_service if update_service is not None else UpdateService(self.sync_service, parent=self)
        self.config_error = None
        self._exit_requested = False
        self.setup_ui()
        self.load_services()
        self.create_tray_icon()
        self.update_service.available.connect(self.on_update_available)
        self.update_service.install_started.connect(self.exit_application)
        QApplication.instance().aboutToQuit.connect(self.prepare_for_exit)
        if isinstance(self.sync_service, SyncService):
            QApplication.instance().aboutToQuit.connect(self.sync_service.wait_for_finished)
        if isinstance(self.scheduler_service, SchedulerService):
            self.destroyed.connect(self.scheduler_service.wait_for_finished)

    def prepare_for_exit(self):
        self.update_service.wait_for_finished()
        if isinstance(self.sync_service, SyncService):
            self.sync_service.wait_for_finished()
        if isinstance(self.scheduler_service, SchedulerService):
            self.scheduler_service.wait_for_finished()
        # pyqtgraph requires PlotItem.close before native scene destruction.
        # Parent QWidget deletion does not call PlotWidget.close automatically.
        from pyqtgraph import PlotWidget
        for chart in self.findChildren(PlotWidget):
            if chart.plotItem is not None:
                chart.close()
                chart.deleteLater()

    def event(self, event):
        if event.type() == QEvent.Type.DeferredDelete and hasattr(self, "update_service"):
            self.prepare_for_exit()
        return super().event(event)

    def setup_ui(self):
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Full-height navigation with a separate header and content column.
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.sidebar = self.create_sidebar()
        main_layout.addWidget(self.sidebar)

        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        self.header = self.create_header()
        content_layout.addWidget(self.header)

        # Central content area (stacked widget)
        self.content_stack = QStackedWidget()
        content_layout.addWidget(self.content_stack, 1)  # stretch factor 1

        main_layout.addLayout(content_layout, 1)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def load_services(self):
        """Handle any configuration errors."""
        try:
            # Check if configuration is available
            app_config = self.configuration_service.get_app_config()
            if app_config is None:
                raise Exception("Configuration is not available or invalid.")

            # Services loaded successfully
            self.config_error = None
            self.add_pages()
            # Set initial header text
            self.update_header("Dashboard", "Overview of sync status")
            self.status_bar.showMessage("Services initialized successfully")

            # Connect to sync service signals
            if self.sync_service:
                self.sync_service.started.connect(self.on_sync_started)
                self.sync_service.completed.connect(self.on_sync_completed)
                self.sync_service.failed.connect(self.on_sync_failed)
                self.sync_service.finished.connect(self.on_sync_finished)
        except Exception as e:
            self.config_error = str(e)
            # We don't set the services to None because they are already created.
            # Show error state
            self.add_error_page()
            self.status_bar.showMessage(f"Service initialization error: {e}")

    def create_tray_icon(self):
        """Create the system tray icon and context menu."""
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(get_app_icon("idle"))
        self.tray_icon.setToolTip("EverySync - Idle")

        # Create context menu
        self.tray_menu = QMenu()
        self.toggle_window_action = QAction("Open", self)
        self.toggle_window_action.triggered.connect(self.toggle_window)
        self.tray_menu.addAction(self.toggle_window_action)

        self.sync_now_action = QAction("Sync Now", self)
        self.sync_now_action.triggered.connect(self.sync_now)
        self.tray_menu.addAction(self.sync_now_action)

        self.pause_resume_action = QAction("Pause", self)
        self.pause_resume_action.triggered.connect(self.toggle_pause_resume)
        self.tray_menu.addAction(self.pause_resume_action)

        self.tray_menu.addSeparator()

        self.settings_action = QAction("Settings", self)
        self.settings_action.triggered.connect(self.open_settings)
        self.tray_menu.addAction(self.settings_action)

        self.updates_action = QAction("Check for updates", self)
        self.updates_action.triggered.connect(lambda: self.open_updates())
        self.tray_menu.addAction(self.updates_action)

        self.exit_action = QAction("Exit", self)
        self.exit_action.triggered.connect(self.exit_application)
        self.tray_menu.addAction(self.exit_action)

        self.tray_icon.setContextMenu(self.tray_menu)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon.show()
        self.tray_icon.activated.connect(self.on_tray_activated)

        if isinstance(self.sync_service, SyncService):
            self.sync_service.state_changed.connect(self.update_sync_actions)
            self.update_sync_actions()

    def toggle_window(self):
        """Show or hide the main window."""
        if self.isVisible():
            self.hide()
            self.toggle_window_action.setText("Open")
        else:
            self.show()
            self.toggle_window_action.setText("Hide")

    def on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_and_activate()

    def show_and_activate(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def update_sync_actions(self):
        service = self.sync_service
        self.sync_now_action.setEnabled(
            not service.is_syncing and not service.is_paused and service.is_shutdown_sync_enabled()
        )
        self.pause_resume_action.setText("Resume UI Sync" if service.is_paused else "Pause UI Sync")
        self.pause_resume_action.setToolTip("Pauses new UI syncs; scheduled Windows tasks continue independently.")

    def sync_now(self):
        """Use the same background coordinator as the dashboard."""
        self.sync_service.request_sync("shutdown")

    def toggle_pause_resume(self):
        self.sync_service.set_paused(not self.sync_service.is_paused)

    def open_settings(self):
        """Open the settings page."""
        self.show()
        self.activateWindow()
        # Navigate to Settings page
        for i in range(self.content_stack.count()):
            widget = self.content_stack.widget(i)
            if isinstance(widget, SettingsPage):
                self.content_stack.setCurrentIndex(i)
                self.nav_list.setCurrentItem(self.nav_list.item(i))
                self.update_header("Settings", "Configure application settings")
                break

    def exit_application(self):
        """Exit the application."""
        if getattr(self.sync_service, "is_syncing", False):
            self._exit_requested = True
            self.status_bar.showMessage("Finishing synchronization before exit...")
            return
        QApplication.instance().quit()

    def open_updates(self, install=False):
        self.show_and_activate()
        for index in range(self.content_stack.count()):
            if isinstance(self.content_stack.widget(index), AboutPage):
                self.nav_list.setCurrentRow(index)
                break
        self.update_service.check(install=install)

    def on_update_available(self, version):
        self.status_bar.showMessage(f"Update {version} is available. Open About to install it.")
        if self.tray_icon.isVisible():
            self.tray_icon.showMessage("EverySync update", f"Version {version} is available. Open About to install.",
                                       get_app_icon(), 5000)

    def closeEvent(self, event):
        """Override close event to hide to tray instead of closing."""
        if QSystemTrayIcon.isSystemTrayAvailable() and self.tray_icon.isVisible():
            self.hide()
            event.ignore()
            self.tray_icon.showMessage(
                "EverySync",
                "Application was minimized to tray. To exit, right-click the tray icon and select Exit.",
                get_app_icon(),
                2000,
            )
        else:
            if getattr(self.sync_service, "is_syncing", False):
                event.ignore()
                self.exit_application()
            else:
                event.accept()

    def on_sync_started(self, operation: str):
        """Handle sync started signal from service."""
        self.tray_icon.setIcon(get_app_icon("running"))
        self.tray_icon.setToolTip(f"EverySync - {operation.capitalize()} synchronization in progress...")

    def on_sync_completed(self, outcomes):
        """Handle sync completed signal from service."""
        # Determine if all succeeded
        if all(outcome.succeeded for outcome in outcomes):
            self.tray_icon.setIcon(get_app_icon("success"))
            self.tray_icon.setToolTip("EverySync - Synchronization completed successfully")
        else:
            self.tray_icon.setIcon(get_app_icon("error"))
            self.tray_icon.setToolTip("EverySync - Synchronization completed with errors")

    def on_sync_failed(self, error_message: str):
        """Handle sync failed signal from service."""
        self.tray_icon.setIcon(get_app_icon("error"))
        self.tray_icon.setToolTip(f"EverySync - Synchronization failed: {error_message}")

    def on_sync_finished(self):
        """Handle sync finished signal from service."""
        # The service emits finished only after its thread has stopped.
        if self._exit_requested:
            self.exit_application()


    def add_pages(self):
        """Add pages to the stacked widget, passing services to pages that need them."""
        # Clear existing pages
        while self.content_stack.count():
            widget = self.content_stack.widget(0)
            self.content_stack.removeWidget(widget)
            widget.deleteLater()

        # Map page names to their classes and required services
        page_factories = {
            "Dashboard": lambda: DashboardPage(
                config_service=self.configuration_service,
                sync_service=self.sync_service,
                backup_service=self.backup_service,
                scheduler_service=self.scheduler_service,
                monitor_service=self.monitor_service,
                log_service=self.log_service
            ),
            "Folders": lambda: FoldersPage(
                config_service=self.configuration_service,
                sync_service=self.sync_service
            ),
            "Backups": lambda: BackupsPage(
                config_service=self.configuration_service,
                backup_service=self.backup_service
            ),
            "Scheduler": lambda: SchedulerPage(
                config_service=self.configuration_service,
                scheduler_service=self.scheduler_service,
                monitor_service=self.monitor_service
            ),
            "Logs": lambda: LogsPage(
                log_service=self.log_service
            ),
            "Settings": lambda: SettingsPage(
                config_service=self.configuration_service
            ),
            "About": lambda: AboutPage(config_service=self.configuration_service, update_service=self.update_service)
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
            page_factory = page_factories[name]
            page = page_factory()
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
            f"Service Initialization Error\n\n{self.config_error}\n\n"
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
        header_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(spacing.LARGE, 22, spacing.LARGE, 20)
        header_layout.setSpacing(5)

        self.header_title = QLabel()
        self.header_title.setTextFormat(Qt.TextFormat.PlainText)
        self.header_title.setWordWrap(True)
        self.header_title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.header_title.setProperty("h1", "true")
        header_layout.addWidget(self.header_title)

        self.header_subtitle = QLabel()
        self.header_subtitle.setTextFormat(Qt.TextFormat.PlainText)
        self.header_subtitle.setProperty("class", "subtitle")
        self.header_subtitle.setWordWrap(True)
        header_layout.addWidget(self.header_subtitle)

        return header_frame

    def create_sidebar(self):
        sidebar_frame = QFrame()
        sidebar_frame.setObjectName("sidebar")
        sidebar_frame.setFixedWidth(spacing.SIDEBAR_WIDTH)
        sidebar_frame.setStyleSheet(get_sidebar_stylesheet())

        sidebar_layout = QVBoxLayout(sidebar_frame)
        sidebar_layout.setContentsMargins(16, 26, 16, 20)
        sidebar_layout.setSpacing(12)

        # Sidebar title (logo/name)
        brand_icon = QLabel()
        brand_icon.setPixmap(get_app_icon().pixmap(QSize(36, 36)))
        sidebar_layout.addWidget(brand_icon)
        title_label = QLabel(APP_NAME)
        title_label.setObjectName("sidebarTitle")
        sidebar_layout.addWidget(title_label)
        caption = QLabel("Your folders. In sync.")
        caption.setObjectName("sidebarCaption")
        sidebar_layout.addWidget(caption)
        sidebar_layout.addSpacing(24)
        workspace_label = QLabel("WORKSPACE")
        workspace_label.setProperty("title", "true")
        sidebar_layout.addWidget(workspace_label)

        # Navigation list
        self.nav_list = QListWidget()
        self.nav_list.setIconSize(QSize(20, 20))
        self.nav_list.setSpacing(0)
        self.nav_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.nav_list.setProperty("class", "nav-list")
        self.nav_list.setAccessibleName("Main navigation")
        self.nav_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

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

        sidebar_layout.addWidget(self.nav_list, 1)
        sidebar_layout.addWidget(separator)
        footer = QLabel("Local PC  /  OneDrive")
        footer.setObjectName("sidebarCaption")
        sidebar_layout.addWidget(footer)
        detail = QLabel("Only the folders you choose.")
        detail.setObjectName("sidebarCaption")
        detail.setWordWrap(True)
        sidebar_layout.addWidget(detail)

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
                "About": ("About", "About EverySync"),
            }
            title, subtitle = page_titles.get(current.text(), ("", ""))
            self.update_header(title, subtitle)

    def update_header(self, title: str, subtitle: str = ""):
        self.header_title.setText(title)
        self.header_subtitle.setText(subtitle)
        # Show/hide subtitle if empty
        self.header_subtitle.setVisible(bool(subtitle))
