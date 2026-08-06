"""
main.py

Entry point for OneDrive PC Sync.

Usage:
    python main.py --mode startup
    python main.py --mode shutdown

Typical deployment:
    - Scheduled/registered to run in "startup" mode when the user logs in
      (downloads the latest data from OneDrive to local application folders).
    - Scheduled/registered to run in "shutdown" mode when the user logs off
      or shuts down (uploads local changes back to OneDrive).

    Additionally, a separate shutdown monitor can be installed via
    Setup-ShutdownMonitor.ps1 to run at logon and wait for Windows shutdown
    signals to trigger an upload sync.

Exit codes:
    0 - All enabled folders synchronized successfully (or none were enabled).
    1 - One or more folders failed to synchronize (see logs for detail).
    2 - Fatal error before synchronization could start (bad config, etc.).
"""
from __future__ import annotations

import sys
from pathlib import Path

import argparse

from src.single_instance import acquire_single_instance_lock
from src.sync_runner import run_sync

APP_ROOT = Path(__file__).resolve().parent
LOCK_FILE_PATH = APP_ROOT / "onedrive_pcsync.lock"


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Argument list (typically sys.argv[1:]).

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        prog="OneDrivePCSync",
        description="Safely synchronize selected application data folders with OneDrive.",
    )
    parser.add_argument(
        "--mode",
        choices=["startup", "shutdown"],
        required=True,
        help="Which sync trigger to run: 'startup' (typically download) or "
        "'shutdown' (typically upload).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=APP_ROOT / "config.json",
        help=f"Path to config.json (default: {APP_ROOT / 'config.json'}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Force dry-run mode regardless of the config.json setting "
        "(no files are copied, no directories are created).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Application entry point.

    Args:
        argv: Optional argument list override (used for testing).

    Returns:
        Process exit code.
    """
    args = parse_arguments(argv if argv is not None else sys.argv[1:])

    # Ensure only one sync runs at a time system-wide, regardless of which
    # scheduled task triggered this run. Two tasks (e.g. the delayed startup
    # download and the periodic upload) can legitimately fire close together;
    # without this, they could run robocopy in opposite directions against
    # the same folder concurrently. If another instance already holds the
    # lock, this run exits cleanly (not an error) rather than racing it.
    lock_handle = acquire_single_instance_lock(LOCK_FILE_PATH)
    if lock_handle is None:
        print(
            "Another OneDrivePCSync run is already in progress on this machine "
            "(this can happen when two triggers fire close together - e.g. the "
            "periodic upload and the delayed startup download). Skipping this run.",
            file=sys.stderr,
        )
        return 0

    try:
        return run_sync(
            mode=args.mode,
            config_path=args.config,
            dry_run=args.dry_run,
        )
    finally:
        lock_handle.close()


if __name__ == "__main__":
    sys.exit(main())