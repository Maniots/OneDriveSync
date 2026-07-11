"""
utils.py

Small, dependency-free helper functions shared across the application.

Kept separate from config_manager.py and sync_manager.py so that the
"dangerous path" detection logic (the single most safety-critical piece
of code in this project) lives in exactly one place and is easy to
audit and unit test in isolation.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List

# Matches Windows-style %VAR% references. Applied explicitly (rather than
# relying solely on os.path.expandvars) because Python's expandvars only
# expands %VAR% syntax when actually running on Windows - since this
# application's config format always uses %VAR%, we expand it manually
# so behavior is identical and testable on any platform.
_WINDOWS_VAR_PATTERN = re.compile(r"%([^%]+)%")


def expand_env_vars(raw_path: str) -> str:
    """Expand both %VAR% (Windows) and $VAR/${VAR} (POSIX) style
    environment variable references in a path string.

    Windows config files commonly use %APPDATA% and %OneDrive%. This
    function expands %VAR% references explicitly using os.environ,
    then also runs os.path.expandvars for any $VAR/${VAR} style
    references, so the same config could be tested on non-Windows
    systems if needed.

    Unrecognized/undefined variables are left untouched rather than
    silently collapsed to an empty string, so missing environment
    variables surface as an obviously-broken path (and therefore fail
    path validation loudly) instead of resolving to some unintended
    shallow directory.

    Args:
        raw_path: The raw path string, possibly containing env var refs.

    Returns:
        The path string with all recognized environment variables expanded.
    """

    def _replace(match: "re.Match[str]") -> str:
        var_name = match.group(1)
        return os.environ.get(var_name, match.group(0))

    expanded = _WINDOWS_VAR_PATTERN.sub(_replace, raw_path)
    expanded = os.path.expandvars(expanded)
    expanded = os.path.expanduser(expanded)
    return expanded


def count_files_recursive(root: Path) -> int:
    """Count all regular files under a directory tree, recursively.

    Symlinks/junctions are not followed to avoid inflated or infinite
    counts from directory loops.

    Args:
        root: Root directory to scan. If it does not exist, returns 0.

    Returns:
        Total number of files found.
    """
    if not root.exists() or not root.is_dir():
        return 0

    count = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        count += len(filenames)
    return count


def calculate_sync_percentage(count_a: int, count_b: int) -> float:
    """Calculate the safety ratio between two file counts, as a percentage.

    The ratio is always (smallest / largest) * 100, so it is symmetric
    and always in the range [0, 100].

    Args:
        count_a: File count of the first location.
        count_b: File count of the second location.

    Returns:
        The percentage ratio. Returns 100.0 if both counts are zero
        (nothing to compare, treated as safe / no-op).
    """
    if count_a == 0 and count_b == 0:
        return 100.0

    smallest = min(count_a, count_b)
    largest = max(count_a, count_b)

    if largest == 0:
        return 100.0

    return (smallest / largest) * 100.0


# Path components that, when they constitute the ENTIRE resolved path
# (i.e. the path is exactly this dangerous root, or a direct alias of it),
# must never be used as a sync source or destination. Comparisons are
# case-insensitive since Windows paths are case-insensitive.
_DANGEROUS_ROOT_SUFFIXES: List[str] = [
    "appdata",
    "appdata\\local",
    "appdata\\roaming",
    "appdata\\locallow",
]


def is_dangerous_root_path(path: Path) -> bool:
    """Determine whether a path is a forbidden "dangerous root" folder.

    A path is considered dangerous if, after normalization, it IS one of:
        - .../AppData
        - .../AppData/Local
        - .../AppData/Roaming
        - .../AppData/LocalLow
    or the filesystem root / drive root / user profile root itself.

    This check intentionally does NOT try to be clever about arbitrary
    "too shallow" paths beyond these explicit, known-dangerous roots,
    because false negatives here are far more costly than false
    positives elsewhere in the pipeline (the percentage-threshold check
    provides a second line of defense).

    Args:
        path: The path to check (should already be expanded, but does
            not need to exist).

    Returns:
        True if the path is a forbidden dangerous root, False otherwise.
    """
    normalized = str(path).strip().rstrip("\\/").lower()
    normalized = normalized.replace("/", "\\")

    for dangerous_suffix in _DANGEROUS_ROOT_SUFFIXES:
        if normalized.endswith("\\" + dangerous_suffix) or normalized == dangerous_suffix:
            return True

    # Reject drive roots like "C:\" or "C:"
    if len(normalized) <= 3 and normalized.endswith(":\\") or (
        len(normalized) == 2 and normalized.endswith(":")
    ):
        return True

    # Reject the user profile root itself, e.g. C:\Users\<username>
    parts = [p for p in normalized.split("\\") if p]
    if len(parts) == 2 and parts[0] == "users":
        return True
    if len(parts) == 3 and parts[0].endswith(":") and parts[1] == "users":
        return True

    return False


def format_bytes(num_bytes: int) -> str:
    """Format a byte count as a human-readable string (e.g. '12.3 MB')."""
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} PB"