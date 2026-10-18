# OneDrive drive selection

OneDrive's `config_driveid` question supplies readable `Examples.Help` labels
and opaque `Examples.Value` identifiers, but is not exclusive. The UI previously
hid its populated selector and displayed the raw default identifier in a text
field instead.

The selector now shows readable labels for questions with examples, selects the
provider default by value, and submits the selected identifier. Non-exclusive
selectors remain editable; manually entered answers never reuse stale item data.
Unlisted and empty defaults are preserved. Password questions always use a blank
masked field, without examples or a prefilled default. Retry controls still reset
between questions.

Validation:

- Reproduced the original display/default/password failures before the fix.
- Regression tests use synthetic identifiers and cover selecting another drive,
  provider defaults, manual answers, password precedence and question transitions.
- Full suite: `pytest tests -q -rs --basetemp <isolated-directory> -p no:cacheprovider`
  with pinned rclone: **421 passed, 2 skipped** (Windows symlink capability).
- Independent Python, input handling and code review: approved; targeted drive
  and setup recovery tests passed.
- Rendered the actual Qt drive selector: the selected drive name is visible,
  while its identifier remains the submitted value.
- Frozen Windows build **1.5.0.2** passed desktop smoke validation with isolated
  configuration and preserved local Google OAuth configuration.

Live Microsoft authorization and remote transfers still require the user's
account session; these checks validate selection behavior, not cloud sync.
