This architecture ensures the UI remains independent from the core synchronization logic under src/.

The main window features a modern header with page title and optional subtitle, a navigation sidebar with application logo, grouped navigation items, and a bottom section for Settings and About. The design follows Windows 11-inspired Fluent Design principles with proper spacing, rounded corners, and subtle hover effects.

Last updated: 2026-10-18

## Windows taskbar identity (2026-10-18)

- `src/app_info.py` owns the stable, version-independent `EverySync.Desktop`
  AppUserModelID. `ui/app.py` applies it using the Windows shell API before
  accessing or creating QApplication. The existing EverySync application,
  window, tray and embedded EXE icons remain the shared product assets.
- Installer application shortcuts on the desktop and Start menu declare the
  same AppUserModelID and explicitly use the EXE's embedded icon at index 0.
  Regression tests read the actual process identity before Qt initialization
  and check shortcut/runtime identity consistency.
- Follow-up user screenshot still showed a generic taskbar icon on 1.5.0.4.
  Pixel checks of all native window icon formats, the EXE and Shell-resolved
  shortcut were correct; the installed SVG plugins were loaded. A Shell
  association refresh (`SHChangeNotify`, `SHCNE_ASSOCCHANGED`) resolved the
  display, with explicit visual confirmation from the user. This supports stale
  Shell icon caching; no further application patch was needed. Temporary window
  property experiments were reverted; no cache deletion or Explorer restart.

## Cloud account and eligible drive policy (2026-10-18)

- `CloudService` permits one new saved connection per non-local provider,
  checking before authorization and before publication. The Connections page
  disables sign-in and explains how to use Cloud Sync or disconnect first.
  Existing duplicate configurations remain loadable and individually removable;
  no accounts or activities are automatically deleted. Local/NAS connections
  remain multiple. Conflicts before publication discard only pending credentials.
- Before exposing OneDrive `config_driveid`, `RcloneTransport` reads each
  candidate root through the pinned engine setup state. Successful candidates
  must have a stored type of personal, business or documentLibrary; SharePoint
  libraries are included. `config/get` reads only the pending remote internally;
  its credential-bearing response never reaches UI or logs. The selector is
  exclusive, deduplicated and has an eligible default. The service rejects
  unlisted IDs or a substituted continuation state. Empty lists offer retry.
- Probes update only the encrypted pending configuration. The user's eventual
  selection is reapplied before confirmation; probes never create remote files.
  Root-read eligibility does not certify write permissions; folder verification
  and normal transfer error handling continue to apply.
- Tests cover duplicate guards, disconnect recovery, legacy/local compatibility,
  late-save conflicts, supported/denied drive selection and protected metadata.
  An isolated Graph fixture exercises the actual pinned rclone engine, including
  rejecting a drive and selecting a different one after the eligibility probes.

## Remove configured folders (2026-10-17)

- Version 1.3.1 adds a Delete action to each folder card. The page asks for
  confirmation (default No), naming the selected folder and explaining that
  local files, OneDrive files and existing backups are retained. Removal only
  updates the folder list through the existing validated, atomic config save.
- Delete works for disabled folders and while UI sync is paused, but is
  disabled during active UI synchronization. The handler rechecks busy state
  and reads current config after confirmation to preserve intervening edits.
  Save failures show a retryable warning and leave the card/config unchanged.
- `tests/test_folder_removal.py` covers confirmation/cancel, persisted removal,
  file/backup preservation, failed-save retry, busy-state recheck and removing
  the last disabled folder. The existing minimum-window layout check verifies
  the new button fits without horizontal overflow.
- Verification: 236 tests passed, 2 skipped; independent review found no
  blocking issues. The 1.3.1.0 frozen EXE passed rendering, 29 native
  navigation clicks, update/startup controls, isolated copies, forced sync
  and native monitor checks. The versioned Windows setup was rebuilt.
  The installed app was upgraded to 1.3.1.0, rendered successfully and
  restarted; its existing four-folder configuration remained byte-identical.

## Repository workflow preference (2026-10-17)

- `AGENTS.md` records the user's standing instruction: after each requested
  change and verification, commit and push to the current branch without
  asking for confirmation again.

## Downloadable Windows installation wizard (2026-10-17)

