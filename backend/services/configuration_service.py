"""
Configuration Service

Provides a clean API for accessing application configuration.
Isolates the UI from the core configuration loading logic.
"""

from typing import Optional
from src.config_manager import ConfigManager
from src.config import AppConfig
from pathlib import Path


class ConfigurationService:
    """Service for managing application configuration."""

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize the configuration service.

        Args:
            config_path: Path to the configuration file.
                         If None, uses the default location.
        """
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

    def reload(self) -> None:
        """Reload the configuration from disk."""
        self._load_config()