# Integrated cloud sign-in

Approved by the user on 2026-10-18: Microsoft / Google / Dropbox sign-in,
browser consent, then choose a cloud folder. Technical configuration belongs
to EverySync, with custom credentials available only as advanced options.
The maintainer confirmed that no Google OAuth application exists yet.

## Behavior

- OAuth providers show a provider-specific sign-in button. Name defaults to
  the provider label. Custom application credentials are collapsed.
- Authorize first, then choose the cloud root in a folder selection panel.
  The panel lists immediate subfolders, supports parent navigation, and allows
  an explicit new relative folder path. Save only after root verification.
- Automatically answer only recognized technical browser prompts. Account,
  drive, shared-drive and other consequential choices remain explicit.
- Browser waiting, cancel, authorization denied, expired login, missing
  application configuration and verification errors have useful feedback.
- Existing connections, activities and non-OAuth provider setup keep working.

## Ownership and security

Keep rclone as the owner of persisted tokens and refresh. Microsoft and Dropbox
may use rclone's existing application identities until EverySync registrations
are supplied. Google must never fall back to rclone's retiring shared client.
Ship maintainer-owned desktop client metadata in src/oauth-apps.json; the
initial file is empty. Desktop application metadata is public, not a
confidential server credential. Do not put user tokens in this file.

Google's initial login uses the standard-library native authorization-code
flow with S256 PKCE, unpredictable state, a short-lived 127.0.0.1 listener on
an OS-assigned port, a system browser and fixed Google HTTPS endpoints.
Persist the returned token only through the encrypted app-owned rclone remote.
The callback contract is docs/contracts/oauth-callback.openapi.json.
Avoid logging callback paths, provider response bodies, codes or tokens.
Cancel, timeout and invalid callback must not publish a connection.

Google retains the existing full Drive scope to preserve arbitrary existing
folder synchronization; changing to drive.file would change product behavior.
The maintainer must enable Drive API, register a desktop client, configure
consent and complete the applicable verification before public distribution.
No provider-console or live-account certification is claimed by this change.

## Verification

Exercise local HTTP callbacks and mocked provider exchanges, including PKCE,
wrong state, denial, timeout, cancellation and redaction. Test the real service
and Qt flow for automatic browser prompts, explicit drive selection, choosing
and creating a root, cancelling after authorization and protecting existing
accounts. Run cloud and full repository regressions and inspect rendered UI.

Sources: [Google native OAuth](https://developers.google.com/identity/protocols/oauth2/native-app),
[Drive scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth),
[rclone Drive](https://rclone.org/drive/),
[rclone OneDrive](https://rclone.org/onedrive/),
[rclone Dropbox](https://rclone.org/dropbox/).
