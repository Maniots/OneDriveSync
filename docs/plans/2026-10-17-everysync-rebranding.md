# EverySync rebranding implementation plan

Approved scope: `docs/specs/2026-10-17-everysync-brand-design.md` and the user's
instruction to implement on a new branch. Base: `95da7eb`; branch:
`feat/everysync-rebranding`; isolated checkout: `.claude/worktrees/everysync`.

## Compatibility decision

EverySync owns visible product identity. Existing installer AppIds, executable
and installed data paths, startup registry value, scheduled task IDs, mutex,
activation server and GitHub repository retain their existing contracts. These
are active dependencies of installed 1.3.1 clients, not competing product names.
Canonical public download: `EverySync-Setup-V.exe`. Compatibility alias:
`OneDrivePCSync-Setup-V.exe`, byte-identical, referenced by `update.json`.
No user data migration or production merge is part of this branch task.

## Steps

1. Branding assets and owner (low risk; no dependencies): update
   `src/app_info.py` with product name and version 1.4.0; create
   `ui/resources/app.svg` and regenerate `app.ico` from the approved mark.
   Add focused branding tests for visible identity and tray state differences.
2. Product surfaces (low risk; depends on 1): use the shared identity/logo in
   `ui/main_window.py`, `ui/pages/about.py`, `ui/app.py`,
   `ui/resources/icons.py`, `backend/notifications.py`,
   `backend/services/update_service.py`, `desktop_entry.py`,
   `src/sync_runner.py`, `src/shutdown_monitor.py` and notification content.
   Preserve meaningful tray status badges and existing control semantics.
3. Windows delivery (medium risk; depends on 1): update
   `packaging/windows-installer.iss`, `packaging/OneDrivePCSync.spec`,
   `scripts/release_metadata.py`, `Build-Windows.ps1`, `.gitignore`,
   `.github/workflows/windows-release.yml` and installer verification paths.
   Generate Windows product/version metadata, preserve upgrade identity,
   replace only known generated old-brand shortcuts, publish the canonical
   installer plus compatibility alias. Test old-updater manifest acceptance and
   byte/hash identity of both installer names before implementation.
4. Documentation and acceptance (low risk; depends on 2-3): update `README.md`
   and `CHANGELOG.md`; extend frozen diagnostics to verify EverySync branding.
   Run full regressions, build and inspect native icon/product resources,
   render isolated screenshots and validate install/upgrade where permitted.
5. Review and handoff (depends on 4): independent spec review, then code/infra
   review; fix findings; commit and push branch, create a draft PR to exercise
   Windows CI, follow it through downloadable artifacts. Preserve master.

## Verification and stop condition

Existing tests are the behavior baseline. New tests cover branding/state and
the compatibility distribution contract, not textual implementation details.
Run the complete suite with isolated temporary directories. Native Windows CI
must validate the shipping EXE and installer lifecycle. Handoff includes the
branch/commit, installer and draft PR, and any remaining integration step.

## Progress

- Initial state: only user-owned `shutdown_monitor_status.json` is untracked in
  the primary checkout. No user edits enter this task's commit.
- Plan accepted under the user's instruction to do all necessary work.
- Steps 1-4 complete; independent specification and code/infra reviews passed.
- Full regression suite: 243 passed, 2 skipped (baseline: 236 passed, 2 skipped).
- Native frozen EXE: EverySync identity/resources, 29 navigation clicks,
  startup registration, manual update check, isolated copy/dry-run/force-sync
  and shutdown monitor checks passed.
- Legacy validation installer -> EverySync validation installer: branding,
  exact shortcut replacement, desktop choice, unrelated file preservation,
  configuration/startup/history preservation and uninstall checks passed.
- Detached update verified under Windows PowerShell 5.1: synchronization-lock
  wait, configuration, four scheduled-task enabled states and staged cleanup.
- Original updater source from `95da7eb`, configured as version 1.3.1.4,
  accepted the generated manifest and downloaded/verified the actual installer
  through an isolated transport. This is a compatibility check, not a claim of
  production publication.
- EXE and setup contain all nine icon sizes; EXE ProductName/FileDescription
  are EverySync. Canonical and legacy installer bytes/checksums match.
- Step 5: commit/push and draft-PR CI provide the final remote handoff evidence;
  master integration and production release remain a separate user action.
