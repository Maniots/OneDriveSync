# Shutdown Monitor Investigation — Root Cause Diagnosis

**Date:** 2026-07-31  
**Investigator:** Claude Code  
**Branch:** `shutdown-management`  
**Status:** ✅ RESOLVED — two fixes implemented in `src/shutdown_monitor.py`

---

## 1. Summary

The shutdown monitor never received the Windows session-ending notification because it created a **message-only window** (`HWND_MESSAGE` / `-3`) as the parent for its hidden window. Message-only windows are **not top-level windows** and are **excluded from the `WM_QUERYENDSESSION` / `WM_ENDSESSION` broadcast chain**. Windows sends these shutdown messages only to top-level windows, so the monitor's window proc was never invoked.

**Fix applied:** Replaced `HWND_MESSAGE` (`-3`) with `NULL` (`0`) as the `hWndParent` parameter in `CreateWindowEx`. This creates a hidden top-level window that participates in the broadcast message chain and receives `WM_QUERYENDSESSION` / `WM_ENDSESSION`.

---

## 2. Where the Failure Occurs

The failure occurs at the **Windows message delivery layer**, specifically in how `WM_QUERYENDSESSION` is routed to windows in the session.

| Step | What Happens | Status |
|------|-------------|--------|
| Monitor process starts | Scheduled Task launches `wscript.exe` → `RunHidden.vbs` → `pythonw.exe` → `shutdown_monitor.py` | Working |
| Hidden window created | `CreateWindowEx` with `HWND_MESSAGE` parent creates a message-only window | Working |
| Message loop started | `win32gui.GetMessage()` blocks, waiting for messages | Working |
| Windows begins shutdown | Windows broadcasts `WM_QUERYENDSESSION` to all top-level windows | **FAILING** |
| Message-only window receives `WM_QUERYENDSESSION` | Message-only windows are NOT top-level windows → message is never delivered | **ROOT CAUSE** |
| `_window_proc` is called | Never happens — no message is received | Never reached |
| `run_sync(mode="shutdown")` is called | Never happens | Never reached |

---

## 3. Why the Shutdown Callback Is Never Executed

### 3.1 Message-only windows are invisible to broadcast shutdown messages

Per Microsoft documentation and confirmed by the StackOverflow analysis:

- `WM_QUERYENDSESSION` is sent to **all top-level windows** in the session via `HWND_BROADCAST`.
- Message-only windows (parent = `HWND_MESSAGE` / `-3`) are **not top-level windows**. They are child windows of a system-managed invisible parent.
- `HWND_BROADCAST` sends to top-level windows, overlay windows, popup windows, and message-only windows — **but only for certain message types**. `WM_QUERYENDSESSION` is sent via `SendMessageTimeout` to `HWND_BROADCAST`, and the routing excludes message-only windows.

### 3.2 The `HWND_MESSAGE` constant is the problem

In `shutdown_monitor.py:148`:
```python
HWND_MESSAGE = -3
...
self._hwnd = win32gui.CreateWindowEx(
    0,
    self._wc_atom,
    "OneDrivePCSync Shutdown Monitor",
    win32con.WS_OVERLAPPED,
    0, 0, 0, 0,
    HWND_MESSAGE,   # <-- THIS IS THE BUG
    0,
    win32api.GetModuleHandle(None),
    None,
)
```

Using `HWND_MESSAGE` as the parent creates a message-only window that cannot receive `WM_QUERYENDSESSION` / `WM_ENDSESSION`.

### 3.3 The old code (SetConsoleCtrlHandler) worked — for a different reason

The previous implementation used `SetConsoleCtrlHandler` with `CTRL_SHUTDOWN_EVENT`. The commit message claimed this was "broken" because:
- `CTRL_SHUTDOWN_EVENT` is documented as only deliverable to services
- Loading `user32.dll` disables the handler for `CTRL_SHUTDOWN_EVENT`

However, the logs from July 27 show the old code **did work** — "Shutdown event received" appears 3 times on that date. The old code allocated a console with `AllocConsole()` and hid it with `ShowWindow()`, which gave the process a console handle that `SetConsoleCtrlHandler` could register with. The `user32.dll` loading issue is real but may not have prevented `CTRL_SHUTDOWN_EVENT` delivery in all cases (the exact interaction is version-dependent).

