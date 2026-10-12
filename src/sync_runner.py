"""
sync_runner.py

Centralized function to run a sync operation (startup or shutdown) given the mode,
config path, and dry-run flag. This is used by both main.py (for command-line
invocation) and the shutdown monitor (for shutdown-triggered sync).

This function does NOT handle singleton locking; callers must ensure only one
sync operation runs at a time if needed.
"""
from __future__ import annotations

import sys
from pathlib import Path

from src.config_manager import ConfigManager
from src.logger import get_logger, setup_logger
from src.notifications import show_windows_toast
from src.sync_manager import SyncManager, FolderSyncOutcome

# Project root is two levels up from this file (since this file lives in src/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.json"
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs"


def _build_notification_summary(outcomes: list[FolderSyncOutcome]) -> str:
    if not outcomes:
        return "No folders were enabled for sync."
    succeeded = sum(1 for o in outcomes if o.succeeded)
    failed = len(outcomes) - succeeded
    if failed == 0:
        return f"{succeeded} folder(s) synced successfully."
    return f"{succeeded} succeeded, {failed} failed - see logs for details."


def _with_dry_run_override(config):
    from dataclasses import replace
    new_general = replace(config.general, dry_run=True)
    return replace(config, general=new_general)


def _exit_code_for_outcomes(outcomes: list[FolderSyncOutcome]) -> int:
    if not outcomes:
        return 0
    if all(outcome.succeeded for outcome in outcomes):
        return 0
    return 1


def run_sync(mode: str, config_path: Path = DEFAULT_CONFIG_PATH, dry_run: bool = False) -> int:
    """Run a sync operation in the specified mode.

    Args:
        mode: Either "startup" or "shutdown".
        config_path: Path to configuration file.
        dry_run: If True, force dry-run mode regardless of config.

    Returns:
        Process exit code (0 for success, 1 for partial failure, 2 for fatal error).
    """
    # Logging must be usable even if configuration loading fails, so we set it up
    # with a safe default level first.
    setup_logger(DEFAULT_LOG_DIR, log_level="INFO")
    logger = get_logger(__name__)

    logger.info("OneDrive PC Sync running (mode=%s, config=%s, dry_run=%s).",
                mode, config_path, dry_run)

    try:
        config_manager = ConfigManager(config_path=config_path)
        config = config_manager.load()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Fatal error while loading configuration.")
        return 2

    # Re-apply the configured log level now that we know it.
    setup_logger(DEFAULT_LOG_DIR, log_level=config.general.log_level.value)
    logger = get_logger(__name__)  # re-get logger to pick up new level

    if dry_run and not config.general.dry_run:
        logger.warning("--dry-run flag supplied: overriding config.json dry_run=false.")
        config = _with_dry_run_override(config)

    try:
        sync_manager = SyncManager(config, history_path=Path(config_path).with_suffix(".history.sqlite3"))

        if mode == "startup":
            outcomes = sync_manager.run_startup_sync()
        elif mode == "shutdown":
            outcomes = sync_manager.run_shutdown_sync()
        else:
            logger.error("Invalid mode specified: %s", mode)
            return 2
    except Exception as exc:  # noqa: BLE001
        logger.exception("Fatal error during synchronization.")
        return 2

    if mode == "startup":
        # Only the download direction gets a notification: it's the one the
        # user is actually waiting on before they start playing/working.
        # Uploads happen silently in the background by design.
        show_windows_toast(
            "OneDrivePCSync - Download complete",
            _build_notification_summary(outcomes),
        )

    return _exit_code_for_outcomes(outcomes)


if __name__ == "__main__":
    # Allow running this module directly for testing, mimicking main.py behavior.
    # In this case, we parse arguments, acquire the singleton lock, and call run_sync.
    import argparse
    from src.single_instance import acquire_single_instance_lock

    def parse_arguments(argv: list[str]) -> argparse.Namespace:
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

    args = parse_arguments(sys.argv[1:])
    lock_handle = acquire_single_instance_lock(PROJECT_ROOT / "onedrive_pcsync.lock")
    if lock_handle is None:
        print("Another OneDrivePCSync run is already in progress. Exiting.", file=sys.stderr)
        sys.exit(1)
    try:
        sys.exit(run_sync(mode=args.mode, config_path=args.config, dry_run=args.dry_run))
    finally:
        lock_handle.close()
