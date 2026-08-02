"""
shutdown_monitor.py

A resident program that runs at user logon and waits for Windows session-
ending notifications (WM_QUERYENDSESSION / WM_ENDSESSION) sent during
shutdown, restart, or user logoff. When a session-ending notification is
received, it triggers a shutdown-mode sync (upload).

This program uses a singleton lock to ensure only one instance runs per user.
It is intended to be started via a Scheduled Task at logon
(Setup-ShutdownMonitor.ps1).

The monitor creates a hidden top-level window (parent = NULL) that receives
WM_QUERYENDSESSION / WM_ENDSESSION broadcast messages from Windows during
session shutdown.  A message-only window (HWND_MESSAGE) must NOT be used
for this purpose — message-only windows are excluded from the broadcast
chain for session-ending messages.

WHY THE SYNC RUNS DURING WM_QUERYENDSESSION, NOT WM_ENDSESSION
-----------------------------------------------------------------
The sync (which spawns robocopy.exe as a child process) runs synchronously
inside the WM_QUERYENDSESSION handler, delaying the TRUE response until it
completes — NOT inside WM_ENDSESSION as an earlier version of this file did.

WM_QUERYENDSESSION is Windows *asking permission* to end the session; the
session is still fully alive and normal at that point. WM_ENDSESSION is
sent only after every app has already agreed, and by then Windows may
already be tearing down parts of the session's subsystems in preparation
for the actual teardown. Spawning a brand new child process (robocopy.exe)
that late was found to fail unreliably with STATUS_DLL_INIT_FAILED
(0xc0000142) — a known category of error when CreateProcess is invoked
during session teardown. Doing the work during WM_QUERYENDSESSION instead
avoids this: robocopy is launched while the session is still fully intact.

Delaying the response to WM_QUERYENDSESSION is an explicitly supported,
documented pattern (it's exactly what Notepad does to show its "save
changes?" prompt), as long as ShutdownBlockReasonCreate is used so Windows
shows a "still working" UI instead of treating the process as hung. This
monitor calls ShutdownBlockReasonCreate right after creating the window,
so it is already active by the time WM_QUERYENDSESSION can arrive.

PROCESS SHUTDOWN PRIORITY
-----------------------------------------------------------------
main() also calls SetProcessShutdownParameters to raise this process's
shutdown priority. Windows queries top-level windows for
WM_QUERYENDSESSION in priority order (not all at once), and a background
helper process started via Scheduled Task uses the default priority,
which risks never being queried at all before the overall "closing
applications" screen's time budget runs out. Raising the priority makes
Windows query this process near the front of the line.

EMERGENCY / CRASH LOGGING
--------------------------
This process runs under pythonw.exe (no console, no stderr), so any
exception raised before the normal logging module is initialized — or
any exception that occurs during shutdown while the process may be
forcefully terminated at any moment — would otherwise leave zero trace.
`_emergency_log()` writes directly to a plain text file with no
dependency on the logging module's handlers/buffers, so it survives
even if normal logging fails or hasn't been set up yet.

Dependencies: pywin32 (win32gui, win32con, win32api).
See: https://learn.microsoft.com/en-us/windows/win32/shutdown/application-responsiveness
"""
from __future__ import annotations

import datetime
import os
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
CRASH_LOG_PATH = DEFAULT_LOG_DIR / "shutdown_monitor_crash.log"

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


def _setup_logging() -> None:
    """Initialize logging to the default log directory with INFO level."""
    setup_logger(DEFAULT_LOG_DIR, log_level="INFO")


def _emergency_log(message: str) -> None:
    """Fallback crash logger that does not depend on the logging module
    being initialized or working correctly. pythonw.exe has no
    console/stderr, so without this an early or late crash (e.g. during
    the few seconds Windows allows before force-terminating the process
    at shutdown) leaves zero trace anywhere.

    Deliberately uses plain open()/write() with no buffering handler in
    between, so the line is on disk immediately, not sitting in a
    logging.Handler buffer that may never get flushed if the process is
    killed a moment later.
    """
    try:
        DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CRASH_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now().isoformat()} PID={os.getpid()} {message}\n")
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        pass  # last resort: nothing more we can do


