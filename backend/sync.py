"""
Sync backend wrapper.
Provides access to synchronization operations.
"""

from src.sync_manager import SyncManager, FolderSyncOutcome
from src.config import AppConfig
from typing import List


class SyncBackend:
    """Wrapper for synchronization operations."""

    def __init__(self, config: AppConfig):
        """
        Initialize the sync backend.

        Args:
            config: The application configuration.
        """
        self.sync_manager = SyncManager(config)

    def run_startup_sync(self) -> List[FolderSyncOutcome]:
        """
        Run startup synchronization.

        Returns:
            List of folder sync outcomes.
        """
        return self.sync_manager.run_startup_sync()

    def run_shutdown_sync(self) -> List[FolderSyncOutcome]:
        """
        Run shutdown synchronization.

        Returns:
            List of folder sync outcomes.
        """
        return self.sync_manager.run_shutdown_sync()

    def is_sync_running(self) -> bool:
        """
        Check if a sync is currently running.

        Note: This is a simplified check. In reality, the sync manager doesn't expose
        a direct way to check if sync is running without additional mechanisms.
        For now, we return False as a placeholder.

        Returns:
            False (placeholder).
        """
        # TODO: Implement proper sync running check if needed for UI.
        return False