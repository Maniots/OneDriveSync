"""
single_instance.py

Ensures only one OneDrivePCSync sync runs at a time on this machine,
regardless of which Scheduled Task triggered it (startup download,
lock-triggered upload, or periodic upload), using an OS-level exclusive
file lock.

This matters because the scheduled tasks are registered independently and
each only protects itself against re-entrancy (Task Scheduler's "Ignore
New" instance policy is per-task). Nothing stops two DIFFERENT tasks - for
example the delayed startup download and the periodic upload - from firing
close together and running robocopy in opposite directions against the
same folders at the same time, which can cause file-locking errors or an
inconsistent file-count read mid-sync.

The lock is released automatically by the operating system when the
process exits or crashes, so no explicit cleanup call is required beyond
keeping the returned handle open for the process lifetime.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import IO, Optional

_LOCK_BYTE_COUNT = 1


def acquire_single_instance_lock(lock_path: Path) -> Optional[IO]:
    """Attempt to become the only running OneDrivePCSync instance system-wide.

    Args:
        lock_path: Path to a lock file (created if missing). Its content is
            irrelevant - only its OS-level lock state matters.

    Returns:
        An open file handle if the lock was acquired. The caller MUST keep
        a reference to it (not close it) for as long as the lock should be
        held - typically for the remainder of the process's lifetime.
        Returns None if another instance already holds the lock, in which
        case the caller should cleanly skip this run rather than treat it
        as an error.
    """
    if sys.platform != "win32":
        # Locking is a Windows-specific safety net for Scheduled Task
        # overlap. On other platforms (e.g. automated testing) we don't
        # enforce single-instance behavior.
        return open(lock_path, "a")

    import msvcrt  # Windows-only stdlib module, imported lazily.

    lock_path.touch(exist_ok=True)
    file_handle = open(lock_path, "r+")
    try:
        msvcrt.locking(file_handle.fileno(), msvcrt.LK_NBLCK, _LOCK_BYTE_COUNT)
    except OSError:
        file_handle.close()
        return None
    return file_handle