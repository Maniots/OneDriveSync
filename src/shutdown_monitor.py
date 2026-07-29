"""
shutdown_monitor.py

A resident program that runs at user logon and waits for Windows session-
ending notifications (WM_QUERYENDSESSION / WM_ENDSESSION) sent during
shutdown, restart, or user logoff. When a session-ending notification is
received, it triggers a shutdown-mode sync (upload).

This program uses a singleton lock to ensure only one instance runs per user.
It is intended to be started via a Scheduled Task at logon
(Setup-ShutdownMonitor.ps1).

Dependencies: pywin32 (win32gui, win32con, win32api).
See: https://learn.microsoft.com/en-us/windows/win32/shutdown/application-responsiveness
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root is on sys.path so that `src` can be imported as a package
sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.logger import get_logger, setup_logger
from src.sync_runner import run_sync
from src.single_instance import acquire_single_instance_lock

# Project root is two levels up from this file (src/shutdown_monitor.py -> src -> project root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs"
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.json"
MONITOR_LOCK_PATH = PROJECT_ROOT / "onedrive_pcsync_shutdown_monitor.lock"

# Windows messages for session-ending notifications
WM_QUERYENDSESSION = 0x0011
WM_ENDSESSION = 0x0016

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# pywin32 — imported once at module load.  This module is used exclusively
# on Windows and requires pywin32; if it is missing the monitor exits
# with a clear error from main().
# ---------------------------------------------------------------------------
try:
    import win32gui
    import win32con
    import win32api
except ImportError:
    win32gui = None  # type: ignore[assignment,misc]
    win32con = None  # type: ignore[assignment,misc]
    win32api = None  # type: ignore[assignment,misc]

# Message-only window constant: win32con.HWND_MESSAGE == -3
HWND_MESSAGE = -3


def _setup_logging() -> None:
    """Initialize logging to the default log directory with INFO level."""
    setup_logger(DEFAULT_LOG_DIR, log_level="INFO")


class ShutdownMonitorWindow:
    """Hidden message-only window that receives WM_QUERYENDSESSION /
    WM_ENDSESSION notifications from Windows during shutdown, restart,
    or user logoff.

    The standard Windows-recommended architecture for interactive
    applications that need to be notified when a session is ending
    relies on a hidden window with a Windows message pump, not on
    SetConsoleCtrlHandler (which only works for console applications
    and never delivers CTRL_SHUTDOWN_EVENT to interactive apps — see
    the HandlerRoutine documentation).

    https://learn.microsoft.com/en-us/windows/console/handlerroutine
    https://learn.microsoft.com/en-us/windows/win32/shutdown/application-responsiveness
    """

    def __init__(self) -> None:
        self._hwnd: int | None = None
        self._wc_atom: int | None = None
        self._shutdown_requested = False

    # ------------------------------------------------------------------
    # Window procedure
    # ------------------------------------------------------------------

    def _window_proc(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        if msg == WM_QUERYENDSESSION:
            # Return TRUE to allow the session to end.
            # DefWindowProc also returns TRUE by default; we return it
            # explicitly to make the intent clear.
            return 1

        if msg == WM_ENDSESSION:
            if wparam == 1:
                # Session IS ending (shutdown, restart, or logoff).
                # Do the sync work synchronously so it completes before
                # the system force-terminates the process after its timeout.
                logger.info("WM_ENDSESSION received — session is ending.")
                self._shutdown_requested = True
                try:
                    exit_code = run_sync(
                        mode="shutdown",
                        config_path=DEFAULT_CONFIG_PATH,
                        dry_run=False,
                    )
                    if exit_code == 0:
                        logger.info("Shutdown sync completed successfully.")
                    else:
                        logger.warning(
                            "Shutdown sync completed with issues"
                            " (exit code %s).",
                            exit_code,
                        )
                except Exception as e:  # noqa: BLE001
                    logger.exception("Error during shutdown sync: %s", e)
            # Return 0 — we have processed the message.
            return 0

        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)  # type: ignore[union-attr]

    # ------------------------------------------------------------------
    # Window lifecycle (no-show window + message loop)
    # ------------------------------------------------------------------

    def register_class(self) -> None:
        """Register the hidden window class."""
        wc = win32gui.WNDCLASS()  # type: ignore[union-attr]
        wc.lpfnWndProc = self._window_proc
        wc.lpszClassName = "OneDrivePCSyncShutdownMonitor"
        wc.hInstance = win32api.GetModuleHandle(None)  # type: ignore[union-attr]
        self._wc_atom = win32gui.RegisterClass(wc)  # type: ignore[union-attr]

    def create(self) -> None:
        """Create the hidden message-only window.

        Using HWND_MESSAGE (-3) as the parent creates a message-only
        window that receives messages but is never visible and has no
        taskbar entry.
        """
        self._hwnd = win32gui.CreateWindowEx(  # type: ignore[union-attr]
            0,  # dwExStyle
            self._wc_atom,
            "OneDrivePCSync Shutdown Monitor",
            win32con.WS_OVERLAPPED,  # type: ignore[union-attr]
            0, 0, 0, 0,  # x, y, width, height
            HWND_MESSAGE,
            0,  # hMenu
            win32api.GetModuleHandle(None),  # type: ignore[union-attr]
            None,  # lpParam
        )

    def run(self) -> None:
        """Run the Windows message loop.

        GetMessage blocks efficiently until a message arrives, so the
        process consumes almost no CPU while idle.  The loop exits when
        we call PostQuitMessage(0) after handling a WM_ENDSESSION with
        wParam == TRUE.
        """
        msg = win32gui.GetMessage(None, 0, 0)  # type: ignore[union-attr]
        while msg != 0:  # 0 means WM_QUIT
            win32gui.TranslateMessage(msg)  # type: ignore[union-attr]
            win32gui.DispatchMessage(msg)  # type: ignore[union-attr]
            if self._shutdown_requested:
                # Signal the message loop to exit cleanly.
                win32gui.PostQuitMessage(0)  # type: ignore[union-attr]
                break
            msg = win32gui.GetMessage(None, 0, 0)  # type: ignore[union-attr]

    def destroy(self) -> None:
        """Clean up the hidden window and unregister its class."""
        if self._hwnd is not None:
            win32gui.DestroyWindow(self._hwnd)  # type: ignore[union-attr]
            self._hwnd = None
        if self._wc_atom is not None:
            win32gui.UnregisterClass(  # type: ignore[union-attr]
                self._wc_atom,
                win32api.GetModuleHandle(None),  # type: ignore[union-attr]
            )
            self._wc_atom = None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    _setup_logging()
    logger.info("OneDrivePCSync shutdown monitor starting...")

    lock_handle = acquire_single_instance_lock(MONITOR_LOCK_PATH)
    if lock_handle is None:
        logger.error(
            "Another shutdown monitor instance is already running."
            " Exiting."
        )
        return 1

    if win32gui is None:  # type: ignore[truthy-testing]
        logger.error(
            "pywin32 is required for the shutdown monitor."
            " Install it with: pip install pywin32"
        )
        lock_handle.close()
        return 1

    monitor = ShutdownMonitorWindow()
    try:
        monitor.register_class()
        monitor.create()
        logger.info(
            "Shutdown monitor window created."
            " Waiting for session end events..."
        )
        monitor.run()
    finally:
        monitor.destroy()
        lock_handle.close()
        logger.info("Shutdown monitor exiting.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