Regardless, the old approach was fragile and the replacement was intended to be more robust. The replacement introduced a different, more fundamental bug.

---

## 4. Whether the Issue Is Caused by the Launcher, Windows, or the Implementation

**The issue is caused by the implementation** (the choice of `HWND_MESSAGE` as the window parent).

| Factor | Verdict |
|--------|---------|
| **Launcher** (`wscript.exe` → `RunHidden.vbs`) | Not the cause. The process is correctly launched in the user's interactive session and has a proper message queue. |
| **Windows** | Not the cause. Windows correctly broadcasts `WM_QUERYENDSESSION` to all eligible windows. The message-only window is simply not eligible. |
| **Implementation** (`HWND_MESSAGE` parent) | **This is the root cause.** Message-only windows do not receive `WM_QUERYENDSESSION` / `WM_ENDSESSION`. |
| **Scheduled Task configuration** | Not the cause. The task runs in the user's interactive session with `TASK_LOGON_INTERACTIVE_TOKEN`. |
| **`pythonw.exe` vs `python.exe`** | Not the cause. Both can create message-only windows. The issue is the window parent, not the process type. |

---

## 5. Recommended Solution

**Replace `HWND_MESSAGE` with `NULL` (0) as the parent window in `CreateWindowEx`.**

This creates a hidden top-level window (not visible, no taskbar entry) that participates in the broadcast message chain and receives `WM_QUERYENDSESSION` / `WM_ENDSESSION`.

### Change in `src/shutdown_monitor.py`

```python
# BEFORE (broken):
HWND_MESSAGE = -3
...
self._hwnd = win32gui.CreateWindowEx(
    0,
    self._wc_atom,
    "OneDrivePCSync Shutdown Monitor",
    win32con.WS_OVERLAPPED,
    0, 0, 0, 0,
    HWND_MESSAGE,   # ← message-only window, does NOT receive WM_QUERYENDSESSION
    0,
    win32api.GetModuleHandle(None),
    None,
)

# AFTER (fixed):
# Use NULL (0) as parent to create a hidden top-level window that
# participates in the WM_QUERYENDSESSION / WM_ENDSESSION broadcast chain.
# Message-only windows (HWND_MESSAGE) are excluded from these broadcasts.
...
self._hwnd = win32gui.CreateWindowEx(
    0,
    self._wc_atom,
    "OneDrivePCSync Shutdown Monitor",
    win32con.WS_OVERLAPPED,
    0, 0, 0, 0,
    0,  # ← NULL parent = hidden top-level window, receives broadcast messages
    0,
    win32api.GetModuleHandle(None),
    None,
)
```

### Additional changes needed

1. Remove the `HWND_MESSAGE = -3` constant (no longer used).
2. Update the docstring for `ShutdownMonitorWindow` to reflect that the window is a hidden top-level window, not a message-only window.
3. Add temporary diagnostic logging for the first few seconds after window creation to confirm the window is receiving messages.

### Why this works

A top-level window with `NULL` parent is included in the `HWND_BROADCAST` message chain. When Windows sends `WM_QUERYENDSESSION` to all top-level windows during shutdown, this hidden window will receive it. The window is invisible (no taskbar entry, no visible UI) because it has `WS_OVERLAPPED` style with zero size and no parent to display.

---

## 6. Alternative Approaches

If the hidden top-level window approach is deemed unreliable, these alternatives exist:

### 6.1 Register a `WM_QUERYENDSESSION` handler via `RegisterWindowMessage`
Register a custom window message and broadcast it from a separate mechanism. This is more complex and doesn't solve the fundamental problem.

### 6.2 Use `SetConsoleCtrlHandler` with a proper console
Allocate a hidden console and use `SetConsoleCtrlHandler` as the old code did. This is what the original code attempted, but it's fragile because loading `user32.dll` disables `CTRL_SHUTDOWN_EVENT` delivery.

### 6.3 Use a Windows Service
Run the monitor as a Windows service that receives shutdown notifications via `SERVICE_CONTROL_SHUTDOWN`. This is the most robust approach but adds significant complexity.

### 6.4 Use `RegisterServiceCtrlHandlerEx`
Similar to 6.3 but for applications that register as service-like handlers. Not applicable for interactive user-session applications.

