"""
robocopy_manager.py

Thin, safety-constrained wrapper around the Windows `robocopy` executable.

Design principle: robocopy is used ONLY as a copy engine. It never makes
safety decisions - those are made entirely by sync_manager.py BEFORE this
module is invoked. This module's job is simply to build a command line
that can NEVER be destructive (no /MIR, /PURGE, /MOVE, /MOV) and to
correctly interpret robocopy's unusual exit code bitmask.

Robocopy exit code bitmask (values can combine by addition):
    0  - No files copied. No failure.
    1  - Files copied successfully.
    2  - Extra files/dirs detected at destination (informational only,
         since we never purge, this simply means dest has files
         source doesn't - not an error for us).
    4  - Mismatched files/dirs detected.
    8  - Some files/dirs could not be copied (copy errors occurred).
    16 - Serious error: robocopy did not copy any files. This is a
         fatal error (e.g. invalid path, access denied at the top level).

Any code with bit 8 or bit 16 set is treated as a failure by this module.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List

from .config import RobocopySettings
from .exceptions import RobocopyExecutionError
from .logger import get_logger

logger = get_logger(__name__)

# Exit code bits that indicate an actual failure occurred.
_FAILURE_BITMASK = 0b11000  # bits 8 (copy errors) and 16 (fatal error)

# Flags that must NEVER appear in a command built by this module.
_FORBIDDEN_FLAGS = {"/mir", "/purge", "/mov", "/move"}


@dataclass(frozen=True)
class RobocopyResult:
    """Outcome of a single robocopy invocation."""

    source: Path
    destination: Path
    exit_code: int
    success: bool
    stdout: str
    stderr: str
    dry_run: bool


class RobocopyManager:
    """Builds and safely executes robocopy commands."""

    def __init__(self, settings: RobocopySettings, dry_run: bool = False) -> None:
        """
        Args:
            settings: Robocopy tuning parameters from configuration.
            dry_run: If True, commands are built and logged but never
                executed (robocopy's own /L "list only" flag is used).
        """
        self._settings = settings
        self._dry_run = dry_run

    def build_command(self, source: Path, destination: Path) -> List[str]:
        """Build a safe, non-destructive robocopy command.

        Args:
            source: Source directory.
            destination: Destination directory.

        Returns:
            The full command as a list of arguments, suitable for
            subprocess.run(). Never contains /MIR, /PURGE, /MOV, or /MOVE.
        """
        command: List[str] = ["robocopy", str(source), str(destination)]

        if self._settings.copy_subdirectories:
            command.append("/E")  # copy subdirectories, including empty ones

        if self._settings.exclude_junctions:
            command.append("/XJ")  # exclude junction points (prevents symlink loops)

        if self._settings.fat_file_times:
            command.append("/FFT")  # tolerant file time comparisons

        command.append(f"/R:{self._settings.retry_count}")
        command.append(f"/W:{self._settings.retry_wait_seconds}")

        if self._settings.multithreading and self._settings.multithreading > 1:
            command.append(f"/MT:{self._settings.multithreading}")

        if self._settings.monitor_mode:
            command.append("/MON:1")

        # /XX excludes "extra" files/dirs from being flagged in a way that
        # could be misread as requiring deletion. We never delete extras.
        command.append("/XX")

        # Always log a full, timestamped, per-file listing for auditability.
        command.append("/NP")  # no progress percentage spam in logs
        command.append("/TEE")  # output to console AND log

        if self._dry_run:
            command.append("/L")  # list only - do not actually copy/move/delete

        self._assert_command_is_safe(command)
        return command

    @staticmethod
    def _assert_command_is_safe(command: List[str]) -> None:
        """Defense-in-depth: verify no destructive flag ever slipped in.

        This is a hard invariant check, not user-configurable. If it ever
        trips, it indicates a programming error in build_command(), and we
        fail loudly rather than risk running a destructive command.
        """
        lowered = {arg.lower() for arg in command}
        intersection = lowered.intersection(_FORBIDDEN_FLAGS)
        if intersection:
            raise RobocopyExecutionError(
                f"Refusing to execute robocopy command containing forbidden "
                f"destructive flag(s): {intersection}. This should never happen "
                f"and indicates a bug in robocopy_manager.py."
            )

    def run(self, source: Path, destination: Path) -> RobocopyResult:
        """Execute robocopy for a single source/destination pair.

        Args:
            source: Source directory (must already exist; validated upstream).
            destination: Destination directory (created upstream if needed).

        Returns:
            A RobocopyResult describing the outcome.

        Raises:
            RobocopyExecutionError: If robocopy reports a fatal failure
                (exit code with bit 8 or bit 16 set), or if the robocopy
                executable itself cannot be launched.
        """
        command = self.build_command(source, destination)
        logger.info("Executing: %s", " ".join(command))

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,  # we interpret the exit code ourselves
            )
        except FileNotFoundError as exc:
            raise RobocopyExecutionError(
                "robocopy executable not found. This application requires Windows."
            ) from exc
        except OSError as exc:
            raise RobocopyExecutionError(f"Failed to launch robocopy: {exc}") from exc

        exit_code = completed.returncode
        success = (exit_code & _FAILURE_BITMASK) == 0

        result = RobocopyResult(
            source=source,
            destination=destination,
            exit_code=exit_code,
            success=success,
            stdout=completed.stdout,
            stderr=completed.stderr,
            dry_run=self._dry_run,
        )

        if not success:
            logger.error(
                "Robocopy reported failure for %s -> %s (exit code %d).",
                source,
                destination,
                exit_code,
            )
            raise RobocopyExecutionError(
                f"Robocopy failed copying '{source}' -> '{destination}' "
                f"with exit code {exit_code}."
            )

        logger.info(
            "Robocopy completed for %s -> %s (exit code %d, dry_run=%s).",
            source,
            destination,
            exit_code,
            self._dry_run,
        )
        return result