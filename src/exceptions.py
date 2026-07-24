"""
exceptions.py

Custom exception hierarchy for OneDrive PC Sync.

Using dedicated exception types (instead of generic Exception/ValueError)
allows sync_manager.py to catch specific failure categories and decide
whether processing can safely continue with independent folders, as
required by the "never silently continue after errors" safety rule.
"""

from __future__ import annotations


class OneDrivePCSyncError(Exception):
    """Base class for all application-specific exceptions."""


class ConfigurationError(OneDrivePCSyncError):
    """Raised when the configuration file is missing, malformed, or invalid."""


class PathValidationError(OneDrivePCSyncError):
    """Raised when a source or destination path fails safety validation.

    Examples: path does not exist and cannot be created, source and
    destination resolve to the same location, or the path is a
    dangerous root folder (e.g. bare AppData, AppData\\Local, AppData\\Roaming).
    """


class SyncThresholdExceededError(OneDrivePCSyncError):
    """Raised when the file-count safety ratio falls below the configured
    minimum_sync_percentage for a folder, aborting that folder's sync."""


class RobocopyExecutionError(OneDrivePCSyncError):
    """Raised when robocopy exits with a code indicating failure.

    Note: robocopy's exit code semantics are bitmask-based and codes
    0-7 are all "success" in some form. Only codes >= 8 indicate a
    real failure. See robocopy_manager.py for the interpretation logic.
    """


class VerificationError(OneDrivePCSyncError):
    """Raised when post-sync verification detects an inconsistency."""


class BackupError(OneDrivePCSyncError):
    """Raised when a required pre-upload backup could not be created.

    By design this ABORTS the upload for that folder rather than proceeding
    without a backup - if backup.enabled is true for a folder, the whole
    point is that an upload should never happen without one. A failure to
    prune old backups (retention cleanup) is treated as non-fatal instead
    and does not raise this exception.
    """