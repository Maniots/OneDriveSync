# Google sign-in activation

The maintainer supplied an OAuth client on 2026-10-18 and asked to check and
enable Google in the installed application.

## Configuration and tests

- The downloaded Google JSON uses the `installed` (Desktop) client type.
- Bundled `drive.client_id` and `drive.client_secret` match that file exactly.
  Only the permitted desktop application fields are present. No user tokens
  were supplied, printed or committed.
- Application credentials remain in the maintainer's local metadata and
  installed bundle. The activation commit excludes the populated metadata;
  the repository template remains empty. The local source file is intentionally
  retained as the maintainer's existing configuration change.
- The standard Google authorization/token endpoints match the downloaded
  metadata. EverySync keeps its fixed Google endpoints and native PKCE flow.
- `setup_parameters("drive", {})` resolves the bundled identity automatically.
  The actual configured UI enables **Sign in with Google** with empty, hidden
  advanced fields. A styled offscreen render confirmed the enabled state.
- Focused OAuth/account/UI suite: **46 passed**.
- Full repository suite with pinned rclone: **406 passed, 2 skipped**. Skips are
  existing symlink-environment cases in test_copy_engine.
- Corrected unavailable-state tests to mock the UI's imported metadata loader
  as well as the provider loader, and removed an assertion tied to unavailable
  hint wording. Added a synthetic configured-app integration check through
  login, folder choice and connection publication without manual credentials.
- Independent auth/security and Python-test review approved the change.

## Package and installed copy

Production Python is unchanged from commit 93430a3. The previously verified
1.5.0.0 desktop bundle was packaged with the configured OAuth metadata, updated
changelog and required automation scripts. Frozen UI smoke/branding checks
passed; bundled Google identity matches the source configuration.

Built `EverySync-Setup-1.5.0.0.exe` (69,323,691 bytes); SHA-256:
`11590ef51831b7871ee69b5d01988a6b5f0c4c4ee53decdcbfc522bc1a966aba`.

The user's installed 1.4.1.9 was updated to 1.5.0.0 using the existing
checksum-verified update helper after acquiring the sync lock and gracefully
exiting the idle desktop. Installed diagnostics and Google metadata checks
passed. The user's configuration SHA-256 was identical before and after.
EverySync was restarted from its installed location.

## Verification boundary

Creating a Desktop client and checking its metadata does not establish that
Drive API is enabled, the consent audience is correct, the account is a test
user, or provider review/publication is complete. Live consent, listing and
refresh still need an interactive account test; no Google console access or
account authorization was available to this verification.