- The existing Inno Setup installer explicitly shows welcome and destination
  pages, including on interactive upgrades. Optional desktop shortcut,
  synchronization automation and the final launch checkbox have Italian and
  English labels. Silent updates continue to use the same installer.
- The Windows workflow builds pull requests targeting master and manual branch
  runs as well as master pushes. After frozen EXE and isolated installer
  install/upgrade/uninstall checks, it uploads the production setup EXE,
  update manifest and release notes as an Actions artifact. The separate
  validation setup is excluded from distribution.
- Public release publication remains restricted to the current master commit.
  Its setup asset is labelled as the Windows installation wizard. README
  links to release Assets and distinguishes the setup from the application
  executable and GitHub source archives.
- Verification: 233 regressions passed on Windows with Python 3.14.6 and
  PySide6 6.12.0; actionlint 1.7.12 passed. The actual frozen EXE passed native
  navigation, update/startup settings, isolated copy, forced sync and monitor
  checks. The production setup is `dist/installer/OneDrivePCSync-Setup-1.3.0.0.exe`
  (49,312,487 bytes), with size and SHA-256 matching `update.json`.
  The separate validation installer passed install, installed UI, upgrade
  preserving configuration/startup, history append and uninstall cleanup
  preserving user data (`build/windows-setup-installer-check.log`). Local
  artifacts are ready; the changed workflow has not yet run on GitHub.

## Update changelog and forced folder sync (2026-10-13)

- Version 1.3.0.0 adds About/Update history: installation time in local time,
  previous/installed versions, selectable release-note snapshots and retryable
  read errors. About uses a scroll area so updates/history fit smaller windows.
  `CHANGELOG.md` owns release notes; metadata/manifests and GitHub release
  publication carry the current section. Remote notes are bounded plain text.
- `src/installation_history.py` stores installer events in
  `%LOCALAPPDATA%\OneDrivePCSync\updates\history.sqlite3`. The installer calls
  `--record-install DATA_DIRECTORY` after files and optional automation setup
  succeed. Desktop launches/checks do not create events. Upgrade appends history
  and uninstall preserves it. Only the last verified legacy `result.json` is
  imported with its original timestamp; older dates/notes are not invented.
- Each enabled folder has Force sync with a default-No confirmation showing
  folder, direction, source, destination and threshold. It requests one
  background run for that selected folder; pause/busy/disabled state and the
  shared lock still apply. The override is a per-call argument owned by
  `SyncManager`, never a persisted threshold change or a global engine flag.
  Only the percentage comparison is skipped. Path guards, additive copying,
  pre-upload backups, dry run and post-copy verification remain active.
- Forced requests/results are tagged in logs and existing sync-history JSON;
  folder status labels show Forced success/failure/dry run. Ordinary UI,
  CLI and scheduled runs continue to enforce their configured thresholds.
- Tests cover copy/backup behavior, confirmation cancellation, configuration
  preservation, one-run/single-folder scope, guarded failures, history dates,
  legacy import and UI recovery. Frozen acceptance adds `--force-sync-test`
  using an explicit reserved folder ID and fixture paths under its report
  directory; it cannot target ordinary personal folders. Installer validation
  checks history creation, upgrade append and uninstall preservation.
- Verification: 231 tests passed, 2 skipped; actionlint passed. The frozen EXE
  passed real Force sync button/modal/worker copying and backup, startup
  registration, update checks, navigation and isolated monitor checks. A
  separate installer created history, appended on upgrade and preserved it
  on uninstall. Legacy `result.json` remains the last-attempt/error owner;
  the SQLite journal owns installation history once created, with no deletion
  or rewrite of legacy records.

## Run at startup in Settings (2026-10-13)

- Settings includes an independent "App startup" card with "Run at startup".
  Its checkbox saves immediately, reads the Windows registration when the
  page opens, and rolls back with a retryable error if a write fails. It
  remains usable when sync configuration is missing; source/non-Windows
  execution explains that the installed Windows app is required.
- `backend/services/app_startup_service.py` owns the current user's
  `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\OneDrivePCSync`
  value. It registers the quoted installed EXE without arguments and removes
  only its own entry. The default is disabled. Windows registration is the
  sole persisted state; there is no duplicate flag in sync configuration.
  This opens the desktop app at sign-in; existing scheduled sync and shutdown
  monitor tasks keep their independent behavior.
