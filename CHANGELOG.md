# Changelog

## Unreleased

- Stop and dispose standalone Qt monitor services after their tests, preventing delayed callbacks from leaking into subsequent CI tests.

- Pin PySide6 to the verified 6.11.1 Windows stack so CI and new builds do not silently upgrade to an unvalidated Qt minor release.

- Windows taskbar grouping now uses the stable EverySync application identity before Qt starts. Start menu and desktop shortcuts use the same identity and explicitly select the EverySync icon embedded in the executable.

- Each cloud service now permits one connected account. Connected providers explain how to add Cloud Sync activities or disconnect before changing accounts. Existing connections remain usable; local/NAS connections are exempt.
- OneDrive drive selection now checks access before offering a drive and includes supported Personal, Business and SharePoint storage only. Unavailable drives are omitted; an empty result offers retry.

- OneDrive drive selection now displays readable drive names, honors the provider's default selection and submits the matching drive identifier. Non-exclusive questions still allow a manual answer.

- Fixed OneDrive setup displaying a blank question after a recoverable drive-discovery error. Retry now reloads available drives and keeps the authorized account pending until folder selection.

- Added integrated Microsoft, Google and Dropbox browser sign-in, automatic technical browser setup and cloud folder selection after authorization.
- Custom OAuth applications are available under Advanced settings. Google native sign-in uses PKCE; the maintainer's local and installed build is now configured for Google sign-in without manual credential entry. Application credentials remain local.
- Accounts are saved only after folder verification. Cancelling an unfinished login removes its credentials while preserving existing connections.

## 1.5.0 — 2026-10-18

- Added Connections and Cloud Sync pages with guided account setup for direct OneDrive, Google Drive, Amazon S3, SFTP, WebDAV, Dropbox, Azure Blob and Backblaze B2, plus local/network storage.
- Cloud jobs support additive uploads/downloads, content verification, full remote snapshots and restore into an empty folder.
- Optional bidirectional jobs preserve conflicting changes for explicit resolution; interrupted work resumes before the next requested direction. Deletes are never propagated.
- Cloud credentials use an encrypted app-owned rclone configuration protected by Windows DPAPI. The installer includes a pinned, checksum-verified rclone engine.
- Session shutdown queues cloud work for the next ordinary run; periodic and manual runs perform transfers while Windows remains available.
- Real cloud account certification is pending; Windows acceptance checks use isolated local storage through the actual cloud engine.

## 1.4.1 — 2026-10-17

- Updates restart EverySync with its window visible after installation.
- Tray and single-instance activation restore windows hidden by Windows.
- Explicit exit bypasses minimize-to-tray and waits for an active synchronization to finish.

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
