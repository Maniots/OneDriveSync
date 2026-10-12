"""Coordinate all UI sync requests, state and background thread ownership."""

from typing import List, Optional
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot, QFileSystemWatcher, QTimer

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
        self._monitor_dirty = False
        self._monitor_running = False
        self._monitor_failed = False
        self.history_error = None
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._on_source_changed)
        self._watcher.fileChanged.connect(self._on_source_changed)
        self._monitor_timer = QTimer(self)
        self._monitor_timer.setSingleShot(True)
        self._monitor_timer.setInterval(1500)
        self._monitor_timer.timeout.connect(self._run_monitored_sync)
        self._unwatched_state = {}
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(3000)
        self._poll_timer.timeout.connect(self._poll_unwatched)
        if hasattr(config_service, "changed"):
            config_service.changed.connect(self._on_configuration_changed)
        self._refresh_monitor()

    @Slot(object)
    def _on_configuration_changed(self, config) -> None:
        self._monitor_dirty = False
        self._refresh_monitor()
        self.state_changed.emit()

    def get_history(self, limit=100):
        from src.sync_history import SyncHistory
        try:
            result = SyncHistory(self._config_service.history_path).recent(limit)
            self.history_error = None
            return result
        except Exception as exc:
            if self.history_error != str(exc):
                from src.logger import get_logger
                get_logger(__name__).warning("Sync history unavailable: %s", exc)
            self.history_error = str(exc)
            return []

    @property
    def history_path(self):
        return self._config_service.history_path

    def get_folder_history(self):
        latest = {}
        for run in self.get_history(1000):
            for outcome in run["outcomes"]:
                latest.setdefault(outcome["folder_id"], dict(outcome, timestamp=run["timestamp"], dry_run=run["dry_run"]))
        return latest

    def _refresh_monitor(self):
        paths = self._watcher.files() + self._watcher.directories()
        if paths:
            self._watcher.removePaths(paths)
        config = self.get_app_config()
        if not config or not config.copy_engine.monitor_mode or not config.sync.shutdown.enabled:
            self._monitor_timer.stop()
            self._poll_timer.stop()
            self._unwatched_state = {}
            return
        from src.robocopy_manager import _walk_source, _collect_files
        watched = set()
        for folder in config.enabled_folders():
            source = folder.local_path_resolved if config.sync.shutdown.direction.value == "upload" else folder.onedrive_path_resolved
            parent = source
            while not parent.exists() and parent != parent.parent:
                parent = parent.parent
            watched.add(str(parent))
            if source.is_dir():
                watched.update(str(root) for root, _, _ in _walk_source(source, config.copy_engine.copy_subdirectories, config.copy_engine.exclude_junctions))
                watched.update(str(p) for p in _collect_files(source, config.copy_engine.copy_subdirectories, config.copy_engine.exclude_junctions))
        if watched:
            failures = self._watcher.addPaths(sorted(watched))
            self._unwatched_state = {path: self._path_state(path) for path in failures}
            if failures:
                from src.logger import get_logger
                get_logger(__name__).warning("Cannot monitor %d path(s): %s", len(failures), failures)
                self._poll_timer.start()
            else:
                self._poll_timer.stop()

    @staticmethod
    def _path_state(path):
        try:
            metadata = Path(path).stat()
            return metadata.st_mtime_ns, metadata.st_size
        except OSError:
            return None

    def _poll_unwatched(self):
        state = {path: self._path_state(path) for path in self._unwatched_state}
        if state != self._unwatched_state:
            self._unwatched_state = state
            self._on_source_changed("")

    def _on_source_changed(self, path):
        self._monitor_dirty = True
        self._monitor_timer.start(1500)

    def _run_monitored_sync(self):
        config = self.get_app_config()
        if not config or not config.copy_engine.monitor_mode:
            self._monitor_dirty = False
            return
        self._refresh_monitor()  # Include new files and reattach atomic replacements.
        if self._monitor_dirty and not self.is_syncing and not self.is_paused and config.sync.shutdown.enabled:
            self._monitor_dirty = False
            self._monitor_running = True
            if not self.request_sync("shutdown"):
                self._monitor_running = False
                self._monitor_dirty = True

    def _on_worker_failed(self, message):
        if self._monitor_running:
            self._monitor_dirty = True
            self._monitor_failed = True
        self.failed.emit(message)

    def _on_worker_completed(self, outcomes):
        if self._monitor_running and any(not outcome.succeeded for outcome in outcomes):
            self._monitor_dirty = True
            self._monitor_failed = True
        self.completed.emit(outcomes)

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
            if not paused and self._monitor_dirty:
                self._monitor_timer.start()

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
        worker.completed.connect(self._on_worker_completed)
        worker.failed.connect(self._on_worker_failed)

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
        self._monitor_running = False
        self.state_changed.emit()
        self.finished.emit()
        if self._monitor_dirty:
            self._monitor_timer.start(30000 if self._monitor_failed else 1500)
            self._monitor_failed = False

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
