# Direct cloud synchronization

EverySync can connect directly to storage through its bundled rclone engine. **Synchronizations** manages every activity, including existing local OneDrive pairs and direct-provider destinations. **Connections** manages storage accounts. Direct providers work without a locally installed OneDrive or Google Drive client.

## One folder, ordered destinations

Open **Synchronizations → Add synchronization**. Choose a PC folder, add the destinations to receive it, and arrange download priority using **Move up / Move down**. Each destination can participate in upload, download or both. Cloud accounts and folders on this PC/network share the same editor. Local ZIP backups and cloud snapshots remain separate recovery mechanisms, accessible from **Backups and restore**.

**Send to destinations** attempts all enabled upload destinations and reports each result. A partial upload is not reported as a complete success. **Download to this PC** chooses one whole-folder source in saved order; it never assembles individual files from different services. Manual direction buttons do not alter scheduled startup/shutdown directions or require a scheduled trigger to be enabled.

The default download fallback is a confirmed missing activity folder. An existing empty folder is reported as empty and leaves PC data unchanged. Access errors, malformed listings, incomplete copies and known prior copies stop download. The advanced **Try the next source when a service is unavailable** option permits fallback only for recognized transport unavailability, not authentication or arbitrary provider errors. Once downloading starts, an error stops that operation; it never continues with another source in the same PC folder.

Explicit activities record verified copy evidence in `config.cloud/groups.json`, under the application's shared synchronization lock. A new explicit activity needs a verified upload before its first download. To use preexisting copies, explicitly enable **Allow existing copies whose freshness is unknown**. That option never bypasses known incomplete/prior data or pending work. The UI distinguishes **Freshness unknown**, **Verified on this PC**, **Incomplete** and **Prior copy**. Evidence belongs to this configuration on this PC; it does not certify global freshness across computers or coordinate remote writers. Existing implicit activities retain their previous ability to use existing copies.

Use **Stop after current destination** for running groups: the current destination finishes safely and remaining work stays pending for a retry. It does not interrupt an in-progress file copy. Dry run reads/plans without transferring files or changing generation evidence. Session-end deferral queues the group without starting network transfers.

Loading an older configuration never combines activities automatically. Existing IDs, paths, history, backups, credentials and bidirectional singletons remain intact. Editing an ordinary singleton without adding destinations preserves its legacy routing. Explicit groups are directional and cannot contain bidirectional activities. Pending membership/endpoint changes are rejected until the earlier work is completed; do not discard state files to bypass recovery. See the [contract](contracts/unified-sync.md) and [migration/rollback notes](specs/2026-10-19-unified-sync-hierarchy-migration.md).

Groups that include ordinary PC/network folder destinations require **Copy subdirectories** in Settings. EverySync rejects an incompatible setting before saving or copying, so a partial folder cannot be certified as a complete copy. Existing independent folder pairs keep their nonrecursive setting.

## Connect storage

1. Open **Connections**, select a provider and give the connection a name.
2. For **OneDrive**, **Google Drive** or **Dropbox**, choose **Sign in with Microsoft / Google / Dropbox** and authorize access in your browser. If the account has multiple drives, choose the one you want in the app. Technical browser questions are handled automatically. Google sign-in requires a release configured with the EverySync Google application; unavailable builds explain this before setup starts.
3. After sign-in, open folders in **Choose your cloud folder**, or enter a relative folder path such as `EverySync`. Choose **Use this folder**. The app verifies the folder before saving the account; the checkbox allows creation if missing. You can cancel before saving. Personal OAuth application credentials are optional under **Advanced settings**.
4. For other providers, choose the root folder or existing bucket/container, fill in the provider fields and choose **Connect account**. Object-storage roots use `bucket-name/prefix`. Passwords are masked. Select a saved account and choose **Test connection** to read its root without writing a test file. Jobs stay below the chosen root.
5. Open **Synchronizations**, choose the PC application folder, add this connection as a destination and enter its folder below the root, such as `ExampleGame/Saves`. Add other destinations and arrange their download priority, then save.
6. Close the application that owns the files. Enable **Settings → Dry Run**, apply it and preview a run. Turn dry run off for actual transfers.

Cloud folders can be created during setup with the explicit checkbox. Buckets and containers must already exist. Local/network roots must be existing directories.

If OneDrive cannot load your drives, choose **Retry account setup** to repeat
discovery without entering a manual drive ID. If it continues, open OneDrive in
your browser with the same Microsoft account to check that storage is available.
You can cancel the pending setup and sign in again; existing connections remain.

