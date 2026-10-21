"""Coordinate all UI sync requests, state and background thread ownership."""

from typing import List, Optional
from dataclasses import replace
from pathlib import Path
import threading

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot, QFileSystemWatcher, QTimer

from src.config import AppConfig, SyncDirection
from src.sync_groups import grouped_job_ids
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
        self.cancellation_event = threading.Event()
        self.active_direction: Optional[SyncDirection] = None
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

    @property
    def cloud_root(self):
        return self._config_service.cloud_root

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
        owned = grouped_job_ids(config)
        active = {destination.job_id for group in config.sync_groups if group.enabled
                  for destination in group.destinations
                  if getattr(destination, f"{config.sync.shutdown.direction.value}_enabled")}
        sources = [folder.local_path_resolved if config.sync.shutdown.direction.value == "upload" else folder.onedrive_path_resolved
                   for folder in config.enabled_folders() if folder.id not in owned or folder.id in active]
        sources.extend(job.local_path_resolved for job in config.remote_jobs
                       if job.enabled and (job.id not in owned or job.id in active)
                       and (job.bidirectional or config.sync.shutdown.direction.value == "upload"))
        for source in sources:
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

    def cancel_after_current_destination(self) -> None:
        """Ask a group run to stop safely between destinations."""
        if self._is_syncing:
            self.cancellation_event.set()

    def _prepare_sync(self, operation: str, folder_id: Optional[str] = None,
                      config_override: Optional[AppConfig] = None) -> Optional[AppConfig]:
        # A duplicate click must not alter the active run's result/signals.
        if self._is_syncing:
            return None
        if self._is_paused:
            self.failed.emit("UI synchronization is paused")
            return None
        config = config_override if config_override is not None else self.get_app_config()
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
            if folder_id in grouped_job_ids(config):
                self.failed.emit("This destination belongs to a synchronization. Select its parent activity.")
                return None
            groups = [group for group in config.sync_groups if group.id == folder_id and group.enabled]
            if groups:
                references = {item.job_id for item in groups[0].destinations}
                config = replace(config, sync_groups=groups,
                    folders=[folder for folder in config.folders if folder.id in references],
                    remote_jobs=[job for job in config.remote_jobs if job.id in references])
                self._is_syncing = True
                self.cancellation_event.clear()
                self.active_direction = getattr(config.sync, operation).direction
                self.state_changed.emit()
                return config
            folders = [folder for folder in config.enabled_folders() if folder.id == folder_id]
            jobs = [job for job in config.remote_jobs if job.enabled and job.id == folder_id]
            if len(folders) + len(jobs) != 1:
                self.failed.emit("Folder not found or disabled")
                return None
            config = replace(config, folders=folders, remote_jobs=jobs, sync_groups=[])
        self._is_syncing = True
        self.cancellation_event.clear()
        self.active_direction = getattr(config.sync, operation).direction
        self.state_changed.emit()
        return config

    def _connect_worker(self, worker: SyncWorker) -> None:
        worker.started.connect(self.started)
        worker.progress.connect(self.progress)
        worker.completed.connect(self._on_worker_completed)
        worker.failed.connect(self._on_worker_failed)

    def request_sync(self, operation: str, folder_id: Optional[str] = None,
                     ignore_threshold: bool = False) -> bool:
        """Start one background operation from the GUI thread, if allowed."""
        return self._start_request(operation, folder_id, ignore_threshold)

    def request_direction_sync(self, direction: SyncDirection | str, item_id: str) -> bool:
        """Run one manual direction without changing persisted scheduled triggers."""
        if not isinstance(item_id, str) or not item_id.strip():
            self.failed.emit("Select one synchronization for a manual direction")
            return False
        try:
            direction = SyncDirection(direction)
        except ValueError:
            self.failed.emit("Invalid synchronization direction")
            return False
        config = self.get_app_config()
        if config is None:
            self.failed.emit("Configuration not available")
            return False
        operation = "startup" if direction == SyncDirection.DOWNLOAD else "shutdown"
        trigger = replace(getattr(config.sync, operation), enabled=True, direction=direction)
        config = replace(config, sync=replace(config.sync, **{operation: trigger}))
        return self._start_request(operation, item_id, False, config_override=config)

    def _start_request(self, operation, folder_id=None, ignore_threshold=False, *, config_override=None):
        if ignore_threshold and folder_id is None:
            self.failed.emit("A threshold override requires a single selected folder")
            return False
        current = config_override if config_override is not None else self.get_app_config()
        if ignore_threshold and current and any(group.id == folder_id for group in current.sync_groups):
            self.failed.emit("Threshold overrides apply only to independent single destinations")
            return False
        config = self._prepare_sync(operation, folder_id, config_override)
        if config is None:
            return False
        self._thread = QThread(self)
        self._worker = SyncWorker(self, config=config,
                                  ignore_threshold_for=folder_id if ignore_threshold else None)
        self._worker.moveToThread(self._thread)
        self._connect_worker(self._worker)
        start = self._worker.start_startup_sync if operation == "startup" else self._worker.start_shutdown_sync
        self._thread.started.connect(start)
        self._worker.finished.connect(self._thread.quit, Qt.ConnectionType.DirectConnection)
        self._worker.finished.connect(self._worker.deleteLater)
        # Join in the completion slot before releasing worker wrappers.
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()
        return True

    @Slot()
    def _on_thread_finished(self) -> None:
        if not self._is_syncing:
            return
        if self._thread is not None:
            self._thread.wait()
        self._worker = None
        self._thread = None
        self._is_syncing = False
        self.active_direction = None
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
            self.active_direction = None
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
