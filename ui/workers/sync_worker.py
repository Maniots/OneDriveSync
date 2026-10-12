"""Run the core sync workflow off the GUI thread, using the CLI's file lock."""

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QObject, Signal, Slot

from src.config import AppConfig
from src.logger import setup_logger
from src.single_instance import acquire_single_instance_lock
from src.sync_manager import SyncManager

if TYPE_CHECKING:
    from backend.services.sync_service import SyncService


class SyncWorker(QObject):
    started = Signal(str)
    progress = Signal(int, str)
    completed = Signal(list)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, sync_service: "SyncService", parent: Optional[QObject] = None,
                 config: Optional[AppConfig] = None):
        super().__init__(parent)
        self._sync_service = sync_service
        self._config = config

    def _run_sync(self, operation: str):
        lock_handle = None
        outcomes = []
        try:
            config = self._config if self._config is not None else self._sync_service.get_app_config()
            if config is None:
                raise RuntimeError("Configuration not available")
            if operation not in ("startup", "shutdown"):
                raise ValueError(f"Invalid sync operation: {operation}")
            trigger = getattr(config.sync, operation)
            if not trigger.enabled:
                raise RuntimeError(f"{operation.capitalize()} sync is disabled in configuration")

            lock_path = Path(__file__).resolve().parents[2] / "onedrive_pcsync.lock"
            lock_handle = acquire_single_instance_lock(lock_path)
            if lock_handle is None:
                raise RuntimeError("Another synchronization is already running on this machine")

            setup_logger(lock_path.parent / "logs", log_level=config.general.log_level.value)
            self.started.emit(operation)
            manager = SyncManager(config, history_path=self._sync_service.history_path)
            run = manager.run_startup_sync if operation == "startup" else manager.run_shutdown_sync
            outcomes = run(progress_callback=self.progress.emit)
            self.progress.emit(100, f"{operation.capitalize()} synchronization finished.")
            self.completed.emit(outcomes)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            if lock_handle is not None:
                lock_handle.close()
            self.finished.emit()
        return outcomes

    @Slot()
    def start_startup_sync(self):
        self._run_sync("startup")

    @Slot()
    def start_shutdown_sync(self):
        self._run_sync("shutdown")
