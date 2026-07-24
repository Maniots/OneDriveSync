# OneDrive PC Sync — Project Memory

**Last updated:** 2026-07-24  
**Branch:** `backups-implementation` (off `master`)  
**Language:** Python 3.14+ (type-annotated, dataclasses, pathlib)  
**Target OS:** Windows 10/11 (uses `robocopy`, PowerShell toast notifications, Windows file locking)

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
├── robocopy_manager.py    # Safe robocopy wrapper: builds non-destructive commands, interprets exit codes
├── backup_manager.py      # Pre-upload zip backups inside OneDrive (timestamped, retention-pruned)
├── sync_manager.py        # Orchestrates: validate → safety threshold → (backup?) → robocopy → verify
├── single_instance.py     # OS-level file lock: prevents concurrent runs from different scheduled tasks
├── notifications.py       # Best-effort Windows toast notifications (PowerShell + WinRT)
└── main.py                # (not yet present — entry point called via PowerShell wrapper)
```

**Key design boundaries:**
- **config.py** — *pure data shapes*, no I/O, no validation logic
- **config_manager.py** — *only* place that touches raw JSON/env vars
- **sync_manager.py** — *owns all safety decisions* (robocopy is a "dumb engine")
- **robocopy_manager.py** — *never* makes safety decisions; forbidden flags (`/MIR`, `/PURGE`, `/MOV`, `/MOVE`) are enforced at command-build time
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
  "robocopy": {
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

### 3. **Non-Destructive robocopy Flags Only** (`robocopy_manager.build_command`)
Mandatory safe flags:
- `/XO` — **never overwrite newer destination with older source** (critical for bidirectional safety)
- `/XX` — exclude "extra" files from deletion consideration
- `/E` — copy subdirectories (incl. empty if configured)
- `/XJ` — exclude junctions (avoid symlink loops)
- `/FFT` — tolerant file-time comparison (FAT/NTFS granularity)

**Forbidden flags (hard-coded assertion):** `/MIR`, `/PURGE`, `/MOV`, `/MOVE`

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
            ├─► robocopy_manager.run(source, dest)
            │       - builds safe command
            │       - executes via subprocess (CREATE_NO_WINDOW)
            │       - interprets exit code bitmask (fail if bit 8 or 16 set)
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
└── test_robocopy.py    # Command building, forbidden flag assertion, exit code interpretation
```

Run: `pytest tests/ -v` (from project root, with `.venv` activated)

Key test patterns:
- `tmp_path` fixture for isolated temp dirs
- `monkeypatch` for env vars (`%OneDrive%`, `%APPDATA%`)
- `monkeypatch.setattr(RobocopyManager, "run", fake_run)` for E2E tests without real robocopy

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

**Hidden-window wrapper:** `RunHidden.vbs` (auto-generated) → launches `wscript.exe` → `pythonw.exe main.py --mode <startup|shutdown>` — avoids console flash even with `pythonw.exe`.

---

## 🚀 Entry Point (main.py — to be created)

The PowerShell wrapper calls:
```bash
pythonw.exe main.py --mode startup   # or --mode shutdown
```

**Expected `main.py` skeleton:**
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
| `src/robocopy_manager.py` | Command building + exit code interpretation — never add destructive flags |
| `src/backup_manager.py` | Backup creation/pruning — OneDrive-only enforcement |
| `src/utils.py` | `is_dangerous_root_path`, `is_under_onedrive_root` — security-critical |
| `src/exceptions.py` | Typed exceptions — catch specific types in sync_manager |
| `Setup-ScheduledTasks.ps1` | Task registration — run after moving project or changing Python |
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