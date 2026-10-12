# OneDrive PC Sync

A safety-first Windows application that synchronizes explicitly chosen
application data folders between the local PC and OneDrive - on **startup**
(download from OneDrive) and **shutdown** (upload to OneDrive).

It exists to solve one problem: keeping small, important per-application
data folders (game saves, editor settings, app configs) in sync across
machines via OneDrive, **without** the risk of a full `AppData` mirror
wiping out live application state.

## Why not just sync all of AppData?

`AppData` contains active databases, caches, locked files, and installed
application binaries. Mirroring it (e.g. `robocopy /MIR`) is destructive
and unsafe. This project **only** syncs folders you explicitly list in
`config.json`, and **never** deletes anything - it is strictly additive
(create missing folders, copy missing files, update changed files).

## Project structure

```
OneDrivePCSync/
│
├── README.md
├── requirements.txt
├── .gitignore
│
├── config.json          # User-editable list of folders to sync
│
├── main.py               # Entry point (--mode startup|shutdown)
│
├── src/
│   ├── __init__.py
│   ├── config.py          # Typed configuration dataclasses/enums
│   ├── config_manager.py  # Loads/validates config.json
│   ├── sync_manager.py    # All safety decisions + orchestration
│   ├── robocopy_manager.py# Safe, non-destructive robocopy wrapper
│   ├── logger.py          # Centralized logging setup
│   ├── exceptions.py      # Application exception hierarchy
│   ├── utils.py           # Env var expansion, dangerous-path checks, ratios
│   ├── sync_runner.py     # Centralized sync logic used by main.py and shutdown monitor
│   └── shutdown_monitor.py   # Resident program that catches Windows shutdown events
│
├── logs/                  # Rotating log files (created at runtime)
├── backups/               # Reserved (unused) - see "Automatic pre-upload
│                          #   backups" below; real backups live in OneDrive,
│                          #   never here, by design
├── data/                  # Reserved for local application state/cache
│
└── tests/
    ├── __init__.py
    ├── test_config.py
    ├── test_sync.py
    └── test_robocopy.py
```

## Installation

### Windows EXE (no Python required on the target PC)

Run `dist/installer/OneDrivePCSync-Setup-1.0.0.exe`. It installs the app for
the current Windows user under `%LOCALAPPDATA%\Programs\OneDrivePCSync`,
adds Start menu links and registers an uninstaller. A desktop shortcut and
automatic synchronization are optional installer checkboxes.

User data lives under `%LOCALAPPDATA%\OneDrivePCSync`: `config.json`, sync
history, logs, monitor status and locks. Updates and uninstall preserve that
data. A new installation contains no folders to sync; add them in the UI.
The installer never includes this repository's personal `config.json`.
To migrate an existing setup, close the app and copy its configuration to
that user-data directory, keeping a backup of any configuration already there.

The installed EXE also accepts `--mode startup|shutdown`, `--dry-run` and
`--config PATH`. `--monitor` starts the native background shutdown monitor.
Scheduled tasks invoke the EXE directly without Python or VBS wrappers.
If enabled, their existing names and timing remain the same. They become
active at the next logon (periodic uploads can begin during this session).

### Building the Windows release

Build on Windows x64, using Python 3.12+ and Inno Setup 6.7+:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
powershell -NoProfile -ExecutionPolicy Bypass -File .\Build-Windows.ps1
# Or create only the self-contained application directory:
powershell -NoProfile -ExecutionPolicy Bypass -File .\Build-Windows.ps1 -BundleOnly
```

Supply `-InnoCompiler C:\path\ISCC.exe` if it is not in a detected location.
The bundle is `dist/OneDrivePCSync`; keep its `_internal` directory with the
EXE. The installer contains the entire bundle in a single setup EXE.
Builds do not automatically download or install build tools.

Runtime paths follow [PyInstaller's documented bundle behavior](https://pyinstaller.org/en/stable/runtime-information.html).
The per-user installer uses [Inno Setup's least-privilege installation mode](https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm).

Acceptance checks use isolated data and do not shut down the machine:

```powershell
.\.venv\Scripts\python.exe scripts\verify_windows_bundle.py dist\OneDrivePCSync\OneDrivePCSync.exe
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\Verify-WindowsAutomation.ps1
# Separate validation installer identity and data location:
ISCC.exe /DValidationBuild packaging\windows-installer.iss
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\Verify-WindowsInstaller.ps1
```

The automation and installer checks need access to the Windows Task Scheduler
and the current user's software registration. They create temporary validation
resources and remove their tasks/uninstall registration after checking them.

### Running from source

Requires Python 3.12+. Windows is required for scheduled tasks, native shutdown monitoring and toast notifications. The desktop UI uses PySide6, qtawesome and pyqtgraph; the synchronization engine uses the standard library. pywin32 is installed only on Windows. Graphify is analysis tooling.

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Run at logon (typically downloads OneDrive -> local)
python main.py --mode startup

# Run at logoff/shutdown (typically uploads local -> OneDrive)
python main.py --mode shutdown

# Preview without copying or creating anything
python main.py --mode startup --dry-run
```