- Version 1.2.0.0 preserves the startup choice on upgrades. Uninstall removes
  the value only if its command belongs to that installation; the validation
  installer uses a separate value name. `--interaction-test` exercises native
  Settings toggles against a temporary registry value and cleans it up.
- `tests/test_app_startup.py` covers persistence, ownership, unsupported
  source runs, immediate save, Cancel/Reset, error rollback/read retry and
  refresh. The installer validator checks upgrade preservation and uninstall
  cleanup alongside existing configuration preservation. Real Windows
  sign-out/sign-in remains outside automated validation.
- Verification: 217 tests passed, 2 skipped; the frozen EXE passed native
  startup checkbox/registry persistence, 29 page clicks, update checks,
  isolated sync and monitor checks. A separate real installer passed startup
  preservation on upgrade and removal on uninstall. The scheduler recovery
  test now isolates monitor status from the developer's runtime status file.

## Native desktop crash repair (2026-10-12)

- Version 1.1.1.0 fixes a Windows worker-disposal race. Native EXE tests
  reproduced access violations in Shiboken while `UpdateService._finish`
  dropped worker references and the QThread was still processing native
  deferred deletion. `QThread.finished` does not mean native cleanup is done.
  Update, scheduler and sync completion slots now join the thread before
  releasing wrappers or announcing completion; background work stays async.
- `desktop_entry.py` captures native exceptions using faulthandler in
  `%LOCALAPPDATA%\OneDrivePCSync\logs\desktop_native_crash.log`. Python
  exception reporting remains in `desktop_crash.log`.
- `--interaction-test REPORT.json` runs the Windows Qt platform, asserts
  real clicks change every sidebar page/header, waits for the automatic
  startup update check, tests the manual check button, then exits normally.
  `scripts/verify_windows_bundle.py` includes this check with four isolated
  folders before testing sync and the shutdown monitor. `--smoke-test`
  remains an offscreen rendering check.
- Correction to the earlier validation scope: the 208 passing tests and
  offscreen frozen rendering did not exercise native Windows clicks across
  update-worker completion. They were insufficient evidence for interactive
  EXE stability. The original installed EXE crashed in the native repeat
  test; joining the updater thread passed the identical 56-click test.
- Verification: 209 tests passed, 2 skipped. The repaired frozen bundle
  passed 29 asserted native navigation clicks, automatic/manual update
  checks, dry-run, real isolated copies, and native monitor sync/exit.

## Updates from master (2026-10-12)

- `src/app_info.py` owns version/repository identity. Build metadata generates
  the EXE version, Inno include and matching SHA-256/size update manifest.
  Local builds use 1.3.0.0; GitHub builds use the run number as component four.
- `.github/workflows/windows-release.yml` tests and builds Windows on pushes
  to master, validates the frozen EXE, and publishes a `master-N` GitHub release
  only for the still-current master commit. It becomes active when merged and
  pushed to master; local commits alone do not publish a release.
- `src/updater.py` reads only the public Maniots/OneDriveSync release channel,
  validates bounded manifests, numeric versions, asset origin, size and hash,
  and stages downloads without shipping repository credentials.
- `backend/services/update_service.py` coordinates background check/download
  workers. The app checks at startup and every four hours while open. The user
  explicitly selected automatic notification plus a manual install button;
  automatic installation remains an optional, initially disabled preference.
  About/Updates and the tray expose availability, progress, retry and install.
- `--check-updates` checks in the desktop update view; `--update` requests
  verified installation if newer. Existing-instance activation carries the
  selected action. Existing sync/monitor commands remain supported.
- The detached `packaging/Apply-Update.ps1` waits for the UI and canonical sync
  lock, temporarily suspends only tasks belonging to this installed EXE, runs
  the existing installer, restores enabled states and restarts the app and any
  previously running task monitor. Configuration/history/backups persist.
  Failed installation is reported on restart and disables automatic retries.
  The shutdown monitor now also acquires the shared sync/update lock.
- Native teardown tests exposed pyqtgraph's requirement to close PlotItem
  before scene destruction. MainWindow now prepares services and charts before
  deferred deletion/event-loop exit; Qt test disposal respects parent ownership
  and explicitly closes independent plots. Updater cancellation prevents queued
  completion from starting installation after exit.
