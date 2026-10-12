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

from .utils import expand_env_vars


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

    def __post_init__(self):
        if not 1 <= self.max_parallel_jobs <= 16:
            raise ValueError("max_parallel_jobs must be between 1 and 16")


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
class CopyEngineSettings:
    """Settings that control the Python copy engine.

    These settings govern the behavior of the pure-Python copy engine
    in robocopy_manager.py. No destructive flags exist in this engine
    — safety is enforced by design (XO semantics, junction skipping,
    additive-only copies).
    """

    retry_count: int = 2
    retry_wait_seconds: int = 2
    multithreading: int = 8
    copy_subdirectories: bool = True
    copy_empty_directories: bool = True
    exclude_junctions: bool = True
    fat_file_times: bool = True
    monitor_mode: bool = False

    def __post_init__(self):
        for name, maximum, minimum in (("retry_count", 10, 0), ("retry_wait_seconds", 60, 0), ("multithreading", 32, 1)):
            if not minimum <= getattr(self, name) <= maximum:
                raise ValueError(f"{name} must be between {minimum} and {maximum}")


@dataclass(frozen=True)
class BackupSettings:
    """Per-folder pre-upload backup settings.

    When enabled, the CURRENT contents of a folder's OneDrive destination
    are compressed into a timestamped archive, stored inside OneDrive
    itself (never on local disk), immediately before every UPLOAD
    (local -> OneDrive) operation overwrites that destination. This
    protects against exactly the failure mode where a bad upload silently
    replaces good OneDrive data with something worse.

    backup_path is stored as an *original string* (with possible
    environment variables) when loaded from JSON; Path inputs from Python
    callers are also supported.
    Resolution to absolute Path happens when needed via the
    backup_path_resolved property.
    Backups are never taken before DOWNLOAD operations, since those
    don't overwrite OneDrive.
    """

    enabled: bool
    backup_path: str | Path
    retention_days: int

    @property
    def backup_path_resolved(self) -> Path:
        """Return the backup path as an absolute Path, with environment variables expanded."""
        return Path(expand_env_vars(self.backup_path)).resolve()


@dataclass(frozen=True)
class FolderSyncConfig:
    """Configuration for a single folder synchronization pair.

    JSON paths are preserved as original strings with environment variables.
    Python callers may also supply Path objects for backward compatibility.
    Resolution to absolute Paths happens when needed via the
    local_path_resolved and onedrive_path_resolved properties.
    """

    id: str
    name: str
    enabled: bool
    local_path: str | Path
    onedrive_path: str | Path
    minimum_sync_percentage: float
    verify_after_sync: bool
    create_destination: bool
    backup: Optional[BackupSettings] = None

    @property
    def local_path_resolved(self) -> Path:
        """Return the local path as an absolute Path, with environment variables expanded."""
        return Path(expand_env_vars(self.local_path)).resolve()

    @property
    def onedrive_path_resolved(self) -> Path:
        """Return the OneDrive path as an absolute Path, with environment variables expanded."""
        return Path(expand_env_vars(self.onedrive_path)).resolve()


@dataclass(frozen=True)
class AppConfig:
    """Top-level application configuration, fully resolved and validated."""

    general: GeneralSettings
    sync: SyncSettings
    copy_engine: CopyEngineSettings
    folders: List[FolderSyncConfig] = field(default_factory=list)

    def enabled_folders(self) -> List[FolderSyncConfig]:
        """Return only the folders that are enabled for synchronization."""
        return [f for f in self.folders if f.enabled]
