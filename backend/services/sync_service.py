"""Coordinate all UI sync requests, state and background thread ownership."""

from typing import List, Optional
from dataclasses import replace

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot

from src.config import AppConfig
from src.sync_manager import FolderSyncOutcome
from ui.workers.sync_worker import SyncWorker
from .configuration_service import ConfigurationService


class SyncService(QObject):
    started = Signal(str)
    progress = Signal(int, str)
    completed = Signal(list)
    failed = Signal(str)
    finished = Signal()
    state_changed = Signal()

    def __init__(self, config_service: ConfigurationService):
        super().__init__()
        self._config_service = config_service
        self._is_syncing = False
        self._is_paused = False
        self._thread: Optional[QThread] = None
        self._worker: Optional[SyncWorker] = None
        if hasattr(config_service, "changed"):
            config_service.changed.connect(self._on_configuration_changed)

    @Slot(object)
    def _on_configuration_changed(self, config) -> None:
        self.state_changed.emit()

    @property
    def is_syncing(self) -> bool:
        return self._is_syncing

    @property
    def is_paused(self) -> bool:
        return self._is_paused

    def set_paused(self, paused: bool) -> None:
        """Pause new UI requests; let any current copy finish safely.

        Windows Scheduled Tasks remain independent of the UI pause state.
        """
        if self._is_paused != paused:
            self._is_paused = paused
            self.state_changed.emit()

    def _prepare_sync(self, operation: str, folder_id: Optional[str] = None) -> Optional[AppConfig]:
        # A duplicate click must not alter the active run's result/signals.
        if self._is_syncing:
            return None
        if self._is_paused:
            self.failed.emit("UI synchronization is paused")
            return None
        config = self.get_app_config()
        if config is None:
            self.failed.emit("Configuration not available")
            return None
        if operation not in ("startup", "shutdown"):
            self.failed.emit(f"Invalid sync operation: {operation}")
            return None
        if not getattr(config.sync, operation).enabled:
            self.failed.emit(f"{operation.capitalize()} sync is disabled in configuration")
            return None
        if folder_id is not None:
            folders = [folder for folder in config.enabled_folders() if folder.id == folder_id]
            if not folders:
                self.failed.emit("Folder not found or disabled")
                return None
            config = replace(config, folders=folders)
        self._is_syncing = True
        self.state_changed.emit()
        return config

    def _connect_worker(self, worker: SyncWorker) -> None:
        worker.started.connect(self.started)
        worker.progress.connect(self.progress)
        worker.completed.connect(self.completed)
        worker.failed.connect(self.failed)

    def request_sync(self, operation: str, folder_id: Optional[str] = None) -> bool:
        """Start one background operation from the GUI thread, if allowed."""
        config = self._prepare_sync(operation, folder_id)
        if config is None:
            return False
        self._thread = QThread(self)
        self._worker = SyncWorker(self, config=config)
        self._worker.moveToThread(self._thread)
        self._connect_worker(self._worker)
        start = self._worker.start_startup_sync if operation == "startup" else self._worker.start_shutdown_sync
        self._thread.started.connect(start)
        self._worker.finished.connect(self._thread.quit, Qt.ConnectionType.DirectConnection)
        self._worker.finished.connect(self._worker.deleteLater)
        # Release references only once the thread has actually stopped.
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()
        return True

    @Slot()
    def _on_thread_finished(self) -> None:
        if not self._is_syncing:
            return
        self._worker = None
        self._thread = None
        self._is_syncing = False
        self.state_changed.emit()
        self.finished.emit()

    @Slot()
    def wait_for_finished(self) -> None:
        """Keep an application shutdown from destroying a running QThread."""
        if self._thread is not None:
            self._thread.wait()
            self._on_thread_finished()

    def _run_blocking_sync(self, operation: str) -> List[FolderSyncOutcome]:
        """Compatibility API for non-interactive callers; UI uses request_sync."""
        config = self._prepare_sync(operation)
        if config is None:
            return []
        worker = SyncWorker(self, config=config)
        self._connect_worker(worker)
        try:
            return worker._run_sync(operation)
        finally:
            self._is_syncing = False
            self.state_changed.emit()
            self.finished.emit()

    def start_startup_sync(self) -> List[FolderSyncOutcome]:
        return self._run_blocking_sync("startup")

    def start_shutdown_sync(self) -> List[FolderSyncOutcome]:
        return self._run_blocking_sync("shutdown")

    def is_startup_sync_enabled(self) -> bool:
        config = self.get_app_config()
        return config is not None and config.sync.startup.enabled

    def is_shutdown_sync_enabled(self) -> bool:
        config = self.get_app_config()
        return config is not None and config.sync.shutdown.enabled

    def get_app_config(self) -> Optional[AppConfig]:
        return self._config_service.get_app_config()