## Desktop UI

```bash
python run_ui.py
# Use a separate development configuration without changing the project config:
python run_ui.py --config /path/to/config.json
```

Dashboard, tray and folder cards share one background synchronization service.
Folder management supports add, edit, enable/disable, search and filtering.
Settings and folder changes are validated before atomically replacing the
configuration file; environment-variable references remain intact.

**Pause UI Sync** blocks new requests from the UI and lets the current copy
finish. Independently scheduled Windows tasks continue to run. Exiting during
synchronization waits for the copy to finish. Without a system tray, closing
the window exits normally.

For Linux development, use temporary local directories in a separate config
and `QT_QPA_PLATFORM=offscreen` for headless Qt validation. Native Windows
integration must be tested on Windows.

## Automated setup (recommended)

Instead of manually configuring Task Scheduler, run the included setup
scripts once:

### For startup/shutdown sync via scheduled tasks:
```powershell
powershell -ExecutionPolicy Bypass -File .\Setup-ScheduledTasks.ps1
```

### For shutdown monitor (catches actual Windows shutdown events):
```powershell
powershell -ExecutionPolicy Bypass -File .\Setup-ShutdownMonitor.ps1
```

(Or right-click the `.ps1` files in Explorer -> **Run with PowerShell**.)

#### Tasks created by `Setup-ScheduledTasks.ps1`:
These register three Scheduled Tasks under **Task Scheduler Library > OneDrivePCSync**:

- **OneDrivePCSync - Startup (Download)** - fires 2 minutes after logon (delayed so the OneDrive client has time to start and mount before we try to read from it)
- **OneDrivePCSync - Shutdown (Upload on Lock)** - fires on workstation lock (Win+L)
- **OneDrivePCSync - Periodic Upload** - fires every 15 minutes while logged on

#### Task created by `Setup-ShutdownMonitor.ps1`:
- **OneDrivePCSync - Shutdown Monitor** - fires at logon and runs silently in the background, waiting for a Windows shutdown signal to trigger an immediate upload sync

## How the shutdown monitor works

The shutdown monitor is a lightweight resident program that starts at user logon and waits for Windows shutdown signals. When Windows begins shutting down (or restarting), it sends a `CTRL_SHUTDOWN_EVENT` to all console processes. The monitor intercepts this signal and immediately triggers an upload sync using the same safety-checked logic as the manual `shutdown` mode.