| Provider | Setup |
| --- | --- |
| **Local folder / NAS** | Browse an existing local or accessible network folder. No account is needed. Use this to try the complete workflow first. |
| **OneDrive online** | Sign in with Microsoft, choose a drive if requested, then choose a folder. No application registration is required from the user. |
| **Google Drive** | Sign in with Google, then choose a folder. Requires a build containing the maintainer's application metadata; the maintainer's installed build is configured. |
| **Amazon S3 / compatible** | Supply an existing AWS profile or access key ID and secret; optionally session token, region and HTTPS endpoint. Root: `bucket-name/prefix`. Custom endpoints use the generic S3 provider. [Provider setup](https://rclone.org/s3/). |
| **SFTP** | Enter host/user and a password or private-key file, plus a trusted `known_hosts` file. Verify the server fingerprint through your server administrator before using that file. [Provider setup](https://rclone.org/sftp/). |
| **WebDAV / Nextcloud** | Enter the HTTPS WebDAV URL, user and app password. |
| **Dropbox** | Complete browser authorization. |
| **Azure Blob Storage** | Enter storage account and account key; root: `container-name/prefix`. |
| **Backblaze B2** | Enter application key ID and key; root: `bucket-name/prefix`. |

### Google availability and advanced applications

The shared rclone Google client is being retired during 2026. EverySync uses a maintainer-owned desktop OAuth application instead. Google sign-in is configured in the maintainer's local sources and installed build; application credentials are kept locally and the repository retains an empty metadata template. Builds containing the configured metadata enable Google automatically; older releases need an update. End users only sign in and consent in their browser. The maintainer manages consent publication, test users and provider verification following [maintainer setup](oauth-maintainer.md).

Advanced users with an existing desktop OAuth application can supply its client ID and client secret under **Advanced settings**. Do not paste user tokens into `config.json` or send them in issue reports. Organization-managed accounts can require administrator approval. Native Google login uses PKCE; token storage and renewal remain managed by the encrypted rclone configuration.

## Run and recover

Activities use the configured startup/download and shutdown/upload directions, manual actions, periodic tasks and local file watching. Remote changes are discovered on a manual or scheduled run; there is no cloud push subscription. The activity buttons display the actual configured direction.

- Copies add/update files and retain destination-only files. Deletions are never propagated. Ordinary directional runs preserve newer destination files.
- A file-count threshold blocks unexpected differences. An empty destination allows a first transfer. Adjust the activity's threshold only after reviewing the paths and preview.
- The default verifies content. Providers without suitable native hashes may require downloading files to compute SHA-256, including on unchanged runs. Large trees can therefore incur substantial traffic, time and provider charges.
- Failures retain pending work. The next ordinary run retries the saved direction before applying its newly requested direction. If recovery fails, the opposite direction stays blocked.
- During actual Windows session shutdown/sign-out, cloud activities are queued locally without starting network transfers. The next ordinary run drains them. Periodic uploads reduce the amount left pending.
- The shared synchronization lock serializes legacy copies, cloud transfers, account operations and restore. Exit and updates wait for active copying/restoring to finish.
- Dry run reads and plans without copying files, creating snapshots or advancing cloud state. Ordinary logs/history may still be recorded.

### Bidirectional activities

Enable **Bidirectional** to compare both sides with the last successful, verified baseline. A new file is copied to the other side; different changes to the same file stop the activity with a conflict. Both versions remain available. With no baseline, differing versions also conflict. Resolve the contents explicitly, then retry. Missing files do not remove their counterparts.

This baseline and lock are local to one PC. They do not coordinate other devices or provide an atomic cross-provider transaction. Close applications writing the files and avoid simultaneous runs on multiple PCs. EverySync rechecks observed changes before copying, but a remote writer can still race a transfer.

## Snapshots and restore

With snapshots enabled, an upload first copies and verifies the complete existing remote job folder under:

```text
<connection root>/.everysync/backups/<activity ID>/<run ID>
```

These are full remote copies, separate from the legacy ZIP backups on the Backups page. Snapshot failure blocks the overwrite. Only completed, verified snapshots appear in **Cloud Sync → Snapshots / restore**. Restore requires an empty local folder and verifies its contents against the published snapshot fingerprint.

Remote snapshots have **no automatic retention or pruning** in this version. Remove unwanted snapshot folders on the provider when you no longer need them. Deleting an activity/disconnecting an account retains live files and snapshots; restore through EverySync requires the original job/connection configuration and its state.

## Credentials, migration and rollback

For an installed default configuration, cloud state is stored in `%LOCALAPPDATA%\OneDrivePCSync\config.cloud`. A custom `--config X.json` uses adjacent `X.cloud`. `config.json` contains only connection/job settings. The app-owned rclone configuration is encrypted; its random password is protected with Windows DPAPI for the current Windows user. It does not reuse your personal rclone configuration. Canceling setup removes the pending app-owned remote; disconnecting removes saved credentials after dependent activities are removed.

Keep a secure backup of the entire user-data directory for recovery. DPAPI credentials cannot simply be moved to another Windows user or PC; reconnect there. Preserve `state.json` with the matching configuration to retain snapshots and baselines. If state/credentials are unreadable, EverySync stops; restore the matching backup rather than deleting it to bypass the error.

Existing folder pairs remain unchanged. To return to a version without cloud support, disable/remove cloud activities and connections first and retain a backup of the new configuration and cloud state. Older apps cannot run the new activities and may reject their configuration fields. Neither removing activities nor uninstalling should be used to delete synchronized data.

## Validation status

The adapter, encrypted configuration, transfer, dry run, snapshots, restore, pending recovery and conflicts are exercised with isolated Windows local storage through the real pinned engine. The frozen executable receives a separate acceptance check. Integrated sign-in, explicit account choices and post-login folder selection are tested with controlled responses. Native Google PKCE tests use real local callbacks and controlled token exchanges.

**Live account certification is pending for every remote provider.** A Google Desktop application is now configured and its client metadata has been checked, but successful live consent, API access and token renewal have not yet been certified. Provider availability is an integration capability, not a claim that each account type, policy or server has been certified. Begin with a disposable folder/account before using important application data.
