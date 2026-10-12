"""
Configuration Service

Provides a clean API for accessing application configuration.
Isolates the UI from the core configuration loading logic.
"""

from typing import Optional
from src.config_manager import ConfigManager
from src.config import AppConfig
from pathlib import Path
from PySide6.QtCore import QObject, Signal


class ConfigurationService(QObject):
    """Service for managing application configuration."""

    changed = Signal(object)

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize the configuration service.

        Args:
            config_path: Path to the configuration file.
                         If None, uses the default location.
        """
        super().__init__()
        if config_path is None:
            # Default to config.json in the project root
            # We assume the project root is two levels up from this file:
            #   backend/services/configuration_service.py -> backend -> project root
            config_path = Path(__file__).resolve().parent.parent.parent / "config.json"
        self._config_manager = ConfigManager(config_path)
        self._app_config: Optional[AppConfig] = None
        self._load_config()

    def _load_config(self) -> None:
        """Load the configuration from disk."""
        try:
            self._app_config = self._config_manager.load()
        except Exception:
            # In case of error, we keep _app_config as None
            self._app_config = None

    def get_app_config(self) -> Optional[AppConfig]:
        """
        Get the application configuration.

        Returns:
            The AppConfig object if configuration is loaded successfully,
            None otherwise.
        """
        return self._app_config

    def save(self, app_config: AppConfig) -> None:
        """Save the given AppConfig to the configuration file.

        This method delegates to the ConfigManager to perform the actual
        write, then updates the cached configuration.

        Args:
            app_config: The configuration to save.

        Raises:
            ConfigurationError: If the configuration cannot be saved.
        """
        self._config_manager.save(app_config)
        # Update the cached configuration to the saved one.
        self._app_config = app_config
        self.changed.emit(app_config)

    def reload(self) -> None:
        """Reload the configuration from disk."""
        self._load_config()
        self.changed.emit(self._app_config)

    def get_shutdown_monitor_status(self) -> dict:
        """Read the monitor status through the core configuration manager."""
        return self._config_manager.get_shutdown_monitor_status()
