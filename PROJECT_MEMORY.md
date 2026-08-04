# OneDrive PC Sync — Project Memory

**Last updated:** 2026-08-01  
**Branch:** `shutdown-management` (off `master`)  
**Language:** Python 3.14+ (type-annotated, dataclasses, pathlib)  
**Target OS:** Windows 10/11 (uses PowerShell toast notifications, Windows file locking, `pywin32` for shutdown monitor)

---

## 📋 Project Overview

**OneDrive PC Sync** is a safety-first, Windows-only utility that synchronizes game save folders (and other per-app data) between a local PC and a user's OneDrive folder. It is designed to run **automatically via Windows Scheduled Tasks** at three trigger points:

| Trigger | Mode | Direction | Purpose |
|---------|------|-----------|---------|
| **Logon** (2-min delay) | `startup` | **Download** (OneDrive → Local) | Restore latest saves after PC boots |
| **Workstation Lock** (Win+L) | `shutdown` | **Upload** (Local → OneDrive) | Backup saves when stepping away |
| **Periodic** (every 15 min) | `shutdown` | **Upload** (Local → OneDrive) | Safety net for shutdown/restart without locking |

**Core philosophy:** *Never silently lose data.* Every sync is guarded by multiple safety rails.

---

## 🏗️ Architecture (src/)

```
src/
├── __init__.py
├── config.py              # Typed, frozen dataclasses = config *shape* only
├── config_manager.py      # Loads config.json, expands env vars, validates → AppConfig
├── exceptions.py          # Typed exception hierarchy (ConfigurationError, PathValidationError, ...)
├── logger.py              # Centralized logging (rotating file + console)
├── utils.py               # Path safety (dangerous roots, OneDrive check), file counting, %VAR% expansion
├── robocopy_manager.py    # Pure-Python copy engine: safe, non-destructive, in-process file copy
├── backup_manager.py      # Pre-upload zip backups inside OneDrive (timestamped, retention-pruned)
├── sync_manager.py        # Orchestrates: validate → safety threshold → (backup?) → copy engine → verify
├── single_instance.py     # OS-level file lock: prevents concurrent runs from different scheduled tasks
├── notifications.py       # Best-effort Windows toast notifications (PowerShell + WinRT)
├── shutdown_monitor.py    # Resident monitor that waits for Windows session-ending
│                           # notifications (WM_QUERYENDSESSION / WM_ENDSESSION)
│                           # via a hidden top-level window (NULL parent) and triggers
│                           # an upload sync on shutdown, restart, or logoff.
│                           # FIXED: Previously used HWND_MESSAGE (message-only window)
│                           # which does NOT receive WM_QUERYENDSESSION broadcast messages.
│                           # Now uses NULL parent (hidden top-level window) instead.
│                           # See shutdown_diagnosis.md for full analysis and resolution.
└── main.py                # (not yet present — entry point called via PowerShell wrapper)
```

**Key design boundaries:**
- **config.py** — *pure data shapes*, no I/O, no validation logic
- **config_manager.py** — *only* place that touches raw JSON/env vars
- **sync_manager.py** — *owns all safety decisions* (the copy engine is a "dumb execution layer")
- **robocopy_manager.py** — *never* makes safety decisions; the Python copy engine is additive and non-destructive by design (no destructive flags possible)
- **backup_manager.py** — creates timestamped ZIP backups *inside OneDrive only*, prunes by retention days
- **single_instance.py** — cross-task mutex using Windows file locking (msvcrt)

---

## ⚙️ Configuration (config.json)

```json
{
  "general": {
    "log_level": "INFO",
    "dry_run": false,
    "verify_after_sync": true,
    "create_destination": true,
    "max_parallel_jobs": 1
  },
  "sync": {
    "startup": { "enabled": true, "direction": "download" },
    "shutdown": { "enabled": true, "direction": "upload" }
  },
  "copy_engine": {
    "retry_count": 2,
    "retry_wait_seconds": 2,
    "multithreading": 16,
    "copy_subdirectories": true,
    "copy_empty_directories": true,
    "exclude_junctions": true,
    "fat_file_times": true,
    "monitor_mode": false
  },
  "folders": [
    {
      "id": "elden_ring",
      "name": "Elden Ring Save",
      "enabled": true,
      "local_path": "%APPDATA%\\EldenRing",
      "onedrive_path": "%OneDrive%\\PCSync\\AppData\\Roaming\\EldenRing",
      "minimum_sync_percentage": 80,
      "verify_after_sync": true,
      "create_destination": true,
      "backup": {
        "enabled": true,
        "backup_path": "%OneDrive%\\PCSync\\Backups",
        "retention_days": 7
      }
    }
  ]
}
```

