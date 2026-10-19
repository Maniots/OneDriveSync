# Unified synchronization: additive migration and rollback

Date: 2026-10-19. Related [runtime contract](../contracts/unified-sync.md).

The user has authorized implementation. This plan covers application-managed
configuration changes; no production user configuration is migrated during
development or testing.

## Before and after

Existing `folders`, `connections`, `remote_jobs`, general settings, trigger
directions, safety limits and copy settings retain their schema and IDs.
An optional top-level `sync_groups` array adds explicit ownership/order of
existing leaves. Missing/empty `sync_groups` means the previous behavior.
Save omits the empty addition to preserve legacy JSON shape.

Loading an old configuration is read-only and creates no groups, directories,
credentials, state files or backups. The unified UI projects every unowned leaf
as a single-destination activity. Merely opening or upgrading the UI never
combines two activities sharing a source path or display name.

Creating/editing an explicit activity atomically saves its group and all
referenced leaves. New leaf IDs use validated safe IDs; unchanged leaves retain
their identities and settings. Membership is exclusive. Configuration validation
runs before persistence. Changing membership must reject pending work or retain
the guarded old identity until resolved; it cannot clear retry evidence.

Deleting a group/destination changes configuration only. The same atomic update
must explicitly disable retained orphan leaves (or remove the selected leaf
configuration after user confirmation), so they cannot unexpectedly return as
automatic independent jobs. Existing on-disk backup/state/history data is kept.

The new generation ledger is separate and additive. Existing cloud `state.json`,
credential store, ZIPs, snapshots and SQLite history are never rewritten into
group records. No credentials or private OAuth registration metadata is copied.

## Dry run and acceptance

Use synthetic fixtures containing enabled/disabled local leaves, remote jobs,
bidirectional jobs, environment-variable paths, backups and old pending work.
Record the input bytes, parse/load/save/reload and verify original fields and
IDs. Assert loading alone writes no files. Compare operation selections before
and after: no groups means identical legacy dispatch; an explicit group owns
each selected leaf exactly once; disabled groups dispatch none of their leaves.

Exercise failed validation and interrupted atomic persistence: the old file
must remain usable and old retry/backup evidence unchanged. Group dry run
performs zero transfer, configuration, generation, snapshot or baseline writes.
Verify UI actions preserve original safety and recovery settings.

## Rollback

Before adopting explicit groups with real data, retain a private backup of the
original configuration alongside its own private state. Roll back the program
and restore that original configuration to recover exactly the previous job
selection. Never run an older binary against a configuration containing groups:
it may ignore group ownership and execute all underlying leaves independently.

The generation ledger may remain unused after rollback; no deletion is needed.
Restore old cloud state only from a coherent backup, never discard pending work
to force a download. Restore requires stopping EverySync/monitor first and must
not overwrite a live writer. Data files and backups need no migration rollback
because configuration adoption never moves or removes them.

Rollback does not undo user-requested synchronization transfers that occurred
after adoption. Recovery of those files uses the existing ZIP/cloud snapshots
and per-destination history, preserving the original leaf IDs.