**Recommended:** The hidden top-level window (`NULL` parent) is the simplest, most reliable fix and follows the Windows-recommended architecture for interactive applications.

---

## 7. Evidence

### 7.1 Log evidence (July 27 — old code working)
```
2026-07-27 19:27:11 | INFO | onedrive_pcsync.__main__ | OneDrivePCSync shutdown monitor starting...
2026-07-27 19:27:27 | INFO | onedrive_pcsync.__main__ | Shutdown event received. Running shutdown sync...
2026-07-27 19:27:27 | INFO | onedrive_pcsync.__main__ | Shutdown monitor exiting.
```
The old `SetConsoleCtrlHandler` approach received the shutdown event and ran the sync.

### 7.2 Log evidence (July 31 — new code NOT working)
```
2026-07-31 19:02:28 | INFO | onedrive_pcsync.__main__ | OneDrivePCSync shutdown monitor starting...
2026-07-31 19:02:29 | INFO | onedrive_pcsync.__main__ | Shutdown monitor window created. Waiting for session end events...
```
The new message-only window approach starts and creates the window, but never receives the shutdown event. No "WM_ENDSESSION received" log entry appears.

### 7.3 Microsoft documentation
- `WM_QUERYENDSESSION`: Sent to all top-level windows in the session. Window proc receives the message.
- `HWND_BROADCAST`: Sends to all top-level windows. Message-only windows are excluded from this broadcast for session-ending messages.
- Message-only windows: Not top-level windows; used for receiving messages but excluded from broadcast message chains for session management.

### 7.4 StackOverflow confirmation
The StackOverflow question "Can a message-only window receive WM_QUERYENDSESSION?" confirms that message-only windows (`HWND_MESSAGE`) do NOT receive `WM_QUERYENDSESSION`. The recommended solution is to use a hidden top-level window (`NULL` parent) instead.

---

## 8. Files Involved

| File | Role |
|------|------|
| `src/shutdown_monitor.py` | Contains both fixes — HWND_MESSAGE→NULL parent, and GetMessage tuple unpacking |
| `Setup-ShutdownMonitor.ps1` | Scheduled Task registration — no changes needed |
| `RunHidden.vbs` | Hidden launch wrapper — no changes needed |
| `src/sync_runner.py` | Sync execution — no changes needed |
| `src/single_instance.py` | Singleton lock — no changes needed |

---

## 9. Verification Plan

After applying the fix (changing `HWND_MESSAGE` to `NULL`):

1. Run the shutdown monitor manually to verify it starts and creates the window.
2. Trigger a Windows shutdown and verify the monitor receives `WM_QUERYENDSESSION` / `WM_ENDSESSION`.
3. Check the logs for "WM_ENDSESSION received" and "Shutdown sync completed successfully."
4. Verify the upload sync runs and completes before the process exits.
5. Verify the monitor exits cleanly after handling the shutdown event.

---

## 10. Resolution

### Fix 1: HWND_MESSAGE → NULL parent (2026-07-31)

**What changed:**
- `HWND_MESSAGE` (`-3`) replaced with `NULL` (`0`) as the `hWndParent` parameter in `CreateWindowEx` in `src/shutdown_monitor.py`.
- Removed the now-unused `HWND_MESSAGE` constant.
- Updated the `ShutdownMonitorWindow` docstring to clarify that the window is a hidden top-level window, not a message-only window.
- Added `os` import for PID logging.
- Added comprehensive logging throughout the monitor lifecycle (startup, window class registered, window created, message loop started, WM_QUERYENDSESSION received, WM_ENDSESSION received, sync starting, sync completed, sync failed, monitor exiting).
- Added `try/except` around the entire monitor run in `main()` to prevent silent termination.
- Added PID to all startup and exit log messages for easier debugging.

### Fix 2: GetMessage tuple unpacking (2026-08-01)

**What changed:**
- Fixed the message loop in `ShutdownMonitorWindow.run()` to correctly unpack the `(rc, msg)` tuple returned by `win32gui.GetMessage()`.
- Changed `msg = win32gui.GetMessage(None, 0, 0)` to `rc, msg = win32gui.GetMessage(None, 0, 0)`.
- Changed `while msg != 0` to `while rc != 0` (the tuple was never equal to 0, causing an infinite loop).
- Changed the `GetMessage` call at the bottom of the loop to also unpack the tuple: `rc, msg = win32gui.GetMessage(None, 0, 0)`.
- Updated the docstring for `run()` to document the `(rc, msg)` return value.

