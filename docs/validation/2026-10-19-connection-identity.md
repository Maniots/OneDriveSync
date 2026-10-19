# Connected account identity verification

Approved design: [identity and table](../specs/2026-10-19-connection-identity-design.md).
The internal contract was independently reviewed before implementation. The pinned
rclone version has no UserInfo implementation for these three OAuth providers;
the adapter therefore reads only fixed official provider profile endpoints using
the existing rclone-managed token, never another OAuth flow.

Fresh Windows verification after implementation:

- Full suite: **509 passed, 2 skipped**, 58.94 seconds. The two skips concern
  symlink capability. Python 3.14 and the pinned native rclone engine were used.
- Focused transport/profile suite: **73 passed**, including native transport
  regressions. Provider HTTP responses and account tokens were synthetic.
- Service/setup/page suite: **50 passed**, including cancellation plus failure,
  stale removed-account results, preserved verification payloads, profile failure
  recovery, GUI responsiveness, selection and shutdown without queued refreshes.
  A task-level failure repaint regression also verifies that the table stops
  showing Loading, preserves selection and does not retry in a loop.
- RED regressions were observed before implementation. An integration run exposed
  queued callbacks after native page destruction; replacing static callbacks with
  a parent-owned timer passed the same teardown checks.
- Native Qt previews were inspected at 1010 and 810 pixel page widths, with the
  actual Segoe UI font and existing theme. Populated, empty, loading and unavailable
  states were inspected. Long names and paths elide with complete tooltips. Preview
  accounts use example.test identities. Previews remain local build artifacts.

Provider boundaries use existing Drive scopes, Microsoft Files.Read permissions,
and Dropbox account_info.read. Microsoft returns only an unambiguous owner from
the authenticated user's drive list; a name without email is valid. Ambiguous,
paged or unavailable profiles are explicit fallbacks. No User.Read request or
auto-provisioning /me/drive operation is used. Source references:
[Google About](https://developers.google.com/workspace/drive/api/reference/rest/v3/about/get),
[Microsoft drive list](https://learn.microsoft.com/en-us/graph/api/drive-list?view=graph-rest-1.0),
[Dropbox API specification](https://github.com/dropbox/dropbox-api-spec/blob/main/users.stone).

No personal account or OAuth metadata was needed for tests or previews. A separate
read-only smoke check used existing installed connections under the installed
application's synchronization lock. It printed only availability booleans, never
names, emails or tokens. Google returned both display name and email. Microsoft's
drive list was paginated/ambiguous, so the intended unavailable fallback was
confirmed; its current grant also did not expose the signed-in /me profile. No
new scope or authorization was requested. The application config remained intact.

This does not certify every live provider/account variant. Unavailable identity
never removes or invalidates a saved connection. Config schemas and credential
storage format are unchanged; display details live only in the service's memory
cache, and rclone remains responsible for normal token refresh.
