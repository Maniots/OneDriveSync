# Connections account identity implementation

The user approved [the design](../specs/2026-10-19-connection-identity-design.md).
The internal identity/service contract in that file is the implementation boundary.
No configuration/schema or OAuth scope changes are needed.

1. Transport (medium risk; independent of the UI): add a narrowly bounded profile
   reader in `src/cloud_identity.py` and `RcloneTransport.account_info` in
   `src/rclone_transport.py`. First reproduce missing identity retrieval with
   failing tests in `tests/test_cloud_identity.py` and transport tests. Verify
   provider fields, fixed URLs, no redirects, time/size bounds, sanitization and
   cancellation. Obtain independent contract/security review before implementation.
2. Service (medium risk; depends on the contract): extend
   `backend/services/cloud_service.py` with runtime identity caching and async
   refresh. Preserve test-completed payloads, pending setup and teardown. Tests in
   `tests/test_connection_identity.py` cover successful/missing/failed accounts,
   cache/retry, cancellation, stale results and responsive Qt event processing.
3. Page (low risk; depends on service contract): replace the account list in
   `ui/pages/connections.py` with an accessible three-column QTableWidget and
   explanation/empty-state labels. Retain IDs and selection across refresh, show
   profile states and clear actions. Trigger metadata requests only while visible.
   Update the existing account-policy table assertion; add UI behavior regressions.
4. Verify and deliver: focused tests, complete suite with pinned native rclone,
   rendered native previews with synthetic profiles, code/Python/security review,
   diff checks. Update README/CHANGELOG for the visible behavior. Commit and push
   the task branch per the user's standing instruction. Remove only task fixtures.

Implementation proceeds within the approved design; routine technical choices do
not request another confirmation. No live accounts or personal OAuth metadata are
needed for tests or rendered previews. Any unavailable live-provider verification
is reported explicitly.
