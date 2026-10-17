# EverySync branding proposal

Status: implemented and locally verified on `feat/everysync-rebranding`.

## Requested outcome

Rename the Windows application to **EverySync** and replace its cloud branding
with a consistent synchronization logo across every product surface.

## Visual direction

Recommended: two rounded, opposing circular arrows in blue and turquoise on a
dark rounded square. The mark communicates two-way synchronization and remains
readable at small Windows icon sizes. Use the existing dark interface palette
and Segoe UI wordmark; retain the existing tagline, "Your folders. In sync."

Alternative: an E monogram. This emphasizes the initial but communicates the
application's purpose less clearly, so the circular arrows are recommended.

The reviewable vector proposal is `everysync-logo-proposal.svg` in this directory.
The production mark will use a standalone SVG and a multi-resolution ICO.

## Scope

- Use EverySync in window titles, sidebar, About, tray tooltips and menus,
  notifications, update messages, command-line product descriptions, installer,
  uninstall entry, Windows shortcuts and current user documentation.
- Use the same mark for window/taskbar, sidebar, About, tray, executable,
  installer and uninstall icon. Tray states retain their existing meaning
  using small state badges rather than replacing the product logo.
- Publish the new branding as a version newer than 1.3.1.4.
- Preserve existing folders, configuration, history, backups, startup choice,
  scheduled-task behavior and single-instance guarantees.

## Upgrade boundary

Do not rename the GitHub repository as part of this request.
Existing updaters require `update.json` and a versioned
`OneDrivePCSync-Setup-*.exe` asset. Retain those as a compatibility distribution
while also offering an EverySync-named download. Do not reinterpret existing
configuration or create an unrelated installation by changing the installer
AppId. Existing data locations, task identities, startup-registration ownership
and lock/activation identifiers stay compatible through this branding release.
Implementation must explicitly verify the old-client upgrade route before
publishing. Expose EverySync in Windows product metadata even where a legacy
technical filename remains necessary for compatibility.

## Verification

- Check visible product strings and render the logo at 16, 24, 32, 48 and 256px.
- Check window, sidebar, About and tray states with isolated configuration.
- Inspect the compiled EXE and installer for the new multi-resolution icon.
- Run relevant regression tests and the complete suite before publication.
- Verify existing updater compatibility, installer upgrade preservation,
  startup registration and single-instance behavior.
- Commit and push the rebranding branch and verify its CI build and downloadable
  installer. Production publication and live update discovery follow a later
  merge to master; this branch task does not authorize that merge.

## Self-review

The proposal covers visible branding and delivery without renaming the remote
repository or discarding existing user data. Compatibility identifiers have a
defined purpose and are not accidental visible branding omissions.
