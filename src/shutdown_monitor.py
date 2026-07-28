"""
shutdown_monitor.py

A resident program that runs at user logon and waits for a Windows shutdown
signal (CTRL_SHUTDOWN_EVENT). When the signal is received, it triggers a
shutdown-mode sync (upload) using the same logic as the main program.

This program uses a singleton lock to ensure only one instance runs per user.
It is intended to be started via a shortcut in the user's startup folder
(or a scheduled task that runs at logon).

Dependencies: Python standard library only (uses ctypes for console control).
"""
from __future__ import annotations

import sys
import threading
import ctypes
from ctypes import wintypes
from pathlib import Path

# Ensure the project root is on sys.path so that `src` can be imported as a package
sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.logger import get_logger, setup_logger
from src.sync_runner import run_sync
from src.single_instance import acquire_single_instance_lock

# Constants for console control events
CTRL_C_EVENT = 0
CTRL_BREAK_EVENT = 1
CTRL_CLOSE_EVENT = 2
CTRL_LOGOFF_EVENT = 5
CTRL_SHUTDOWN_EVENT = 6

# Define the handler routine type
HandlerRoutine = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

# Project root is two levels up from this file (src/shutdown_monitor.py -> src -> project root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_PATH = Path(__file__).resolve().parent
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs"
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.json"
MONITOR_LOCK_PATH = PROJECT_ROOT / "onedrive_pcsync_shutdown_monitor.lock"

logger = get_logger(__name__)


def _setup_logging() -> None:
    """Initialize logging to the default log directory with INFO level."""
    setup_logger(DEFAULT_LOG_DIR, log_level="INFO")


def _console_handler(ctrl_type: int) -> bool:
    """
    Windows console control handler.
    Returns True if the event was handled, False otherwise.
    """
    if ctrl_type == CTRL_SHUTDOWN_EVENT:
        logger.info("Received CTRL_SHUTDOWN_EVENT (system shutdown).")
        # Trigger the shutdown sync in a way that does not block this thread too long.
        # We set an event and let the main loop handle the sync.
        shutdown_event.set()
        return True
    # For debugging, allow Ctrl+C to exit cleanly.
    if ctrl_type == CTRL_C_EVENT:
        logger.info("Received CTRL_C_EVENT (Ctrl+C). Shutting down monitor.")
        shutdown_event.set()
        return True
    # We do not handle other events (close, logoff, etc.) but return False so
    # the system can perform default handling.
    return False


def main() -> int:
    _setup_logging()
    logger.info("OneDrivePCSync shutdown monitor starting...")

    # Ensure we have a console for SetConsoleCtrlHandler to work.
    # If we are not attached to a console, allocate one and hide it immediately.
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    user32 = ctypes.WinDLL('user32', use_last_error=True)

    # GetConsoleWindow returns HWND of the console window, or NULL if none.
    GetConsoleWindow = kernel32.GetConsoleWindow
    GetConsoleWindow.restype = wintypes.HWND

    # AllocConsole creates a new console.
    AllocConsole = kernel32.AllocConsole
    AllocConsole.restype = wintypes.BOOL

    # ShowWindow to hide the console.
    ShowWindow = user32.ShowWindow
    ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
    ShowWindow.restype = wintypes.BOOL

    SW_HIDE = 0

    console_allocated = False
    if GetConsoleWindow() == 0:
        # We are not attached to a console.
        if not AllocConsole():
            logger.warning("Failed to allocate console.")
        else:
            console_allocated = True
            # Hide the console window immediately.
            hWnd = GetConsoleWindow()
            if hWnd != 0:
                ShowWindow(hWnd, SW_HIDE)

    # Ensure only one instance of this monitor runs.
    lock_handle = acquire_single_instance_lock(MONITOR_LOCK_PATH)
    if lock_handle is None:
        logger.error("Another shutdown monitor instance is already running. Exiting.")
        if console_allocated:
            kernel32.FreeConsole()
        return 1

    # Set up the console control handler.
    handler_ptr = HandlerRoutine(_console_handler)
    if not ctypes.windll.kernel32.SetConsoleCtrlHandler(handler_ptr, True):
        logger.error("Failed to set console control handler.")
        lock_handle.close()
        if console_allocated:
            kernel32.FreeConsole()
        return 1

    # Keep a reference to the handler function to prevent garbage collection.
    global _handler_ptr
    _handler_ptr = handler_ptr

    # Event that will be set when a shutdown (or Ctrl+C) is received.
    global shutdown_event
    shutdown_event = threading.Event()

    try:
        # Wait for the shutdown event (or Ctrl+C during testing).
        while not shutdown_event.wait(timeout=0.5):
            # Just idle; we could do nothing here.
            pass

        # Event is set: perform the shutdown sync.
        logger.info("Shutdown event received. Running shutdown sync...")
        exit_code = run_sync(
            mode="shutdown",
            config_path=DEFAULT_CONFIG_PATH,
            dry_run=False,  # Always perform real sync for shutdown.
        )
        if exit_code == 0:
            logger.info("Shutdown sync completed successfully.")
        else:
            logger.warning("Shutdown sync completed with issues (exit code %s).", exit_code)
    except Exception as e:  # pylint: disable=broad-except
        logger.exception("Unexpected error in shutdown monitor: %s", e)
        return 1
    finally:
        # Clean up: remove the handler.
        ctypes.windll.kernel32.SetConsoleCtrlHandler(handler_ptr, False)
        lock_handle.close()
        if console_allocated:
            kernel32.FreeConsole()
        logger.info("Shutdown monitor exiting.")

    return 0


if __name__ == "__main__":
    sys.exit(main())