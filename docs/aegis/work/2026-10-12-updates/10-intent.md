# Updates from master

User request: retain the Windows EXE and receive/install updates when commits
reach master, without manually finding/downloading a new executable.

Start: clean `from-master/exe-implementation`, HEAD
`e4542267747d6c2cc960b898a0185d4b960ea819`. Public origin is
`Maniots/OneDriveSync`, default branch master (GitHub metadata verified).
Authority: PROJECT_MEMORY, README and docs/windows-packaging.md; Graphify
identifies launch/scheduler owners but lacks the UI and release workflow.

Plan and boundaries:

1. One build metadata owner supplies desktop, installer and update versions.
2. GitHub Actions tests/builds Windows on pushes to master and publishes a
   versioned installer plus a bounded update manifest after successful checks.
3. An updater reads releases from the fixed public repository over HTTPS,
   validates version/asset origin/size/hash, and downloads in a background job.
4. About/tray expose checking, no release, current, available, download,
   ready, failure/retry and install states. Default: notify and one-click
   install. Optional automatic installation waits until UI sync is idle.
5. A detached helper waits for the UI and shared sync lock, suspends only
   tasks owned by this installed EXE, runs the existing installer, restores
   task enabled states, restarts the monitor if it was running, and restarts
   the app. User config/history/backups are preserved by the existing setup.
6. Add --check-updates and --update to open the update flow, including when
   an existing UI instance is running. Document existing sync commands.
7. Verify hostile/incomplete manifests, hash mismatch, async recovery and
   queued install; test the actual new bundle and installed build. Validate
   the detached helper against a separate installer identity/data set.

Implementation is authorized by the user's request. Public push/merge/release
of this local feature is outside current scope; the workflow becomes active
when these changes reach master. Never embed GitHub tokens in the EXE.

Medium/high distribution and persistence change: architecture review is inline
against the existing runtime/installer/task owners. No subagents requested.
Copy/backup safety and unrelated application design stay unchanged.