- Verification: 208 tests passed, 2 skipped; actionlint passed; actual frozen
  UI, dry-run, copy and native monitor passed. An isolated real upgrade from
  1.0 to 1.1 preserved configuration and four task enabled states, waited for
  the sync lock and removed the verified staged download. Task-triggered
  restart of an already-running monitor and the first hosted GitHub publication
  remain unverified. Live public API currently reports no release.

## Windows executable and per-user installation (2026-10-12)

- `desktop_entry.py` is the unified frozen entry point: no arguments opens
  the existing desktop UI; `--mode startup|shutdown` invokes the sync CLI;
  `--monitor` invokes the native shutdown monitor. Explicit configurations
  and dry-run remain supported for sync. `--init-config`, `--diagnostics`
  and `--smoke-test` support installation and reproducible bundle validation.
- `src/runtime_paths.py` owns writable runtime locations. Source execution
  retains project-local data. Frozen execution uses
  `%LOCALAPPDATA%\OneDrivePCSync` for config, logs, history, monitor status
  and locks. Configuration/log services, CLI, UI worker and monitor use
  these paths; bundled SVG resources stay relative to their package.
- `packaging/default-config.json` contains an empty folder list. First-run
  seeding and the installer preserve existing configuration. Personal
  repository configuration is never packaged. Windowless logging omits a
  console handler when stdout is unavailable; startup failures are recorded
  in `logs/desktop_crash.log`.
- `packaging/OneDrivePCSync.spec`, `requirements-build.txt` and
  `Build-Windows.ps1` build the PyInstaller directory bundle, including
  PySide6, pywin32, qtawesome fonts and SVG assets. The target machine does
  not require Python. `packaging/windows-installer.iss` builds a per-user
  Inno Setup installer with a stable identity, uninstall registration,
  Start menu links and optional desktop shortcut/automation. User data is
  preserved on upgrade and uninstall. Automation setup failures are surfaced.
- Both setup scripts accept `-ApplicationExe` for direct EXE task actions
  and retain their source/Python route. Trigger names/timing stay unchanged.
  Installed-app uninstall checks action ownership before stopping/removing
  a task, preserving tasks from other installations. `-TaskFolderPath`
  permits isolated validation without touching production task names.
- Native bundle acceptance exposed missing pywin32 imports in the existing
  shutdown monitor; restored them. The monitor now persists completed sync
  timestamps immediately, so its status readers see the actual result.
- Automated packaging regressions live in `tests/test_windows_packaging.py`.
  `scripts/verify_windows_bundle.py` checks actual frozen UI rendering,
  resources, dry-run, file copy and native monitor signals on an isolated
  HWND/data set. `Verify-WindowsAutomation.ps1` checks four tasks including
  the hidden monitor and ownership-safe removal. `Verify-WindowsInstaller.ps1`
  uses a separate validation installer identity for installation, upgrade,
  installed UI and uninstall preservation checks. A real Windows reboot and
  forced shutdown timing remain outside these automated checks.
- Windows validation completed: 182 tests passed, 2 skipped; actual frozen
  UI/resources, dry-run, file copy, native monitor and all four EXE task actions
  passed. Installer install/upgrade/uninstall preserved configuration. The
  production release was installed for the current user with desktop/Start
  menu links; the existing project configuration (4 folders) was migrated and
  the installed UI rendered successfully. Automatic tasks remain an optional
  setup choice. Evidence and remaining shutdown timing limits are recorded in
  `docs/windows-packaging.md`.


## UI and synchronization fixes (2026-10-12)


### Follow-up: local Qt compatibility

Validation: 105 automated tests passed on Linux with both Python 3.12.14 / PySide6 6.12.0 and the reported local versions Python 3.14.6 / PySide6 6.11.1. Real Windows named-pipe and native desktop behavior still require local validation.

