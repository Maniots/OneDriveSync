"""
sync_manager.py

Orchestrates the full synchronization workflow: path validation, file-count
safety-ratio checks, robocopy execution, and optional post-sync
verification - for every configured folder, in both startup (download)
and shutdown (upload) modes.

This module owns ALL safety decisions. robocopy_manager.py is treated as
a dumb copy engine that this module chooses whether or not to invoke.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .backup_manager import BackupManager
from .config import AppConfig, FolderSyncConfig, SyncDirection
from .exceptions import (
    BackupError,
    OneDrivePCSyncError,
    PathValidationError,
    RobocopyExecutionError,
    SyncThresholdExceededError,
    VerificationError,
)
from .logger import get_logger
from .robocopy_manager import RobocopyManager
from .utils import calculate_sync_percentage, count_files_recursive, is_dangerous_root_path

logger = get_logger(__name__)


@dataclass(frozen=True)
class FolderSyncOutcome:
    """Result of attempting to synchronize a single folder."""

    folder_id: str
    folder_name: str
    direction: SyncDirection
    succeeded: bool
    message: str


class SyncManager:
    """Coordinates safe synchronization of all configured folders."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._robocopy = RobocopyManager(
            settings=config.robocopy,
            dry_run=config.general.dry_run,
        )
        self._backup = BackupManager(dry_run=config.general.dry_run)

    def run_startup_sync(self) -> List[FolderSyncOutcome]:
        """Run the configured startup synchronization (typically download)."""
        trigger = self._config.sync.startup
        if not trigger.enabled:
            logger.info("Startup sync is disabled in configuration. Skipping.")
            return []
        logger.info("=== Starting STARTUP sync (direction=%s) ===", trigger.direction.value)
        return self._run_all_folders(trigger.direction)

    def run_shutdown_sync(self) -> List[FolderSyncOutcome]:
        """Run the configured shutdown synchronization (typically upload)."""
        trigger = self._config.sync.shutdown
        if not trigger.enabled:
            logger.info("Shutdown sync is disabled in configuration. Skipping.")
            return []
        logger.info("=== Starting SHUTDOWN sync (direction=%s) ===", trigger.direction.value)
        return self._run_all_folders(trigger.direction)

    def _run_all_folders(self, direction: SyncDirection) -> List[FolderSyncOutcome]:
        outcomes: List[FolderSyncOutcome] = []

        for folder in self._config.enabled_folders():
            # Each folder is fully independent: an error in one must never
            # prevent the others from being processed.
            try:
                outcome = self._sync_single_folder(folder, direction)
                outcomes.append(outcome)
            except OneDrivePCSyncError as exc:
                logger.error(
                    "Sync aborted for folder '%s' (%s): %s",
                    folder.id,
                    folder.name,
                    exc,
                )
                outcomes.append(
                    FolderSyncOutcome(
                        folder_id=folder.id,
                        folder_name=folder.name,
                        direction=direction,
                        succeeded=False,
                        message=str(exc),
                    )
                )
            except Exception as exc:  # noqa: BLE001 - last line of defense
                logger.exception(
                    "Unexpected error while syncing folder '%s' (%s).",
                    folder.id,
                    folder.name,
                )
                outcomes.append(
                    FolderSyncOutcome(
                        folder_id=folder.id,
                        folder_name=folder.name,
                        direction=direction,
                        succeeded=False,
                        message=f"Unexpected error: {exc}",
                    )
                )

        self._log_summary(outcomes)
        return outcomes

    def _sync_single_folder(
        self, folder: FolderSyncConfig, direction: SyncDirection
    ) -> FolderSyncOutcome:
        source, destination = self._resolve_source_and_destination(folder, direction)

        logger.info(
            "Processing folder '%s' (%s): %s -> %s",
            folder.id,
            folder.name,
            source,
            destination,
        )

        self._validate_paths(folder, source, destination)
        self._enforce_safety_threshold(folder, source, destination)

        if direction == SyncDirection.UPLOAD and folder.backup is not None and folder.backup.enabled:
            self._backup.create_backup(folder.id, folder.backup, destination)
            self._backup.prune_old_backups(folder.id, folder.backup)

        result = self._robocopy.run(source, destination)

        if (
            folder.verify_after_sync
            and self._config.general.verify_after_sync
            and not self._config.general.dry_run
        ):
            self._verify_after_sync(folder, source, destination)
        elif folder.verify_after_sync and self._config.general.verify_after_sync:
            logger.info(
                "Folder '%s': skipping verification because this is a dry run "
                "(no files were actually copied).",
                folder.id,
            )

        message = (
            f"Sync completed successfully (dry_run={result.dry_run}, "
            f"exit_code={result.exit_code})."
        )
        logger.info("Folder '%s': %s", folder.id, message)

        return FolderSyncOutcome(
            folder_id=folder.id,
            folder_name=folder.name,
            direction=direction,
            succeeded=True,
            message=message,
        )

    @staticmethod
    def _resolve_source_and_destination(
        folder: FolderSyncConfig, direction: SyncDirection
    ) -> tuple[Path, Path]:
        """Determine source/destination based on sync direction.

        DOWNLOAD: OneDrive -> Local
        UPLOAD:   Local -> OneDrive
        """
        if direction == SyncDirection.DOWNLOAD:
            return folder.onedrive_path, folder.local_path
        return folder.local_path, folder.onedrive_path

    def _validate_paths(
        self, folder: FolderSyncConfig, source: Path, destination: Path
    ) -> None:
        """Rule 1: Validate paths before any copy is attempted.

        Checks:
            - source exists
            - destination exists or can be created
            - source and destination are not identical
            - neither path is a dangerous root folder
        """
        if is_dangerous_root_path(source) or is_dangerous_root_path(destination):
            raise PathValidationError(
                f"Folder '{folder.id}': refusing to sync a dangerous root path "
                f"(source='{source}', destination='{destination}')."
            )

        if source.resolve() == destination.resolve():
            raise PathValidationError(
                f"Folder '{folder.id}': source and destination are identical "
                f"('{source}')."
            )

        if not source.exists():
            raise PathValidationError(
                f"Folder '{folder.id}': source path does not exist: '{source}'. "
                f"Nothing to synchronize."
            )
        if not source.is_dir():
            raise PathValidationError(
                f"Folder '{folder.id}': source path is not a directory: '{source}'."
            )

        if not destination.exists():
            create_allowed = folder.create_destination and self._config.general.create_destination
            if not create_allowed:
                raise PathValidationError(
                    f"Folder '{folder.id}': destination path does not exist and "
                    f"create_destination is disabled: '{destination}'."
                )
            if not self._config.general.dry_run:
                logger.info("Creating missing destination directory: %s", destination)
                destination.mkdir(parents=True, exist_ok=True)
            else:
                logger.info(
                    "[DRY RUN] Would create missing destination directory: %s", destination
                )
        elif not destination.is_dir():
            raise PathValidationError(
                f"Folder '{folder.id}': destination path exists but is not a "
                f"directory: '{destination}'."
            )

    def _enforce_safety_threshold(
        self, folder: FolderSyncConfig, source: Path, destination: Path
    ) -> None:
        """Rules 2 & 3: File-count protection and percentage threshold.

        If the destination does not exist yet (freshly created, empty),
        this is treated as a first-time sync and is always allowed,
        since an empty destination cannot represent data loss.
        """
        source_count = count_files_recursive(source)
        destination_count = count_files_recursive(destination)

        logger.info(
            "Folder '%s': source file count=%d, destination file count=%d.",
            folder.id,
            source_count,
            destination_count,
        )

        if source_count == 0:
            logger.warning(
                "Folder '%s': source is empty. Nothing to synchronize.", folder.id
            )

        # First-time sync: destination has zero files. Always allowed -
        # there is nothing at the destination that could be lost or
        # inconsistently compared against.
        if destination_count == 0:
            logger.info(
                "Folder '%s': destination is currently empty - treating as "
                "first-time sync, skipping percentage threshold check.",
                folder.id,
            )
            return

        percentage = calculate_sync_percentage(source_count, destination_count)
        logger.info(
            "Folder '%s': sync safety ratio = %.2f%% (threshold = %.2f%%).",
            folder.id,
            percentage,
            folder.minimum_sync_percentage,
        )

        if percentage < folder.minimum_sync_percentage:
            raise SyncThresholdExceededError(
                "Synchronization aborted because source/destination difference "
                f"exceeds safety threshold for folder '{folder.id}' "
                f"(ratio={percentage:.2f}%, threshold={folder.minimum_sync_percentage:.2f}%, "
                f"source_files={source_count}, destination_files={destination_count})."
            )

    @staticmethod
    def _verify_after_sync(
        folder: FolderSyncConfig, source: Path, destination: Path
    ) -> None:
        """Post-sync sanity check: destination must contain at least as many
        files as the source did (since sync is purely additive, destination
        file count should never decrease and should now be >= source count
        for files that originated from source).

        This is intentionally a lightweight structural check, not a
        byte-for-byte verification (robocopy's own logging provides
        per-file detail for deeper audits).
        """
        source_count = count_files_recursive(source)
        destination_count = count_files_recursive(destination)

        if destination_count < source_count:
            raise VerificationError(
                f"Folder '{folder.id}': verification failed. Destination file "
                f"count ({destination_count}) is lower than source file count "
                f"({source_count}) after sync. Manual inspection required."
            )

        logger.info(
            "Folder '%s': verification passed (source=%d, destination=%d).",
            folder.id,
            source_count,
            destination_count,
        )

    @staticmethod
    def _log_summary(outcomes: List[FolderSyncOutcome]) -> None:
        succeeded = sum(1 for o in outcomes if o.succeeded)
        failed = len(outcomes) - succeeded
        logger.info(
            "=== Sync run complete: %d succeeded, %d failed, %d total ===",
            succeeded,
            failed,
            len(outcomes),
        )
        for outcome in outcomes:
            status = "OK" if outcome.succeeded else "FAILED"
            logger.info(
                "  [%s] %s (%s): %s", status, outcome.folder_name, outcome.folder_id, outcome.message
            )