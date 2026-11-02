# Implementation Plan: Account disconnection without job deletion

## Overview

Disconnecting an account will remove its connection and credentials while
retaining every associated remote job as a disabled, recoverable job with no
assigned account. Configuration, service, synchronization, and UI behavior
will explicitly support this state without weakening validation for connected
jobs.

## Requirements

- Accounts can be disconnected when referenced by jobs.
- Referencing jobs keep their IDs, paths, backup options, group membership, and
  other settings.
- Referencing jobs become disabled and have an empty connection ID.
- Disconnected jobs remain visible and editable but cannot run or be enabled.
- Credential deletion failure leaves the saved configuration unchanged.
- Existing connected configurations remain compatible.

## Architecture Changes

- `src/cloud_models.py`: allow an empty connection ID only for disabled remote
  jobs.
- `src/config_manager.py`: accept disabled disconnected jobs while continuing
  to reject non-empty references to unknown connections.
- `backend/services/cloud_service.py`: detach and disable associated jobs when
  the credential-removal worker succeeds.
- `src/sync_groups.py`: validate and describe disconnected group destinations
  without treating them as runnable endpoints.
- `ui/pages/connections.py`: explain the job-preserving effect in the
  confirmation prompt.
- `ui/pages/synchronizations.py`: render disconnected jobs safely and prevent
  enabling or running them.
- `ui/widgets/synchronization_editor.py`: preserve disconnected drafts and
  require replacement-account selection before saving.

## Implementation Steps

### Phase 1: Persistent disconnected jobs — Minimum viable

1. **Add disconnected-model tests** (`tests/test_cloud_config.py`)
   - Action: Add round-trip tests for a disabled remote job with an empty
     connection ID and rejection tests for enabled disconnected jobs and
     unknown non-empty connection IDs.
   - Why: Establish the exact persistence contract before production changes.
   - Dependencies: None.
   - Risk: Low.

2. **Represent disconnected jobs explicitly** (`src/cloud_models.py`)
   - Action: Permit an empty `connection_id` only when the job is disabled;
     retain normal ID validation for non-empty values.
   - Why: Preserve jobs without inventing placeholder connections.
   - Dependencies: Step 1.
   - Risk: Medium.

3. **Validate disconnected references** (`src/config_manager.py`)
   - Action: Skip connection lookup only for disabled jobs with an empty
     connection ID; keep rejecting all unknown non-empty references.
   - Why: Make saved disconnected jobs loadable without weakening reference
     integrity.
   - Dependencies: Step 2.
   - Risk: Medium.

4. **Make group validation disconnected-aware** (`src/sync_groups.py`)
   - Action: Allow disabled disconnected leaves to remain members of existing
     groups while endpoint-identity operations still return a clear error.
   - Why: Preserve group membership while preventing accidental execution.
   - Dependencies: Step 3.
   - Risk: Medium.

### Phase 2: Account removal — Core experience

5. **Add service disconnection tests** (`tests/test_cloud_ui.py`)
   - Action: Replace the old in-use rejection test with RED tests proving that
     one or multiple jobs are retained, detached, disabled, and still referenced
     by their groups; retain failure coverage for credential deletion.
   - Why: Capture the user-requested behavior at the service boundary.
   - Dependencies: Phase 1.
   - Risk: Low.

6. **Detach jobs after credential deletion** (`backend/services/cloud_service.py`)
   - Action: Remove the in-use guard and, on successful worker completion,
     atomically save the connection removal plus disabled jobs with empty
     connection IDs.
   - Why: Ensure the account can be removed without deleting jobs and that
     failed credential cleanup leaves configuration intact.
   - Dependencies: Step 5.
   - Risk: High.

7. **Update the confirmation copy** (`ui/pages/connections.py`)
   - Action: State that linked synchronization jobs will be kept and disabled
     while remote files remain untouched.
   - Why: Make the consequence explicit before confirmation.
   - Dependencies: Step 6.
   - Risk: Low.

### Phase 3: Recovery UI and execution safety — Edge cases

8. **Add disconnected-UI tests** (`tests/test_synchronizations_ui.py`)
   - Action: Test list/detail rendering, disabled run/enable actions, and editor
     recovery by selecting a replacement account.
   - Why: Prevent crashes from assumptions that every remote job has a live
     connection.
   - Dependencies: Phase 2.
   - Risk: Low.

9. **Render and guard disconnected activities** (`ui/pages/synchronizations.py`)
   - Action: Use an “Account not connected” label/path fallback, keep run
     controls disabled, and reject enabling until an account is assigned.
   - Why: Keep the retained job visible but inert and understandable.
   - Dependencies: Step 8.
   - Risk: Medium.

10. **Recover a disconnected destination in the editor** (`ui/widgets/synchronization_editor.py`)
    - Action: Keep the existing disconnected draft visible, require editing it
      to select a live account, and preserve the job ID/settings when repaired.
    - Why: Give users a direct recovery path without recreating the job.
    - Dependencies: Step 9.
    - Risk: Medium.

11. **Document the behavior** (`CHANGELOG.md`, `README.md`)
    - Action: Add concise release and user-facing notes about retained,
      disabled jobs after account disconnection.
    - Why: Keep product documentation aligned with visible behavior.
    - Dependencies: Steps 7–10.
    - Risk: Low.

## Testing Strategy

- Unit: model construction, configuration validation, round-trip persistence,
  and unknown-reference rejection in `tests/test_cloud_config.py`.
- Integration: asynchronous credential removal and atomic connection/job update
  in `tests/test_cloud_ui.py` and `tests/test_connection_identity.py`.
- UI: disconnected labels, controls, group preservation, and replacement-account
  editing in `tests/test_synchronizations_ui.py`.
- Regression: run cloud configuration, service, identity, synchronization UI,
  cloud sync, group validation, and group sync suites with a workspace-local
  pytest temporary directory.

## Success Criteria

- [ ] An account referenced by jobs can be disconnected.
- [ ] Associated jobs and group references remain present.
- [ ] Associated jobs are disabled and have no connection ID.
- [ ] Disconnected jobs survive save/reload and render without crashes.
- [ ] Disconnected jobs cannot run or be enabled.
- [ ] Assigning a replacement account preserves the job identity and settings.
- [ ] Credential deletion failure preserves the original configuration.
- [ ] Relevant regression tests pass.
