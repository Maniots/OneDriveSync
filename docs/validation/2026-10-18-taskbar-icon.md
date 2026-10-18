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

## Follow-up: generic taskbar icon despite correct resources

The user's screenshot showed that 1.5.0.4 still displayed a generic taskbar
icon. Native handles being nonzero had not verified that visible result.

The follow-up compared actual icon pixels from the running window (ICON_SMALL,
ICON_BIG and ICON_SMALL2), executable resources and Windows Shell resolution of
the EXE/Start shortcut. All contained the EverySync logo. The running frozen
process had loaded the SVG plugins, and installed resources matched source.
No stale EverySync shortcut was found in the classic pinned-taskbar directory.

A temporary explicit window icon-resource/identity assignment did not resolve
the display and was reverted. Targeted UPDATEITEM notifications were followed
by the Windows Shell association refresh:
`SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST | SHCNF_FLUSH, NULL, NULL)`.
The user then confirmed visually that the taskbar showed the correct logo.
This supports a stale Shell icon-cache diagnosis; no further application code
change was needed. No cache files were deleted and Explorer was not restarted.

The previous process/shortcut identity change remains valid, but did not by
itself resolve this cached display. The visible resolution is established by
the user's confirmation, not by the earlier automated icon-presence checks.
See [Microsoft Shell change notifications](https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core/nf-shlobj_core-shchangenotify).
