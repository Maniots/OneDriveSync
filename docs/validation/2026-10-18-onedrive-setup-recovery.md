# OneDrive setup recovery

User report: OneDrive online displayed both "Choose an account setup option"
and "The provider rejected that answer", without a useful choice.

## Cause and correction

Pinned rclone 1.75.2 returns `State + Error + Option: null` when OneDrive drive
discovery fails. The service treated any state as an answer question; the UI
therefore displayed a placeholder and a blank input. This lost the distinction
between a provider error and a rejected user answer.

The service now preserves error-only states as explicit retry steps and emits
static safe messages. The UI hides answer controls and shows **Retry account
setup**. OneDrive's recognized discovery failure with fallback state `driveid`
retries state `onedrive`, listing drives again without asking for a manual ID.
Other error states remain unchanged. Error-free states without questions can
advance automatically, within the existing transition cap. Account/drive
decisions remain explicit; cancel still removes only pending credentials.

## Evidence

- Four regression tests reproduced the previous behavior and failed before
  implementation, then passed after the correction.
- Focused setup/account/UI tests: **31 passed**.
- A native pinned-rclone test uses an isolated loopback Graph fixture and dummy
  tokens: a 403 response produces the actual `driveid + Error + null Option`
  shape, then a successful retry returns `config_driveid`. No Microsoft files
  or real tokens are used by this test.
- Full repository suite: **411 passed, 2 skipped**. The skips are existing
  symlink-environment cases in test_copy_engine.
- A bounded diagnostic using the existing authorized pending OneDrive account
  successfully rediscovered drives and returned `config_driveid`. Only safe
  result flags were output. This supports a transient discovery problem followed
  by the former UI trap; it does not establish a persistent permission issue.
- Styled Qt rendering confirmed a useful recovery message, visible retry/cancel
  controls, hidden answer inputs and no raw provider error text.
- Independent contract, security and Python review approved the correction.

## Desktop delivery

Built the frozen Windows desktop and installer as **1.5.0.1**. Frozen UI smoke
and resource checks passed; the locally configured Google application metadata
was preserved in the package and remains excluded from Git.

Updated the user's installed copy through the existing checksum-verified update
helper after an idle-sync check and graceful desktop exit. Installed diagnostics
report 1.5.0.1; the user configuration hash and Google metadata match their
pre-update values. EverySync was restarted from its installed location.

Real cloud file transfers and other Microsoft account types are outside this
recovery check. Provider errors remain retryable, rather than being reported as
successful authorization or an empty drive list.
