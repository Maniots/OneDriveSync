# Verified implementation

Key judgment: publish verified master builds and let the installed application
notify and apply a verified installer. The user chose manual installation.
The existing runtime directory, sync lock, installer identity and task owners
remain canonical; no alternate copy engine or distribution credentials were added.

Evidence (Windows x64, Python 3.14.6 / PySide6 6.11.1):

- `pytest tests -q --basetemp build/update-regressions-06 -p no:cacheprovider`:
  exit 0, 208 passed, 2 skipped. Includes hostile manifests, corrupt downloads,
  responsiveness/retry, queued installation, exit during checking, commands,
  shared monitor lock and direct native window/chart deletion.
- `actionlint .github/workflows/windows-release.yml`: exit 0.
- `Build-Windows.ps1`: exit 0, installer and manifest 1.1.0.0.
- Frozen acceptance: exit 0, UI/resources, dry-run, actual copy, native monitor
  sync/status and clean monitor exit. Log: `build/update-frozen-final.log`.
- Detached real validation upgrade 1.0 -> 1.1: exit 0, shared-lock waiting,
  unchanged configuration, four task enabled states, staged download removal.
  Log: `build/update-install-final.log`. Validation resources were uninstalled.
- Live fixed public GitHub endpoint: no_release before first publication.

Confidence B. Hosted CI execution, downloading its first actual release and
restarting an already-running task monitor during installation remain uncovered.
Scheduler tasks were registered but not run in isolated upgrade validation:
they use the real user's environment. Frozen monitor checks are process-isolated.
The most valuable subsequent check is the first release after master integration.

Debug closure: changing updater ownership alone did not repair teardown.
Explicit pyqtgraph plot closure before native scene destruction did; this is
applied at window lifecycle ownership and in disposal of independent test plots.
Background update completion cannot install after application exit starts.

Baseline alignment: aligned with README/PROJECT_MEMORY runtime and installer
owners and the user's confirmed notification preference. Build version moves
to one canonical owner. Source launch compatibility remains supported.
No project Aegis workspace helper or ADR backfill configuration is installed;
work-record paths and evidence links were inspected directly, without claiming
automated workspace integrity or hosted publication.

Delivery: retain `from-master/exe-implementation` for integration. Make one
local feature commit, rebuild with its identity, verify the resulting EXE and
upgrade the current user's installation. Publication activates after this
feature is pushed/merged to master, not from the local commit alone.
