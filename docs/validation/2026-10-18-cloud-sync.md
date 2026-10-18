# Cloud synchronization validation — 2026-10-18

Branch: `feat/multi-provider-sync`. Product implementation: `87ffc4f`. Local Windows build: `1.5.0.0`. Review: [draft PR #6](https://github.com/Maniots/OneDriveSync/pull/6).

## Evidence

| Check | Result |
| --- | --- |
| Full regression suite | `375 passed, 2 skipped` in 64.12 seconds. The skipped legacy symlink tests require symlink creation privileges unavailable in this environment. Native cloud/rclone tests ran. |
| Focused configuration, credentials, transport, coordinator and integration suite | `111 passed`, including native transfers, snapshots, restore and recovery. |
| UI/account cancellation and updater tests | Passed, including multi-question authorization, masked secrets, pending-only cleanup, stale worker completion, restore waiting, updater deferral and dialog ownership. |
| Independent reviews | Spec, Python/security and packaging/CI reviews approved after fixes. |
| Windows build | PyInstaller bundle and Inno Setup installer succeeded; pinned rclone v1.75.2 and MIT notice included. |
| Frozen desktop acceptance | Passed: 30 native navigation clicks, branding, Run at startup, dry run, actual copy, force sync, shutdown monitor sync and monitor exit. |
| Frozen cloud acceptance | Passed: real Windows DPAPI and encrypted config, additive upload/download, newer destination and extra-file preservation, full snapshot/restore, dry run, pending upload before download, and conflict preservation. |
| Installer upgrade lifecycle | Passed against the retained previous validation installer: branding, shortcut migration, configuration/startup preservation, installed UI and uninstall cleanup. |
| Local detached updater | Passed after fixing validation task isolation: synchronization-lock wait, visible restart, hidden-window activation, one instance, configuration/task-state preservation and staged installer cleanup. A separate loop also passed 20 consecutive activations. |
| GitHub Windows workflow | [Run 39107752191](https://github.com/Maniots/OneDriveSync/actions/runs/39107752191) passed for implementation commit `87ffc4f`, including installer and update/restart acceptance. Production publication was skipped on the PR. |

The two review regressions first failed and then passed: differing bytes with equal size/mtime are transferred when selected by the content planner; case/prefix/file-directory aliases across endpoints stop before snapshots or live writes. Two UI regressions also failed before fixes and then passed: reselecting an activity after New, and each snapshot dialog retaining its original job.

## Reproduce

From Windows PowerShell in the repository, with the development virtual environment prepared:

```powershell
.\scripts\Prepare-Rclone.ps1
.\.venv\Scripts\python.exe -m pytest tests -q --basetemp build/cloud-release-tests -p no:cacheprovider
.\Build-Windows.ps1
.\.venv\Scripts\python.exe scripts/verify_windows_bundle.py dist/OneDrivePCSync/OneDrivePCSync.exe
.\.venv\Scripts\python.exe scripts/verify_cloud_bundle.py dist/OneDrivePCSync/OneDrivePCSync.exe
ISCC.exe /Qp /DValidationBuild packaging/windows-installer.iss
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/Verify-WindowsInstaller.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/Verify-WindowsUpdate.ps1 -BaselineInstaller <previous-validation-setup.exe> -UpdateInstaller dist/installer/EverySync-Validation-Setup.exe -ExpectedVersion 1.5.0.0
```

Corrected native installer checks use separate validation registration, isolated data and temporary task folders with automatic triggers removed. They do not broadcast shutdown or use production accounts/data. See the initial isolation failure below.

## Initial test isolation failure and containment

An existing verifier registered a periodic validation task starting after one minute. Although it did not explicitly run that task, its timer fired during a long install at 09:34 Europe/Rome. Scheduled actions inherited the real user's environment, so this fixture process used the real legacy configuration and was incorrectly counted as a second desktop instance. The updater itself installed and restarted successfully.

The interrupted legacy run removed one expired backup through retention and began a new archive. No copy-engine start or completed synchronization was recorded. Read-only inspection found 46 current source/destination files identical by SHA-256 and seven retained archives for the affected activity valid by ZIP CRC. The deleted expired archive was not recovered; repository matches were unrelated test placeholders. The new incomplete archive (552 bytes) was preserved by renaming it with an `.incomplete` suffix, under the actual synchronization lock and only after checking its exact path, size, SHA-256 and invalid ZIP structure. No valid archive or synchronized file was changed during containment.

The verifier fix removes automatic triggers immediately after each task setup, accepts only owned GUID validation folders and matching executable actions, and checks zero triggers plus preserved Enabled state. Both native automation and the original updater scenario then passed. Product scheduling behavior is unchanged. Independent infra/security review approved this correction.

## Remaining external certification

No Microsoft/Google OAuth apps, S3 buckets or other cloud service test accounts were available. Real provider authentication, permissions, account policies, quotas and interrupted network transfers remain to be certified. The setup guide is [cloud-sync.md](../cloud-sync.md); these local tests do not certify every provider.

Remote snapshots have manual retention. Hash fallback can require downloading unchanged files and incur traffic/cost. A local baseline and lock cannot serialize writers on different computers. These limits are documented in the UI/setup guide and are not represented as completed live-account tests.
