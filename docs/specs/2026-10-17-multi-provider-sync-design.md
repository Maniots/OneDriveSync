# EverySync multi-provider synchronization

Approved direction: the user's 2026-10-17 instruction to create a branch and follow the milestones from the preceding feasibility analysis. Implementation remains on `feat/multi-provider-sync`, not master.

## Milestones and observable behavior

1. Foundation: preserve legacy `folders` and local copy/ZIP semantics. Add non-secret `connections` and `remote_jobs` to the same atomic configuration. Existing settings/folder edits must preserve both new collections. IDs are unique across legacy folders and remote jobs.
2. Cloud transfers: use a pinned, verified rclone binary behind an internal transport adapter. OneDrive online, Google Drive and S3 share the same safe engine. Add a local provider for native integration fixtures. Upload/download are additive, protect newer destinations, validate inventories, enforce thresholds and verify copies. Empty/missing remote folders and unavailable networks are distinct states. Never turn an inventory error into an empty directory.
3. Experience and delivery: add Connections and Cloud Sync pages without changing the indexes of existing pages. Guide creation/authentication, connection testing and remote-job management; operations run off the GUI thread and share the existing sync lock/busy state. Include rclone in Windows builds and CI. Curated additional connectors: SFTP, WebDAV/Nextcloud, Dropbox, Azure Blob and B2. Availability means configurable, not certified against an account we cannot access.
4. Reconciliation: persistent state and retry records, conservative bidirectional planning. Changed files on both sides are conflicts, not silently selected by timestamps. Never propagate deletes. Failed/incomplete runs do not advance the baseline. Interrupted work can be retried; no claim of universal byte-level resume or distributed transaction support. Cloud authentication and concurrent-writer behavior require account-based acceptance before production certification.

## Configuration and ownership

`ConnectionConfig`: id, display name, provider and root. Rclone remote names are generated from safe IDs. Account options, tokens and passwords never enter config.json or sync history. Connection roots bound all remote access; job paths are nonempty relative paths without `..`, absolute roots, colon remote substitutions or the reserved `.everysync` tree.

`RemoteJobConfig`: id, name, enabled, local_path, connection_id, remote_path, minimum_sync_percentage, verify_after_sync, backup_enabled and bidirectional. Trigger directions and enablement retain existing settings. Local paths use the existing dangerous-root checks. Jobs execute after legacy folders, serially, under the caller's shared sync lock. Per-folder UI requests select exactly one legacy folder or remote job.

The canonical new transport contract is `docs/contracts/cloud-sync.md`; public configuration shape is `docs/contracts/cloud-config.schema.json`. There is no new public HTTP API. rclone's authenticated loopback API is an existing third-party boundary; expose only a bounded set of operations through our adapter.

## Credentials and processes

Use an app-owned encrypted rclone config and a random config password protected with Windows DPAPI for the current user. Never read or modify the user's unrelated rclone configuration. The encryption password reaches child processes through private environment or stdin, not command arguments. Configuration responses/logs must not echo tokens or credentials. A per-instance authenticated loopback rclone daemon is started only when needed and closed deterministically. Scheduler/monitor runs use the same user-owned credential store. Non-Windows tests inject an ephemeral secret store; production credentials fail closed when protection is unavailable.

Connection setup uses rclone config/create and config/update nonInteractive state/options. OAuth opens the system browser; questions are displayed as guided controls, with secret answers masked. Cancel cleans up only the pending app-owned connection. Retry/test errors are actionable and sanitized. Editing config is blocked while sync is active.

## Backups, verification and interrupted work

Legacy ZIP backups stay unchanged. Remote jobs explicitly use timestamped full directory snapshots under `<connection root>/.everysync/backups/<job id>/<run id>`, outside the live job path. Snapshot must succeed before overwriting; dry run creates nothing. Initial empty destinations need no snapshot. Restore targets a separately validated local folder and uses the same lock. Retention/format are not silently equated to the legacy daily ZIP policy.

Inventory entries validate relative paths, duplicates/case collisions, hashes and sizes before local writes. Counts are a threshold guard, not proof of identity. Verification uses comparable hashes when available and falls back to an actual transfer check; unverified transfers cannot be reported as verified. Local downloads must retain destination-only files and newer files. Multi-file transfer is not atomic; snapshots and retry state are explicit recovery mechanisms.

The shutdown path must not depend on starting a new network transfer process late in session teardown: defer remote jobs with a persisted retry reason, keep legacy local shutdown copies, and retry remote work during a normal subsequent run. Periodic/manual/sign-in transfers are the main cloud path.

## Evidence and limits

Fresh regression suite, configuration round trips, secret isolation, native rclone local-to-local fixtures, snapshot/restore, threshold failures, interrupted-transfer retry and bidirectional conflict tests are required. Build the Windows bundle and verify native navigation with isolated credentials/data. Real OneDrive/Google/S3 account acceptance is separately recorded and stays unverified until credentials and isolated test destinations are available.
