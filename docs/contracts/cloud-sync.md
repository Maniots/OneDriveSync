# Internal cloud transport contract — v1

This Python-internal contract is reviewed before implementation. It does not define a new network service. File operations use an app-owned rclone daemon authenticated on a loopback address. Account display metadata may also use the narrowly defined fixed provider endpoints below.

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
- Account policy: new connections permit one saved account per non-local provider.
  Enforce before authorization and before save. Existing duplicate accounts remain
  usable/removable; no migration or automatic deletion. Local/NAS connections are
  exempt. Pending setup remains exclusive to its service.
- OneDrive `config_driveid` questions are filtered before presentation: probe each
  distinct offered ID using that returned setup state, require successful
  `config_drive_ok` plus stored `drive_type` personal/business/documentLibrary.
  For these setup probes, `config/get` is limited to this pending remote's metadata; credentials
  in the response stay internal and never reach UI, errors or logs. Probe errors
  returned by the provider omit that candidate; transport exceptions/cancellation
  abort the check. No remote files are created or changed. Return exclusive
  choices and preserve an eligible default, otherwise select the first eligible
  ID. If none qualify, return a retry-only `choose_type` step with a static safe
  message. The service rejects answers outside the offered IDs before transport.
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
- Recoverable setup errors can contain `State` and `Error` with no `Option`.
  These are retry steps, not answer questions: show a static safe message, hide
  answer controls, preserve the authorized pending remote and require an explicit
  retry or cancel. Never expose the raw provider error. For OneDrive's failed
  drive-discovery fallback (`driveid`), retry the known `onedrive` discovery
  state instead of asking the user to supply an unavailable drive ID. Other
  error continuations keep the provider's returned state. Error-free states
  without options may advance automatically, bounded by the existing step cap.
- `test(connection) -> success`: authenticated read of the configured root; does not write a sentinel into user data.
- `account_info(connection) -> {name?, email?}`: optional display-only identity for
  an existing app-owned OAuth remote, under the same locks. A root read lets
  rclone refresh authorization; `config/get` may then read only that remote's
  matching provider and access token internally. Tokens and raw config never
  reach UI, cache, errors, logs or another config file. The token is used only
  against fixed HTTPS Google Drive About, Microsoft /me, or Dropbox
  get_current_account endpoints, with redirects rejected, bounded reads/timeouts
  and cancellation. No new scopes or browser login. Microsoft uses only the
  authenticated caller's profile if the existing grant permits it; otherwise
  identity is unavailable. Never infer the caller from a drive owner or call
  the auto-provisioning /me/drive endpoint. No User.Read consent is requested.
  Return only normalized bounded name/email fields; missing or unsupported
  identity remains explicit. Details and reviewed service/cache semantics:
  [identity contract](../specs/2026-10-19-connection-identity-design.md).
- `close()`: release owned subprocesses and socket resources, including failure/cancel paths.

## Coordinator semantics

Legacy local jobs retain current behavior. Remote jobs preserve no-delete behavior, threshold checks, backup failures blocking overwrite, isolated errors, progress, shared history and global lock. Dry run performs reads/planning without files, snapshots or baseline changes. State is stored beside the chosen configuration/history, not an unrelated default user directory.

Bidirectional planning compares both current inventories against the last successful baseline. A double change is a conflict and does not overwrite either version. A missing file never deletes its counterpart. Baseline updates occur only after successful verification. Local state cannot provide a cross-device lock or guarantee compare-and-swap across all providers; state this limitation explicitly and preserve snapshots for recovery.

Bidirectional verification is mandatory even if directional verification is disabled. Baseline identity includes provider, connection root, remote path and resolved local path; changing identity invalidates it. Reinventory before writing and stop on observed changes. Contract review approved before implementation on 2026-10-17, with these compatibility, scope, credentials and verification clarifications.
