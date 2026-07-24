"""
notifications.py

Best-effort Windows toast notifications, with zero third-party
dependencies - implemented by shelling out to PowerShell's built-in
access to the Windows Runtime toast notification APIs, which ship with
every Windows 10/11 install.

Showing a notification is a convenience layered on top of the sync
result, never a correctness concern: if it fails for any reason (running
on a non-Windows platform, PowerShell missing or blocked, notifications
disabled by the user, etc.), that failure is logged and swallowed rather
than affecting the sync's own success/failure outcome or exit code.
"""

from __future__ import annotations

import subprocess
import sys

from .logger import get_logger

logger = get_logger(__name__)

# Windows CREATE_NO_WINDOW process creation flag (0x08000000). See
# robocopy_manager.py for why this is defined locally rather than via
# subprocess.CREATE_NO_WINDOW (that attribute doesn't exist on non-Windows
# Python builds).
_CREATE_NO_WINDOW = 0x08000000

# A well-known trick: this AUMID corresponds to PowerShell's own
# auto-registered Start Menu identity, so Windows accepts it as a valid
# toast notifier without requiring this application to register its own
# AUMID (which arbitrary custom strings generally cannot do reliably).
_TOAST_APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"

_TOAST_SCRIPT_TEMPLATE = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

$AppId = '{app_id}'

$template = @'
<toast>
    <visual>
        <binding template="ToastGeneric">
            <text>{title}</text>
            <text>{message}</text>
        </binding>
    </visual>
</toast>
'@

$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($template)
$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($AppId).Show($toast)
"""


def show_windows_toast(title: str, message: str) -> None:
    """Best-effort attempt to show a Windows toast notification.

    Never raises. Any failure is logged at WARNING level and otherwise
    ignored - a missing notification should never fail a sync run.

    Args:
        title: Toast title line.
        message: Toast body line.
    """
    if sys.platform != "win32":
        return

    # Single quotes are the PowerShell string delimiter used in the
    # template above, so escape any embedded single quotes (doubling them
    # is PowerShell's own escape convention) to avoid breaking the script.
    safe_title = title.replace("'", "''")
    safe_message = message.replace("'", "''")
    script = _TOAST_SCRIPT_TEMPLATE.format(
        app_id=_TOAST_APP_ID, title=safe_title, message=safe_message
    )

    try:
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-WindowStyle",
                "Hidden",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
            creationflags=_CREATE_NO_WINDOW,
        )
    except Exception:  # noqa: BLE001 - notifications are best-effort only
        logger.warning("Could not show Windows notification (non-fatal).", exc_info=True)