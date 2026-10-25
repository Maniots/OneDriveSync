"""
sync_manager.py

Orchestrates the full synchronization workflow: path validation, file-count
safety-ratio checks, copy engine execution, and optional post-sync
verification - for every configured folder, in both startup (download)
and shutdown (upload) modes.

This module owns ALL safety decisions. robocopy_manager.py (the copy
engine) is a pure-Python execution layer that this module chooses whether
or not to invoke.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
from typing import Callable, List, Optional

from .backup_manager import BackupManager
from .config import AppConfig, FolderSyncConfig, SyncDirection
from .exceptions import (
    BackupError,
    OneDrivePCSyncError,
    PathValidationError,
    SyncThresholdExceededError,
    VerificationError,
    CopyEngineError,
)
from .logger import get_logger
from .robocopy_manager import CopyEngine
from .utils import calculate_sync_percentage, count_files_recursive, is_dangerous_root_path
from .sync_groups import grouped_job_ids

logger = get_logger(__name__)


@dataclass(frozen=True)
class FolderSyncOutcome:
    """Result of attempting to synchronize a single folder."""

    folder_id: str
    folder_name: str
    direction: SyncDirection
    succeeded: bool
    message: str
    threshold_bypassed: bool = False


class SyncManager:
    """Coordinates safe synchronization of all configured folders."""

    def __init__(self, config: AppConfig, history_path: Optional[Path] = None, *,
                 cloud_root: Optional[Path] = None, defer_remote: bool = False, cancel_event=None) -> None:
        self._config = config
        self._copy_engine = CopyEngine(
            settings=config.copy_engine,
            dry_run=config.general.dry_run,
        )
        self._backup = BackupManager(dry_run=config.general.dry_run)
        # Track the current sync mode for logging context in copy_engine.
        self._mode: str = "unknown"
        self._history_path = history_path
        self._cloud_root = cloud_root
        self._defer_remote = defer_remote
        self._cancel_event = cancel_event or threading.Event()

    def run_startup_sync(self, progress_callback: Optional[Callable[[int, str], None]] = None, *, ignore_threshold_for: Optional[str] = None) -> List[FolderSyncOutcome]:
        """Run the configured startup synchronization (typically download)."""
        self._mode = "startup"
        trigger = self._config.sync.startup
        if not trigger.enabled:
            logger.info("Startup sync is disabled in configuration. Skipping.")
            return []
        logger.info("=== Starting STARTUP sync (direction=%s) ===", trigger.direction.value)
        return self._run_all_folders(trigger.direction, progress_callback, ignore_threshold_for)

    def run_shutdown_sync(self, progress_callback: Optional[Callable[[int, str], None]] = None, *, ignore_threshold_for: Optional[str] = None) -> List[FolderSyncOutcome]:
        """Run the configured shutdown synchronization (typically upload)."""
        self._mode = "shutdown"
        trigger = self._config.sync.shutdown
        if not trigger.enabled:
            logger.info("Shutdown sync is disabled in configuration. Skipping.")
            return []
        logger.info("=== Starting SHUTDOWN sync (direction=%s) ===", trigger.direction.value)
        return self._run_all_folders(trigger.direction, progress_callback, ignore_threshold_for)

    def _run_all_folders(self, direction: SyncDirection, progress_callback: Optional[Callable[[int, str], None]] = None, ignore_threshold_for: Optional[str] = None) -> List[FolderSyncOutcome]:
        outcomes: List[FolderSyncOutcome] = []

        owned = grouped_job_ids(self._config)
        folders = [folder for folder in self._config.enabled_folders() if folder.id not in owned]
        def sync_folder(folder):
            # Each folder is fully independent: an error in one must never
            # prevent the others from being processed.
            try:
                outcome = self._sync_single_folder(folder, direction, ignore_threshold=folder.id == ignore_threshold_for)
                return outcome
            except OneDrivePCSyncError as exc:
                logger.error(
                    "Sync aborted for folder '%s' (%s): %s",
                    folder.id,
                    folder.name,
                    exc,
                )
                return FolderSyncOutcome(
                        folder_id=folder.id,
                        folder_name=folder.name,
                        direction=direction,
                        succeeded=False,
                        message=str(exc),
                        threshold_bypassed=folder.id == ignore_threshold_for,
                )
            except Exception as exc:  # noqa: BLE001 - last line of defense
                logger.exception(
                    "Unexpected error while syncing folder '%s' (%s).",
                    folder.id,
                    folder.name,
                )
                return FolderSyncOutcome(
                        folder_id=folder.id,
                        folder_name=folder.name,
                        direction=direction,
                        succeeded=False,
                        message=f"Unexpected error: {exc}",
                        threshold_bypassed=folder.id == ignore_threshold_for,
                )

        workers = self._config.general.max_parallel_jobs
        # Overlapping pairs must remain sequential to protect backup/copy reads.
        roots = [[f.local_path_resolved, f.onedrive_path_resolved] for f in folders]
        if direction == SyncDirection.UPLOAD:
            for folder, pair in zip(folders, roots):
                if folder.backup and folder.backup.enabled:
                    pair.append(folder.backup.directory_for(folder.id).resolve())
        if any(a.is_relative_to(b) or b.is_relative_to(a)
               for i, pair in enumerate(roots) for other in roots[i + 1:]
               for a in pair for b in other):
            workers = 1
        if progress_callback and folders:
            progress_callback(0, f"Processing {len(folders)} folder(s)")
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for index, outcome in enumerate(executor.map(sync_folder, folders)):
                outcomes.append(outcome)
                if progress_callback is not None:
                    progress_callback(int((index + 1) / len(folders) * 100), f"Processed folder {outcome.folder_name} ({index + 1}/{len(folders)})")

        for group in self._config.sync_groups:
            if not group.enabled:
                continue
            if self._cloud_root is None:
                outcomes.append(FolderSyncOutcome(group.id, group.name, direction, False,
                    "Group state location is unavailable. Run this configuration through EverySync."))
                continue
            from .group_sync import GroupSyncRunner
            if progress_callback:
                progress_callback(0, f"Processing synchronization {group.name}")
            outcomes.extend(GroupSyncRunner(self._config, self._cloud_root,
                local_runner=self._sync_single_folder, cancel_event=self._cancel_event).run(group, direction, defer=self._defer_remote))
            if progress_callback:
                progress_callback(100, f"Processed synchronization {group.name}")

        ungrouped_jobs = [job for job in self._config.remote_jobs if job.id not in owned]
        if any(job.enabled for job in ungrouped_jobs):
            if self._cloud_root is None:
                outcomes.extend(FolderSyncOutcome(job.id, job.name, direction, False,
                    "Cloud state location is unavailable. Run this configuration through EverySync.")
                    for job in ungrouped_jobs if job.enabled)
            else:
                from .cloud_sync import CloudSyncRunner
                if progress_callback:
                    progress_callback(0, "Processing cloud jobs")
                outcomes.extend(CloudSyncRunner(replace(self._config, remote_jobs=ungrouped_jobs), self._cloud_root).run(
                    direction, ignore_threshold_for=ignore_threshold_for, defer=self._defer_remote))
                if progress_callback:
                    progress_callback(100, "Cloud jobs processed")

        self._log_summary(outcomes)
        if self._history_path is not None:
            from .sync_history import SyncHistory
            try:
                SyncHistory(self._history_path).record(self._mode, outcomes, self._config.general.dry_run)
            except Exception:
                logger.exception("Could not save synchronization history")
        return outcomes

    def _sync_single_folder(
        self, folder: FolderSyncConfig, direction: SyncDirection, *, ignore_threshold: bool = False
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
        if ignore_threshold:
            logger.warning("Folder '%s': percentage threshold explicitly bypassed for this run.", folder.id)
        else:
            self._enforce_safety_threshold(folder, source, destination)

        if direction == SyncDirection.UPLOAD and folder.backup is not None and folder.backup.enabled:
            self._backup.create_backup(folder.id, folder.backup, destination)
            self._backup.prune_old_backups(folder.id, folder.backup)

        result = self._copy_engine.run(source, destination, mode=self._mode)
        if not result.success:
            raise CopyEngineError(result.stderr or f"Copy failed with exit code {result.exit_code}")

        if (
            folder.verify_after_sync
            and self._config.general.verify_after_sync
            and not self._config.general.dry_run
        ):
            self._verify_after_sync(folder, source, destination, self._config.copy_engine.copy_subdirectories)
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
        if result.stderr:
            message += f" Warning: {result.stderr}"
        if ignore_threshold:
            message += " Percentage threshold bypassed by explicit request."
        logger.info("Folder '%s': %s", folder.id, message)

        return FolderSyncOutcome(
            folder_id=folder.id,
            folder_name=folder.name,
            direction=direction,
            succeeded=True,
            message=message,
            threshold_bypassed=ignore_threshold,
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
            return folder.onedrive_path_resolved, folder.local_path_resolved
        return folder.local_path_resolved, folder.onedrive_path_resolved

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
        folder: FolderSyncConfig, source: Path, destination: Path, recursive: bool = True
    ) -> None:
        """Post-sync sanity check: destination must contain at least as many
        files as the source did (since sync is purely additive, destination
        file count should never decrease and should now be >= source count
        for files that originated from source).

        This is intentionally a lightweight structural check, not a
        byte-for-byte verification (the copy engine's own logging provides
        per-file detail for deeper audits).
        """
        source_count = count_files_recursive(source) if recursive else sum(p.is_file() for p in source.iterdir())
        destination_count = count_files_recursive(destination) if recursive else sum(p.is_file() for p in destination.iterdir())

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
        logger.log(25 if failed == 0 else 20,
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
