# Connected account identity

Approved by the user on 2026-10-19: retain the Connections page and replace its
ambiguous `name · provider · root` rows with Service, Connected account and Cloud
folder columns. Retrieve real account identity for existing connections without
another sign-in. Clearly state when identity is unavailable. Use clearer verify
and disconnect labels and explain what the cloud folder means.

The user's 2026-10-24 request to show the Microsoft account supersedes the
original no-new-consent restriction for explicit Microsoft sign-in only.

Keep the existing English application language and theme. Service labels are
distinct from optional connection nicknames. Account cells show the email and
display name returned by the provider, never infer an email from a nickname or
storage owner on a selected shared drive. Local/NAS storage has no cloud account.
An empty list, loading, unavailable identity and unsupported providers have clear
text. Selection survives updates; verify/disconnect require a selected row.
Cloud-folder tooltips retain complete paths. Keyboard row selection remains usable.

## Identity contract

`RcloneTransport.account_info(connection) -> dict[str, str]` returns only `name`
and `email`, each optional, normalized single-line strings (name <= 200 and email
<= 320 characters). Empty/unavailable fields are omitted. Unsupported providers
return `{}`. Expected authentication, network or malformed-response failures raise
`CloudSyncError` with a generic message, without provider response bodies or tokens.

This is an internal Python interface, not a new HTTP server/API. It reads only an
existing app-owned remote. The transport lets rclone initialize/read that remote
to refresh its token, then uses its authenticated local config/get operation.
Provider APIs use fixed HTTPS URLs, reject redirects, have bounded response size
and timeout, and return only normalized display fields. Tokens remain in memory;
no credentials export, shell command or config migration.
Google uses Drive About.user; Dropbox uses get_current_account. Microsoft reads
only /me (displayName, mail), which identifies the authenticated
caller. Updated by user request on 2026-10-24: new OneDrive sign-ins request
User.Read alongside the existing storage scopes. Background identity reads and
Verify access never open a browser. Existing accounts can explicitly choose
Show Microsoft account to grant profile access in the browser.
Drive owners, even a single apparently unambiguous personal/business owner, do not
prove the caller's identity and are never used. Do not list drives or call the
auto-provisioning /me/drive endpoint. Missing email remains missing. An unavailable
profile does not invalidate the saved connection. Do not infer an email from
userPrincipalName; a display name alone is sufficient.

`RcloneTransport.authorize_account_identity(connection) -> {name?, email?}` is
OneDrive-only and requires an explicit user action. Under the existing locks,
it authorizes a temporary encrypted remote using the existing application's
settings and drive, adding only User.Read to the stored storage scopes. It
reads the actual caller profile and verifies access to the unchanged root,
then removes the temporary remote before updating only the saved token and
scope settings. Cancellation, denied consent, missing profile, inaccessible
root and temporary-credential cleanup failure leave the saved connection intact.
No drive discovery, owner inference, app-config rewrite or job changes occur.
`CloudService.authorize_account_identity(connection)` runs this off the GUI
thread, validates the saved connection, updates the existing identity cache and
emits `completed('authorize_account', connection.id)`. The page exposes a
OneDrive-only action, browser/waiting feedback, cancellation and retry.

`CloudService.refresh_account_identities(force=False)` asynchronously populates
`account_identities[id]` with `{name?, email?, status}`; status is `available`,
`unavailable`, or `unsupported`. It respects the existing operation/sync lock and
pending-setup exclusion. Results for removed connections are ignored. The cache
lasts for this service instance, and disconnect removes its entry. Existing
`completed('test', connection_id)` semantics are retained; verification refreshes
that account's identity best-effort, without failing a readable folder if its
profile is unavailable. Passive metadata failure never deletes credentials or prompts OAuth.

Only the visible Connections page requests uncached identities. Repainting and
configuration-change signals do not repeatedly access the network; unavailable
results are retried with Verify access. Cancellation/exit waits for bounded work
and discards cancelled results. The normal setup and synchronization flows remain.

## Acceptance

- Existing Google/Microsoft/Dropbox connections show genuine available identity.
- Profile errors, unsupported storage, missing email and offline use stay explicit.
- The table separates service, identity and folder and preserves selection.
- No network request or profile parsing blocks the GUI thread.
- Existing account setup, provider policy, cleanup, configuration and sync pass.
- Native rendered checks cover populated, loading, unavailable and empty states,
  with long names/paths and keyboard selection. Test identities are synthetic.
