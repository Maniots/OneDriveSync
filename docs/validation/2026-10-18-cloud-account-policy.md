# Cloud account and OneDrive eligibility validation

Requested: one connected account per cloud service; offer all accessible,
supported OneDrive drives, including SharePoint libraries.

- Before implementation, duplicate-account tests reproduced authorization being
  allowed for every cloud provider. Drive tests reproduced denied, unsupported
  and duplicate candidates reaching the selector.
- Full suite with pinned rclone: **437 passed, 2 skipped** (Windows symlink
  capability), using `pytest tests -q -rs --basetemp <isolated-directory>
  -p no:cacheprovider`.
- Provider guards run before authorization and before final publication.
  Tests cover disconnect recovery, multiple local connections, preserving
  legacy duplicate configurations and deleting only pending credentials on a
  late provider conflict.
- Eligibility tests cover denied/unsupported candidates, deduplication, safe
  defaults, exclusive choices, empty-list retry, transport failure and rejecting
  an unlisted ID or substituted continuation state before engine access.
- The actual rclone v1.75.2 engine uses an isolated loopback Graph fixture with
  dummy tokens. A denied root and unsupported drive are omitted; personal and
  SharePoint drives remain. Selecting the first drive after all probes reapplies
  its ID instead of accepting the last probed drive.
- Independent contract, Python and security review approved; 17 focused tests
  passed in independent verification. `git diff --check` passed.
- Qt screenshots exercise the disabled connected-provider sign-in state and
  exclusive eligible-drive selection using synthetic accounts and identifiers.
- Frozen Windows desktop **1.5.0.3** passed isolated startup/rendering smoke
  validation and preserves the local Google OAuth application configuration.

Root access checks are read-only on Microsoft storage. They validate access and
supported drive type at setup time; they do not certify write permissions or
remote transfers. Local Google application metadata is excluded from Git.
