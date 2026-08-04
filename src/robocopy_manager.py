"""
robocopy_manager.py

Pure-Python file copy engine that replaces the previous robocopy.exe-based
implementation.

Design principle: this module is the copy engine only. It never makes
safety decisions — those are made entirely by sync_manager.py BEFORE this
module is invoked. This module's job is to walk directories, copy files
safely, preserve metadata, and return structured results.

The engine is:
- Additive and conservative: never deletes source or destination files.
- Non-destructive: never overwrites a newer destination file with an older
  source file (XO semantics).
- Junction/symlink-aware: skips them to avoid infinite loops.
- Metadata-preserving: copies timestamps and permissions via shutil.copy2.
- Dry-run capable: logs what would happen without touching files.
- Resilient: tolerates a small number of individual file errors (e.g. files
  locked by another process during shutdown) rather than failing the entire
  sync.
"""

from __future__ import annotations

import os
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from .config import CopyEngineSettings
from .exceptions import CopyEngineError
from .logger import get_logger

logger = get_logger(__name__)

# Exit code used when the copy engine reports overall success.
_SUCCESS_EXIT_CODE = 1

# Exit code used when the copy engine reports failure (too many file errors).
_FAILURE_EXIT_CODE = 8

# Maximum number of individual file-copy errors tolerated before the engine
# reports overall failure. A small number of failures (e.g. a file locked by
# another process during shutdown) should not cause the entire sync to fail.
_MAX_FILE_ERRORS = 5


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CopyResult:
    """Outcome of a single copy engine invocation."""

    source: Path
    destination: Path
    exit_code: int
    success: bool
    stdout: str
    stderr: str
    dry_run: bool


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_junction_or_symlink(path: Path) -> bool:
    """Return True if *path* is a junction or symlink (reparse point).

    Junctions and symlinks are skipped to avoid infinite loops and because
    the engine never follows them into potentially dangerous locations.
    """
    if not path.exists():
        return False
    try:
        st = path.lstat()
        return stat.S_ISLNK(st.st_mode)
    except OSError:
        return False


def _compare_files(src_file: Path, dst_file: Path) -> Tuple[bool, str]:
    """Compare two files and return (should_copy, reason).

    Implements XO semantics: the destination file is never overwritten if it
    is newer than or identical to the source file. The source file is
    copied only when it is newer or when the destination does not exist.
    """
    if not dst_file.exists():
        return True, "Destination does not exist — will copy"

    try:
        src_stat = src_file.stat()
        dst_stat = dst_file.stat()
    except OSError as exc:
        return False, f"Cannot stat files for comparison: {exc}"

    src_mtime = src_stat.st_mtime
    dst_mtime = dst_stat.st_mtime

    # XO: never overwrite a newer destination.
    if dst_mtime > src_mtime:
        return False, f"XO: dest is newer (dst_mtime={dst_mtime}, src_mtime={src_mtime}) — skipping"

    # Same mtime — compare sizes to decide.
    if dst_mtime == src_mtime:
        if src_stat.st_size != dst_stat.st_size:
            return True, f"Same mtime but size differs (src={src_stat.st_size}, dst={dst_stat.st_size}) — will copy"
        return False, "XO: dest is same age and size — skipping"

    # Source is newer — copy.
    return True, f"Source is newer (src_mtime={src_mtime}, dst_mtime={dst_mtime}) — will copy"


def _copy_single_file(src_file: Path, dst_file: Path) -> Tuple[bool, str]:
    """Copy a single file, preserving metadata via shutil.copy2.

    Returns (was_copied, message).
    """
    try:
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src_file), str(dst_file))
        return True, f"Copied: {src_file} -> {dst_file}"
    except OSError as exc:
        return False, f"Failed: {src_file} -> {dst_file}: {exc}"


def _collect_files(source: Path) -> List[Path]:
    """Recursively collect all regular files under *source*, skipping
    junctions and symlinks."""
    files: List[Path] = []
    for root, _, filenames in os.walk(str(source), followlinks=False):
        for filename in filenames:
            full_path = Path(root) / filename
            if _is_junction_or_symlink(full_path):
                continue
            files.append(full_path)
    return files


