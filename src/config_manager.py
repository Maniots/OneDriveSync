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
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import (
    AppConfig,
    BackupSettings,
    CopyEngineSettings,
    FolderSyncConfig,
    GeneralSettings,
    LogLevel,
    SyncDirection,
    SyncSettings,
    SyncTriggerSettings,
)
from .exceptions import ConfigurationError, PathValidationError
from .cloud_models import ConnectionConfig, RemoteJobConfig, validate_local_path
from .sync_groups import SyncGroupConfig, SyncDestinationConfig, validate_groups, validate_pending_edits
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

    @property
    def config_path(self) -> Path:
        return self._config_path

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
            copy_engine_settings = self._parse_copy_engine(raw.get("copy_engine", {}))
            folders = self._parse_folders(raw.get("folders", []))
            connections = self._parse_cloud_entries(raw.get("connections", []), ConnectionConfig)
            remote_jobs = self._parse_cloud_entries(raw.get("remote_jobs", []), RemoteJobConfig)
            groups_raw = raw.get("sync_groups", [])
            if not isinstance(groups_raw, list) or any(not isinstance(item, dict) for item in groups_raw):
                raise ValueError("sync_groups must be an array of objects")
            groups = []
            for entry in groups_raw:
                entry = dict(entry)
                destinations = entry.get("destinations")
                if not isinstance(destinations, list) or any(not isinstance(item, dict) for item in destinations):
                    raise ValueError("destinations must be an array of objects")
                entry["destinations"] = [SyncDestinationConfig(**item) for item in destinations]
                groups.append(SyncGroupConfig(**entry))
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigurationError(f"Invalid configuration structure: {exc}") from exc

        config = AppConfig(
            general=general,
            sync=sync_settings,
            copy_engine=copy_engine_settings,
            folders=folders,
            connections=connections,
            remote_jobs=remote_jobs,
            sync_groups=groups,
        )

        self._validate_folder_uniqueness(config.folders)
        self._validate_cloud_references(config)
        validate_groups(config)

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
    def _parse_cloud_entries(data, model):
        if not isinstance(data, list) or any(not isinstance(entry, dict) for entry in data):
            raise ValueError("Cloud configuration sections must be arrays of objects")
        # Explicit model constructors reject unknown fields, including secrets.
        return [model(**entry) for entry in data]

    @staticmethod
    def _validate_cloud_references(config: AppConfig) -> None:
        connections = {}
        for connection in config.connections:
            if connection.id in connections:
                raise ConfigurationError("Duplicate connection ID")
            connections[connection.id] = connection
        job_ids = {folder.id for folder in config.folders}
        for job in config.remote_jobs:
            if job.id in job_ids:
                raise ConfigurationError("Duplicate sync job ID")
            job_ids.add(job.id)
            connection = connections.get(job.connection_id)
            if connection is None:
                raise ConfigurationError("Remote job references an unknown connection")
            if connection.provider == "local":
                remote_root = validate_local_path(connection.root)
                local_root = job.local_path_resolved
                if remote_root.is_relative_to(local_root) or local_root.is_relative_to(remote_root):
                    raise ConfigurationError("A local connection and its job folder cannot overlap")

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
    def _parse_copy_engine(data: Dict[str, Any]) -> CopyEngineSettings:
        return CopyEngineSettings(
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

            local_path_resolved = Path(expand_env_vars(local_raw)).resolve()
            onedrive_path_resolved = Path(expand_env_vars(onedrive_raw)).resolve()

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
            if is_dangerous_root_path(local_path_resolved):
                raise PathValidationError(
                    f"Folder '{folder_id}': local_path '{local_path_resolved}' is a forbidden "
                    f"dangerous root folder (e.g. AppData, AppData\\Local, "
                    f"AppData\\Roaming). Only explicit subfolders are allowed."
                )
            if is_dangerous_root_path(onedrive_path_resolved):
                raise PathValidationError(
                    f"Folder '{folder_id}': onedrive_path '{onedrive_path_resolved}' is a "
                    f"forbidden dangerous root folder."
                )

            if local_path_resolved == onedrive_path_resolved:
                raise PathValidationError(
                    f"Folder '{folder_id}': local_path and onedrive_path resolve to "
                    f"the same location ('{local_path_resolved}')."
                )

            folders.append(
                FolderSyncConfig(
                    id=folder_id,
                    name=name,
                    enabled=enabled,
                    local_path=local_raw,
                    onedrive_path=onedrive_raw,
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

        backup_path_resolved = Path(expand_env_vars(str(backup_path_raw))).resolve()

        if not is_under_onedrive_root(backup_path_resolved):
            raise ConfigurationError(
                f"Folder '{folder_id}': backup_path '{backup_path_resolved}' is not inside "
                f"the OneDrive folder (%OneDrive% must be set and backup_path must "
                f"resolve underneath it). Backups are never permitted on local disk."
            )

        if is_dangerous_root_path(backup_path_resolved):
            raise PathValidationError(
                f"Folder '{folder_id}': backup_path '{backup_path_resolved}' is a forbidden "
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
            backup_path=str(backup_path_raw),
            retention_days=retention_days,
            directory_name=data.get("directory_name"),
        )

    @staticmethod
    def _validate_folder_uniqueness(folders: List[FolderSyncConfig]) -> None:
        seen_ids = set()
        for folder in folders:
            if folder.id in seen_ids:
                raise ConfigurationError(f"Duplicate folder id detected in config: '{folder.id}'")
            seen_ids.add(folder.id)

    @staticmethod
    def _app_config_to_raw_dict(app_config: AppConfig) -> Dict[str, Any]:
        """Convert an AppConfig to a raw dictionary suitable for JSON serialization.

        This is the inverse of the parsing functions in ConfigManager.
        """
        raw: Dict[str, Any] = {}

        # General settings
        raw["general"] = {
            "log_level": app_config.general.log_level.value,
            "dry_run": app_config.general.dry_run,
            "verify_after_sync": app_config.general.verify_after_sync,
            "create_destination": app_config.general.create_destination,
            "max_parallel_jobs": app_config.general.max_parallel_jobs,
        }

        # Sync settings
        raw["sync"] = {
            "startup": {
                "enabled": app_config.sync.startup.enabled,
                "direction": app_config.sync.startup.direction.value,
            },
            "shutdown": {
                "enabled": app_config.sync.shutdown.enabled,
                "direction": app_config.sync.shutdown.direction.value,
            },
        }

        # Copy engine settings
        raw["copy_engine"] = {
            "retry_count": app_config.copy_engine.retry_count,
            "retry_wait_seconds": app_config.copy_engine.retry_wait_seconds,
            "multithreading": app_config.copy_engine.multithreading,
            "copy_subdirectories": app_config.copy_engine.copy_subdirectories,
            "copy_empty_directories": app_config.copy_engine.copy_empty_directories,
            "exclude_junctions": app_config.copy_engine.exclude_junctions,
            "fat_file_times": app_config.copy_engine.fat_file_times,
            "monitor_mode": app_config.copy_engine.monitor_mode,
        }

        # Folders
        raw["folders"] = []
        for folder in app_config.folders:
            folder_raw: Dict[str, Any] = {
                "id": folder.id,
                "name": folder.name,
                "enabled": folder.enabled,
                "local_path": str(folder.local_path),
                "onedrive_path": str(folder.onedrive_path),
                "minimum_sync_percentage": folder.minimum_sync_percentage,
                "verify_after_sync": folder.verify_after_sync,
                "create_destination": folder.create_destination,
            }
            if folder.backup is not None:
                folder_raw["backup"] = {
                    "enabled": folder.backup.enabled,
                    "backup_path": str(folder.backup.backup_path),
                    "retention_days": folder.backup.retention_days,
                }
                if folder.backup.directory_name is not None:
                    folder_raw["backup"]["directory_name"] = folder.backup.directory_name
            else:
                folder_raw["backup"] = None
            raw["folders"].append(folder_raw)

        # Omit empty additions so saving old configurations retains their shape.
        if app_config.connections:
            raw["connections"] = [asdict(connection) for connection in app_config.connections]
        if app_config.remote_jobs:
            raw["remote_jobs"] = [asdict(job) for job in app_config.remote_jobs]
        if app_config.sync_groups:
            raw["sync_groups"] = [asdict(group) for group in app_config.sync_groups]

        return raw

    def save(self, app_config: AppConfig) -> None:
        """Validate and atomically save the given AppConfig as JSON.

        This method converts the AppConfig to a raw dictionary (with original
        strings, including environment variable references) and writes it to
        the config file.

        Args:
            app_config: The configuration to save.

        Raises:
            ConfigurationError: If the file cannot be written.
        """
        raw_dict = self._app_config_to_raw_dict(app_config)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self._config_path.parent,
                                             prefix=f".{self._config_path.name}.", suffix=".tmp", delete=False) as f:
                temporary_path = Path(f.name)
                json.dump(raw_dict, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            # Validate with the same rules as loading before touching the original.
            candidate = ConfigManager(temporary_path).load()
            try:
                self._config_path.stat()
            except FileNotFoundError:
                previous = None
            else:
                previous = self.load()
            validate_pending_edits(previous, candidate, self._config_path.with_suffix(".cloud"))
            os.replace(temporary_path, self._config_path)
        except (OSError, TypeError, ValueError) as exc:
            raise ConfigurationError(
                f"Failed to write configuration file '{self._config_path}': {exc}"
            ) from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def get_shutdown_monitor_status(self) -> dict:
        """Return the shutdown monitor status as a dictionary.
        If the status file cannot be read, returns a default status with
        status: "unknown".
        """
        from src.runtime_paths import data_root
        status_file = data_root() / "shutdown_monitor_status.json"
        try:
            if status_file.exists():
                with status_file.open("r", encoding="utf-8") as f:
                    return json.load(f)
            else:
                return {
                    "status": "unknown",
                    "pid": None,
                    "startup_time": None,
                    "last_detected_event": None,
                    "last_shutdown_sync": None,
                    "last_error": None,
                }
        except (json.JSONDecodeError, OSError):
            return {
                "status": "unknown",
                "pid": None,
                "startup_time": None,
                "last_detected_event": None,
                "last_shutdown_sync": None,
                "last_error": None,
            }
