# Integrated OAuth sign-in validation

Date: 2026-10-18. Implementation follows the user-approved integrated sign-in
design; the maintainer confirmed there is no Google OAuth registration yet.

## Automated evidence

- Full repository suite with the pinned native rclone v1.75.2 available:
  `python -m pytest tests -q -rs -p no:cacheprovider`: **405 passed, 2 skipped**.
  The skips are existing Windows symlink-environment tests in test_copy_engine;
  OAuth and native transport tests did not skip.
- Google-specific suite after the final maintainer-metadata test adjustment:
  **19 passed**. Real local callbacks exercise PKCE/state, contract status
  responses, denial, malformed/duplicate parameters, cancellation, timeout,
  safe error text, token normalization and fixed HTTPS exchange endpoint.
- Native encrypted-rclone token-import regression confirmed that a Google
  token obtained through PKCE does not request a second browser login.
  Internal `config_refresh_token=false` preserves the imported token.
- Qt/service tests cover automatic technical browser prompts, explicit drive
  choices, delayed publication until root verification, folder selection,
  cancel/exit cleanup, retry, provider switching, missing Google app metadata
  and preventing unrelated operations during pending setup.
- Independent design/contract review and subsequent code/security review
  approved the implementation after the reported UI issues were corrected.
- `git diff --check` passed.

## Windows package and visual checks

PyInstaller successfully built the desktop application. Its frozen desktop
smoke check loaded/rendered the UI and verified app branding and resources.
The bundle contains `_internal/src/oauth-apps.json` with the intended empty
metadata. The build emitted the existing optional pyqtgraph OpenGL-submodule
warning; the application does not require that optional package for this flow.

`scripts/verify_cloud_bundle.py` also passed against the frozen executable:
actual local transfers, newer/extra-file preservation, DPAPI and encrypted
configuration, snapshot/restore, dry run, pending recovery and conflict safety.
The sandbox could not access Windows DPAPI key material; the same acceptance
script passed under the real Windows user context using only isolated local
fixtures. No production credential implementation was changed for this limit.

Rendered the styled sign-in, Google-unavailable and cloud-folder selection
states. Single selection updates the chosen path; activation opens a folder.
After sign-in, the setup form is hidden so the folder confirmation and cancel
controls remain visible. Rendering used Qt offscreen with the system Segoe UI
font explicitly loaded into the preview process.

## Remaining external acceptance

Google sign-in is disabled in the default source/release metadata until the
maintainer registers and publishes the EverySync desktop application, supplies
its identity and completes applicable consent/scope verification. See
`docs/oauth-maintainer.md`. No user account token was supplied or committed.
Live Google/Microsoft/Dropbox consent, refresh and account policy acceptance
remain unverified. Microsoft and Dropbox use rclone identities unless the
maintainer supplies EverySync registrations.
