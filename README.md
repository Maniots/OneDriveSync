<div align="center">

<img src="ui/resources/app.png" alt="EverySync logo" width="104" height="104">

# EverySync

**Your app data, ready on your next PC.**

Sync selected game saves, settings and application folders across local and cloud storage.

[![Windows build](https://github.com/Maniots/OneDriveSync/actions/workflows/windows-release.yml/badge.svg)](https://github.com/Maniots/OneDriveSync/actions/workflows/windows-release.yml)

**[Download for Windows](https://github.com/Maniots/OneDriveSync/releases/latest)** · [What's new](CHANGELOG.md) · [Report an issue](https://github.com/Maniots/OneDriveSync/issues)

Windows 10+ · x64 · No Python required to install

</div>

---

[Get started](#get-started) · [Daily use](#daily-use) · [Automation](#automation) · [Updates](#updates) · [Configuration](#configuration) · [Troubleshooting](#troubleshooting) · [Development](#development)

EverySync copies a selected PC folder to destinations you choose: folders on this PC, network storage or connected cloud accounts. **Synchronizations** is the single workspace for adding folders, selecting destinations and arranging download priority. Upload sends to every enabled destination; download uses one whole source in the chosen order. **Connections** manages direct OneDrive, Google Drive, Amazon S3 / compatible storage, SFTP, WebDAV, Dropbox, Azure Blob and Backblaze B2. See the [guided setup](docs/cloud-sync.md) for account requirements, snapshots and validation status. Live account certification is pending; real-engine Windows checks use isolated local storage.

**Connections** separates the service, connected account and cloud folder. Google,
Microsoft and Dropbox account details load in the background using the saved
sign-in. A provider may return only a display name; unavailable details are stated
explicitly. Select a row and choose **Verify access** to check its folder and retry
account details. For an existing OneDrive connection whose account details are
unavailable, choose **Show Microsoft account** and allow profile access in the
browser; its cloud folder and synchronizations are kept. New Microsoft sign-ins
include profile access. Use **Disconnect account** to remove the connection. The cloud
folder is the parent folder used by destinations you add in **Synchronizations**.

| Mode | Default direction | Purpose |
| --- | --- | --- |
| **Startup** | Ordered source → this PC | Bring a selected copy onto this machine. |
| **Shutdown** | This PC → enabled destinations | Send local changes to the destinations you chose. |

Directions are configurable. Copies create missing files and update changed files, keeping destination-only files in place. Path validation, file-count thresholds, optional backups and a shared synchronization lock protect each run.

## Get started

1. Open the [latest release](https://github.com/Maniots/OneDriveSync/releases/latest) and download **`EverySync-Setup-<version>.exe`** from **Assets**.
2. Run the installer. Choose the installation folder and, optionally, a desktop shortcut and automatic synchronization.
3. Connect any required account in **Connections**, then open **Synchronizations → Add synchronization**. Choose the PC folder, add destinations and arrange their download order with **Move up / Move down**. You can mix cloud accounts and folders without choosing a separate page.
4. Close the application that owns the files. Enable **Dry Run** in **Settings** and preview **Send to destinations** or **Download to this PC**. Turn dry run off for real transfers. New explicit activities require a verified upload before downloading; to use preexisting copies, explicitly enable **Allow existing copies whose freshness is unknown** in the activity's advanced options. Local OneDrive files must be available on the PC.

Choose specific folders, such as `%APPDATA%\ExampleApp\Saves`. Whole `AppData`, `AppData\Local` and `AppData\Roaming` roots are rejected.

The setup installs for the current Windows user and includes an uninstaller. Download the setup asset; GitHub's **Source code** ZIP/TAR archives are for development.

## Daily use

| Where | What you can do |
| --- | --- |
| **Dashboard** | Start a download or upload and follow background progress. |
| **Synchronizations** | Add, edit, enable, disable, search and filter activities, including existing single-destination folders. |
| **Connections** | Connect storage with guided provider fields/browser sign-in, test access and disconnect. |
| **Synchronizations → Send / Download** | Upload to enabled destinations or download from one source in priority order. Manual buttons use their stated direction, independently of scheduled trigger settings. Existing bidirectional singletons retain **Synchronize both folders**. |
| **Synchronizations → Remove** | Confirm removal while keeping files, history and stored backups. Group destinations remain as disabled activities for backup access; remove those separately to forget them and allow account disconnection. |
| **Synchronizations → More** | Refresh results or bypass an existing single-destination activity's file-count threshold for one confirmed configured run. Other checks and backups still apply; explicit groups cannot bypass generation guards. |
| **Synchronizations → Backups and restore** | Access local ZIP archives or a selected destination's verified cloud snapshots. |
| **Backups** | Browse, open, restore or delete backup archives. |
| **Scheduler** | Review tasks and shutdown monitor status; enable or disable existing sync tasks. |
| **Logs** | Inspect synchronization results and errors. |
| **Settings → App startup** | Enable **Run at startup** to open the desktop app at sign-in. This checkbox saves immediately and survives updates. |
| **Tray menu** | Reopen the window, start a sync, open settings, check updates or exit. |
| **About → Update history** | See installation dates, version changes and release notes. |

Closing the window keeps EverySync in the tray when a system tray is available. **Exit** waits for an active synchronization to finish. Without a tray, closing the window exits the app safely.

**Pause UI Sync** prevents new UI requests and lets a running copy finish. Independently scheduled Windows tasks continue to run. Folder deletion is unavailable during an active UI sync.

## Automation

**Run at startup** opens the desktop window. Automatic synchronization is configured separately through the installer's optional automation checkbox or the setup scripts below.

| Trigger | Default action |
| --- | --- |
| Sign-in, after a two-minute delay | Download from OneDrive. |
| Workstation lock, including **Win+L** | Upload to OneDrive. |
| Every 15 minutes while signed in | Upload to OneDrive. |
| Shutdown, restart or sign-out | The background shutdown monitor attempts an upload. |

The monitor receives Windows session-ending notifications and runs the copy before allowing the session to end. Completion depends on Windows allowing enough time and on the files being available. Periodic uploads reduce the work left at shutdown; let OneDrive finish its cloud transfer before switching PCs.

Direct cloud activities are queued during session shutdown and retried on the next ordinary run. Manual, lock and periodic runs perform actual transfers. Cloud snapshots are full remote copies with manual retention; providers without native SHA-256 may require extra downloads for verification. See [cloud behavior and recovery](docs/cloud-sync.md#run-and-recover).

<details>
<summary><strong>Set up or remove automation manually</strong></summary>

For an installed app, run these commands in PowerShell. Adjust `$install` if you chose a different installation folder.

```powershell
$install = "$env:LOCALAPPDATA\Programs\OneDrivePCSync"
$app = Join-Path $install 'OneDrivePCSync.exe'

# Download at sign-in; upload on lock and every 15 minutes.
powershell -NoProfile -ExecutionPolicy Bypass -File "$install\Setup-ScheduledTasks.ps1" -ApplicationExe $app

# Start the background shutdown monitor at the next sign-in.
powershell -NoProfile -ExecutionPolicy Bypass -File "$install\Setup-ShutdownMonitor.ps1" -ApplicationExe $app
```

Re-running a script replaces its existing tasks. Add `-Uninstall` to either command to remove the tasks it manages. Tasks appear under **Task Scheduler Library → OneDrivePCSync**; the monitor starts at the next sign-in, and periodic uploads can begin during the current session.

When running from source, use `powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup-ScheduledTasks.ps1` and the equivalent command for `Setup-ShutdownMonitor.ps1` from the repository root. The scripts detect the project-local `.venv`.

</details>

## Updates

The installed app checks for releases at startup and every four hours while running. Open **About → Updates** or the tray's **Check for updates**, then choose **Download and install**. Automatic installation is available as an explicit opt-in in the Updates card.

The updater verifies the download's size and SHA-256, waits for synchronization to finish, installs the update and restarts EverySync with its window visible. Configuration, update history, startup preference and existing task enabled states are preserved. Network errors allow retry and leave synchronization available.

Releases come from successful builds of `master`. Pull requests produce downloadable test artifacts on the [Actions page](https://github.com/Maniots/OneDriveSync/actions/workflows/windows-release.yml); they reach the production update channel after merging and a successful release build.

<details>
<summary><strong>Upgrading from OneDrive PC Sync</strong></summary>

Run the EverySync installer over the existing installation. No separate data migration is needed. Version 1.0 installations need this installer once to gain the in-app updater.

The executable remains `OneDrivePCSync.exe`, and the installation/data directories, task names and other technical identifiers retain their original names to preserve compatibility. Windows product metadata, the app and shortcuts display **EverySync**.

Each new release contains a single installer, `EverySync-Setup-<version>.exe`, also referenced by the update manifest. Versions through 1.5.0.21 expect the old installer name: download and run the EverySync installer manually once to migrate; subsequent updates use the new name. The repository remains `Maniots/OneDriveSync`.

</details>

## Configuration

Use **Synchronizations** and **Settings** for day-to-day changes. The installed app stores `config.json`, logs, history and runtime state in:

```text
%LOCALAPPDATA%\OneDrivePCSync
```

Updates and uninstall preserve this user data. To migrate a source-based setup, close EverySync, back up the existing installed configuration and copy your `config.json` into this directory.

<details>
<summary><strong>Folder configuration, thresholds and backups</strong></summary>

Add an entry like this to the `folders` array in `config.json`. Paths can use Windows environment variables.

```json
{
  "id": "example_saves",
  "name": "Example app saves",
  "enabled": true,
  "local_path": "%APPDATA%\\ExampleApp\\Saves",
  "onedrive_path": "%OneDrive%\\EverySync\\ExampleApp\\Saves",
  "minimum_sync_percentage": 80,
  "verify_after_sync": true,
  "create_destination": true,
  "backup": {
    "enabled": true,
    "backup_path": "%OneDrive%\\EverySync\\Backups",
    "retention_days": 7
  }
}
```

Start from [the empty default configuration](packaging/default-config.json) when creating a new configuration file.

| Setting | Behavior |
| --- | --- |
| `minimum_sync_percentage` | Compares the smaller file count with the larger: `min / max × 100`. A result below the threshold aborts that folder. Empty destinations are treated as first-time syncs. |
| `verify_after_sync` | Checks that the destination contains at least as many files as the source after copying. This is a file-count check. |
| `create_destination` | Allows a missing destination directory to be created. |
| `general.dry_run` | Previews copies without changing synchronized files or creating backup archives. Logs and run history may still be written. |
| `backup.enabled` | Creates a ZIP of the current OneDrive destination before an upload. Backups are opt-in per folder. |
| `backup.backup_path` | Must resolve inside the folder identified by `%OneDrive%`. Archives are grouped by folder ID. |
| `backup.retention_days` | Removes backup archives older than the configured retention period. |

Backups run before uploads; an empty destination has nothing to archive. If backup creation fails, that folder's upload stops while other folders can continue. Download-mode copies can overwrite local files, so check the direction before running them.

Configuration changes are validated and saved atomically. Dangerous root paths are checked again before copying. A failed folder does not stop the other configured folders.

</details>

<details>
<summary><strong>Command-line usage</strong></summary>

Use PowerShell with the default installation path below, or substitute your chosen path.

```powershell
$app = "$env:LOCALAPPDATA\Programs\OneDrivePCSync\OneDrivePCSync.exe"

& $app                           # Open or reactivate the desktop app.
& $app --check-updates           # Open Updates and check for a release.
& $app --update                  # Check, download, verify and install if newer.
& $app --mode startup --dry-run  # Preview OneDrive → local.
& $app --mode startup            # Download configured folders.
& $app --mode shutdown           # Upload configured folders.
```

The mode directions above are the defaults. Use `--config PATH` to select a separate configuration for UI or sync commands. `--monitor` starts the native background shutdown monitor with the shared application configuration.

</details>

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Nothing is synchronized | Add at least one enabled folder pair and check that the selected sync mode is enabled. |
| A folder is blocked by the safety threshold | Confirm the paths, direction and file counts. Use **Force sync** only after reviewing the difference. |
| Closing the window leaves the app running | Open it from the tray. Choose **Exit** to close it after any active sync finishes. |
| The desktop app opens at sign-in, but no automatic copy runs | Configure synchronization automation separately from **Run at startup**. |
| Another PC has not received the latest files | Check the sync result and let OneDrive complete its cloud transfer on both PCs. |
| A copy or update fails | Check **Logs**, the files under the user-data directory's `logs` folder, and `updates/install.log` for installation failures. |

## Development

Requires **Python 3.12+**. Build and test native Windows integration on Windows; the desktop uses PySide6, qtawesome and pyqtgraph, with pywin32 for Windows integration.

<details>
<summary><strong>Run from source</strong></summary>

```powershell
git clone https://github.com/Maniots/OneDriveSync.git
Set-Location OneDriveSync
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\scripts\Prepare-Rclone.ps1 # Pinned cloud engine, verified by SHA-256.

# Start with an empty development configuration.
Copy-Item packaging\default-config.json config.dev.json
.\.venv\Scripts\python.exe run_ui.py --config config.dev.json

# Preview a configured download without copying files.
.\.venv\Scripts\python.exe main.py --config config.dev.json --mode startup --dry-run
```

Source runs default to the repository's `config.json` and runtime paths. Use a separate configuration and temporary local folders for development. Linux Qt checks can use `QT_QPA_PLATFORM=offscreen`; native Windows behavior still needs Windows verification.

</details>

<details>
<summary><strong>Build a Windows installer</strong></summary>

On Windows x64, install **Inno Setup 6.7+**, then run:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
powershell -NoProfile -ExecutionPolicy Bypass -File .\Build-Windows.ps1
```

Use `-InnoCompiler C:\path\ISCC.exe` if the compiler is outside a detected location, or `-BundleOnly` to build the application directory without an installer. Build tools are installed separately.

| Output | Location |
| --- | --- |
| Self-contained application | `dist/OneDrivePCSync/` — keep `_internal` alongside the EXE. |
| Distributable installer | `dist/installer/EverySync-Setup-<version>.exe` |
| Update metadata | `dist/installer/update.json` |

`src/app_info.py` defines the base version. `-BuildNumber N` sets the fourth numeric component; CI uses its workflow run number. The EXE, installer and manifest share the same build identity.

</details>

<details>
<summary><strong>Run tests and Windows acceptance checks</strong></summary>

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install pytest
New-Item -ItemType Directory -Force build | Out-Null
.\.venv\Scripts\python.exe -m pytest tests -q --basetemp build/readme-tests -p no:cacheprovider

# After building the Windows bundle:
.\.venv\Scripts\python.exe scripts\verify_windows_bundle.py dist\OneDrivePCSync\OneDrivePCSync.exe
.\.venv\Scripts\python.exe scripts\verify_cloud_bundle.py dist\OneDrivePCSync\OneDrivePCSync.exe
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\Verify-WindowsAutomation.ps1

# Compile a separate validation installer, then verify its lifecycle.
ISCC.exe /DValidationBuild packaging\windows-installer.iss
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\Verify-WindowsInstaller.ps1

# Test update/restart using the validation installer as both baseline and update.
$version = (Get-Content dist\installer\update.json -Raw | ConvertFrom-Json).version
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\Verify-WindowsUpdate.ps1 -BaselineInstaller dist\installer\EverySync-Validation-Setup.exe -UpdateInstaller dist\installer\EverySync-Validation-Setup.exe -ExpectedVersion $version
```

For an upgrade across versions, retain a previous **validation** installer and pass it with `-BaselineInstaller`. Native checks use isolated data, tasks and installer registration; they need access to Task Scheduler and the current user's software registration. They do not request a system shutdown.

The [Windows workflow](.github/workflows/windows-release.yml) runs regressions, frozen EXE checks, installer lifecycle checks and actual update/restart checks before publishing a release. [CHANGELOG.md](CHANGELOG.md) records user-facing changes.

</details>
