"""
Configuration backend wrapper.
Provides access to the application configuration.
"""

from src.config_manager import ConfigManager
from src.config import AppConfig


class ConfigurationBackend:
    """Wrapper for configuration management."""

    def __init__(self, config_path: str):
        """
        Initialize the configuration backend.

        Args:
            config_path: Path to the configuration file.
        """
        from pathlib import Path
        self.config_path = Path(config_path)
        self._config_manager = ConfigManager(self.config_path)
        self._config: AppConfig = self._config_manager.load()

    @property
    def config(self) -> AppConfig:
        """Get the current configuration."""
        return self._config

    def reload(self) -> None:
        """Reload the configuration from file."""
        self._config = self._config_manager.load()

    def get_general_settings(self):
        """Get general settings."""
        return self._config.general

    def get_sync_settings(self):
        """Get sync settings."""
        return self._config.sync

    def get_copy_engine_settings(self):
        """Get copy engine settings."""
        return self._config.copy_engine

    def get_folders(self):
        """Get folder configurations."""
        return self._config.folders