"""
Backup Service

Provides a clean API for accessing backup information.
Isolates the UI from the core backup logic.
"""

import os
import re
import shutil
import stat
import tempfile
import zipfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from .configuration_service import ConfigurationService
from src.single_instance import acquire_single_instance_lock
from src.utils import expand_env_vars, is_dangerous_root_path


class BackupService:
    """Service for managing backup information."""

    def __init__(self, config_service: ConfigurationService):
        """
        Initialize the backup service.

        Args:
            config_service: Service to provide application configuration.
        """
        self._config_service = config_service

    @staticmethod
    def _reject_links(path: Path) -> None:
        """Inspect lexical ancestors before resolving: resolve() conceals links."""
        for component in (path, *path.parents):
            try:
                metadata = component.lstat()
            except FileNotFoundError:
                continue
            reparse_tag = getattr(metadata, "st_reparse_tag", 0)
            # Cloud Files placeholders preserve their name/path. Allow the
            # documented CLOUD..CLOUD_F family used by OneDrive, while rejecting
            # mount points, symlinks and unrecognized reparse handlers.
            # https://learn.microsoft.com/en-us/windows/win32/fileio/reparse-point-tags
            cloud_placeholder = reparse_tag & 0xFFFF0FFF == 0x9000001A
            unsafe_reparse = getattr(metadata, "st_file_attributes", 0) & 0x400 and not cloud_placeholder
            if stat.S_ISLNK(metadata.st_mode) or unsafe_reparse:
                raise ValueError(f"Links and reparse points are not allowed: {component}")

    def _managed_directory(self, folder_id: str) -> Path:
        if not folder_id or folder_id in (".", "..") or any(c in folder_id for c in '/\\:'):
            raise ValueError("Invalid backup folder identifier")
        config = self._config_service.get_app_config()
        folder = next((folder for folder in config.folders if folder.id == folder_id), None) if config else None
        if folder is None or folder.backup is None:
            raise ValueError("Backup folder is not configured")
        directory = Path(os.path.abspath(expand_env_vars(folder.backup.backup_path))) / (folder.backup.directory_name or folder_id)
        self._reject_links(directory)
        return directory

    def get_archive_path(self, folder_id: str, archive_path: str | Path) -> Path:
        """Bind an action to exactly one regular, configured backup archive."""
        directory = self._managed_directory(folder_id)
        if ".." in Path(archive_path).parts:
            raise ValueError("Archive path traversal is not allowed")
        archive = Path(os.path.abspath(archive_path))
        match = re.fullmatch(rf"{re.escape(folder_id)}_(\d{{4}}-\d{{2}}-\d{{2}})\.zip", archive.name)
        if archive.parent != directory or match is None:
            raise ValueError("Archive is outside the configured backup directory")
        datetime.strptime(match.group(1), "%Y-%m-%d")
        self._reject_links(archive)
        if not archive.is_file():
            raise ValueError("Backup archive no longer exists")
        return archive

    @contextmanager
    def _mutation_lock(self):
        config = self._config_service.get_app_config()
        if config is None:
            raise RuntimeError("Configuration not available")
        if config.general.dry_run:
            raise RuntimeError("Backup restore and deletion are disabled in dry-run mode")
        lock_path = Path(__file__).resolve().parents[2] / "onedrive_pcsync.lock"
        handle = acquire_single_instance_lock(lock_path)
        if handle is None:
            raise RuntimeError("Another synchronization or backup operation is already running")
        try:
            yield
        finally:
            handle.close()

    def delete_backup(self, folder_id: str, archive_path: str | Path) -> None:
        """Delete only the selected managed archive, while sync is excluded."""
        with self._mutation_lock():
            self.get_archive_path(folder_id, archive_path).unlink()

    @staticmethod
    def _member_parts(member: zipfile.ZipInfo) -> tuple[str, ...]:
        name = member.filename
        if not name or name.startswith(("/", "\\")) or "\\" in name:
            raise ValueError(f"Unsafe archive member: {name!r}")
        if member.orig_filename != name:
            raise ValueError("Archive member contains a null byte")
        parts = tuple((name[:-1] if name.endswith("/") else name).split("/"))
        reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                    *(f"LPT{i}" for i in range(1, 10)),
                    *(f"COM{i}" for i in "¹²³"), *(f"LPT{i}" for i in "¹²³")}
        for part in parts:
            if (part in ("", ".", "..") or part.endswith((".", " "))
                    or any(ord(c) < 32 or c in '<>:"|?*' for c in part)
                    or part.split(".")[0].upper() in reserved):
                raise ValueError(f"Unsafe archive member: {name!r}")
        mode = member.external_attr >> 16
        file_type = stat.S_IFMT(mode)
        if file_type not in (0, stat.S_IFREG, stat.S_IFDIR) or member.external_attr & 0x400:
            raise ValueError(f"Archive links and special files are not allowed: {name!r}")
        if bool(file_type == stat.S_IFDIR) and not member.is_dir():
            raise ValueError(f"Invalid directory member: {name!r}")
        return parts

    @staticmethod
    def _atomic_copy(source: Path, destination: Path) -> None:
        """Replace a file only after a complete copy exists on the same volume."""
        BackupService._reject_links(destination)
        descriptor, temporary = tempfile.mkstemp(prefix=".restore-", dir=destination.parent)
        os.close(descriptor)
        try:
            shutil.copy2(source, temporary)
            os.replace(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def restore_backup(self, folder_id: str, archive_path: str | Path, target_path: str | Path) -> int:
        """Validate/stage the whole ZIP, then restore atomically with rollback.

        Existing unrelated files are retained. Callers must obtain explicit
        overwrite confirmation before calling; GUI callers run this off-thread.
        """
        with self._mutation_lock():
            archive = self.get_archive_path(folder_id, archive_path)
            target = Path(os.path.abspath(target_path))
            self._reject_links(target)
            config = self._config_service.get_app_config()
            managed_directories = [folder.backup.directory_for(folder.id)
                                   for folder in config.folders if folder.backup]
            if any(target.resolve().is_relative_to(directory.resolve()) for directory in managed_directories):
                raise ValueError("Restore cannot overwrite managed backup archives")
            if (target == Path(target.anchor) or target == Path.home().resolve()
                    or is_dangerous_root_path(target) or not target.is_dir()):
                raise ValueError("Choose an existing, safe restore directory")
            stage = Path(tempfile.mkdtemp(prefix="onedrive-backup-restore-"))
            keep_recovery = False
            committed = []
            created_directories = []
            try:
                entries = []
                seen = {}
                with zipfile.ZipFile(archive) as zipped:
                    # Validate ALL paths before staging or writing any member.
                    for member in zipped.infolist():
                        parts = self._member_parts(member)
                        key = "/".join(parts).casefold()
                        if key in seen:
                            raise ValueError(f"Duplicate archive member: {member.filename}")
                        seen[key] = member.is_dir()
                        destination = target.joinpath(*parts)
                        self._reject_links(destination)
                        if not destination.resolve().is_relative_to(target.resolve()):
                            raise ValueError("Archive member escapes the restore directory")
                        if any(destination.resolve().is_relative_to(directory.resolve()) for directory in managed_directories):
                            raise ValueError("Restore cannot overwrite managed backup archives")
                        if destination.exists() and destination.is_dir() != member.is_dir():
                            raise ValueError(f"File/directory conflict: {destination}")
                        entries.append((member, parts, destination))
                    for key in seen:
                        components = key.split("/")
                        if any(seen.get("/".join(components[:i])) is False for i in range(1, len(components))):
                            raise ValueError("Archive contains a file/directory path conflict")
                    for index, (member, parts, destination) in enumerate(entries):
                        if member.is_dir():
                            with zipped.open(member) as source:
                                while source.read(1024 * 1024):
                                    pass  # Validate CRC even on directory entries.
                        else:
                            # Reading through EOF checks the CRC, including when
                            # corruption occurs in a later archive member.
                            with zipped.open(member) as source, (stage / f"new-{index}").open("wb") as output:
                                shutil.copyfileobj(source, output)
                            if destination.exists():
                                shutil.copy2(destination, stage / f"old-{index}")
                # Preflight non-member parent paths too, before touching target.
                for member, parts, destination in entries:
                    for parent in destination.parents:
                        if parent == target:
                            break
                        if parent.exists() and not parent.is_dir():
                            raise ValueError(f"Restore parent is not a directory: {parent}")
                try:
                    for index, (member, parts, destination) in enumerate(entries):
                        self._reject_links(destination)
                        directory = destination if member.is_dir() else destination.parent
                        missing = []
                        while not directory.exists():
                            missing.append(directory)
                            directory = directory.parent
                        for directory in reversed(missing):
                            directory.mkdir()
                            created_directories.append(directory)
                        if not member.is_dir():
                            self._atomic_copy(stage / f"new-{index}", destination)
                            committed.append((destination, stage / f"old-{index}"))
                except Exception as failure:
                    rollback_errors = []
                    for destination, original in reversed(committed):
                        try:
                            self._reject_links(destination)
                            if original.exists():
                                self._atomic_copy(original, destination)
                            else:
                                destination.unlink()
                        except Exception as rollback_failure:
                            rollback_errors.append(str(rollback_failure))
                    for directory in reversed(created_directories):
                        try:
                            directory.rmdir()  # Remove only newly created, empty directories.
                        except OSError:
                            pass
                    if rollback_errors:
                        keep_recovery = True
                        raise RuntimeError(f"Restore failed: {failure}. Recovery copies retained in {stage}: "
                                           + "; ".join(rollback_errors)) from failure
                    raise
                return sum(not member.is_dir() for member, _, _ in entries)
            finally:
                if not keep_recovery:
                    # Cleanup must not turn a successfully committed restore
                    # into a reported failure; target contents remain valid.
                    shutil.rmtree(stage, ignore_errors=True)

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

        backup_dir = self._managed_directory(folder_id)

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
                self.get_archive_path(folder_id, backup_file)
                size = backup_file.stat().st_size
                # Format size in a human-readable way (we'll keep it as bytes for now, but we can format if needed)
                # For simplicity, we'll return the size in bytes and let the UI format it.
                # Alternatively, we can return a formatted string.
                # We'll return the size in bytes and the UI can format it.
                size_bytes = size
            except (OSError, ValueError):
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