class ShutdownMonitorWindow:
    """Hidden top-level window that receives WM_QUERYENDSESSION /
    WM_ENDSESSION notifications from Windows during shutdown, restart,
    or user logoff.

    The window is created with a NULL parent (not HWND_MESSAGE) so that
    it participates in the broadcast message chain for session-ending
    notifications.  Message-only windows (HWND_MESSAGE) are excluded
    from this chain and must not be used for this purpose.

    The standard Windows-recommended architecture for interactive
    applications that need to be notified when a session is ending
    relies on a hidden window with a Windows message pump, not on
    SetConsoleCtrlHandler (which only works for console applications
    and never delivers CTRL_SHUTDOWN_EVENT to interactive apps — see
    the HandlerRoutine documentation).

    https://learn.microsoft.com/en-us/windows/win32/shutdown/application-responsiveness
    https://learn.microsoft.com/en-us/windows/win32/shutdown/wm-queryendsession
    """

    def __init__(self) -> None:
        self._hwnd: int | None = None
        self._wc_atom: int | None = None
        self._shutdown_requested = False
        self._sync_done = False

    # ------------------------------------------------------------------
    # Window procedure
    # ------------------------------------------------------------------

    def _window_proc(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        # Emergency log FIRST, before any other logic, for both messages
        # of interest. This is the single most important log line in the
        # whole program: if this line is missing after a shutdown, the
        # broadcast never reached this process at all.
        if msg in (WM_QUERYENDSESSION, WM_ENDSESSION):
            _emergency_log(f"_window_proc received msg={msg:#06x} wparam={wparam} lparam={lparam}")

        if msg == WM_QUERYENDSESSION:
            # IMPORTANT: the sync work happens HERE, synchronously, and
            # NOT in WM_ENDSESSION. By the time WM_ENDSESSION arrives the
            # session has already committed to ending and Windows may
            # already be tearing down parts of the session's subsystems;
            # spawning a brand new child process (robocopy.exe) at that
            # point is unreliable and can fail with STATUS_DLL_INIT_FAILED
            # (0xc0000142). During WM_QUERYENDSESSION the session is
            # still fully alive — Windows is only *asking* whether it's
            # OK to end — so this is the correct, safe place to run
            # robocopy. We delay responding TRUE until the sync is done;
            # ShutdownBlockReasonCreate (set at window creation) tells
            # Windows we're legitimately still working, so it shows a
            # "waiting" UI instead of treating the process as hung.
            if self._sync_done:
                # Windows can re-query in some scenarios (e.g. another
                # app initially blocked shutdown). Don't re-run the sync.
                _emergency_log("WM_QUERYENDSESSION received again — sync already done, allowing.")
                return 1

            _emergency_log("Starting shutdown upload sync (inside WM_QUERYENDSESSION)...")
            try:
                logger.info("WM_QUERYENDSESSION received — starting shutdown upload sync before allowing session end.")
            except Exception:
                pass

            try:
                exit_code = run_sync(
                    mode="shutdown",
                    config_path=DEFAULT_CONFIG_PATH,
                    dry_run=False,
                )
                _emergency_log(f"run_sync returned exit_code={exit_code}")
                try:
                    if exit_code == 0:
                        logger.info("Shutdown sync completed successfully.")
                    else:
                        logger.warning(
                            "Shutdown sync completed with issues (exit code %s).",
                            exit_code,
                        )
                except Exception:
                    pass
            except Exception as e:  # noqa: BLE001
                _emergency_log(f"EXCEPTION during run_sync: {e!r}")
                try:
                    logger.exception("Error during shutdown sync: %s", e)
                except Exception:
                    pass

            self._sync_done = True
            _emergency_log("Sync attempt finished — allowing session to end.")
            # Return TRUE now: sync (successful or not) is done, don't
            # hold up shutdown any further.
            return 1

        if msg == WM_ENDSESSION:
            if wparam == 1:
                _emergency_log("WM_ENDSESSION wparam=1 — session ending (sync already ran during query phase).")
                try:
                    logger.info("WM_ENDSESSION received — session is ending. Sync already completed during query phase.")
                except Exception:
                    pass
                self._shutdown_requested = True
            else:
                _emergency_log("WM_ENDSESSION wparam=0 — session end was cancelled.")
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
        logger.info("Hidden window class registered (atom=%s).", self._wc_atom)
        _emergency_log(f"register_class OK atom={self._wc_atom}")

    def create(self) -> None:
        """Create the hidden top-level window.

        Using NULL (0) as the parent creates a hidden top-level window
        that participates in the WM_QUERYENDSESSION / WM_ENDSESSION
        broadcast chain.  The window is invisible (no taskbar entry,
        no visible UI) because it has WS_OVERLAPPED style with zero
        size and no parent to display.

        NOTE: HWND_MESSAGE must NOT be used here — message-only windows
        are excluded from the broadcast chain for session-ending messages.
        """
        self._hwnd = win32gui.CreateWindowEx(  # type: ignore[union-attr]
            0,  # dwExStyle
            self._wc_atom,
            "OneDrivePCSync Shutdown Monitor",
            win32con.WS_OVERLAPPED,  # type: ignore[union-attr]
            0, 0, 0, 0,  # x, y, width, height
            0,  # hWndParent — NULL = hidden top-level window
            0,  # hMenu
            win32api.GetModuleHandle(None),  # type: ignore[union-attr]
            None,  # lpParam
        )
        logger.info(
            "Hidden top-level window created (hwnd=%s)."
            " Waiting for session end events...",
            self._hwnd,
        )
        _emergency_log(f"create OK hwnd={self._hwnd}")

        # Explicitly ask Windows to wait and show a reason in the shutdown
        # UI if this app is still working when the session tries to end.
        # This also makes the process visible to Windows as an app that
        # is actively participating in shutdown, rather than one that can
        # be silently skipped/terminated. Harmless if unsupported.
        try:
            import ctypes
            ctypes.windll.user32.ShutdownBlockReasonCreate(
                self._hwnd, "OneDrivePCSync is uploading your saves"
            )
            _emergency_log("ShutdownBlockReasonCreate OK")
        except Exception as e:  # noqa: BLE001
            _emergency_log(f"ShutdownBlockReasonCreate failed: {e!r}")


    def run(self) -> None:
        """Run the Windows message loop.

        GetMessage blocks efficiently until a message arrives, so the
        process consumes almost no CPU while idle.  The loop exits when
        we call PostQuitMessage(0) after handling a WM_ENDSESSION with
        wParam == TRUE.

        GetMessage returns a tuple (rc, msg) where rc is 0 for WM_QUIT
        and msg is the MSG structure to pass to TranslateMessage/DispatchMessage.
        """
        logger.info("Message loop started — waiting for Windows session events.")
        _emergency_log("message loop started")
        rc, msg = win32gui.GetMessage(None, 0, 0)  # type: ignore[union-attr]
        while rc != 0:  # 0 means WM_QUIT
            win32gui.TranslateMessage(msg)  # type: ignore[union-attr]
            win32gui.DispatchMessage(msg)  # type: ignore[union-attr]
            if self._shutdown_requested:
                # Signal the message loop to exit cleanly.
                logger.info("Shutdown sync complete — posting quit message.")
                _emergency_log("shutdown sync complete, posting quit message")
                win32gui.PostQuitMessage(0)  # type: ignore[union-attr]
                break
            rc, msg = win32gui.GetMessage(None, 0, 0)  # type: ignore[union-attr]
        _emergency_log(f"message loop exited rc={rc}")

    def destroy(self) -> None:
        """Clean up the hidden window and unregister its class."""
        if self._hwnd is not None:
            win32gui.DestroyWindow(self._hwnd)  # type: ignore[union-attr]
            logger.info("Hidden window destroyed (hwnd=%s).", self._hwnd)
            self._hwnd = None
        if self._wc_atom is not None:
            win32gui.UnregisterClass(  # type: ignore[union-attr]
                self._wc_atom,
                win32api.GetModuleHandle(None),  # type: ignore[union-attr]
            )
            logger.info("Window class unregistered (atom=%s).", self._wc_atom)
            self._wc_atom = None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _raise_shutdown_priority() -> None:
    """Ask Windows to notify this process EARLY during session shutdown,
    ahead of normal applications.

    Windows queries top-level windows for WM_QUERYENDSESSION in shutdown
    -priority order, not all at once, and the "Closing applications"
    screen appears to operate on a limited overall time budget rather
    than a per-app-only timeout. A background helper process started via
    Scheduled Task uses the default priority (0x280) and can end up
    queried last, after the budget for the whole screen has already run
    out — meaning it may never receive the message at all. Raising the
    priority towards the high end of the application range (documented
    max for apps below reserved system levels) makes Windows query this
    process near the front of the line instead.
    See: https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setprocessshutdownparameters
    """
    try:
        import ctypes
        # 0x3FF = highest documented level available to applications
        # (0x400+ is reserved for system components). 0 = no special flags.
        result = ctypes.windll.kernel32.SetProcessShutdownParameters(0x3FF, 0)
        if result:
            _emergency_log("SetProcessShutdownParameters OK (priority raised to 0x3FF)")
        else:
            err = ctypes.windll.kernel32.GetLastError()
            _emergency_log(f"SetProcessShutdownParameters returned FALSE, GetLastError={err}")
    except Exception as e:  # noqa: BLE001
        _emergency_log(f"SetProcessShutdownParameters failed: {e!r}")


def main() -> int:
    _emergency_log("main() starting")
    _raise_shutdown_priority()
    try:
        _setup_logging()
    except Exception as e:
        _emergency_log(f"FATAL: _setup_logging() raised: {e!r}")
        return 1

    pid = os.getpid()
    logger.info("OneDrivePCSync shutdown monitor starting (PID=%s).", pid)

    lock_handle = acquire_single_instance_lock(MONITOR_LOCK_PATH)
    if lock_handle is None:
        logger.error(
            "Another shutdown monitor instance is already running."
            " Exiting."
        )
        _emergency_log("another instance already running — exiting")
        return 1
    logger.info("Singleton lock acquired.")
    _emergency_log("singleton lock acquired")

    if win32gui is None:  # type: ignore[truthy-testing]
        logger.error(
            "pywin32 is required for the shutdown monitor."
            " Install it with: pip install pywin32"
        )
        _emergency_log("FATAL: pywin32 not available (win32gui is None)")
        lock_handle.close()
        return 1

    monitor = ShutdownMonitorWindow()
    try:
        monitor.register_class()
        monitor.create()
        logger.info("Shutdown handler initialized — waiting for session end events.")
        _emergency_log("shutdown handler initialized, entering run()")
        monitor.run()
    except Exception as e:  # noqa: BLE001
        logger.exception("Fatal error in shutdown monitor: %s", e)
        _emergency_log(f"FATAL: unhandled exception in main(): {e!r}")
        return 1
    finally:
        monitor.destroy()
        lock_handle.close()
        logger.info("Shutdown monitor exiting (PID=%s).", pid)
        _emergency_log(f"main() exiting, PID={pid}")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        _emergency_log(f"FATAL: uncaught at top level: {e!r}")
        sys.exit(1)