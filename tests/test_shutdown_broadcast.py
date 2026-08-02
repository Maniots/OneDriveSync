"""
test_shutdown_broadcast.py

Standalone diagnostic script — NOT part of the OneDrivePCSync monitor.
Run this manually (python test_shutdown_broadcast.py) before a restart
to get an unambiguous, visible answer to one question: does this PC's
session ending broadcast (WM_QUERYENDSESSION) reach a plain top-level
window at all?

- On WM_QUERYENDSESSION: writes to test_broadcast.log AND pops a
  MessageBox (with MB_SYSTEMMODAL so it stays on top through shutdown
  teardown). If you see the box, the broadcast works — the earlier
  problem is isolated to the monitor process/launch chain. If you
  never see it and never restart is delayed at all, the broadcast is
  not reaching apps on this system.
- On WM_ENDSESSION: also logs.

Run it, then Start -> Power -> Restart, and watch the screen during
the restart countdown/teardown.
"""
import ctypes
import datetime
import os
import sys

import win32gui
import win32con
import win32api

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_broadcast.log")


def log(msg: str) -> None:
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now().isoformat()} PID={os.getpid()} {msg}\n")
        f.flush()
        os.fsync(f.fileno())


def window_proc(hwnd, msg, wparam, lparam):
    if msg == win32con.WM_QUERYENDSESSION:
        log(f"WM_QUERYENDSESSION received wparam={wparam} lparam={lparam}")
        # MB_SYSTEMMODAL + MB_TOPMOST so it's visible even during teardown.
        ctypes.windll.user32.MessageBoxW(
            0,
            "WM_QUERYENDSESSION arrived! The broadcast works.",
            "Shutdown broadcast test",
            0x1000 | 0x40000,  # MB_SYSTEMMODAL | MB_TOPMOST
        )
        return 1
    if msg == win32con.WM_ENDSESSION:
        log(f"WM_ENDSESSION received wparam={wparam}")
        return 0
    return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)


def main():
    log("test script starting")

    try:
        result = ctypes.windll.kernel32.SetProcessShutdownParameters(0x3FF, 0)
        log(f"SetProcessShutdownParameters result={result}")
    except Exception as e:
        log(f"SetProcessShutdownParameters failed: {e!r}")

    wc = win32gui.WNDCLASS()
    wc.lpfnWndProc = window_proc
    wc.lpszClassName = "ShutdownBroadcastTestWindow"
    wc.hInstance = win32api.GetModuleHandle(None)
    atom = win32gui.RegisterClass(wc)
    log(f"class registered atom={atom}")

    hwnd = win32gui.CreateWindow(
        atom,
        "Shutdown Broadcast Test",
        win32con.WS_OVERLAPPEDWINDOW,
        100, 100, 300, 100,
        0, 0,
        win32api.GetModuleHandle(None),
        None,
    )
    # Deliberately VISIBLE this time, unlike the real monitor, to remove
    # any doubt about whether visibility affects broadcast delivery.
    win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
    log(f"visible window created hwnd={hwnd}")

    print(f"Test window created (hwnd={hwnd}). Leave this running and restart the PC.")
    print(f"Watch the screen during restart, and check {LOG_PATH} afterwards.")

    win32gui.PumpMessages()


if __name__ == "__main__":
    main()