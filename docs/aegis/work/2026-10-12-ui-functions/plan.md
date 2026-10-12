# Complete audited UI functionality

User authorized implementation of missing functionality after the full-project audit, extending the earlier frontend-only request to required backend work.
TaskStartSnapshot: clean working tree, HEAD d077c83f99fd78e52c22cdc6eb9812c5bc937b39. No branch, deployment, live task mutation, or user data operations required for development.
Change necessity: visible actions lack handlers, configurable behavior lacks consumers, and displayed results can be false.
Architecture review required: yes, bounded to history persistence, archive validation, and copy/monitor ownership. TDD route: light/risk-based; meaningful safety and integration regressions required.

1. Backup actions: open containing folder, delete selected managed archive with confirmation, restore selected archive to a chosen directory with confirmation, validate archive members against traversal/reparse points, share sync lock and run heavy extraction off GUI thread. BackupService owns operations. No live user archive modified during development.
2. Copy/sync: implement retries/waits, bounded file and folder concurrency, recursive/empty-directory flags, FAT timestamp precision and safe explicit link handling; propagate copy errors. Monitor Mode belongs to GUI SyncService and watches configured sources while open; CLI one-shot sync remains finite. Preserve no-delete/XO/dry-run safeguards.
3. Scheduler: query language-independent Windows Task Scheduler COM via PowerShell JSON; derive enabled state, actual timestamps and trigger delays/intervals; real error/missing states. Maintain OS task mutation handlers.
4. Metadata: persist GUI/CLI run history in SQLite beside configuration; use it for folder/dashboard history, truthful direction, storage totals and next task; distinguish configured/no archive/error backup states.
5. Logs/settings: show all supported severities, real success filtering, update logger levels without duplicate handlers, validate tuning limits. Retain existing modern layout.
6. Review spec compliance, then code quality; resolve findings. Run targeted safety/integration tests, full suite and render affected pages. No commit/push unless user requests it.

Acceptance: all active audit F01-F14 are implemented, or an explicitly documented meaningful supported behavior replaces misleading presentation. No inert enabled controls. Restore/delete remain explicit user actions. Legacy unused wrappers are outside active UI scope.

Checkpoint: all six slices completed. Spec review passed after correcting failed dry-run status. Quality review passed after correcting backup/copy overlap, protection of all managed backup directories, monitored failure retries, asynchronous scheduler reads, and QObject-bound dashboard signal cleanup. Root render verification also corrected SQLite handle closure and backup action widths.

Final evidence: 174 passed, 2 skipped (tests total176), full suite exit0, build/ui-functions/tests.xml. 71 targeted safety/integration/layout tests passed at preceding checkpoint; final suite includes database handle regression. Fourteen populated page renders verified at1100x700 and1440x960; build/ui-functions/render.json. git diff --check passed; no staging/commit/branch/push. All fixtures/artifacts used temporary directories/build. Final verification excludes installed task mutations, real shutdown, and live OneDrive propagation. Read-only live COM query correctly reports absent task folder as Not Found.

Environment recovery: a full-suite attempt failed only because the shared external pytest temp root was inaccessible. Re-ran using explicit workspace basetemp and disabled pytest cache to avoid unrelated permission warnings. Native dashboard teardown regression was reproduced, corrected, and rechecked through isolated plus complete suites. Neither failed attempt was counted as passing evidence.

Delivered semantics: Monitor operates while GUI is open; CLI sync stays one-shot. Junctions outside declared source stay excluded even when internal links are allowed. Storage means local free disk space at the configured OneDrive path. History retains1000run records; chart shows last100. Unused legacy wrappers remain outside active UI scope. Confidence B: target and regressions verified, external live integrations bounded above.
