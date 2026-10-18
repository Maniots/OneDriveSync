# Direct cloud synchronization

EverySync can connect directly to storage through its bundled rclone engine. The **Folders** page continues to support local OneDrive folder pairs. Use **Connections** and **Cloud Sync** for the providers below, without a locally installed OneDrive or Google Drive client.

## Connect storage

1. Open **Connections**, select a provider and give the connection a name.
2. Choose the root folder or existing bucket/container. A cloud folder is a relative path such as `EverySync`; an object-storage root is `bucket-name/prefix`. Jobs stay below this root.
3. Fill in the provider fields, then choose **Connect account**. Passwords are masked. For browser sign-in, complete the questions in **Finish account setup** and authorize access in the system browser.
4. When the connection is saved, select it and choose **Test connection**. This reads the root without writing a test file.
5. Open **Cloud Sync**, choose the connection, local application folder and folder below the root, such as `ExampleGame/Saves`. Save the activity.
6. Close the application that owns the files. Enable **Settings → Dry Run**, apply it and preview a run. Turn dry run off for actual transfers.

Cloud folders can be created during setup with the explicit checkbox. Buckets and containers must already exist. Local/network roots must be existing directories.

| Provider | Setup |
| --- | --- |
| **Local folder / NAS** | Browse an existing local or accessible network folder. No account is needed. Use this to try the complete workflow first. |
| **OneDrive online** | Sign in with Microsoft, answer the account/drive selection questions and choose the intended drive. Optional custom OAuth credentials are supported. [Provider setup](https://rclone.org/onedrive/). |
| **Google Drive** | Supply your own Desktop OAuth client, then authorize in the browser; see below. |
| **Amazon S3 / compatible** | Supply an existing AWS profile or access key ID and secret; optionally session token, region and HTTPS endpoint. Root: `bucket-name/prefix`. Custom endpoints use the generic S3 provider. [Provider setup](https://rclone.org/s3/). |
| **SFTP** | Enter host/user and a password or private-key file, plus a trusted `known_hosts` file. Verify the server fingerprint through your server administrator before using that file. [Provider setup](https://rclone.org/sftp/). |
| **WebDAV / Nextcloud** | Enter the HTTPS WebDAV URL, user and app password. |
| **Dropbox** | Complete browser authorization. |
| **Azure Blob Storage** | Enter storage account and account key; root: `container-name/prefix`. |
| **Backblaze B2** | Enter application key ID and key; root: `bucket-name/prefix`. |

### Create a Google OAuth client

The shared rclone Google client is being retired during 2026. EverySync therefore requires your own client. In [Google Cloud Console](https://console.cloud.google.com/), select/create a project, enable **Google Drive API**, configure the OAuth consent screen and add your Google account as a test user when using testing mode. Create an OAuth client with application type **Desktop app**. Copy its client ID and secret into Connections. Follow the [official rclone walkthrough](https://rclone.org/drive/#making-your-own-client-id) for the current console screens and consent requirements.

The client secret belongs in the masked setup field; do not paste tokens into `config.json` or send them in issue reports. Authorization can require additional approval for organization-managed accounts.

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

The adapter, encrypted configuration, transfer, dry run, snapshots, restore, pending recovery and conflicts are exercised with isolated Windows local storage through the real pinned engine. The frozen executable receives a separate acceptance check. Guided OAuth continuation is tested with controlled responses.

**Live account certification is pending for every remote provider.** No test Microsoft/Google OAuth apps, S3 buckets or other service accounts were available for this implementation. Provider availability is an integration capability, not a claim that each account type, policy or server has been certified. Begin with a disposable folder/account before using important application data.
