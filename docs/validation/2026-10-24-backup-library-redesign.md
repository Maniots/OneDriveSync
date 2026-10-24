# Backup library redesign

The Backups page now uses a searchable archive list and a selected-backup panel.
Folder names and archive filenames have distinct typography; date and size remain
visible without repeating three action buttons on every row. Restore is the
primary action, with Open location and Delete archive below it. The existing
palette, Segoe UI typography and confirmation dialogs are retained.

Search and folder filters apply to loaded archives. Refresh preserves the selected
archive by path and retains the filters. Filtering out the selected archive clears
the action target. Empty, no-match, unavailable and dry-run states provide specific
feedback. At shorter window heights, metadata scrolls while actions stay visible.
Long names wrap or elide with complete archive paths available in tooltips.

Verification on Windows:

- Full suite: **595 passed, 2 skipped** in 74.70 seconds. The native credential
  test requires running outside the sandbox: Windows CryptProtectData is not
  available inside it. The native test passed independently outside the sandbox
  before the full suite was rerun there.
- After the final filename-painting adjustment: **48 focused tests passed** in
  2.22 seconds, covering filtering, keyboard selection, archive-specific actions,
  confirmation/cancellation, dry-run protections, real restore/delete safety,
  asynchronous restore, failure recovery and shutdown.
- Native previews inspected at **810 × 820**, **1100 × 820** and **810 × 640**.
  Covered populated, empty, no-match, error, dry-run and long-content states.
  The compact view has no horizontal table scrolling and all action buttons
  remain visible. Previews use explicitly labelled sample data and register
  installed Windows font files for the headless Qt process.

Local before/after previews and verification artifacts are retained under the
ignored `build/validation/backups-redesign/` directory. No storage-service,
configuration-schema or archive-format changes were made. Manual screen-reader
testing was not performed.
