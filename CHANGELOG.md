# Changelog

## 1.4.0 — 2026-10-17

- Renamed the application to EverySync throughout the desktop and Windows setup.
- Added a consistent synchronization logo to the window, taskbar, tray, notifications and installer.
- Tray badges keep idle, running, success and error states visible.
- Existing installations retain their configuration, backups, history, startup choice and automation.
- EverySync downloads retain a compatible update package for earlier OneDrive PC Sync installations.

## 1.3.1 — 2026-10-17

- Added Delete on folder cards, with confirmation before removing a sync pair.
- Removing a folder keeps local files, OneDrive files and existing backups.
- Folder removal is unavailable while UI synchronization is running.

## 1.3.0 — 2026-10-13

- About now shows installation dates, version transitions and release notes.
- Each folder has Force sync to bypass its percentage threshold for one confirmed run.
- Forced sync preserves backups, path validation, dry run, verification and the shared sync lock.
- Windows installations retain update history across upgrades and uninstall.

## 1.2.0 — 2026-10-13

- Added Run at startup in Settings, saved immediately for the current Windows user.
- Startup registration survives upgrades and is removed when its installation is uninstalled.

## 1.1.1 — 2026-10-12

- Fixed native Qt worker-disposal crashes during navigation and update completion.
- Added native Windows interaction checks and native crash logs.

## 1.1.0 — 2026-10-12

- Added automatic update notifications and manual download/install from master releases.

## 1.0.0 — 2026-10-12

- Added the Windows executable, per-user installer and installed scheduled-task support.
