"""
Notifications backend wrapper.
Provides access to notification operations.
"""

from src.notifications import show_windows_toast


class NotificationsBackend:
    """Wrapper for notifications."""

    def show_toast(self, title: str, message: str) -> None:
        """
        Show a Windows toast notification.

        Args:
            title: The title of the toast.
            message: The message of the toast.
        """
        show_windows_toast(title, message)

    def show_sync_success(self) -> None:
        """Show a success toast for sync completion."""
        self.show_toast("OneDrive PC Sync", "Sync completed successfully.")

    def show_sync_failed(self, failed_count: int) -> None:
        """
        Show a failure toast for sync.

        Args:
            failed_count: Number of folders that failed to sync.
        """
        self.show_toast(
            "OneDrive PC Sync — Issues",
            f"{failed_count} folder(s) failed to sync. Check logs.",
        )