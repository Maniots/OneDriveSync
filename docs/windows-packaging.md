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

## Installation wizard and release delivery (2026-10-17)

The existing Inno Setup wizard now explicitly displays welcome and destination
pages, with Italian/English optional-task and launch labels. Production setup:
`dist/installer/OneDrivePCSync-Setup-1.3.0.0.exe` (49,312,487 bytes). Its size and
SHA-256 match `dist/installer/update.json`.

- 233 regression tests passed on Windows, Python 3.14.6 / PySide6 6.12.0
  (`build/installer-regressions-full.log`); actionlint 1.7.12 passed.
- The actual frozen app passed UI, native navigation, startup/update controls,
  isolated copies, forced sync and native monitor checks
  (`build/windows-setup-bundle-check-full.log`).
- A separate validation setup passed install, installed UI, upgrade preserving
  config/startup, installation history and uninstall preserving user data
  (`build/windows-setup-installer-check.log`).
- The workflow now runs for pull requests to master and manual branch builds,
  and uploads only the production setup, manifest and release notes as an
  Actions artifact after EXE and installer checks pass. Current-master builds
  still publish the setup and manifest to GitHub Releases. These workflow
  changes are locally validated; hosted execution/publication is pending.