**Environment variables expanded:** `%APPDATA%`, `%USERPROFILE%`, `%OneDrive%`, `%LOCALAPPDATA%`, etc. (Windows `%VAR%` + POSIX `$VAR` both supported)

---

## 🛡️ Safety Architecture (The "Why")

### 1. **Dangerous Root Path Rejection** (`utils.is_dangerous_root_path`)
Rejects bare roots that would sync entire AppData, User profile, or drive roots:
- `AppData`, `AppData\Local`, `AppData\Roaming`, `AppData\LocalLow`
- Drive roots: `C:\`, `C:`
- User profile root: `C:\Users\<name>`

Only *explicit subfolders* (e.g., `AppData\Roaming\EldenRing`) are allowed.

### 2. **File-Count Safety Threshold** (`sync_manager._enforce_safety_threshold`)
Before any copy, compares file counts:
```
ratio = min(source_count, dest_count) / max(source_count, dest_count) * 100
```
If `ratio < minimum_sync_percentage` (default 80%), **sync is aborted**.  
*Exception:* first-time sync (destination empty) always allowed.

### 3. **Non-Destructive Copy Semantics** (`robocopy_manager.CopyEngine`)
The Python copy engine is additive and conservative by design — no destructive flags are possible because there are no flags at all. Safety is enforced by design:
- **XO semantics** — never overwrite a newer destination file with an older source file
- **Junction/symlink skipping** — avoids infinite loops and dangerous following
- **Additive-only** — never deletes source or destination files
- **No mirroring or purging** — destination files not in source are left untouched

### 4. **Pre-Upload Backups** (`backup_manager.py`)
- **Only before UPLOAD** (local → OneDrive), never before DOWNLOAD
- Backup = ZIP of current OneDrive destination, stored *inside* OneDrive at `backup_path/<folder_id>/<folder_id>_<timestamp>.zip`
- `backup_path` **must resolve under `%OneDrive%`** (enforced at config load)
- Retention: `retention_days` (default 7), pruned after each successful backup
- Backup failure = **fatal for that folder's upload** (never proceed unprotected)

### 5. **Post-Sync Verification** (`sync_manager._verify_after_sync`)
After robocopy succeeds: `destination_file_count >= source_file_count` (since sync is additive via `/XO`). Failure raises `VerificationError`.

### 6. **Single-Instance Lock** (`single_instance.py`)
OS-level exclusive file lock (`msvcrt.locking`) at a known path. Prevents:
- Startup download + periodic upload running simultaneously
- Lock-triggered upload + periodic upload overlapping
If lock unavailable → **skip this run silently** (not an error).

---

## 🔄 Sync Flow (SyncManager)

```
run_startup_sync() / run_shutdown_sync()
    │
    ├─► Check trigger.enabled → skip if false
    │
    └─► For each enabled folder (independent, errors don't cascade):
            │
            ├─► _resolve_source_and_destination(folder, direction)
            │       DOWNLOAD: onedrive_path → local_path
            │       UPLOAD:   local_path → onedrive_path
            │
            ├─► _validate_paths()
            │       - source exists & is dir
            │       - dest exists or can be created
            │       - source != dest
            │       - neither is dangerous root
            │
            ├─► _enforce_safety_threshold()
            │       - count files both sides
            │       - if dest empty → first-time sync, allow
            │       - else ratio >= threshold? → proceed else ABORT
            │
            ├─► [UPLOAD only] backup_manager.create_backup() + prune_old_backups()
            │
            ├─► robocopy_manager.run(source, dest, mode)
            │       - runs the pure-Python copy engine (no child process)
            │       - walks source tree, copies files with XO semantics
            │       - skips junctions/symlinks, creates empty dirs
            │       - preserves metadata via shutil.copy2
            │       - tolerates up to 5 individual file errors
            │
            ├─► [if verify_after_sync] _verify_after_sync()
            │
            └─► Record FolderSyncOutcome (success/fail + message)
```

---

## 📦 Backup System Details

**Config (per-folder, optional):**
```json
"backup": {
  "enabled": true,
  "backup_path": "%OneDrive%\\PCSync\\Backups",
  "retention_days": 7
}
```

**Archive naming:** `<folder_id>_<YYYYMMDD_HHMMSS>.zip`  
**Location:** `<backup_path>/<folder_id>/<archive>.zip`  
**Contents:** Full recursive copy of OneDrive destination *before* upload overwrites it.

**Pruning:** Runs after each successful backup creation. Deletes archives older than `retention_days` (mtime-based). Prune failures are **non-fatal** (logged warning only).

---

## 🔔 Notifications (Best-Effort)

`notifications.show_windows_toast(title, message)` — uses PowerShell + WinRT Toast API.  
- No-op on non-Windows
- Never raises; failures logged at WARNING and swallowed
- Uses PowerShell's well-known AUMID so no custom registration needed

---

## 🧪 Testing

```
tests/
├── test_config.py      # Config loading, env expansion, dangerous path rejection
├── test_sync.py        # Safety threshold, first-time sync, verification, disabled folders
├── test_backup.py      # Config validation (OneDrive-only), archive creation, pruning, E2E wiring
└── test_copy_engine.py  # Python copy engine: safe copy, XO semantics, error handling, verification
```

Run: `pytest tests/ -v` (from project root, with `.venv` activated)

Key test patterns:
- `tmp_path` fixture for isolated temp dirs
- `monkeypatch` for env vars (`%OneDrive%`, `%APPDATA%`)
- `monkeypatch.setattr(CopyEngine, "run", fake_run)` for E2E tests without real copy engine

---

## 📋 Scheduled Task Setup (Setup-ScheduledTasks.ps1)

**Run once (Run with PowerShell):**
```powershell
powershell -ExecutionPolicy Bypass -File .\Setup-ScheduledTasks.ps1
```

**Creates 3 tasks in `Task Scheduler Library\OneDrivePCSync`:**
1. **Startup (Download)** — Logon trigger, 2-min delay
2. **Shutdown (Upload on Lock)** — Session State Change → Lock
3. **Periodic Upload** — Time trigger, repeat every 15 min indefinitely

**Idempotent:** Re-running replaces existing tasks (safe for updates/moves).

**Uninstall:**
```powershell
powershell -ExecutionPolicy Bypass -File .\Setup-ScheduledTasks.ps1 -Uninstall
```

**Hidden-window wrapper:** `RunHidden.vbs` (auto-generated) → launches `wscript.exe` → Python executable → Python script — avoids console flash even with `pythonw.exe`. Used by both `main.py` (scheduled tasks) and `shutdown_monitor.py`.

## 📋 Desktop Heap Setup (Setup-DesktopHeap.ps1)

**Run once (as Administrator):**
```powershell
powershell -ExecutionPolicy Bypass -File .\Setup-DesktopHeap.ps1
```

**What it does:** Increases the non-interactive desktop heap size in the Windows registry from the default 768 KB to 12288 KB. This resolves `STATUS_DLL_INIT_FAILED` (0xC0000142) errors when spawning `robocopy.exe` from a background process (e.g., a Scheduled Task with no visible desktop) during system shutdown.

**Why it's needed:** Background processes create child processes on a non-interactive desktop with a much smaller heap budget. During shutdown, when many processes are closing simultaneously, that heap can be exhausted, causing robocopy to fail even though the same command works fine interactively.

**Requires a reboot** to take effect. The script backs up the original value to `desktop_heap_original_value.txt` and supports `-Revert` to restore it.

**Idempotent:** Re-running the script reports success if the heap is already set to 12288 KB.

---

## 🚀 Entry Points

### Shutdown monitor (`src/shutdown_monitor.py`) — implemented
Runs as a resident background process at user logon (via Scheduled Task,
`Setup-ShutdownMonitor.ps1`). Uses a hidden message-only window and a
Windows message loop to receive `WM_QUERYENDSESSION` / `WM_ENDSESSION`
notifications. When the session is ending, it runs `run_sync(mode="shutdown")`.

### Main sync script (`src/main.py`) — not yet created
**
```python
from pathlib import Path
from src.config_manager import ConfigManager
from src.logger import setup_logger
from src.sync_manager import SyncManager
from src.single_instance import acquire_single_instance_lock
from src.notifications import show_windows_toast
import sys
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["startup", "shutdown"], required=True)
    args = parser.parse_args()

    project_root = Path(__file__).parent
    config_path = project_root / "config.json"
    log_dir = project_root / "logs"

    # 1. Single-instance lock
    lock_file = project_root / ".sync.lock"
    lock_handle = acquire_single_instance_lock(lock_file)
    if lock_handle is None:
        print("Another sync is already running. Exiting.")
        return 0

    # 2. Logger
    setup_logger(log_dir, "INFO")  # level from config later
    logger = get_logger(__name__)

    # 3. Load config
    config = ConfigManager(config_path).load()

    # 4. Reconfigure log level from config
    setup_logger(log_dir, config.general.log_level.value)

    # 5. Run sync
    manager = SyncManager(config)
    if args.mode == "startup":
        outcomes = manager.run_startup_sync()
    else:
        outcomes = manager.run_shutdown_sync()

    # 6. Summary notification
    failed = [o for o in outcomes if not o.succeeded]
    if failed:
        show_windows_toast("OneDrive PC Sync — Issues", f"{len(failed)} folder(s) failed to sync. Check logs.")
        return 1
    else:
        show_windows_toast("OneDrive PC Sync", "Sync completed successfully.")
        return 0

