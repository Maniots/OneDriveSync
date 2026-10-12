"""
Monitor Service

Provides a clean API for accessing shutdown monitor status.
Isolates the UI from the core shutdown monitor logic.
"""

from typing import Dict, Optional
from .configuration_service import ConfigurationService


class MonitorService:
    """Service for managing shutdown monitor status."""

    def __init__(self, config_service: ConfigurationService):
        """
        Initialize the monitor service.

        Args:
            config_service: Service to provide application configuration.
        """
        self._config_service = config_service

    def get_status(self) -> Dict[str, Optional[str]]:
        """
        Get the shutdown monitor status.

        Returns:
            Dictionary containing:
                - status: 'running', 'stopped', 'error', or 'unknown'
                - pid: process ID as string, or None
                - startup_time: ISO format timestamp string, or None
                - last_detected_event: ISO format timestamp string, or None
                - last_shutdown_sync: ISO format timestamp string, or None
                - last_error: error message string, or None
            Returns a default dictionary with all values as None and status 'unknown'
            if the configuration service is not available or an error occurs.
        """
        try:
            return self._config_service.get_shutdown_monitor_status()
        except Exception:
            return {
                "status": "unknown",
                "pid": None,
                "startup_time": None,
                "last_detected_event": None,
                "last_shutdown_sync": None,
                "last_error": None
            }