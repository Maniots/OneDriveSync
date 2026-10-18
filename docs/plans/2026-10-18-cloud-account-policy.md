# Cloud account and drive policy

Requested behavior: one connected account per cloud provider; OneDrive selectors
include all accessible, compatible drives, including SharePoint document libraries.

## Implementation

1. `backend/services/cloud_service.py`, `ui/pages/connections.py`: reject new
   cloud accounts when the provider already has a saved connection. Disable its
   sign-in button with a clear explanation. Local/NAS connections remain multiple.
   Keep existing duplicates readable and removable; never delete accounts or jobs
   automatically. Recheck before saving and clean up only pending credentials on
   conflict. Risk: medium (authorization lifecycle).
2. `src/rclone_transport.py`: before returning a OneDrive `config_driveid`
   question, probe each listed ID through the pinned engine's root-read setup
   state. Accept only successful `config_drive_ok` results with a stored
   `drive_type` of personal, business or documentLibrary. Read config metadata
   only in memory. Return exclusive, deduplicated choices with a valid default;
   no eligible results return a retry state. Exceptions/cancellation fail safely.
   Risk: medium (provider protocol); depends on written contract review.
3. `backend/services/cloud_service.py`: remember the offered OneDrive IDs while
   pending and reject unlisted answers before transport access. Reset on cleanup.
   Risk: medium; depends on step 2.
4. Regression tests: duplicate sign-in blocked before browser/transport; other
   providers and local storage still available; disconnect re-enables sign-in;
   late conflict cleanup; mixed eligible/denied/unsupported drives, default and
   empty results; cancellation and real pinned rclone with isolated Graph fixture.
5. Update project memory, changelog and validation. Run targeted/full tests,
   independent Python/security review, frozen desktop smoke; build/install the
   local Windows update preserving configuration and Google identity. Commit and
   push task files to the current branch, excluding local OAuth metadata.

Read-only eligibility confirms root access and engine support. It does not
certify write permission or perform any remote write; normal folder validation
and transfer errors remain authoritative for later operations.
