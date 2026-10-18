# Implementation plan: multi-provider synchronization

User approved the milestone direction in the preceding conversation and explicitly requested this branch and implementation. This plan operationalizes that approval; no additional permission checkpoint is needed for reversible implementation/tests.

Contract: `docs/contracts/cloud-sync.md` and `cloud-config.schema.json`. Baseline: 91697f1; existing suite 247 passed, 2 skipped (fresh run pending completion at plan creation). Worktree: `.claude/worktrees/multi-provider-sync`; branch: `feat/multi-provider-sync`.

## M1 — Configuration and compatibility (medium risk)

1. `tests/test_cloud_config.py`: RED legacy load/save, new fields round trip, unsafe path/provider/ID rejection and reference validation.
2. `src/cloud_models.py`, `src/config.py`, `src/config_manager.py`: implement immutable typed connections/jobs, bounded validation and atomic serialization; preserve legacy-only JSON compatibility. Depends on contract review.
3. `ui/pages/settings.py`: preserve new collections when replacing existing settings. Regression tests cover settings/folder edits retaining new data. Commit milestone.

## M2 — Transport and coordinator (high risk)

1. `src/cloud_credentials.py`, `src/rclone_transport.py`: RED secret encryption/roundtrip, safe environment/arguments, secure app-owned config, authenticated loopback lifecycle, configuration state and validated inventory. Pin rclone in `packaging/rclone-version.json`; prepare download with hash verification in `scripts/Prepare-Rclone.ps1`.
2. `src/cloud_sync.py`, `src/cloud_state.py`: RED additive copy, newer-file protection, threshold, snapshot-before-overwrite, content check, persistent pending/failure state, dry-run, restore and conflict planner. Use a native local provider fixture against the actual bundled tool.
3. `src/sync_manager.py`, `src/sync_runner.py`, `ui/workers/sync_worker.py`, `backend/services/sync_service.py`: wire jobs through existing worker, shared lock, history and exit/update wait. Keep local behavior and execute remote jobs serially after legacy pairs. Shutdown monitor explicitly defers cloud work instead of spawning during teardown. Commit milestone.

## M3 — Account/job experience and distribution (high risk)

1. `backend/services/cloud_service.py`, `ui/pages/connections.py`, `ui/pages/cloud_sync.py`: asynchronous service actions, guided provider setup, browser OAuth continuation, test/delete connections, job add/edit/delete/toggle, upload/download, snapshots and restore. Blocking/error/retry states remain visible; secret fields masked; config changes blocked while sync active. Inject service/transport for isolated UI acceptance.
2. `ui/main_window.py`: append pages without changing existing indexes; generic sidebar caption. Regression test navigation and form persistence.
3. `Build-Windows.ps1`, `packaging/OneDrivePCSync.spec`, `.github/workflows/windows-release.yml`: bundle pinned rclone and notices; test native fixture transfers in CI; no production release from this branch.
4. `README.md`, `docs/cloud-sync.md`, `CHANGELOG.md`: document setup, OAuth app prerequisites, snapshots, provider test status, offline/shutdown semantics and rollback. Commit milestone.

## M4 — Bidirectional and recovery (high risk)

1. Exercise persisted baselines, first-run conflicts, double changes, deletes not propagated, interrupted run recovery, endpoint identity changes and snapshots through real local fixtures. Implement only conservative additive reconciliation; surface conflicts for explicit resolution.
2. Final independent spec then Python/security/infra reviews. Address findings and rerun affected checks.
3. Full regression suite, Windows build, native UI/bundle and native transfer/snapshot/restore acceptance. Record real-account tests honestly as pending when unavailable. Update checkpoint and push all milestones to the requested branch. Never merge into master without user instruction.

## Continuation checkpoint

- Design/contract independently reviewed and approved before implementation.
- M1 implemented and approved in separate spec and Python quality reviews; 51 fresh configuration/UI preservation tests passed. Legacy baseline was 247 passed, 2 skipped; all existing regressions remained green during M1.
- M2 and M4 core implemented and independently approved after spec and Python/security reviews. Fresh focused suite: 111 passed, including native rclone. Review regressions prove selected copies replace differing bytes even with equal size/mtime and cross-endpoint Windows case/prefix/file-directory aliases stop before any writes.
- M3 pages, guided setup, packaging and documentation are implemented and independently approved. Final Python suite: 375 passed, 2 legacy symlink-privilege skips. Frozen desktop/cloud acceptance, installer upgrade/uninstall and detached update/restart checks passed. GitHub Windows run 39107752191 passed for implementation commit 87ffc4f.
- Native validation exposed an existing temporary-task timer escaping the fixture environment. Verifiers now remove automatic triggers immediately after each setup while preserving Enabled/action state; independent infra/security review and native reruns passed. Impact and containment are recorded in `docs/validation/2026-10-18-cloud-sync.md`.
- User has no test accounts and requested guided account setup. Actual cloud-account certification remains pending; isolated native transfer tests do not substitute for it.
