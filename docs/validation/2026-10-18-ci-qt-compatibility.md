# Windows CI Qt lifecycle and compatibility

Failed runs: [Windows build #18](https://github.com/Maniots/OneDriveSync/actions/runs/39153355228)
and [#19](https://github.com/Maniots/OneDriveSync/actions/runs/39154138482).
Both stopped with a native access violation while `test_server` processed events
waiting for an activation connection. The isolated server test passed.

The unconstrained dependency had installed PySide6/shiboken 6.12.0, whereas
locally verified builds used 6.11.1. The same full-suite crash was reproduced
locally with 6.12.0. Pinning the known Windows stack made dependency selection
reproducible, but run #19 still crashed with 6.11.1. A clean local 6.11.1
stack passed 439 tests with 2 symlink capability skips. This ruled out the Qt
version alone as an adequate fix.

A concrete isolation defect was then observed: monitor tests left a parentless
SyncService timer active after teardown. One retry timer had a 30-second
interval, and restoring an instance monkeypatch left a bound-method cycle that
retained the service. QWidget-only cleanup did not stop these standalone
services. A regression with a cyclic service and an active timer reproduced
callbacks firing after the old cleanup.

The corrected tests use a managed SyncService factory. Teardown stops timers,
waits for workers and explicitly destroys the owned QObject services. Instance
monkeypatches are restored before service destruction. Native socket and event
loop assertions remain unchanged; no tests are disabled. PySide6 stays pinned
to the stack used for Windows acceptance builds. No particular upstream Qt
bug is asserted.

Independent security review of the feature branch passed 127 focused OAuth,
credential, transport, synchronization and configuration tests with native
rclone. Private local OAuth metadata remains excluded from the branch.

The final isolated full suite passed **441 tests with 2 skips** in 57.01s
using the clean Windows dependency environment and native rclone. The skips
reflect Windows symlink capability. Independent review also passed all 26
lifecycle and audit tests and found no blocker.
