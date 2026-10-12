# Checkpoint

Implemented release metadata/workflow, verified-download client, Qt service,
About/tray controls, activation commands and detached installer helper.
User explicitly chose notification plus manual install. Automatic install
is optional and defaults off. The workflow awaits integration on master.

Verification: 208 passed, 2 skipped; actionlint exit 0; frozen acceptance
exit 0; isolated real 1.0 -> 1.1 helper upgrade exit 0. Configuration, sync
lock waiting, four task enabled states and download cleanup were checked.
Public releases/latest returned no_release; no hosted release exists yet.

Debugging correction: initial suspicion of UpdateService destruction timing
was insufficient. Multiple ownership changes did not repair native teardown.
The actual discriminating check was explicitly calling PlotWidget.close:
19 UI regressions passed after this. Installed pyqtgraph PlotItem.close
documents the need to remove graphics/proxy widgets before scene destruction
on PySide. Canonical window exit now closes plots before native destruction;
the direct-window-deletion regression and full suite pass. TDD Route: off.

Validation boundary: scheduler-launched processes use the real user environment,
so the temporary update test does not run its tasks. It checks task ownership
and enabled states only. The frozen monitor is tested separately with an
isolated process environment. Restarting a task-owned running monitor during
upgrade and hosted CI publication remain uncovered; confidence B.

Next: commit the verified feature, stamp/build that commit, recheck the delivered
artifact and install the new updater-enabled version for the current user.
