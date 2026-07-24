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

Exit codes:
    0 - All enabled folders synchronized successfully (or none were enabled).
    1 - One or more folders failed to synchronize (see logs for detail).
    2 - Fatal error before synchronization could start (bad config, etc.).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.config_manager import ConfigManager
from src.exceptions import OneDrivePCSyncError
from src.logger import get_logger, setup_logger
from src.notifications import show_windows_toast
from src.single_instance import acquire_single_instance_lock
from src.sync_manager import FolderSyncOutcome, SyncManager

APP_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = APP_ROOT / "config.json"
DEFAULT_LOG_DIR = APP_ROOT / "logs"
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
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to config.json (default: {DEFAULT_CONFIG_PATH}).",
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

    # Logging must be usable even if configuration loading fails, so we
    # set it up with a safe default level first.
    setup_logger(DEFAULT_LOG_DIR, log_level="INFO")
    logger = get_logger(__name__)

    logger.info("OneDrive PC Sync starting (mode=%s, config=%s).", args.mode, args.config)

    # Ensure only one sync runs at a time system-wide, regardless of which
    # scheduled task triggered this run. Two tasks (e.g. the delayed startup
    # download and the periodic upload) can legitimately fire close together;
    # without this, they could run robocopy in opposite directions against
    # the same folder concurrently. If another instance already holds the
    # lock, this run exits cleanly (not an error) rather than racing it.
    lock_handle = acquire_single_instance_lock(LOCK_FILE_PATH)
    if lock_handle is None:
        logger.info(
            "Another OneDrivePCSync run is already in progress on this machine "
            "(this can happen when two triggers fire close together - e.g. the "
            "periodic upload and the delayed startup download). Skipping this run."
        )
        return 0

    try:
        config_manager = ConfigManager(config_path=args.config)
        config = config_manager.load()
    except OneDrivePCSyncError as exc:
        logger.error("Fatal configuration error: %s", exc)
        return 2
    except Exception:  # noqa: BLE001 - last line of defense at the top level
        logger.exception("Unexpected fatal error while loading configuration.")
        return 2

    # Re-apply the configured log level now that we know it.
    setup_logger(DEFAULT_LOG_DIR, log_level=config.general.log_level.value)

    if args.dry_run and not config.general.dry_run:
        logger.warning("--dry-run flag supplied: overriding config.json dry_run=false.")
        config = _with_dry_run_override(config)

    try:
        sync_manager = SyncManager(config)

        if args.mode == "startup":
            outcomes = sync_manager.run_startup_sync()
        else:
            outcomes = sync_manager.run_shutdown_sync()
    except OneDrivePCSyncError as exc:
        logger.error("Fatal error during synchronization: %s", exc)
        return 2
    except Exception:  # noqa: BLE001 - last line of defense at the top level
        logger.exception("Unexpected fatal error during synchronization.")
        return 2
    finally:
        lock_handle.close()

    if args.mode == "startup":
        # Only the download direction gets a notification: it's the one the
        # user is actually waiting on before they start playing/working.
        # Uploads happen silently in the background by design.
        show_windows_toast(
            "OneDrivePCSync - Download complete",
            _build_notification_summary(outcomes),
        )

    return _exit_code_for_outcomes(outcomes)


def _build_notification_summary(outcomes: list[FolderSyncOutcome]) -> str:
    """Build a short, human-readable summary line for the toast notification."""
    if not outcomes:
        return "No folders were enabled for sync."

    succeeded = sum(1 for o in outcomes if o.succeeded)
    failed = len(outcomes) - succeeded

    if failed == 0:
        return f"{succeeded} folder(s) synced successfully."
    return f"{succeeded} succeeded, {failed} failed - check logs for details."


def _with_dry_run_override(config):
    """Return a copy of AppConfig with general.dry_run forced to True.

    Dataclasses used here are frozen, so we rebuild the nested object
    rather than mutating it in place.
    """
    from dataclasses import replace

    new_general = replace(config.general, dry_run=True)
    return replace(config, general=new_general)


def _exit_code_for_outcomes(outcomes: list[FolderSyncOutcome]) -> int:
    if not outcomes:
        return 0
    if all(outcome.succeeded for outcome in outcomes):
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())