- BackupsPage now colors status items with QBrush(QColor(...)) instead of an unsupported string passed to QTableWidgetItem.setForeground. Empty/error states keep the same QTableWidget alive and use a separate label, allowing refresh and recovery without dangling wrappers. The initial refresh timer belongs to the page and configuration changes refresh its data.
- Local socket activation accepts writes that have already completed synchronously (including Windows named-pipe behavior). Buffered writes still require the queue to drain within the timeout. Tests wait for actual connection and activation events, rather than a fixed number of event-loop polls, and retain the fragmented-message assertion.
- Qt test teardown disposes newly created windows after each UI test, stops their owned timers, and checks shiboken6.isValid before accessing wrappers whose native child may already be destroyed. A regression explicitly covers a snapshot containing an already deleted QTableWidget.
- Log date filtering uses QDate.startOfDay through LogService. LogsPage filters its bounded cached data, refreshes only when data changes, and clears stale rows when the file is truncated. Today/Yesterday filtering and real backup rendering/error recovery have functional coverage.

- JSON paths retain their original environment-variable strings. Folder and backup dataclasses also accept `Path` inputs from existing Python callers. Core sync uses resolved path properties; configuration saving validates a temporary JSON file and atomically replaces the original only after validation succeeds.
- `SyncService.request_sync(operation, folder_id=None)` coordinates Dashboard, tray and folder-card requests in one background thread. It reserves the active run before starting the thread, shares pause/busy state, and snapshots the current configuration. Existing synchronous `start_startup_sync` and `start_shutdown_sync` methods remain available to non-interactive callers.
- `SyncWorker` uses the same `onedrive_pcsync.lock` as the CLI and invokes the public core workflow, including per-folder isolation, safety thresholds, pre-upload backups, dry-run and verification. Optional progress callbacks keep the core independent of Qt. Pause blocks new UI requests, allows the current run to finish, and does not change independent Windows Scheduled Tasks. Exiting waits for any active copy and thread cleanup.
- Dashboard and tray receive the same started/progress/completed/failed/finished signals. Partial failures are reported as errors; refresh preserves the result and the chart uses actual session outcomes instead of dummy data. Folder add/edit/toggle/filter/refresh/single-folder-sync actions are connected to validated configuration and synchronization services. Settings apply retains the latest folder list so it cannot overwrite newly added folders.
- Scheduler errors use a persistent label instead of deleting monitor widgets. Status refresh and checkbox rollback block signals to prevent unwanted confirmations or scheduler writes. Missing timestamps display as N/A, and controls for unavailable tasks are disabled. `ConfigurationService` delegates monitor status reads and emits `changed` after successful saves/reloads. Log parsing accepts the padded level format used by the logger.
- `run_ui.py --config PATH` supports development with a separate configuration. Qt local-server activation works for fragmented show messages; Windows mutex signatures use pointer-sized handles and ERROR_ALREADY_EXISTS=183. A tray is shown only when available; clicking it restores the window. Wizard editing preloads existing values, supports environment variables and Windows drive paths, and qualifies relative OneDrive paths under `%OneDrive%`.
- Runtime dependencies are PySide6, qtawesome and pyqtgraph; pywin32 is declared only for Windows. Removed the unused, invalid qdarktheme requirement; the application uses its existing local QSS theme. Graphify remains analysis tooling. The existing graph lacks UI/service nodes and wiki/index.md, so those components were inspected from source.
- Regression coverage lives in `tests/test_ui_regressions.py`, with a shared Qt application fixture in `tests/conftest.py`. Existing path tests now separately assert preservation of raw strings and resolution for filesystem operations. Tests cover real temporary-directory copy and pre-upload backup, dry-run, partial failures, external lock refusal, UI responsiveness, duplicate requests, shared pause, deferred exit, atomic configuration rejection, monitor delegation, scheduler recovery without implicit writes, log parsing, folder actions, settings consistency, wizard editing and launcher configuration. Manual shutdown-broadcast diagnostics remain outside automated pytest collection.
- Linux validation cannot establish native Windows shutdown-event, Task Scheduler or system-tray integration behavior; these still need Windows validation.

