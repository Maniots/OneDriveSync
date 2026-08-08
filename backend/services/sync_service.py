"""
Sync Service

Provides a clean API for initiating synchronization operations.
Isolates the UI from the core synchronization logic.
"""

from typing import List, Optional
from PySide6.QtCore import QObject, Signal
from src.config import AppConfig
from src.sync_manager import SyncManager, FolderSyncOutcome
from .configuration_service import ConfigurationService


class SyncService(QObject):
    """Service for managing synchronization operations."""

    # Signals for sync state changes
    started = Signal(str)  # operation type: "startup" or "shutdown"
    progress = Signal(int, str)  # percentage, message
    completed = Signal(list)  # list of FolderSyncOutcome
    failed = Signal(str)  # error message
    finished = Signal()  # sync finished (success or failed)

    def __init__(self, config_service: ConfigurationService):
        """
        Initialize the sync service.

        Args:
            config_service: Service to provide application configuration.
        """
        super().__init__()
        self._config_service = config_service
        self._sync_manager: Optional[SyncManager] = None
        self._update_sync_manager()

    def _update_sync_manager(self) -> None:
        """Update the sync manager with the latest configuration."""
        app_config = self._config_service.get_app_config()
        if app_config is not None:
            self._sync_manager = SyncManager(app_config)
        else:
            self._sync_manager = None

    def start_startup_sync(self) -> List[FolderSyncOutcome]:
        """
        Start the startup synchronization.

        Returns:
            List of FolderSyncOutcome for each folder.
            Returns empty list if sync is not configured or enabled.
            Returns empty list if configuration is not available.
        """
        self._update_sync_manager()
        if self._sync_manager is None:
            self.failed.emit("Configuration not available")
            self.finished.emit()
            return []
        self.started.emit("startup")
        try:
            outcomes = self._sync_manager.run_startup_sync()
            self.completed.emit(outcomes)
            self.finished.emit()
            return outcomes
        except Exception as e:
            self.failed.emit(str(e))
            self.finished.emit()
            return []

    def start_shutdown_sync(self) -> List[FolderSyncOutcome]:
        """
        Start the shutdown synchronization.

        Returns:
            List of FolderSyncOutcome for each folder.
            Returns empty list if sync is not configured or enabled.
            Returns empty list if configuration is not available.
        """
        self._update_sync_manager()
        if self._sync_manager is None:
            self.failed.emit("Configuration not available")
            self.finished.emit()
            return []
        self.started.emit("shutdown")
        try:
            outcomes = self._sync_manager.run_shutdown_sync()
            self.completed.emit(outcomes)
            self.finished.emit()
            return outcomes
        except Exception as e:
            self.failed.emit(str(e))
            self.finished.emit()
            return []

    def is_startup_sync_enabled(self) -> bool:
        """
        Check if startup sync is enabled in the configuration.

        Returns:
            True if startup sync is enabled, False otherwise.
        """
        app_config = self._config_service.get_app_config()
        if app_config is None:
            return False
        return app_config.sync.startup.enabled

    def is_shutdown_sync_enabled(self) -> bool:
        """
        Check if shutdown sync is enabled in the configuration.

        Returns:
            True if shutdown sync is enabled, False otherwise.
        """
        app_config = self._config_service.get_app_config()
        if app_config is None:
            return False
        return app_config.sync.shutdown.enabled

    def get_app_config(self) -> Optional[AppConfig]:
        """
        Get the application configuration.

        Returns:
            The AppConfig object if available, None otherwise.
        """
        return self._config_service.get_app_config()