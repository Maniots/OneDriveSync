import os
import sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow

# Mock services
class MockConfigurationService:
    def get_app_config(self):
        return None  # Simulate no config available, which will trigger error state but not crash

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

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

try:
    window = MainWindow(
        configuration_service=MockConfigurationService(),
        sync_service=MockSyncService(),
        backup_service=MockBackupService(),
        scheduler_service=MockSchedulerService(),
        monitor_service=MockMonitorService(),
        log_service=MockLogService()
    )
    print("SUCCESS: MainWindow created")
    window.close()
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)