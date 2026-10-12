# Windows executable and installation

Task started 2026-10-12 from a clean working tree. Existing owners: `main.py`
(sync CLI), `ui/app.py` (desktop), `src/shutdown_monitor.py` (native monitor),
and the two setup scripts (Task Scheduler). Graphify identifies the core
owners; its wiki and UI/service nodes are missing, so source fills those gaps.

Implementation and acceptance:

1. Share writable runtime paths: source runs retain the project paths; frozen
   runs use `%LOCALAPPDATA%\OneDrivePCSync`. Configuration, logs, history,
   monitor status and both locks must use consistent locations.
2. Bundle one windowless executable supporting the UI, sync CLI and shutdown
   monitor. Include Qt resources and icon fonts; seed only an empty config.
3. Adapt scheduled-task scripts to invoke the installed executable directly,
   retaining source execution. Uninstall removes only tasks belonging to the
   supplied installed executable.
4. Add a reproducible PyInstaller build and an Inno Setup per-user installer,
   Start menu/optional desktop links, optional automation, upgrade-safe data
   and uninstall registration.
5. Verify regressions, real frozen UI and empty sync from an unrelated working
   directory, compile the installer and verify install/upgrade/uninstall in an
   isolated directory. Install the verified app on this PC if permitted by
   the environment, preserving this PC's existing configuration.

No change to folder selection, copy safety, backups or shutdown semantics.
The installer must never embed the developer's personal `config.json`.

## Verification result

Completed on Windows x64, 2026-10-12, Python 3.14.6 / PySide6 6.11.1.

- Automated regression suite: 182 passed, 2 skipped
  (`build/packaging-regressions.log`).
- Actual frozen EXE: GUI/resources, dry-run, real file copy, native monitor
  receiving targeted session messages and clean monitor exit passed
  (`build/windows-acceptance.log`). No system shutdown was requested.
- Four scheduled EXE tasks, least privilege, hidden monitor and ownership-safe
  uninstall passed in an isolated task folder (`build/windows-automation.log`).
- Validation installer: install, installed GUI, upgrade preserving modified
  config and uninstall preserving config passed
  (`build/windows-installer-acceptance.log`). Temporary software registration
  and scheduled tasks were removed.
- Production installer generated at
  `dist/installer/OneDrivePCSync-Setup-1.0.0.exe` (about 47 MiB). Installed
  successfully for the current Windows user at
  `%LOCALAPPDATA%\Programs\OneDrivePCSync`, with desktop/Start menu links and
  uninstall registration. Existing project config was migrated (4 folders).
  The installed EXE rendered its UI using that config from an unrelated working
  directory (`build/pc-installed-diagnostics.json`). Automation is optional
  and was not enabled by this installation.
- README and PROJECT_MEMORY describe the delivered runtime/build paths.

Confidence B: the binary, installation lifecycle and targeted native signals
are verified; a real Windows restart/shutdown and its OS-enforced timeout were
not exercised. No changes to selected folders, copy policy or backup policy.
