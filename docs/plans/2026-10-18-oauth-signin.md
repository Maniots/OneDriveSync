# Implementation plan: integrated cloud sign-in

Approved design: docs/specs/2026-10-18-oauth-signin-design.md.
Callback contract: docs/contracts/oauth-callback.openapi.json.

1. Native Google authorization and application identity (risk: high).
   Files: src/cloud_oauth.py, src/oauth-apps.json,
   tests/test_cloud_oauth.py, packaging/OneDrivePCSync.spec.
   Implement maintainer desktop metadata loading and cancellable native Google
   PKCE login with a tested callback contract. Package empty metadata safely.
   Red/green tests precede each behavior. No dependencies.
2. Transport and account flow (risk: high; depends on 1).
   Files: src/cloud_providers.py, src/rclone_transport.py,
   backend/services/cloud_service.py, tests/test_rclone_transport.py,
   tests/test_cloud_ui.py, docs/contracts/cloud-sync.md.
   Import Google tokens internally, automate known browser prompts, retain
   explicit choices, keep pending authorization until root choice, list
   folders and verify the selected root before publishing the connection.
3. Desktop experience (risk: medium; depends on 2).
   Files: ui/pages/connections.py, tests/test_cloud_ui.py.
   Provider-specific sign-in, advanced credentials, post-login folder choice,
   useful waiting and cancellation states; reuse existing Qt styles.
4. Delivery (risk: low; depends on 1-3).
   Files: docs/cloud-sync.md, docs/oauth-maintainer.md, CHANGELOG.md.
   Document maintainer registration and Google activation requirement. Run
   focused and full regressions, inspect a UI render, obtain independent
   spec and security/code reviews, commit and push to the original branch.

Success evidence: callback security tests, service/UI account and folder
tests, existing cloud credential and transfer regressions, packaging metadata
inclusion, no user tokens or developer credentials in tracked data.
Live Google login remains unavailable until the maintainer registers its app.