---
## ���������������� �������������� �������������� ������������ �������������� ������������ ������������ ���������� �������������� ������������ ������������ ���������� ������������ ���������� ���������� �������� �������������� ������������ ������������ ���������� ������������ ���������� ���������� �������� ������������ ���������� �������� �������� ������ �������������� ������������ ������������ ���������� ������������ ���������� �������� ������������ ������������ ���������� �������� ������������ ���������� �������� �������� ������ ������������ ������������ �������� �������� �������� �������� ������ ���������� �������� �������� ������ �������� ������ ������ ���� �������������� ������������ ������������ ������������ ������������ ���������� ������������ �������� ������������ ���������� �������� ������������ ���������� �������� �������� ������ ������������ ���������� ���������� �������� �������� ������ ���������� �������� �������� ������ �������� ������ ���� ������������ ���������� ���������� �������� �������� ������ ���������� �������� �������� ������ �������� ������ ���� �������� ������ ������ ���� ������ ���� ���� �� �������������� ������������ ������������ ���������� ������������ ���������� ���������� �������� ������������ ���������� ���������� �������� ���������� �������� �������� ������ ������������ ���������� ���������� �������� ���������� �������� �������� ������ ���������� �������� ������ ������ ���� ������������ ���������� ���������� �������� ���������� �������� ������ ���������� ���������� �������� ������ ���������� �������� ������ ������ ���� ���������� ���������� ������ ������ ������ ������ ���� �������� ������ ������ ���� ������ ���� ���� �� ������������ ���������� ���������� ���������� ���������� �������� ���������� ������ ���������� �������� ������ ���������� �������� ������ ������ ���� ���������� �������� �������� ������ ������ ���� �������� ������ ������ ���� ������ ���� �� ���������� �������� �������� ������ ������ ���� �������� ������ ������ ���� ������ ���� �� ������ ���� ���� �� ���� �� �� 📝 Recent Changes (from git log)
| `local` | 2026-08-09 | Fixed PySide6 runtime errors in UI by correcting QLabel constructor calls with invalid property keyword arguments, added dependency injection to MainWindow for testability, and created headless UI smoke test that passes without GUI.

