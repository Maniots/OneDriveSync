# Internal cloud transport contract — v1

This Python-internal contract is reviewed before implementation. It does not define a new network service. Its implementation talks only to an app-owned rclone daemon authenticated on a loopback address.

## Inputs and errors

- Connections and jobs must pass cloud-config.schema.json and semantic validation before transport access.
- Remote identity derives from a connection ID; no inline rclone remote specifications or arbitrary command flags are accepted from configuration.
- Operations accept scoped, normalized paths. `.`, `..`, absolute remote paths, embedded remotes, NUL and reserved metadata traversal are rejected. Provider-reported entries receive the same validation before reaching a local destination.
- Safe-ID syntax applies only to new connection/job IDs; legacy folder IDs retain existing validation. Reject Windows device names, alternate data stream syntax, trailing-dot/space and case-colliding names before local writes. Validate resolved local containment and reject symlink/junction/reparse escapes. A local fixture provider cannot overlap or contain its job's local tree, including backup destinations.
- Errors raise `CloudSyncError` with a user-safe message. Provider credential bodies, bearer tokens, signed URLs and daemon passwords never appear in errors or logs. Timeout/auth/unavailable/verification/conflict are reported as failures, not empty success.
- Snapshot completion requires verification and a completion marker before it can be restored. Reconstruct restore references from validated connection/job/run IDs, never an arbitrary caller-supplied remote path.

## Adapter operations

- `inventory(connection, relative_path) -> dict[str, FileEntry]`: complete recursive file listing including size, normalized UTC modified time and optional named hashes. Missing job directory returns empty only on a confirmed not-found response. Authentication/listing failures raise. A listing never follows escaped paths or ambiguous duplicate names.
- `copy(source_fs, destination_fs, *, dry_run, update, ...)`: additive directory copy only; no delete, move, purge, shell, arbitrary flags or mirror operation. Apply bounded timeout/retries. Destination-newer files are protected for ordinary directional runs. EverySync supplies only internally constructed local/scoped remote paths.
- `check(source_fs, destination_fs)`: verify selected transferred files, respecting destination-only files and update semantics. Unsupported/no-hash results must be distinguished from successful content verification.
- `snapshot(connection, job, run_id) -> snapshot_ref | None`: copy the full pre-upload live destination to a unique reserved backup directory; failure blocks subsequent overwrite. Initial empty destination returns None. Never prune unrelated data.
- `restore(snapshot_ref, local_target)`: validated snapshot under the owning connection/job to a validated local target, under the same sync lock. No automatic overwrite without explicit user intent.
- `configure(connection, parameters, state=None, answer=None) -> setup_question | ready`: use existing rclone config state protocol; secrets are allowed only in memory/secure transport and encrypted config. Only registered provider options are accepted.
- Integrated sign-in (2026-10-18): the service can defer publishing an OAuth
  connection until the user chooses its root. Authorization completion returns
  `choose_root: true`; folder listing and root selection use only that service's
  authorized pending connection. List immediate safe directory names at an
  account-relative path; verify/create the explicitly selected root before save.
  Listing/selection errors retain the authorized pending connection for retry.
  Cancel/exit removes only pending credentials, including after authorization.
- `configure_google(connection, parameters, token)` is an internal transport
  operation: validated desktop client identity plus a native PKCE token are
  written together to the encrypted remote. Normal setup never accepts tokens,
  auth URLs, scopes or arbitrary engine flags from user fields.
- Auto-answer only a valid, error-free OAuth `config_is_local` browser choice;
  all account/drive/shared-drive and unknown questions remain user choices.
- `test(connection) -> success`: authenticated read of the configured root; does not write a sentinel into user data.
- `close()`: release owned subprocesses and socket resources, including failure/cancel paths.

## Coordinator semantics

Legacy local jobs retain current behavior. Remote jobs preserve no-delete behavior, threshold checks, backup failures blocking overwrite, isolated errors, progress, shared history and global lock. Dry run performs reads/planning without files, snapshots or baseline changes. State is stored beside the chosen configuration/history, not an unrelated default user directory.

Bidirectional planning compares both current inventories against the last successful baseline. A double change is a conflict and does not overwrite either version. A missing file never deletes its counterpart. Baseline updates occur only after successful verification. Local state cannot provide a cross-device lock or guarantee compare-and-swap across all providers; state this limitation explicitly and preserve snapshots for recovery.

Bidirectional verification is mandatory even if directional verification is disabled. Baseline identity includes provider, connection root, remote path and resolved local path; changing identity invalidates it. Reinventory before writing and stop on observed changes. Contract review approved before implementation on 2026-10-17, with these compatibility, scope, credentials and verification clarifications.
