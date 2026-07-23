"""
config.py

Configuration data models for OneDrive PC Sync.

This module defines the strongly-typed, immutable-by-convention data
structures that represent the application's configuration. No I/O,
environment variable expansion, or validation logic lives here -
that responsibility belongs to config_manager.py. This module only
describes the *shape* of a valid configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional


class SyncDirection(str, Enum):
    """Direction of a synchronization operation."""

    DOWNLOAD = "download"  # OneDrive -> Local PC
    UPLOAD = "upload"      # Local PC -> OneDrive


class LogLevel(str, Enum):
    """Supported logging verbosity levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class GeneralSettings:
    """Global application behavior settings."""

    log_level: LogLevel = LogLevel.INFO
    dry_run: bool = False
    verify_after_sync: bool = True
    create_destination: bool = True
    max_parallel_jobs: int = 1


@dataclass(frozen=True)
class SyncTriggerSettings:
    """Settings for a single sync trigger (startup or shutdown)."""

    enabled: bool
    direction: SyncDirection


@dataclass(frozen=True)
class SyncSettings:
    """Container for all sync trigger settings."""

    startup: SyncTriggerSettings
    shutdown: SyncTriggerSettings


@dataclass(frozen=True)
class RobocopySettings:
    """Settings that control how robocopy is invoked.

    These settings NEVER include destructive flags such as /MIR, /PURGE,
    or /MOVE. robocopy_manager.py enforces this at the command-building
    stage regardless of what is configured here.
    """

    retry_count: int = 2
    retry_wait_seconds: int = 2
    multithreading: int = 8
    copy_subdirectories: bool = True
    copy_empty_directories: bool = True
    exclude_junctions: bool = True
    fat_file_times: bool = True
    monitor_mode: bool = False


@dataclass(frozen=True)
class BackupSettings:
    """Per-folder pre-upload backup settings.

    When enabled, the CURRENT contents of a folder's OneDrive destination
    are compressed into a timestamped archive, stored inside OneDrive
    itself (never on local disk), immediately before every UPLOAD
    (local -> OneDrive) operation overwrites that destination. This
    protects against exactly the failure mode where a bad upload silently
    replaces good OneDrive data with something worse.

    backup_path is stored as an *expanded, resolved* Path by the time this
    object is constructed (expansion and OneDrive-location validation
    happen in config_manager.py). Backups are never taken before DOWNLOAD
    operations, since those don't overwrite OneDrive.
    """

    enabled: bool
    backup_path: Path
    retention_days: int


@dataclass(frozen=True)
class FolderSyncConfig:
    """Configuration for a single folder synchronization pair.

    local_path and onedrive_path are stored as *expanded, resolved*
    Path objects by the time this object is constructed (expansion
    happens in config_manager.py).
    """

    id: str
    name: str
    enabled: bool
    local_path: Path
    onedrive_path: Path
    minimum_sync_percentage: float
    verify_after_sync: bool
    create_destination: bool
    backup: Optional[BackupSettings] = None


@dataclass(frozen=True)
class AppConfig:
    """Top-level application configuration, fully resolved and validated."""

    general: GeneralSettings
    sync: SyncSettings
    robocopy: RobocopySettings
    folders: List[FolderSyncConfig] = field(default_factory=list)

    def enabled_folders(self) -> List[FolderSyncConfig]:
        """Return only the folders that are enabled for synchronization."""
        return [f for f in self.folders if f.enabled]