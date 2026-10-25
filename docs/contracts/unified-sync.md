# Unified synchronization contract — v1

Date: 2026-10-19. Scope: the user-approved unified synchronization hierarchy.
This is a Python-internal configuration/coordinator contract, not a network API.
It supplements [the cloud contract](cloud-sync.md); existing leaf safety rules
remain authoritative. Implementation requires review of this contract.

## Configuration and ownership

Models and validation helpers live in `src/sync_groups.py`.
`AppConfig.sync_groups` is an optional list, defaulting to empty. A
`SyncGroupConfig` has `id`, `name`, `local_path`, ordered `destinations`,
`enabled=True`, `fallback_on_unavailable=False`, and
`allow_untracked_download=False`. A `SyncDestinationConfig` has `job_id`,
`upload_enabled=True`, and `download_enabled=True`.

Each `job_id` refers to exactly one existing `FolderSyncConfig` or
`RemoteJobConfig`. Existing folders and remote jobs remain the execution leaves;
their IDs, settings, backup identities, paths and history are preserved.

New UI destinations compose `EverySync/<sync name>` below the selected parent;
backups use the sibling `EverySync Backups/<sync name>` tree. Existing saved
destinations keep their paths unless the destination is changed. Local
`BackupSettings.directory_name` optionally supplies the safe single-component
backup directory; its absence retains the legacy folder-ID directory. Runtime
and configuration overlap checks use the same effective backup directory.

Boolean fields require actual booleans; names/local paths require nonblank
strings. Destination `job_id` preserves the referenced legacy ID syntax rather
than imposing new safe-ID rules on existing folder IDs.
Validation rejects unknown fields, wrong types, unsafe new IDs, duplicate group
IDs, IDs colliding with leaf IDs, empty destinations, missing references,
repeated references within/across groups, mismatched resolved local roots and
unsafe overlaps between a group's source, its destinations and backup roots.
At least one direction is enabled per destination. A group may contain local,
network and connected-provider leaves together. The ordering of the list is the
download priority; changing order does not change a destination's identity.
Explicit groups cannot contain bidirectional leaves in v1. Existing ungrouped
bidirectional jobs retain their behavior, including after editing their name or
paths without adding destinations; the UI describes their separate
two-way action rather than promising a one-way transfer.
Groups containing filesystem folder-pair destinations require
`copy_engine.copy_subdirectories=True`: configuration validation rejects the
combination before persistence or transfer. This v1 restriction prevents a
nonrecursive local copy from being published as a complete recursive generation.
Existing ungrouped nonrecursive folder pairs retain their behavior; remote-only
groups retain their existing recursive provider behavior.

Grouped leaves are excluded from independent bulk execution, including when a
group is disabled. Group and leaf enablement both apply; the hierarchy does not
silently enable a previously disabled leaf. Unreferenced legacy leaves appear
as implicit single-destination activities and retain their execution semantics.
Never infer grouping from matching names or local paths.

## Operations and integration seams

`SyncManager` owns routing between ungrouped leaves and explicit groups for GUI,
command-line, startup, shutdown and monitor operations. It delegates leaf work
to the existing local/cloud engines under the existing application lock.
Leaf adapters must not reacquire the owning application lock.

`src/group_sync.py` provides
`GroupSyncRunner(config, state_root, *, transport_factory=None)` and
`run(group, direction, *, defer=False) -> list[FolderSyncOutcome]`.
It may receive an internally owned local-leaf callback to reuse the current
`SyncManager._sync_single_folder` safety implementation without recursion.
`state_root` is the chosen configuration's existing cloud state directory.
The group ledger is `state_root / "groups.json"`; it is independently versioned
and atomically saved. No GUI imports belong in models, ledger or coordinator.

`SyncService.request_direction_sync(direction: SyncDirection | str,
item_id: str) -> bool` starts one explicit manual upload/download of an explicit
group or implicit legacy singleton, subject to pause, busy and lock checks.
Singleton execution never creates a group or changes saved configuration.
Existing ungrouped bidirectional jobs keep their bidirectional engine semantics;
their UI action must say "Synchronize both folders" rather than one-way upload.
This constructs
an operation-local configuration; it never changes saved startup/shutdown
directions or enablement. It may reuse the existing worker by constructing a
filtered temporary config whose matching startup/download or shutdown/upload
trigger is enabled with the explicitly requested direction. This manual action
does not require the corresponding scheduled trigger to be enabled. The
existing `request_sync(operation, folder_id=None, ignore_threshold=False)`
retains its signature and configured-direction semantics, including selecting
a group by ID for a configured trigger. Bulk trigger operations retain
configured directions.
Selecting a grouped leaf through an older API must not accidentally execute its
siblings or bypass the group's freshness/pending guards.

The runner returns existing per-leaf `FolderSyncOutcome` records plus one group
summary keyed by the group ID. Summary success requires every selected upload
destination to succeed, or one complete download to succeed. Partial upload is
a failed aggregate with explicit success/total counts and individual failures;
history and notifications must not describe it as complete. Backup and restore
continue to address the original leaf ID.

## Upload

Visit every enabled upload destination. A destination-scoped failure does not
prevent independent destinations from being attempted. Cancellation, invalid
source data and a source that changes during a generation stop further work.
No concurrency across destinations is needed in v1.

