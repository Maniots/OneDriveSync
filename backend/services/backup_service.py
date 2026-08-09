"""
Backup Service

Provides a clean API for accessing backup information.
Isolates the UI from the core backup logic.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from .configuration_service import ConfigurationService
from src.config import BackupSettings


class BackupService:
    """Service for managing backup information."""

    def __init__(self, config_service: ConfigurationService):
        """
        Initialize the backup service.

        Args:
            config_service: Service to provide application configuration.
        """
        self._config_service = config_service

    def get_backup_info(self, folder_id: str) -> List[Dict[str, Optional[str]]]:
        """
        Get information about existing backups for a folder.

        Args:
            folder_id: The ID of the folder to get backup information for.

        Returns:
            A list of dictionaries, each containing:
                - timestamp: string in YYYY-MM-DD format (from the filename)
                - size: string representing the size (e.g., "1.2 MB")
                - path: full path to the backup file
            Returns an empty list if no backups are found or configuration is not available.
        """
        app_config = self._config_service.get_app_config()
        if app_config is None:
            return []

        # Find the folder configuration to get backup settings
        folder_config = None
        for folder in app_config.folders:
            if folder.id == folder_id:
                folder_config = folder
                break

        if folder_config is None or folder_config.backup is None:
            return []

        backup_settings: BackupSettings = folder_config.backup
        backup_dir = backup_settings.backup_path_resolved / folder_id

        if not backup_dir.exists() or not backup_dir.is_dir():
            return []

        # Pattern for backup files: <folder_id>_YYYY-MM-DD.zip
        pattern = re.compile(rf"^{re.escape(folder_id)}_(\d{{4}}-\d{{2}}-\d{{2}})\.zip$")
        backups: List[Dict[str, Optional[str]]] = []

        for backup_file in backup_dir.glob(f"{folder_id}_*.zip"):
            match = pattern.match(backup_file.name)
            if not match:
                continue

            timestamp_str = match.group(1)  # YYYY-MM-DD
            try:
                # Validate the date
                datetime.strptime(timestamp_str, "%Y-%m-%d")
            except ValueError:
                continue

            try:
                size = backup_file.stat().st_size
                # Format size in a human-readable way (we'll keep it as bytes for now, but we can format if needed)
                # For simplicity, we'll return the size in bytes and let the UI format it.
                # Alternatively, we can return a formatted string.
                # We'll return the size in bytes and the UI can format it.
                size_bytes = size
            except OSError:
                # If we can't get the size, skip this backup
                continue

            backups.append({
                "timestamp": timestamp_str,
                "size": str(size_bytes),  # We'll store as string for simplicity, but note it's bytes
                "path": str(backup_file)
            })

        # Sort by timestamp, newest first
        backups.sort(key=lambda x: x["timestamp"], reverse=True)
        return backups

    def get_backup_info_formatted(self, folder_id: str) -> List[Dict[str, str]]:
        """
        Get backup information with formatted size (e.g., "1.2 MB").

        Returns:
            List of dictionaries with keys: timestamp, size (formatted), path.
        """
        backups = self.get_backup_info(folder_id)
        formatted_backups: List[Dict[str, str]] = []
        for backup in backups:
            try:
                size_bytes = int(backup["size"])
                # Format the size
                if size_bytes < 1024:
                    size_str = f"{size_bytes} B"
                elif size_bytes < 1024 * 1024:
                    size_str = f"{size_bytes / 1024:.1f} KB"
                elif size_bytes < 1024 * 1024 * 1024:
                    size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
                else:
                    size_str = f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
            except (ValueError, TypeError):
                size_str = "Unknown"
            formatted_backups.append({
                "timestamp": backup["timestamp"],
                "size": size_str,
                "path": backup["path"]
            })
        return formatted_backups