This provides a more reliable shutdown-triggered sync than the lock-based task, because it fires at the actual beginning of system shutdown rather than relying on the workstation lock event (which doesn't always precede a shutdown/restart).

**Important timing note:** The Windows shutdown handler only gives applications a limited time (typically ~5 seconds, registry-tunable via `HKEY_LOCAL_SYSTEM\SYSTEM\CurrentControlSet\Control\WaitToKillServiceTimeout`) to complete their shutdown handling before force-terminating the process. For most users with regular periodic syncs (every 15 minutes), the shutdown sync only needs to upload recent changes and completes quickly. If your sync typically takes longer than a few seconds, consider increasing the shutdown timeout via the registry setting mentioned above (requires reboot).

## Important limitation note

Even with the shutdown monitor, a direct Start Menu **Shut Down/Restart** still doesn't guarantee a successful sync if:

1. Your sync takes longer than the Windows shutdown timeout (default ~5 seconds)
2. You have Fast Startup enabled (where "shutdown" is actually a hybrid hibernation that may not send the shutdown signal to all applications)

The existing **Periodic Upload** task (every 15 minutes) remains an important safety net - it ensures your last upload is never more than ~15 minutes old regardless of how the session ends. For maximum protection, press Win+L before shutting down to trigger both the lock-based upload *and* give the shutdown monitor a chance to run.

The script auto-detects your project-local `.venv` if present, requires no
admin rights, and is safe to re-run any time (it replaces the existing
tasks rather than duplicating them - useful after moving the project folder
or changing Python interpreters). To remove the tasks later:

#### To remove startup/shutdown sync tasks:
```powershell
powershell -ExecutionPolicy Bypass -File .\Setup-ScheduledTasks.ps1 -Uninstall
```

#### To remove the shutdown monitor task:
```powershell
powershell -ExecutionPolicy Bypass -File .\Setup-ShutdownMonitor.ps1 -Uninstall
```

## Manual setup

If you'd rather not use the scripts, wire these into Task Scheduler by hand:
- Startup sync: Trigger "At log on" (with 2-minute delay), run `python main.py --mode startup`
- Lock-triggered upload: Trigger "On workstation lock", run `python main.py --mode shutdown`
- Periodic upload: Trigger "On a schedule" (every 15 minutes), run `python main.py --mode shutdown`
- Shutdown monitor: Trigger "At log on", run `python src/shutdown_monitor.py` (hidden window)

## Automatic pre-upload backups

For any folder, you can enable an automatic backup of its CURRENT OneDrive
contents immediately before every UPLOAD overwrites them - protection
against exactly the failure mode where a bad or premature upload replaces
good OneDrive data with something worse.

```json
"backup": {
    "enabled": true,
    "backup_path": "%OneDrive%\\PCSync\\Backups",
    "retention_days": 7
}
```

- **enabled** - opt-in per folder; omit the section entirely or set this
  to `false` to disable (the default).
- **backup_path** - where timestamped `.zip` archives are stored, namespaced
  per folder (`<backup_path>\<folder_id>\<folder_id>_YYYYMMDD_HHMMSS.zip`).
  **Must resolve inside your OneDrive folder** - the app validates this at
  config-load time using the `%OneDrive%` environment variable and refuses
  to start if `backup_path` points anywhere on local disk. Backups only
  protect you if they survive independently of the machine that made them.
- **retention_days** - archives older than this are deleted automatically
  after each backup (failures here are logged as warnings and never block
  the upload itself, since retention cleanup is housekeeping, not safety).

Backups only ever happen before UPLOAD (local -> OneDrive), never before
DOWNLOAD - a download doesn't overwrite OneDrive, so there's nothing to
protect there. If a folder's OneDrive destination is empty (first-time
sync), there's nothing to back up yet, so this is skipped automatically.
If backup creation itself fails for any other reason, the upload for that
folder is aborted rather than proceeding without one - the same
per-folder isolation used everywhere else in this app means other
folders are unaffected.

## Configuring folders

Edit `config.json` and add an entry under `"folders"` for each folder you
want synchronized. **Only list explicit application subfolders** - never
`AppData`, `AppData\Local`, or `AppData\Roaming` themselves; the app will
refuse to load a config that tries to sync one of these.

```json
{
    "id": "elden_ring",
    "name": "Elden Ring Save",
    "enabled": true,
    "local_path": "%APPDATA%\\EldenRing",
    "onedrive_path": "%OneDrive%\\PCSync\\AppData\\Roaming\\EldenRing",
    "minimum_sync_percentage": 80,
    "verify_after_sync": true,
    "create_destination": true
}
```

`minimum_sync_percentage` is the safety threshold: if the smaller of the
two file counts (source vs. destination) is below this percentage of the
larger, the sync for that folder aborts rather than risk overwriting
recent data with stale data (or vice versa).

## Safety guarantees

- **No destructive robocopy flags, ever.** `/MIR`, `/PURGE`, `/MOV`,
  `/MOVE` are hard-blocked in `robocopy_manager.py`, independent of config.
- **Dangerous root rejection**, checked both when `config.json` loads and
  again immediately before every sync.
- **File-count ratio abort**, per the `minimum_sync_percentage` rule above.
- **Per-folder isolation** - one folder failing never stops the others.
- **Dry-run mode** via `general.dry_run` in `config.json` or `--dry-run`.
- **Post-sync verification** (optional) checks the destination file count
  never dropped below the source's.

## Running tests

```bash
pip install pytest
python -m pytest tests/ --ignore=tests/test_shutdown_broadcast.py -v
```

Tests use temporary directories. Functional tests copy fixture files and create backup archives there; dry-run tests verify that data remains unchanged. The excluded shutdown-broadcast script is a manual Windows diagnostic, not an automated pytest test.
