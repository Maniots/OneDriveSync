# Unified synchronization hierarchy implementation

The user requested implementation of the saved
[analysis](../specs/2026-10-19-unified-sync-hierarchy-analysis.md) on 2026-10-19.
The reviewed [contract](../contracts/unified-sync.md) resolves the safety defaults.
This authorization covers implementation and normal verification, commit and push;
it does not request a merge, live-account transfer or installed-app update.

## Architecture and migration

Add explicit groups referencing existing local and remote jobs. Ungrouped jobs
appear as independent single-destination synchronizations. Preserve IDs, paths,
credentials, backups, history and legacy behavior; never guess groups from names
or shared paths. Only explicit editing persists new group configuration.

Upload fans out to enabled destinations. Download selects one whole-folder source
in saved order and falls back only on confirmed absence by default. Corrupt,
incomplete, known older or pending state stops the operation. Unknown provenance
and unavailable-service fallback require explicit activity options. Provenance
is local bookkeeping, not cross-PC certification or a distributed transaction.

## Implementation slices

1. **Models and validated persistence** (high risk; no dependencies): add
   `src/sync_groups.py`; extend `src/config.py` and `src/config_manager.py` with
   optional group serialization and strict reference/overlap validation. Existing
   configs round-trip unchanged. Test malformed groups, shared leaves, mismatched
   local roots and preservation of IDs and backup settings before implementation.
2. **Safe hierarchy execution** (high risk; depends on 1): add
   `src/group_sync.py` and atomic group bookkeeping; integrate group selection
   into `src/sync_manager.py` and explicit manual direction into
   `backend/services/sync_service.py`. Reuse the lock-owned worker and leaf safety
   engines. Add typed transport absence/unavailability only where provable.
   Cover partial upload, stable content verification, ordered download, empty vs
   absent, unknown/stale/incomplete data, dry run, pending recovery and shutdown
   deferral. Use synthetic local trees and bounded transports first.
3. **Unified native UI** (medium risk; depends on public model/service contract):
   add `ui/pages/synchronizations.py` and `ui/widgets/synchronization_editor.py`.
   Show implicit and explicit groups together, search/filter, clear per-destination
   status, accessible order controls, explicit send/download buttons, and a single
   creation/editing flow with advanced settings. Update `ui/main_window.py`
   navigation and references in Connections/Settings. Keep existing backup and
   snapshot recovery reachable. Test actual save/reload, editing an existing leaf,
   destination ordering, cancellation, removal preservation and explicit actions.
4. **Integration and delivery** (medium risk; depends on 1-3): run focused tests,
   full suite with pinned native rclone, native previews with synthetic content at
   minimum and normal sizes, independent spec then Python/security review. Resolve
   findings; update `docs/cloud-sync.md`, `README.md`, `CHANGELOG.md` and validation
   evidence. Commit and push only task files on `feat/unified-sync-hierarchy`.

## Verification boundaries

- Baseline: clean dedicated worktree at `a4b7611`; the root checkout contains
  unrelated local OAuth metadata and runtime status that are outside this task.
- TDD applies to new behavioral surfaces: observe missing behavior, implement,
  rerun and cover failure/recovery next. Do not add implementation-mirroring tests.
- All task fixtures are disposable synthetic local data. No OAuth changes,
  production migration, external-account writes, installer execution or merge.
- UI verification uses the existing PySide6 theme and native offscreen rendering;
  inspect screenshots, accessible action names, long paths and narrow layouts.
- Final evidence distinguishes tested local engine behavior from untested live
  provider availability and local provenance from cross-PC freshness.