if __name__ == "__main__":
    sys.exit(main())
```

---

## 📝 Recent Changes (from git log)

| Commit | Date | Summary |
|--------|------|---------|
| `e3a1b42` (HEAD) | 2026-07-29 | Replaced broken `SetConsoleCtrlHandler`/`CTRL_SHUTDOWN_EVENT` approach in `shutdown_monitor.py` with a hidden message-only window + Windows message loop handling `WM_QUERYENDSESSION` / `WM_ENDSESSION` (the Windows-recommended architecture for interactive apps); added `pywin32` dependency |
| `2aa2931` | 2026-07-31 | **Fix applied:** Replaced `HWND_MESSAGE` with `NULL` (0) as window parent in `shutdown_monitor.py` so the hidden top-level window receives `WM_QUERYENDSESSION`/`WM_ENDSESSION` broadcast messages. Improved logging (PID, startup method, handler initialized, sync start/complete/fail, monitor exit). Added `try/except` around monitor run. Updated `shutdown_diagnosis.md` — marked as resolved. |
| 2026-08-01 | **Fix applied:** Fixed `SystemError: new style getargs format but argument is not a tuple` in `shutdown_monitor.py`. Root cause: `win32gui.GetMessage()` returns a tuple `(rc, msg)`, not just the `msg` object. The code was assigning the entire tuple to `msg` and passing it to `TranslateMessage(msg)`, which expects only the `MSG` structure. Fixed by unpacking the tuple correctly: `rc, msg = win32gui.GetMessage(None, 0, 0)` and checking `rc != 0` for WM_QUIT. |
| 2026-08-02 | **Fix applied:** `Setup-DesktopHeap.ps1` — fixed 3 references to `Fix-DesktopHeap.ps1` → `Setup-DesktopHeap.ps1` in help text; added idempotency check (already set to 12288 KB → reports success, exits 0); documented in PROJECT_MEMORY.md and shutdown_diagnosis.md. |
| 2026-08-03 | **Fix applied:** `robocopy_manager.py` — added in-process Python copy fallback (`copy_files_in_process`) that activates when `robocopy.exe` fails to start after retries (e.g. `STATUS_DLL_INIT_FAILED` / `0xC0000142` during shutdown). This makes shutdown upload reliable even when the OS cannot spawn child processes during session teardown. Also added `mode` parameter to `run()` for better launch logging, and enhanced logging with working directory, parent PID, and detailed launch diagnostics. Updated `sync_manager.py` to track and pass sync mode. |
| `595fd32` | 2026-07-24 | Added backups management + notification when startup download finishes |
| `deea75a` | 2026-07-24 | Added single-instance tasks (prevent overlap) |
| `0624a76` | 2026-07-24 | Added 2-minute delay on PC startup |
| `a5c7eda` | 2026-07-24 | Fixed focus-stealing issue with fullscreen apps |
| `4580fec` | 2026-07-24 | Changed PowerShell script to wrap Python run |

---

## 🔑 Key Files to Remember

| File | Purpose |
|------|---------|
| `src/config.py` | **Source of truth for config shape** — add fields here first |
| `src/config_manager.py` | Validation & env expansion — add checks here |
| `src/sync_manager.py` | **All safety logic lives here** — audit this for correctness |
| `src/robocopy_manager.py` | Command building + exit code interpretation + in-process Python copy fallback — never add destructive flags |
| `src/backup_manager.py` | Backup creation/pruning — OneDrive-only enforcement |
| `src/utils.py` | `is_dangerous_root_path`, `is_under_onedrive_root` — security-critical |
| `src/exceptions.py` | Typed exceptions — catch specific types in sync_manager |
| `src/shutdown_monitor.py` | Resident monitor that receives WM_QUERYENDSESSION / WM_ENDSESSION via a hidden window and triggers shutdown sync |
| `Setup-ScheduledTasks.ps1` | Task registration — run after moving project or changing Python |
| `Setup-DesktopHeap.ps1` | Increases non-interactive desktop heap (768 → 12288 KB) in registry to fix STATUS_DLL_INIT_FAILED when robocopy runs from a background process during shutdown |
| `Setup-ShutdownMonitor.ps1` | Registers the shutdown monitor as a Scheduled Task (logon trigger) |
| `config.json` | User-editable config — env vars expanded at load time |

---

## ⚠️ Gotchas & Invariants

1. **Never add `/MIR`, `/PURGE`, `/MOV`, `/MOVE` to robocopy command** — `_assert_command_is_safe` will raise.
2. **Backup path MUST be under `%OneDrive%`** — `is_under_onedrive_root()` returns `False` if `%OneDrive%` unset or path outside → config load fails.
3. **Single-instance lock is per-machine, not per-task** — prevents *any* two sync runs overlapping.
4. **Exit code interpretation:** robocopy bits 8 (copy errors) and 16 (fatal) = failure. Bits 0-7 = success variants.
5. **`/XO` is mandatory** — ensures newer destination files are never overwritten by older source files (critical for bidirectional safety).
6. **Dry-run uses robocopy `/L`** — no files touched, but command still logged.
7. **First-time sync (empty dest) bypasses threshold** — by design, since there's nothing to lose.
8. **Notifications are best-effort** — never fail the sync if toast fails.
9. **Message-only windows (`HWND_MESSAGE`) do NOT receive `WM_QUERYENDSESSION` / `WM_ENDSESSION`** — broadcast shutdown messages are sent only to top-level windows. Use `NULL` (0) as the window parent for hidden windows that need to receive session-ending notifications. This was fixed in `shutdown_monitor.py` — the monitor now uses a hidden top-level window (`NULL` parent) instead of a message-only window.

---

## 🧭 Future Work / TODOs

- [ ] Create `src/main.py` entry point (see skeleton above)
- [ ] Add `--dry-run` CLI flag to override config
- [ ] Add `--folder <id>` CLI flag to sync single folder
- [ ] Consider adding a "manual" mode for on-demand sync
- [ ] Add unit tests for `notifications.py` and `single_instance.py`
- [ ] Document log rotation location (`logs/onedrive_pcsync.log*`)
- [ ] Consider adding a "verify only" mode (no copy, just compare counts)

---

## 📚 Related Memories

- [[project-structure]] — High-level module map
- [[config-schema]] — Detailed config.json schema reference
- [[safety-invariants]] — The non-negotiable safety rules
- [[scheduled-tasks]] — Task Scheduler setup details