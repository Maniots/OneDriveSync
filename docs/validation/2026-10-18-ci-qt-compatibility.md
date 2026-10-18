# CI Qt compatibility

Failed run: [Windows installer and release #18](https://github.com/Maniots/OneDriveSync/actions/runs/39153355228).

The regression step crashed with a native access violation in
`tests/test_server.py:13`, processing events while waiting for the activation
server to accept a connection. The runner installed PySide6/shiboken 6.12.0
from an unconstrained requirement; locally verified builds used 6.11.1.

Reproduction used an isolated Python 3.14.6 environment with PySide6 6.12.0,
pytest 9.1.1 and the native pinned rclone. The isolated server tests passed,
but the complete suite reproduced the same native crash at the same wait.
This demonstrates a suite-level compatibility problem; it does not prove a
particular application callback bug or a specific upstream defect.

The fix pins the PySide6 distribution to 6.11.1 (its Qt components and shiboken
are exact transitive dependencies), matching the validated Windows stack.
No tests are skipped and event-loop/socket assertions remain unchanged.
Qt minor upgrades must pass full regression and frozen acceptance checks.

With the pinned 6.11.1 stack and the repository's empty OAuth metadata template,
the full local suite passed: **439 passed, 2 skipped** (Windows symlink
capability). Commands retained all server/event-loop assertions and enabled
native rclone tests. Independent Python/infra review approved the dependency
constraint; both CI test installation and build inherit it through
`requirements-build.txt`.

Independent security review of the branch passed; 127 focused OAuth,
credential, transport, synchronization and configuration regressions passed
with native rclone. No real provider accounts were used and private local
OAuth application metadata remains excluded from the branch.