def _collect_empty_dirs(source: Path, destination: Path) -> List[Path]:
    """Collect empty directories under *source* so they can be recreated
    at *destination* (matching the /E behaviour of the previous robocopy
    engine)."""
    empty_dirs: List[Path] = []
    for root, dirs, filenames in os.walk(str(source), followlinks=False):
        if not dirs and not filenames:
            rel = Path(root).relative_to(source)
            empty_dirs.append(destination / rel)
    return empty_dirs


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class CopyEngine:
    """Pure-Python file copy engine — no external executables required.

    Replaces the previous robocopy.exe-based implementation with a
    safe, deterministic, non-destructive Python copy engine.
    """

    def __init__(self, settings: CopyEngineSettings, dry_run: bool = False) -> None:
        """
        Args:
            settings: Copy engine tuning parameters from configuration.
            dry_run: If True, operations are logged but no files are
                touched.
        """
        self._settings = settings
        self._dry_run = dry_run

    # -- Public methods matching the previous copy engine API --------

    def run(self, source: Path, destination: Path, mode: str = "unknown") -> CopyResult:
        """Execute a full directory copy from *source* to *destination*.

        This is the primary entry point, matching the previous
        CopyEngine.run() signature so sync_manager.py can consume
        it without changes.

        Args:
            source: Source directory (must already exist; validated upstream).
            destination: Destination directory (created upstream if needed).
            mode: Sync trigger context ('startup', 'shutdown', or 'unknown').
                  Logged for diagnostics; does not change copy semantics.

        Returns:
            A CopyResult describing the outcome.

        Raises:
            CopyEngineError: If the source does not exist or is not a
                directory, or if the copy fails catastrophically.
        """
        if not source.exists():
            raise CopyEngineError(f"Source path does not exist: '{source}'")
        if not source.is_dir():
            raise CopyEngineError(f"Source path is not a directory: '{source}'")

        logger.info(
            "=== copy engine start === mode=%s | source=%s | destination=%s | dry_run=%s",
            mode,
            source,
            destination,
            self._dry_run,
        )

        if self._dry_run:
            return self._dry_run_copy(source, destination)

        return self._live_copy(source, destination)

    def copy_tree(self, source: Path, destination: Path) -> CopyResult:
        """Copy an entire directory tree from *source* to *destination*.

        Alias for run() with mode='copy_tree'. Provides a named API
        for callers that want to express intent explicitly.
        """
        return self.run(source, destination, mode="copy_tree")

    def copy_file(self, src_file: Path, dst_file: Path) -> Tuple[bool, str]:
        """Copy a single file with XO (don't overwrite newer dest) semantics.

        Args:
            src_file: Source file path.
            dst_file: Destination file path.

        Returns:
            (was_copied, message) tuple.
        """
        if self._dry_run:
            return True, f"[DRY RUN] Would copy {src_file} -> {dst_file}"

        should_copy, reason = _compare_files(src_file, dst_file)
        if not should_copy:
            return False, reason

        return _copy_single_file(src_file, dst_file)

    def compare_files(self, src_file: Path, dst_file: Path) -> Tuple[bool, str]:
        """Compare two files and return (should_copy, reason).

        Implements XO semantics: destination is never overwritten with an
        older source file. Returns (False, reason) when the destination is
        newer or identical; (True, reason) when the source is newer or the
        destination does not exist.
        """
        return _compare_files(src_file, dst_file)

    # -- Internal implementation -----------------------------------------

    def _dry_run_copy(self, source: Path, destination: Path) -> CopyResult:
        """Log what would be copied without touching any files."""
        logger.info("[DRY RUN] Copy engine: would copy %s -> %s", source, destination)

        files = _collect_files(source)
        empty_dirs = _collect_empty_dirs(source, destination)

        stdout_lines = [f"[DRY RUN] Would copy {len(files)} file(s) and {len(empty_dirs)} empty dir(s)"]
        for f in files:
            rel = f.relative_to(source)
            dst_file = destination / rel
            stdout_lines.append(f"[DRY RUN] Would copy {f} -> {dst_file}")

        return CopyResult(
            source=source,
            destination=destination,
            exit_code=_SUCCESS_EXIT_CODE,
            success=True,
            stdout="\n".join(stdout_lines),
            stderr="",
            dry_run=True,
        )

    def _live_copy(self, source: Path, destination: Path) -> CopyResult:
        """Perform the actual file copy with full logging and error handling."""
        stdout_lines: List[str] = []
        file_errors = 0
        files_copied = 0
        files_skipped = 0
        files_overwritten = 0
        dirs_created = 0

        # Collect and copy regular files
        all_files = _collect_files(source)
        logger.info(
            "Copy engine: found %d file(s) in source '%s'.",
            len(all_files),
            source,
        )

        for src_file in all_files:
            rel = src_file.relative_to(source)
            dst_file = destination / rel

            should_copy, reason = _compare_files(src_file, dst_file)
            if not should_copy:
                files_skipped += 1
                stdout_lines.append(f"Skipped: {src_file} ({reason})")
                continue

            copied, msg = _copy_single_file(src_file, dst_file)
            if copied:
                files_copied += 1
                files_overwritten += 1 if dst_file.exists() else 0
                stdout_lines.append(msg)
            else:
                file_errors += 1
                logger.warning("%s", msg)
                stdout_lines.append(msg)

        # Recreate empty directories (matching /E behaviour)
        empty_dirs = _collect_empty_dirs(source, destination)
        for empty_dir in empty_dirs:
            try:
                empty_dir.mkdir(parents=True, exist_ok=True)
                dirs_created += 1
                stdout_lines.append(f"Created empty dir: {empty_dir}")
            except OSError as exc:
                file_errors += 1
                logger.warning("Failed to create empty directory %s: %s", empty_dir, exc)
                stdout_lines.append(f"Failed to create empty dir {empty_dir}: {exc}")

        # Determine overall success
        overall_success = file_errors <= _MAX_FILE_ERRORS
        exit_code = _SUCCESS_EXIT_CODE if overall_success else _FAILURE_EXIT_CODE

        stdout = "\n".join(stdout_lines)
        stderr = ""
        if file_errors > 0:
            stderr = (
                f"{file_errors} file(s) failed to copy "
                f"(tolerated up to {_MAX_FILE_ERRORS})."
            )

        logger.info(
            "Copy engine completed for %s -> %s: "
            "%d files copied, %d skipped, %d overwritten, "
            "%d dirs created, %d errors, success=%s.",
            source,
            destination,
            files_copied,
            files_skipped,
            files_overwritten,
            dirs_created,
            file_errors,
            overall_success,
        )

        return CopyResult(
            source=source,
            destination=destination,
            exit_code=exit_code,
            success=overall_success,
            stdout=stdout,
            stderr=stderr,
            dry_run=False,
        )