| `local` | 2026-08-09 | Applied visual polish pass across all UI pages and widgets: consistent spacing using theme constants, proper title/value semantics for labels, card property applied to containers, improved button hierarchies, consistent dark theme, and enhanced accessibility. |
| `local` | 2026-08-09 | Fixed QLabel constructor calls in AddFolderWizard where property was passed as a keyword argument, causing "setProperty expected 2 arguments got 1" error. |
| `local` | 2026-08-08 | Redesigned LogsPage into a professional log viewer with live stream, search, level filters, date filtering, refresh, copy selected, and auto-scroll toggle. Fixed refresh button connection error. |
| `local` | 2026-08-08 | Fixed QHeaderView setResizeMode error in LogsPage (used setSectionResizeMode instead). |
| `local` | 2026-08-08 | Redesigned SchedulerPage to show automation system with sections and visual timeline. |
| `local` | 2026-08-08 | Updated SchedulerModel to include detailed scheduler fields. |
| `local` | 2026-08-08 | Updated ui/config.py to convert backend config to the new SchedulerModel. |
| `local` | 2026-08-08 | Corrected PROJECT_MEMORY.md Last updated date to current date |
| `local` | 2026-08-10 | Connected UI to configuration backend - load AppConfig through ConfigManager, convert to UI models, populate Dashboard, FoldersPage, and SettingsPage with error handling |
| `local` | 2026-08-10 | Created ui/config.py utility for converting backend AppConfig to UI models and handling configuration errors |
| `local` | 2026-08-10 | Modified MainWindow to load configuration and handle missing/invalid config gracefully |
| `local` | 2026-08-10 | Updated DashboardPage to accept configuration backend and display real configuration data |
| `local` | 2026-08-10 | Updated FoldersPage to accept configuration backend and display real folder data from config |
| `local` | 2026-08-10 | Updated SettingsPage to accept configuration backend and display real settings from config |
| `local` | 2026-08-08 | Redesigned BackupsPage as a modern backup management interface. |
| `local` | 2026-08-09 | Add AddFolderWizard multi-step wizard for adding/editing folder configurations with validation and review |
| `local` | 2026-08-09 | Implemented safe settings persistence with edit, validation, apply, cancel, reset functionality in SettingsPage, using the existing configuration architecture without writing raw JSON directly. |
| `local` | 2026-08-09 | Added scheduler controls to enable/disable supported scheduled tasks and refresh task status in SchedulerPage UI. |
| `local` | 2026-08-09 | Fixed backup path handling in backup_manager.py and backup_service.py to use resolved paths for Path operations while preserving original strings in config. |
| `local` | 2026-08-09 | Fixed missing LogLevel import in ui/pages/settings.py. |
| `local` | 2026-08-08 | Redesigned MainWindow with header, updated sidebar layout, and modern UI enhancements |
| `local` | 2026-08-08 | Created SyncChartWidget reusable chart widget with dark theme, minimal grid, tooltip support, and responsive resizing |
| `local` | 2026-08-08 | Redesigned DashboardPage to use SyncChartWidget for sync activity visualization, with premium layout including status cards, folder overview, backup status, and recent activity |
| `local` | 2026-08-08 | Redesigned FoldersPage to use FolderCard widget with toolbar, responsive grid, and loading/error/empty states |
| `local` | 2026-08-08 | Updated theme to add status label styles for FolderCard widget |
| `local` = 2026-08-08 | Created FolderCard widget with folder information display and action signals |
| `local` | 2026-08-08 | Verified all UI components work correctly together with no errors |
| `local` | 2026-08-08 | Fixed missing QScrollArea import in settings.py |
| `local` | 2026-08-07 | Implemented centralized icon system with semantic names using qtawesome |
| `local` | 2026-08-07 | Implemented complete PySide6 UI with design system, backend wrappers, and UI models |
| `local` | 2026-08-06 | Fixed test_copy_engine.py: added missing engine fixture to test_copy_engine_skips_symlinks and test_copy_engine_skips_junctions |
| `e3a1b42` (HEAD) | 2026-07-29 | Replaced broken `SetConsoleCtrlHandler`/`CTRL_SHUTDOWN_EVENT` approach in `shutdown_monitor.py` with a hidden message-only window + Windows message loop handling `WM_QUERYENDSESSION` / `WM_ENDSESSION` (the Windows-recommended architecture for interactive apps); added `pywin32` dependency |
| `2aa2931` | 2026-07-31 | **Fix applied:** Replaced `HWND_MESSAGE` with `NULL` (0) as window parent in `shutdown_monitor.py` so the hidden top-level window receives `WM_QUERYENDSESSION`/`WM_ENDSESSION` broadcast messages. Improved logging (PID, startup method, handler initialized, sync start/complete/fail, monitor exit). Added `try/except` around monitor run. Updated `shutdown_diagnosis.md` — marked as resolved. |
| 2026-08-01 | **Fix applied:** Fixed `SystemError: new style getargs format but argument is not a tuple` in `shutdown_monitor.py`. Root cause: `win32gui.GetMessage()` returns a tuple `(rc, msg)`, not just the `msg` object. The code was assigning the entire tuple to `msg` and passing it to `TranslateMessage(msg)`, which expects only the `MSG` structure. Fixed by unpacking the tuple correctly: `rc, msg = win32gui.GetMessage(None, 0, 0)` and checking `rc != 0` for WM_QUIT. |
| 2026-08-02 | **Fix applied:** `Setup-DesktopHeap.ps1` — fixed 3 references to `Fix-DesktopHeap.ps1` → `Setup-DesktopHeap.ps1` in help text; added idempotency check (already set to 12288 KB → reports success, exits 0); documented in PROJECT_MEMORY.md and shutdown_diagnosis.md. |
| 2026-08-03 | **Fix applied:** `robocopy_manager.py` — added in-process Python copy fallback (`copy_files_in_process`) that activates when `robocopy.exe` fails to start after retries (e.g. `STATUS_DLL_INIT_FAILED` / `0xC0000142` during shutdown). This makes shutdown upload reliable even when the OS cannot spawn child processes during session teardown. Also added `mode` parameter to `run()` for better launch logging, and enhanced logging with working directory, parent PID, and detailed launch diagnostics. Updated `sync_manager.py` to track and pass sync mode. |
| `595fd32` | 2026-07-24 | Added backups management + notification when startup download finishes |
| `deea75a` | 2026-07-24 | Added single-instance tasks (prevent overlap) |
| `0624a76` | 2026-07-24 | Added 2-minute delay on PC startup |
| `a5c7eda` | 2026-07-24 | Changed focus-stealing issue with fullscreen apps |
| `4580fec` | 2026-07-24 | Changed PowerShell script to wrap Python run |
| `local` | 2026-08-08 | Fixed QDateTime error in LogsPage when parsing timestamps for date filtering. |
| `local` | 2026-08-08 | Implemented real read-only Shutdown Monitor status panel with PID, startup time, last detected event, last shutdown sync, last error, using status file from shutdown monitor and backend method in ConfigManager. Updated SchedulerPage to display status with timer updates. |
| `local` | 2026-08-08 | Designed and implemented application service layer in backend/services with ConfigurationService, SyncService, BackupService, SchedulerService, MonitorService, and LogService. Updated SchedulerPage and LogsPage to use services. |
| `local` | 2026-08-08 | Fixed missing import of get_icon in ui/pages/backups.py causing name not defined error. |
| `local` | 2026-08-08 | Fixed QHeaderView FIXED error in ui/pages/logs.py (used Fixed instead of FIXED). |
| `local` | 2026-08-08 | Fixed QHeaderView STRETCH error in ui/pages/logs.py (used Stretch instead of STRETCH). |
| `local` | 2026-08-08 | Fixed folderModel object has no attribute get error in ui/pages/folders.py by converting FolderModel to dict for FolderCard. |
| `local` | 2026-08-08 | Fixed FolderCard signal connections in ui/pages/folders.py (used edit_clicked and enabled_toggled signals with lambda to pass folder_id). |
| `local` | 2026-08-08 | Modified backend/services/sync_service.py to add get_app_config method. |
| `local` | 2026-08-08 | Added reusable Qt background worker for synchronization in ui/workers/sync_worker.py. |
| `local` | 2026-08-08 | Modified ui/pages/dashboard.py to display real synchronization state (current operation, folder, direction, elapsed time, result, last successful/failed sync) and to start sync via worker threads. |
| `local` | 2026-08-08 | Fixed missing self parameter in is_shutdown_sync_enabled method in backend/services/sync_service.py. |
| `local` | 2026-08-08 | Added finished signal to SyncWorker and emitted upon completion/failure to fix AttributeError in dashboard. |
| `local` | 2026-08-08 | Removed duplicate deleteLater connections in dashboard.py to avoid RuntimeError on already deleted SyncWorker. |
| `local` | 2026-08-08 | Fixed QThread destroyed while thread still running by proper thread cleanup: connect finished to quit, worker deleteLater, thread deleteLater; removed manual deleteLater in on_sync_finished. |
| `local` | 2026-08-08 | Fixed SyncWorker completed signal definition: changed from Signal(List[FolderSyncOutcome]) to Signal(list) to prevent 'completed only accepts 0 argument, 1 given!' error. |
| `local` | 2026-08-08 | Modified ui/workers/sync_worker.py to provide per-folder progress signals during synchronization, enabling dashboard to show current folder. |
| `local` | 2026-08-08 | Modified ui/pages/dashboard.py to update current folder label from worker progress messages. |
| `local` | 2026-08-08 | Added system tray integration with idle/syncing/success/warning/error states and context menu (Open, Sync Now, Pause/Resume, Settings, Exit). |
| `local` | 2026-08-08 | Modified MainWindow close event to hide to tray instead of terminating application, keeping background services running. |
| `local` | 2026-08-08 | Modified SyncService to inherit from QObject and added signals (started, progress, completed, failed, finished) for sync state reporting. |
| `local` | 2026-08-08 | Modified MainWindow to connect to sync service signals in load_services and update tray icon based on sync state. |
| `local` | 2026-08-09 | Added single-instance protection for the UI using QLocalServer and QLocalSocket. |
| `local` | 2026-08-09 | Modified MainWindow to check for another instance on startup and send a show message if found. |
| `local` | 2026-08-09 | Added main function and __main__ block to run the application with single instance check. |
| `local` | 2026-08-09 | Added show_and_activate method to show and activate the window from another instance. |
| `local` | 2026-08-09 | Moved single instance check to beginning of __init__ to prevent UI setup for secondary instances.
| `local` | 2026-08-09 | Connected SchedulerPage to Windows Scheduled Task infrastructure to display task status, existence, enabled state, last run, and next run times for startup, periodic, and workstation lock tasks without modifying existing PowerShell scripts.
| `local` | 2026-08-09 | Added scheduler controls to enable/disable supported scheduled tasks and refresh task status in SchedulerPage UI.
| `local` | 2026-08-09 | Fixed missing SyncTriggerSettings import in ui/pages/settings.py. |
| `local` | 2026-08-09 | Fixed missing expand_env_vars import in src.config (used in BackupSettings and FolderSyncConfig resolved path properties). |
|--------|------|---------|
