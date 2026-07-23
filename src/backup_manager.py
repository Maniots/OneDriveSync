"""
backup_manager.py

Creates a compressed, timestamped backup of a folder's CURRENT OneDrive
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
"""

from __future__ import annotations

import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import BackupSettings
from .exceptions import BackupError
from .logger import get_logger
from .utils import count_files_recursive, format_bytes

logger = get_logger(__name__)

_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"
_SECONDS_PER_DAY = 86400


class BackupManager:
    """Creates and prunes pre-upload backups for a single folder."""

    def __init__(self, dry_run: bool = False) -> None:
        self._dry_run = dry_run

    def create_backup(
        self, folder_id: str, backup_settings: BackupSettings, onedrive_path: Path
    ) -> Optional[Path]:
        """Compress the current contents of `onedrive_path` into a
        timestamped archive under this folder's backup directory.

        Args:
            folder_id: The folder's config id, used to namespace backups
                so multiple folders never collide in the same backup_path.
            backup_settings: This folder's validated backup configuration.
            onedrive_path: The OneDrive destination about to be overwritten
                by the upcoming upload - this is what gets backed up.

        Returns:
            The path to the created archive, or None if there was nothing
            to back up (onedrive_path doesn't exist or is empty) or this
            is a dry run.

        Raises:
            BackupError: If backup creation fails for any other reason.
                Callers should treat this as fatal for the folder's upload.
        """
        if not onedrive_path.exists() or count_files_recursive(onedrive_path) == 0:
            logger.info(
                "Folder '%s': nothing to back up (destination is empty or "
                "doesn't exist yet) - skipping backup, proceeding with upload.",
                folder_id,
            )
            return None

        backup_dir = backup_settings.backup_path / folder_id
        timestamp = datetime.now().strftime(_TIMESTAMP_FORMAT)
        archive_path = backup_dir / f"{folder_id}_{timestamp}.zip"

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

    def prune_old_backups(
        self, folder_id: str, backup_settings: BackupSettings
    ) -> None:
        """Delete backup archives older than retention_days for this folder.

        Failures here are logged as warnings and never raised - retention
        cleanup must never block or fail an otherwise-successful upload
        that already has a fresh backup in place.
        """
        backup_dir = backup_settings.backup_path / folder_id
        if not backup_dir.exists():
            return

        cutoff_seconds = time.time() - (backup_settings.retention_days * _SECONDS_PER_DAY)

        for archive_path in backup_dir.glob(f"{folder_id}_*.zip"):
            try:
                if archive_path.stat().st_mtime < cutoff_seconds:
                    if self._dry_run:
                        logger.info(
                            "[DRY RUN] Would delete expired backup: %s", archive_path
                        )
                    else:
                        archive_path.unlink()
                        logger.info("Folder '%s': deleted expired backup '%s'.", folder_id, archive_path)
            except OSError as exc:
                logger.warning(
                    "Folder '%s': failed to prune old backup '%s' (non-fatal): %s",
                    folder_id,
                    archive_path,
                    exc,
                )