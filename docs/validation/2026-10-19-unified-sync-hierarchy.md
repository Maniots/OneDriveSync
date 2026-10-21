# Unified synchronization hierarchy validation

Date: 2026-10-19. Branch: `feat/unified-sync-hierarchy`.
Base: `2f22840`; approved requirements and safety defaults are recorded in the
[contract](../contracts/unified-sync.md), with
[migration/rollback](../specs/2026-10-19-unified-sync-hierarchy-migration.md).

## Source verification

- Clean isolated baseline: **508 passed, 2 skipped**.
- Complete updated suite: **572 passed, 2 skipped** with the pinned native rclone
  available. The skips concern unavailable symbolic-link capability, not hierarchy
  execution or provider fallback.
- After the final table rendering adjustment, the combined synchronization UI,
  rendered layout and existing functional UI regression files: **36 passed**.
- Independent spec compliance review followed by Python/security quality review
  accepted the implementation and final rendering/frozen-verifier deltas.
- `git diff --check` passed. No dependency or OAuth permission changes.

Commands run from the dedicated worktree with the existing project virtualenv:

```powershell
$env:EVERYSYNC_RCLONE = 'C:/Coding/OneDriveSync/build/tools/rclone/rclone-v1.75.2-windows-amd64/rclone.exe'
python -m pytest -q -p no:cacheprovider --basetemp=build/pytest-release-candidate
python -m pytest -q tests/test_synchronizations_ui.py tests/test_ui_layout.py tests/test_ui_regressions.py -p no:cacheprovider --basetemp=build/pytest-final-rendered-ui
```

Coverage includes legacy configuration round trips, group ownership, mixed
fanout, partial upload, stable source fingerprints, immutable interrupted-download
retries, prior-copy reassignment, missing activity versus missing account root,
permission errors, pending-edit rejection, explicit untracked/unavailable options,
dry run, session-end deferral, cancellation boundaries and manual direction
selection independent of scheduled triggers. UI journeys exercise real atomic
saves, selection/filtering, actual selected-only copies, existing two-way jobs,
account ID collisions, removal, backup access and force confirmation.

## Native application and rendering

Built a local Windows bundle using `Build-Windows.ps1 -BundleOnly` and the verified
pinned rclone archive. The local acceptance build uses build number zero; it is
not an installer update or a public release.

Native Windows acceptance exercises branding/resources, navigation, selected
copies, dry run, the real threshold confirmation with default No, ZIP backup
contents, the isolated startup setting, and monitor synchronization/exit.
The external cloud acceptance script also exercises the packaged EXE with a
mixed explicit group: upload to both destinations, provider-first download,
confirmed activity-folder absence fallback, and unchanged ledger/files in dry run.
Local evidence reports are retained under `build/`; the group assertions are now
part of the existing CI cloud-bundle verifier.

Native previews were rendered with explicitly loaded Segoe UI under Qt offscreen
and inspected at normal and compact widths. They cover the workspace, PC-folder
step, ordered-destinations step and review/options step. Final table cells keep
accounts and download priorities readable without duplicate painted text; long
paths retain full tooltips and the page scrolls vertically at minimum size.
Preview images remain local in `build/unified-sync-previews/` and use only
synthetic accounts under `example.test`.

## Scope and limits

No real cloud accounts or user files were transferred. OAuth metadata in the
root checkout, the installed application and its configuration were untouched.
The generation ledger is evidence from this configuration on this PC; it does
not coordinate independent computers or certify globally newest data. Unknown
copies require explicit permission, while known incomplete/prior copies and
opposite pending work remain blocked. Explicit groups are directional; existing
implicit bidirectional jobs keep their previous behavior. Groups containing local
folder pairs require recursive copying and reject incompatible settings before
any persistence or transfer.