Fingerprint the local source before the generation and verify it around each
upload. Publish a destination as complete only after successful leaf execution,
source stability and verification that every expected source file is present
with matching content. Count-only local verification and leaf success alone do
not establish generation completeness: destination-newer protection can skip
files. Preserve destination-only files according to the existing additive-only
contract; record their observed inventory too. A changed source or failed check
leaves that destination incomplete. Do not claim a cross-provider transaction.

Before writes, durably record an attempted generation and incomplete destination
states. Commit each completed destination independently and atomically. Failed
uploads stay visible and can be retried; a later download cannot erase this
pending information or download an older successful destination silently.
Dry run performs probes/planning only and changes neither ledger nor leaf state.

## Ordered download and error policy

Before any write, probe whole sources in saved priority order. Select exactly
one source for the whole operation. Never fill individual missing files from
later services. After download starts, any error stops the operation; no fallback
to another source may continue writing into the same local folder.

Revalidate the selected source inventory against its ledger evidence immediately
before invoking its writing leaf; a successful earlier probe is insufficient.
Cancellation stops the group and is never an unavailable-source fallback.

The default fallback condition is confirmed absence of the activity directory,
after validating/accessing its account or filesystem root. `CloudNotFound` at
the activity path qualifies; an inaccessible account root does not. For a local
or network folder, a missing/unreachable volume or parent is unavailable rather
than proof of absence. An existing empty directory is an explicit empty-source
result, preserving local data; it is not a missing copy.

With `fallback_on_unavailable=True`, a typed, bounded transport/network
unavailability result may also advance to the next source. Authentication,
permission, malformed metadata, case/path ambiguity, conflicts, incomplete
copies, known prior copies and pending opposite-direction work never qualify.
Do not classify arbitrary exception text as an unavailable service. Unknown
failures stop with a safe error. If no source qualifies, leave local data intact.

Before either direction, check pending work for every group leaf and the group.
Opposite-direction pending work blocks the whole group before any leaf writes.
Do not invoke the cloud runner's automatic opposite-direction recovery inside a
group: it could modify the common source midway through fanout. Existing cloud
recovery rules cannot be bypassed by selecting another destination. Resolve or
block pending upload before downloading a group; never automatically perform a
new download first. Shutdown deferral retains the group direction and does not
queue every fallback source as independent downloads. No network process starts
during session-end deferral.

## Generation ledger and limits

Keep additive group bookkeeping beside the selected configuration's cloud
state, in its own versioned atomic file. Corrupt or unsupported state fails
closed. It stores no credentials: group/source identity, attempted generation,
content fingerprints, and per-destination identity/status/verified inventory.
Bind records to resolved source and leaf endpoint identities; path or account
changes invalidate only the affected evidence. Order/display changes do not.
Retain pending identity records when an endpoint changes until the pending work
is explicitly resolved; an edit cannot convert incomplete evidence into an
untracked copy eligible for opt-in download.

A source whose actual content no longer matches its last verified inventory is
untracked, not implicitly current. A destination from an older known generation
is explicitly prior; an attempted but unverified copy is incomplete. Neither is
selected automatically. Show which destination needs a successful upload.

`allow_untracked_download=True` is an explicit advanced choice for preexisting
copies with no usable recorded generation. It permits untracked data only;
it does not override known incomplete/prior status, corrupt state, pending work,
conflicts or authentication. The UI labels such copies "Freshness unknown" and
does not report them as verified/current. Legacy implicit activities retain
their previous ability to use existing copies.

This ledger provides evidence from this configuration on this PC. It does not
establish global recency across PCs, coordinate independent writers or publish
portable complete-copy manifests. The UI/docs must state that limit. Compare
content before use; an ordinary listing timestamp is not a generation marker.

## UI contract

One navigation entry, "Synchronizations", owns all activities. "Connections"
continues to own account management. Use one searchable list and one creation
entry point. Each activity exposes its PC folder and ordered destinations,
upload/download participation and clear status text. Offer keyboard-accessible
Move up/Move down; drag ordering is optional supplementary interaction.

Use "Send to destinations" and "Download to this PC" for directional actions;
show the selected source and fallback reason. Advanced settings explain unknown
freshness and unavailable-service fallback. Report partial results per
destination, empty/absent/unavailable/authentication/incomplete/prior states,
busy/paused/dry-run and cancellation. Do not hide errors behind color alone.
Running groups offer Stop after current destination: cancellation is cooperative
at destination boundaries and does not interrupt a leaf while it is copying.
Remaining destinations retain incomplete/pending evidence. A transfer which has
already completed is not relabeled as cancelled.
Keep destination-specific local ZIP versus cloud snapshot recovery accessible.
Removing a reference/group never deletes user files or backups. It must not
silently turn removed references into newly automatic jobs; preserve or disable
them explicitly in the same atomic configuration update.

## Verification evidence required

Tests cover legacy round trips, invalid references/overlaps, mixed upload with
partial success, stable and changing sources, generation bookkeeping failure,
confirmed absence fallback, empty source, authentication and malformed listings,
opt-in unavailable fallback, prior/incomplete/untracked copies, error after first
write, pending recovery, dry run, shutdown deferral and grouped-leaf routing.
UI checks cover one navigation item, legacy and mixed activities, creation/edit,
keyboard ordering, clear directions, partial and unknown status, backup access
and pause/busy behavior. Use synthetic local/fake providers only; never initiate
live account transfers or modify installed EverySync as implementation testing.
