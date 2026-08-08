"""
Sync Worker
-----------
Provides a Qt background worker for synchronization operations.
Ensures UI remains responsive during long-running sync tasks.
"""

from PySide6.QtCore import QObject, Signal, Slot
from typing import Optional
import time

from backend.services.sync_service import SyncService
from src.sync_manager import SyncManager, FolderSyncOutcome
from src.config import SyncDirection


class SyncWorker(QObject):
    """
    Worker object that runs synchronization in a separate thread.
    """

    # Signals
    started = Signal(str)  # operation type: "startup" or "shutdown"
    # progress signal: percentage (0-100), message
    progress = Signal(int, str)
    completed = Signal(list)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, sync_service: SyncService, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._sync_service = sync_service
        self._is_cancelled = False  # Not used for now, but kept for future safe cancellation

    def _run_sync(self, operation: str):
        """Internal method to run synchronization for given operation."""
        self.started.emit(operation)
        self.progress.emit(0, f"Starting {operation} synchronization...")
        start_time = time.time()

        try:
            config = self._sync_service.get_app_config()
            if config is None:
                raise RuntimeError("Configuration not available")

            trigger = config.sync.startup if operation == "startup" else config.sync.shutdown
            if not trigger.enabled:
                raise RuntimeError(f"{operation.capitalize()} sync is disabled in configuration")

            sync_manager = SyncManager(config)
            folders = config.enabled_folders()
            total = len(folders)
            outcomes: List[FolderSyncOutcome] = []

            for i, folder in enumerate(folders):
                if self._is_cancelled:
                    break

                try:
                    outcome = sync_manager._sync_single_folder(folder, trigger.direction)
                except Exception as e:
                    outcome = FolderSyncOutcome(
                        folder_id=folder.id,
                        folder_name=folder.name,
                        direction=trigger.direction,
                        succeeded=False,
                        message=str(e),
                    )
                outcomes.append(outcome)

                # Emit progress after each folder
                percentage = int((i + 1) / total * 100) if total > 0 else 100
                self.progress.emit(
                    percentage,
                    f"Processing folder {folder.name} ({i + 1}/{total})",
                )

            elapsed = time.time() - start_time
            if not self._is_cancelled:
                self.progress.emit(
                    100,
                    f"{operation.capitalize()} synchronization completed in {elapsed:.1f} seconds.",
                )
                self.completed.emit(outcomes)
            else:
                self.progress.emit(0, f"{operation.capitalize()} synchronization cancelled.")
                self.completed.emit(outcomes)  # still return partial outcomes

        except Exception as e:
            elapsed = time.time() - start_time
            self.progress.emit(
                0,
                f"{operation.capitalize()} synchronization failed after {elapsed:.1f} seconds: {e}",
            )
            self.failed.emit(str(e))
        finally:
            self.finished.emit()

    @Slot()
    def start_startup_sync(self):
        """Slot to start startup synchronization."""
        self._run_sync("startup")

    @Slot()
    def start_shutdown_sync(self):
        """Slot to start shutdown synchronization."""
        self._run_sync("shutdown")

    # Cancellation not implemented safely; no cancel slot provided.