**Why the new implementation works:**
- A top-level window with `NULL` parent is included in the `HWND_BROADCAST` message chain.
- When Windows sends `WM_QUERYENDSESSION` to all top-level windows during shutdown, this hidden window receives it.
- The window is invisible (no taskbar entry, no visible UI) because it has `WS_OVERLAPPED` style with zero size and no parent to display.
- The message-only window approach (`HWND_MESSAGE`) was the root cause — message-only windows are excluded from the broadcast chain for session-ending messages.

## 11. Second Fix: `GetMessage` Return Value Tuple Unpacking

**Date:** 2026-08-01  
**Issue:** `SystemError: new style getargs format but argument is not a tuple` at `win32gui.TranslateMessage(msg)`

### Root Cause

`win32gui.GetMessage()` returns a **tuple** `(rc, msg)`, not just the `msg` object:

| Element | Type | Description |
|---------|------|-------------|
| `rc` | `int` | Return code; `0` for `WM_QUIT`, `1` otherwise |
| `msg` | `PyMSG` (tuple-like) | The Windows `MSG` structure to pass to `TranslateMessage`/`DispatchMessage` |

The code was assigning the entire tuple to `msg` and passing it to `TranslateMessage(msg)`, which expects only the `MSG` structure portion. This caused the `SystemError`.

### Fix

Changed the message loop to correctly unpack the tuple:

```python
# BEFORE (broken):
msg = win32gui.GetMessage(None, 0, 0)
while msg != 0:  # Tuple never equals 0 — infinite loop
    win32gui.TranslateMessage(msg)  # Passes tuple, not MSG → SystemError

# AFTER (fixed):
rc, msg = win32gui.GetMessage(None, 0, 0)
while rc != 0:  # 0 means WM_QUIT
    win32gui.TranslateMessage(msg)  # Passes MSG structure correctly
    win32gui.DispatchMessage(msg)
    ...
    rc, msg = win32gui.GetMessage(None, 0, 0)
```

### Why the Error Message Was Misleading

The error `new style getargs format but argument is not a tuple` refers to the fact that `TranslateMessage`'s C implementation uses `PyArg_ParseTuple` to parse its argument, and it expects a tuple (the `MSG` structure). When it received the `(rc, msg)` tuple from `GetMessage`, the outer tuple was not a valid `MSG` structure, causing the error.

### Remaining limitations / Windows-specific constraints:
- Windows gives GUI applications a limited time (default 5 seconds, registry-tunable via `WaitToKillServiceTimeout`) to process `WM_ENDSESSION` before forcefully terminating the process. If the shutdown sync regularly exceeds this window, the process will be terminated mid-sync. This is a Windows-imposed constraint, not a bug in the implementation.
- The monitor must be started via a Scheduled Task with `TASK_LOGON_INTERACTIVE_TOKEN` to run in the user's interactive session. If the task is configured incorrectly (e.g., running in session 0), it won't receive session-ending messages.
- The `RunHidden.vbs` wrapper is still required to prevent console window flashing when launched via Task Scheduler, even when using `pythonw.exe`. This is a known Task Scheduler quirk.

---

## Sources

- [WM_QUERYENDSESSION message — Microsoft Learn](https://learn.microsoft.com/en-us/windows/win32/shutdown/wm-queryendsession)
- [WM_ENDSESSION message — Microsoft Learn](https://learn.microsoft.com/en-us/windows/win32/shutdown/wm-endsession)
- [System Shutdown Messages — Microsoft Learn](https://learn.microsoft.com/en-us/windows/win32/shutdown/system-shutdown-messages)
- [Application Responsiveness — Microsoft Learn](https://learn.microsoft.com/en-us/windows/win32/shutdown/application-responsiveness)
- [Can a message-only window receive WM_QUERYENDSESSION? — StackOverflow](https://stackoverflow.com/questions/21141193/can-a-message-only-window-receive-wm-queryendsession)
- [A brief discussion on how best to respond to the end-session messages — Raymond Chen](https://devblogs.microsoft.com/oldnewthing/20170329-00/?p=95855)
