"""
Scheduler backend wrapper.
Note: Scheduling is handled externally via Windows Scheduled Tasks.
This wrapper is a placeholder for UI integration.
"""

class SchedulerBackend:
    """Wrapper for scheduler (external)."""

    def __init__(self):
        """Initialize the scheduler backend."""
        # No internal state needed as scheduling is external.
        pass

    def get_scheduled_tasks(self):
        """
        Get information about scheduled tasks.

        Note: This is a placeholder. In a real implementation, this might
        query the Windows Task Scheduler, but we are not to change behavior.
        For now, returns empty list.

        Returns:
            Empty list (placeholder).
        """
        # TODO: Implement if needed for UI, but note that we are not to change
        # the synchronization behavior. Querying task status is likely safe.
        return []

    def is_startup_task_enabled(self) -> bool:
        """
        Check if the startup task is enabled.

        Returns:
            Placeholder: True.
        """
        return True

    def is_shutdown_task_enabled(self) -> bool:
        """
        Check if the shutdown task is enabled.

        Returns:
            Placeholder: True.
        """
        return True

    def is_periodic_task_enabled(self) -> bool:
        """
        Check if the periodic task is enabled.

        Returns:
            Placeholder: True.
        """
        return True