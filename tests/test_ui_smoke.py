import os
import sys
import pytest

# Set the QT_QPA_PLATFORM to offscreen before importing PySide6
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow
from ui.pages.dashboard import DashboardPage
from ui.pages.folders import FoldersPage
from ui.pages.backups import BackupsPage
from ui.pages.scheduler import SchedulerPage
from ui.pages.logs import LogsPage
from ui.pages.settings import SettingsPage
from ui.pages.about import AboutPage
from ui.widgets.card import Card
from ui.widgets.folder_card import FolderCard
from ui.widgets.sync_chart import SyncChartWidget
from ui.widgets.add_folder_wizard import AddFolderWizard

# Mock services for testing
class MockConfigurationService:
    def get_app_config(self):
        return None

class MockSyncService:
    pass

class MockBackupService:
    pass

class MockSchedulerService:
    pass

class MockMonitorService:
    pass

class MockLogService:
    pass

def create_services():
    """Create mock services for testing."""
    return (
        MockConfigurationService(),
        MockSyncService(),
        MockBackupService(),
        MockSchedulerService(),
        MockMonitorService(),
        MockLogService()
    )


def create_services():
    """Create mock services for testing."""
    # For the smoke test, we don't need real services, but we need to pass something.
    # We'll create mock services that return None or default values.
    class MockConfigService:
        def get_app_config(self):
            return None

    class MockSyncService:
        pass

    class MockBackupService:
        pass

    class MockSchedulerService:
        pass

    class MockMonitorService:
        pass

    class MockLogService:
        pass

    return (
        MockConfigService(),
        MockSyncService(),
        MockBackupService(),
        MockSchedulerService(),
        MockMonitorService(),
        MockLogService(),
    )


def test_main_window_creation():
    """Test that MainWindow can be created without errors."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    config_service, sync_service, backup_service, scheduler_service, monitor_service, log_service = create_services()
    window = MainWindow(
        configuration_service=config_service,
        sync_service=sync_service,
        backup_service=backup_service,
        scheduler_service=scheduler_service,
        monitor_service=monitor_service,
        log_service=log_service
    )
    assert window is not None
    window.close()


def test_dashboard_page_creation():
    """Test that DashboardPage can be created without errors."""
    config_service, sync_service, backup_service, scheduler_service, monitor_service, log_service = create_services()
    page = DashboardPage(config_service, sync_service, backup_service, scheduler_service, monitor_service, log_service)
    assert page is not None


def test_folders_page_creation():
    """Test that FoldersPage can be created without errors."""
    config_service, _, _, _, _, _ = create_services()
    page = FoldersPage(config_service)
    assert page is not None


def test_backups_page_creation():
    """Test that BackupsPage can be created without errors."""
    config_service, _, backup_service, _, _, _ = create_services()
    page = BackupsPage(config_service, backup_service)
    assert page is not None


def test_scheduler_page_creation():
    """Test that SchedulerPage can be created without errors."""
    config_service, _, _, scheduler_service, monitor_service, _ = create_services()
    page = SchedulerPage(config_service, scheduler_service, monitor_service)
    assert page is not None


def test_logs_page_creation():
    """Test that LogsPage can be created without errors."""
    _, _, _, _, _, log_service = create_services()
    page = LogsPage(log_service)
    assert page is not None


def test_settings_page_creation():
    """Test that SettingsPage can be created without errors."""
    config_service, _, _, _, _, _ = create_services()
    page = SettingsPage(config_service)
    assert page is not None


def test_about_page_creation():
    """Test that AboutPage can be created without errors."""
    page = AboutPage()
    assert page is not None


def test_card_creation():
    """Test that Card widget can be created without errors."""
    card = Card(title="Test", value="123", icon_name="test", description="Test description")
    assert card is not None


def test_folder_card_creation():
    """Test that FolderCard widget can be created without errors."""
    folder_data = {
        "name": "Test Folder",
        "local_path": "C:\\Test",
        "onedrive_path": "Test",
        "direction": "Download",
        "safety_threshold": 80,
        "backup_status": "Configured",
        "last_sync": "Never",
        "sync_status": "Idle",
        "enabled": True,
        "icon": "folder"
    }
    card = FolderCard(folder_data=folder_data)
    assert card is not None


def test_sync_chart_widget_creation():
    """Test that SyncChartWidget can be created without errors."""
    widget = SyncChartWidget()
    assert widget is not None


def test_add_folder_wizard_creation():
    """Test that AddFolderWizard can be created without errors."""
    wizard = AddFolderWizard()
    assert wizard is not None


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])