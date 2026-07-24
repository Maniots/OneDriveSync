"""
backup_manager.py

Creates a DAILY ROLLING ZIP backup of a folder's CURRENT OneDrive
contents immediately before an UPLOAD (local -> OneDrive) operation
overwrites them, and prunes backups older than the configured retention
period.

Design principles, matching the rest of this application:
    - Backups are written ONLY inside the user's OneDrive folder, never to
      local disk (enforced earlier, at config-load time, by
      config_manager.py via utils.is_under_onedrive_root).
    - Backups are only taken before UPLOAD operations, never DOWNLOAD -
      a download doesn't overwrite OneDrive, so there's nothing to protect
      there.
    - A failure to CREATE a backup is treated as fatal for that folder's
      upload (see exceptions.BackupError) - if backups are enabled, an
      upload must never proceed without one succeeding first.
    - A failure to PRUNE old backups is treated as non-fatal - retention
      cleanup is a housekeeping concern, not a safety concern, and must
      never block an otherwise-successful, already-backed-up upload.
    - dry_run is fully respected: no archive is created and no files are
      deleted, only logged as what "would" happen.

BACKUP FORMAT (daily rolling):
    One ZIP per calendar day per folder.
    Naming: <folder_id>_YYYY-MM-DD.zip
    Example: elden_ring_2026-07-23.zip

    On each UPLOAD:
        1. Prune expired backups (older than retention_days).
        2. If today's ZIP exists, delete it.
        3. Create a fresh ZIP with today's date.
        4. Proceed with upload.

    This guarantees exactly ONE backup per day, always reflecting the
    OneDrive state immediately before the most recent upload of that day.
"""

from __future__ import annotations

import re
import time
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from .config import BackupSettings
from .exceptions import BackupError
from .logger import get_logger
from .utils import count_files_recursive, format_bytes

logger = get_logger(__name__)

# Daily ZIP naming: <folder_id>_YYYY-MM-DD.zip
_DAILY_ZIP_PATTERN = re.compile(r"^(.+)_(\d{4}-\d{2}-\d{2})\.zip$")


class BackupManager:
    """Creates and prunes daily rolling pre-upload backups for a single folder."""

    def __init__(self, dry_run: bool = False) -> None:
        self._dry_run = dry_run

    def create_backup(
        self, folder_id: str, backup_settings: BackupSettings, onedrive_path: Path
    ) -> Optional[Path]:
        """Create (or replace) today's backup of the OneDrive folder.

        This method implements the daily rolling backup logic:
        1. Prune expired backups (older than retention_days).
        2. Delete today's backup if it already exists.
        3. Create a fresh backup with today's date.
        4. Return the path to the created backup.

        If the OneDrive folder doesn't exist or is empty, this is treated
        as a first-time sync and no backup is needed (returns None).

        Args:
            folder_id: The folder's config id, used to namespace backups.
            backup_settings: This folder's validated backup configuration.
            onedrive_path: The OneDrive destination about to be overwritten
                by the upcoming upload - this is what gets backed up.

        Returns:
            The path to the created archive, or None if there was nothing
            to back up (first-time sync) or this is a dry run.

        Raises:
            BackupError: If backup creation fails for any reason.
                Callers MUST treat this as fatal for the folder's upload.
        """
        if not onedrive_path.exists() or count_files_recursive(onedrive_path) == 0:
            logger.info(
                "Folder '%s': nothing to back up (destination is empty or "
                "doesn't exist yet) - skipping backup, proceeding with upload.",
                folder_id,
            )
            return None

        backup_dir = backup_settings.backup_path / folder_id
        today = date.today()
        today_str = today.isoformat()  # YYYY-MM-DD
        archive_path = backup_dir / f"{folder_id}_{today_str}.zip"

        # Step 1: Prune expired backups (based on date in filename)
        self._prune_expired_backups(folder_id, backup_settings, today)

        # Step 2: Delete today's backup if it already exists (replacement)
        if archive_path.exists():
            if self._dry_run:
                logger.info(
                    "[DRY RUN] Would replace today's backup: %s", archive_path
                )
            else:
                logger.info("Today's backup already exists. Replacing: %s", archive_path)
                archive_path.unlink()

        # Step 3: Create fresh backup for today
        if self._dry_run:
            logger.info(
                "[DRY RUN] Would create backup of '%s' at '%s'.",
                onedrive_path,
                archive_path,
            )
            return None

        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            self._compress_directory(onedrive_path, archive_path)
        except OSError as exc:
            raise BackupError(
                f"Folder '{folder_id}': failed to create backup of '{onedrive_path}' "
                f"at '{archive_path}': {exc}"
            ) from exc

        archive_size = archive_path.stat().st_size
        logger.info(
            "Folder '%s': backup created at '%s' (%s).",
            folder_id,
            archive_path,
            format_bytes(archive_size),
        )
        return archive_path

    @staticmethod
    def _compress_directory(source_dir: Path, archive_path: Path) -> None:
        """Compress every file under source_dir into a zip archive,
        preserving the relative directory structure."""
        with zipfile.ZipFile(archive_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file_path in source_dir.rglob("*"):
                if file_path.is_file():
                    zf.write(file_path, arcname=file_path.relative_to(source_dir))

    def _prune_expired_backups(
        self, folder_id: str, backup_settings: BackupSettings, today: date
    ) -> None:
        """Delete backup archives older than retention_days.

        Retention is calculated based on the DATE ENCODED IN THE FILENAME,
        not on filesystem mtime. This ensures correct behavior even if
        files are copied/restored.

        Failures are logged as warnings and never raised.
        """
        backup_dir = backup_settings.backup_path / folder_id
        if not backup_dir.exists():
            return

        retention_days = backup_settings.retention_days
        cutoff_date = today - __import__("datetime").timedelta(days=retention_days)

        logger.info("Cleaning expired backups (retention: %d days)...", retention_days)

        for archive_path in backup_dir.glob(f"{folder_id}_*.zip"):
            try:
                match = _DAILY_ZIP_PATTERN.match(archive_path.name)
                if not match:
                    # Skip files that don't match our naming convention
                    logger.warning(
                        "Folder '%s': skipping unrecognized backup file '%s'.",
                        folder_id,
                        archive_path.name,
                    )
                    continue

                file_date_str = match.group(2)
                file_date = date.fromisoformat(file_date_str)

                if file_date < cutoff_date:
                    if self._dry_run:
                        logger.info(
                            "[DRY RUN] Would delete expired backup: %s", archive_path
                        )
                    else:
                        archive_path.unlink()
                        logger.info("Removing expired backup: %s", archive_path.name)
                # Files from today or within retention window are kept

            except (ValueError, OSError) as exc:
                logger.warning(
                    "Folder '%s': failed to prune old backup '%s' (non-fatal): %s",
                    folder_id,
                    archive_path.name,
                    exc,
                )

    def prune_old_backups(
        self, folder_id: str, backup_settings: BackupSettings
    ) -> None:
        """Public method to prune expired backups.

        This can be called independently (e.g., for testing or manual cleanup).
        It uses today's date as the reference point.
        """
        today = date.today()
        self._prune_expired_backups(folder_id, backup_settings, today)