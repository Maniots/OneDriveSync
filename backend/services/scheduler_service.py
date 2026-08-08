"""
Scheduler Service

Provides a clean API for accessing scheduler-related information.
Isolates the UI from the core scheduling logic (which is handled by Windows Scheduled Tasks).
"""

from typing import Optional
from .configuration_service import ConfigurationService
from src.config import AppConfig, SyncTriggerSettings, SyncDirection


class SchedulerService:
    """Service for managing scheduler information."""

    def __init__(self, config_service: ConfigurationService):
        """
        Initialize the scheduler service.

        Args:
            config_service: Service to provide application configuration.
        """
        self._config_service = config_service

    def get_startup_sync_info(self) -> Optional[Dict[str, str]]:
        """
        Get information about the startup sync trigger.

        Returns:
            Dictionary with keys: trigger, delay, direction, enabled.
            Returns None if configuration is not available.
        """
        app_config = self._config_service.get_app_config()
        if app_config is None:
            return None

        trigger: SyncTriggerSettings = app_config.sync.startup
        return {
            "trigger": "Logon",  # Hardcoded as per the application design
            "delay": f"{trigger.enabled and 2 or 0} minutes",  # The delay is hardcoded to 2 minutes if enabled? Actually, the delay is fixed at 2 minutes in the UI and in the shutdown monitor.
            # Note: The delay is not in the configuration. The shutdown monitor waits 2 minutes at logon before triggering the startup download.
            # We'll hardcode the delay as 2 minutes if enabled, else 0.
            "direction": trigger.direction.value.capitalize(),
            "enabled": "Enabled" if trigger.enabled else "Disabled"
        }

    def get_periodic_sync_info(self) -> Optional[Dict[str, str]]:
        """
        Get information about the periodic sync trigger.

        Returns:
            Dictionary with keys: interval, direction, enabled.
            Returns None if configuration is not available.
        """
        app_config = self._config_service.get_app_config()
        if app_config is None:
            return None

        # Note: The periodic sync is not explicitly in the configuration.
        # The application has a fixed periodic interval of 15 minutes for upload.
        # We'll hardcode the interval and direction.
        return {
            "interval": "15 minutes",
            "direction": "Upload",  # Fixed as per the application design
            "enabled": "Enabled"  # We don't have a way to know if the periodic task is enabled from the config.
                                  # The periodic task is created by the Setup-ScheduledTasks.ps1 script.
                                  # We'll assume it's enabled if the application is set up.
                                  # We'll return "Enabled" as a placeholder.
        }

    def get_workstation_lock_info(self) -> Optional[Dict[str, str]]:
        """
        Get information about the workstation lock (shutdown on lock) trigger.

        Returns:
            Dictionary with keys: trigger, direction, enabled.
            Returns None if configuration is not available.
        """
        app_config = self._config_service.get_app_config()
        if app_config is None:
            return None

        trigger: SyncTriggerSettings = app_config.sync.shutdown
        return {
            "trigger": "Workstation Lock",
            "direction": trigger.direction.value.capitalize(),
            "enabled": "Enabled" if trigger.enabled else "Disabled"
        }

    def get_scheduler_summary(self) -> Optional[Dict[str, Optional[Dict[str, str]]]]:
        """
        Get a summary of all scheduler information.

        Returns:
            Dictionary with keys: 'startup', 'periodic', 'workstation_lock'.
            Each value is a dictionary as returned by the respective get_*_info method.
            Returns None if configuration is not available.
        """
        app_config = self._config_service.get_app_config()
        if app_config is None:
            return None

        return {
            "startup": self.get_startup_sync_info(),
            "periodic": self.get_periodic_sync_info(),
            "workstation_lock": self.get_workstation_lock_info()
        }