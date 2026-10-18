# Windows taskbar identity

The installed 1.5.0.3 window already had nonzero native small/large icon handles,
and both the application/window Qt icons and embedded executable ICO existed.
Its Start menu shortcut had no AppUserModelID; the source never assigned a
process AppUserModelID. The taskbar capture in this environment was black, so
it did not establish the user-visible rendering defect independently.

The correction sets a stable `EverySync.Desktop` identity before QApplication
initialization and assigns the same identity to installer application shortcuts.
Both shortcuts explicitly select the embedded executable icon, index 0.
No icon cache is deleted and no Explorer restart is required by the change.

Verification:

- The native Windows regression failed before implementation: the process still
  had the previous identity when QApplication was about to be accessed.
- The corrected native regression reads back `EverySync.Desktop` through
  `GetCurrentProcessExplicitAppUserModelID` before Qt initialization.
- A consistency check validates both installer shortcut IDs against the runtime
  constant and checks their explicit executable icon source.
- Existing product logo and tray-state tests pass alongside these regressions.
- Full suite with pinned rclone: **439 passed, 2 skipped** (Windows symlink
  capability); independent Python/code review approved.
- Frozen Windows desktop **1.5.0.4** passed isolated startup/rendering smoke
  validation; its bundled Google OAuth application configuration was preserved.

References: [Microsoft process identity API](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-setcurrentprocessexplicitappusermodelid)
and [Inno Setup shortcut properties](https://jrsoftware.org/ishelp/topic_iconssection.htm).
