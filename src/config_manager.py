"""
config_manager.py

Loads config.json from disk, expands environment variables in every
folder path, validates the resulting configuration, and produces a
fully-typed AppConfig object (see config.py).

This is the ONLY module that touches raw JSON. Everything downstream
(sync_manager.py, robocopy_manager.py) works exclusively with the
typed dataclasses defined in config.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import (
    AppConfig,
    BackupSettings,
    FolderSyncConfig,
    GeneralSettings,
    LogLevel,
    RobocopySettings,
    SyncDirection,
    SyncSettings,
    SyncTriggerSettings,
)
from .exceptions import ConfigurationError, PathValidationError
from .logger import get_logger
from .utils import expand_env_vars, is_dangerous_root_path, is_under_onedrive_root

logger = get_logger(__name__)


class ConfigManager:
    """Loads and validates OneDrive PC Sync configuration files."""

    def __init__(self, config_path: Path) -> None:
        """
        Args:
            config_path: Path to config.json.
        """
        self._config_path = config_path

    def load(self) -> AppConfig:
        """Load, expand, validate, and return the application configuration.

        Raises:
            ConfigurationError: If the file is missing, malformed, or
                fails structural/semantic validation.
        """
        raw = self._read_json()

        try:
            general = self._parse_general(raw.get("general", {}))
            sync_settings = self._parse_sync(raw.get("sync", {}))
            robocopy_settings = self._parse_robocopy(raw.get("robocopy", {}))
            folders = self._parse_folders(raw.get("folders", []))
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigurationError(f"Invalid configuration structure: {exc}") from exc

        config = AppConfig(
            general=general,
            sync=sync_settings,
            robocopy=robocopy_settings,
            folders=folders,
        )

        self._validate_folder_uniqueness(config.folders)

        logger.info(
            "Configuration loaded successfully: %d folder(s) defined, %d enabled.",
            len(config.folders),
            len(config.enabled_folders()),
        )
        return config

    def _read_json(self) -> Dict[str, Any]:
        if not self._config_path.exists():
            raise ConfigurationError(f"Configuration file not found: {self._config_path}")

        try:
            with self._config_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as exc:
            raise ConfigurationError(
                f"Configuration file is not valid JSON: {self._config_path} ({exc})"
            ) from exc

    @staticmethod
    def _parse_general(data: Dict[str, Any]) -> GeneralSettings:
        return GeneralSettings(
            log_level=LogLevel(data.get("log_level", "INFO")),
            dry_run=bool(data.get("dry_run", False)),
            verify_after_sync=bool(data.get("verify_after_sync", True)),
            create_destination=bool(data.get("create_destination", True)),
            max_parallel_jobs=int(data.get("max_parallel_jobs", 1)),
        )

    @staticmethod
    def _parse_sync(data: Dict[str, Any]) -> SyncSettings:
        startup_raw = data.get("startup", {})
        shutdown_raw = data.get("shutdown", {})

        startup = SyncTriggerSettings(
            enabled=bool(startup_raw.get("enabled", True)),
            direction=SyncDirection(startup_raw.get("direction", "download")),
        )
        shutdown = SyncTriggerSettings(
            enabled=bool(shutdown_raw.get("enabled", True)),
            direction=SyncDirection(shutdown_raw.get("direction", "upload")),
        )
        return SyncSettings(startup=startup, shutdown=shutdown)

    @staticmethod
    def _parse_robocopy(data: Dict[str, Any]) -> RobocopySettings:
        return RobocopySettings(
            retry_count=int(data.get("retry_count", 2)),
            retry_wait_seconds=int(data.get("retry_wait_seconds", 2)),
            multithreading=int(data.get("multithreading", 8)),
            copy_subdirectories=bool(data.get("copy_subdirectories", True)),
            copy_empty_directories=bool(data.get("copy_empty_directories", True)),
            exclude_junctions=bool(data.get("exclude_junctions", True)),
            fat_file_times=bool(data.get("fat_file_times", True)),
            monitor_mode=bool(data.get("monitor_mode", False)),
        )

    def _parse_folders(self, data: List[Dict[str, Any]]) -> List[FolderSyncConfig]:
        folders: List[FolderSyncConfig] = []

        for entry in data:
            folder_id = str(entry["id"])
            name = str(entry.get("name", folder_id))
            enabled = bool(entry.get("enabled", True))

            local_raw = str(entry["local_path"])
            onedrive_raw = str(entry["onedrive_path"])

            local_path = Path(expand_env_vars(local_raw)).resolve()
            onedrive_path = Path(expand_env_vars(onedrive_raw)).resolve()

            minimum_sync_percentage = float(entry.get("minimum_sync_percentage", 80))
            if not 0 <= minimum_sync_percentage <= 100:
                raise ConfigurationError(
                    f"Folder '{folder_id}': minimum_sync_percentage must be between "
                    f"0 and 100, got {minimum_sync_percentage}."
                )

            verify_after_sync = bool(entry.get("verify_after_sync", True))
            create_destination = bool(entry.get("create_destination", True))

            backup = self._parse_backup(folder_id, entry.get("backup"))

            # Reject dangerous roots at load time, before any sync ever runs.
            if is_dangerous_root_path(local_path):
                raise PathValidationError(
                    f"Folder '{folder_id}': local_path '{local_path}' is a forbidden "
                    f"dangerous root folder (e.g. AppData, AppData\\Local, "
                    f"AppData\\Roaming). Only explicit subfolders are allowed."
                )
            if is_dangerous_root_path(onedrive_path):
                raise PathValidationError(
                    f"Folder '{folder_id}': onedrive_path '{onedrive_path}' is a "
                    f"forbidden dangerous root folder."
                )

            if local_path == onedrive_path:
                raise PathValidationError(
                    f"Folder '{folder_id}': local_path and onedrive_path resolve to "
                    f"the same location ('{local_path}')."
                )

            folders.append(
                FolderSyncConfig(
                    id=folder_id,
                    name=name,
                    enabled=enabled,
                    local_path=local_path,
                    onedrive_path=onedrive_path,
                    minimum_sync_percentage=minimum_sync_percentage,
                    verify_after_sync=verify_after_sync,
                    create_destination=create_destination,
                    backup=backup,
                )
            )

        return folders

    @staticmethod
    def _parse_backup(folder_id: str, data: Any) -> Optional[BackupSettings]:
        """Parse and validate a folder's optional "backup" section.

        Returns None if the section is absent or explicitly disabled -
        backup is strictly opt-in. When enabled, backup_path MUST resolve
        to a location inside the user's OneDrive folder (never local
        disk) - this is enforced here, at config-load time, before any
        sync ever runs, matching this application's existing pattern of
        rejecting unsafe configuration as early as possible.
        """
        if not data:
            return None

        enabled = bool(data.get("enabled", False))
        if not enabled:
            return None

        backup_path_raw = data.get("backup_path")
        if not backup_path_raw:
            raise ConfigurationError(
                f"Folder '{folder_id}': backup.enabled is true but backup_path is missing."
            )

        backup_path = Path(expand_env_vars(str(backup_path_raw))).resolve()

        if not is_under_onedrive_root(backup_path):
            raise ConfigurationError(
                f"Folder '{folder_id}': backup_path '{backup_path}' is not inside "
                f"the OneDrive folder (%OneDrive% must be set and backup_path must "
                f"resolve underneath it). Backups are never permitted on local disk."
            )

        if is_dangerous_root_path(backup_path):
            raise PathValidationError(
                f"Folder '{folder_id}': backup_path '{backup_path}' is a forbidden "
                f"dangerous root folder."
            )

        retention_days = int(data.get("retention_days", 7))
        if retention_days < 1:
            raise ConfigurationError(
                f"Folder '{folder_id}': backup.retention_days must be at least 1, "
                f"got {retention_days}."
            )

        return BackupSettings(
            enabled=True,
            backup_path=backup_path,
            retention_days=retention_days,
        )

    @staticmethod
    def _validate_folder_uniqueness(folders: List[FolderSyncConfig]) -> None:
        seen_ids = set()
        for folder in folders:
            if folder.id in seen_ids:
                raise ConfigurationError(f"Duplicate folder id detected in config: '{folder.id}'")
            seen_ids.add(folder.id)