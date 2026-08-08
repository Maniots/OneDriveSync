This architecture ensures the UI remains independent from the core synchronization logic under src/.

The main window features a modern header with page title and optional subtitle, a navigation sidebar with application logo, grouped navigation items, and a bottom section for Settings and About. The design follows Windows 11-inspired Fluent Design principles with proper spacing, rounded corners, and subtle hover effects.

---

## ���� �� �� 📝 Recent Changes (from git log)

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
| `local` | 2026-08-09 | Added AddFolderWizard multi-step wizard for adding/editing folder configurations with validation and review |
| `local` | 2026-08-08 | Redesigned MainWindow with header, updated sidebar layout, and modern UI enhancements |
| `local` | 2026-08-08 | Created SyncChartWidget reusable chart component with dark theme, minimal grid, tooltip support, and responsive resizing |
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
| `a5c7eda` | 2026-07-24 | Fixed focus-stealing issue with fullscreen apps |
| `4580fec` | 2026-07-24 | Changed PowerShell script to wrap Python run |
| `local` | 2026-08-08 | Fixed QDateTime error in LogsPage when parsing timestamps for date filtering. |
| `local` | 2026-08-08 | Implemented real read-only Shutdown Monitor status panel with PID, startup time, last detected event, last shutdown sync, last error, using status file from shutdown monitor and backend method in ConfigManager. Updated SchedulerPage to display status with timer updates.
|--------|------|---------|

---