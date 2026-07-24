"""
tests/test_notifications.py

Tests for src.notifications: verifies the toast notification is only
attempted on Windows, is invoked with console suppression, never raises
(even when the underlying subprocess call fails), and correctly escapes
single quotes to avoid breaking the embedded PowerShell script.

Run with: pytest tests/test_notifications.py -v
"""

from __future__ import annotations

import subprocess
import sys

import pytest

import src.notifications as notifications_module
from src.notifications import show_windows_toast


def test_non_windows_platforms_do_not_invoke_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: calls.append((a, kw)))

    show_windows_toast("Title", "Message")

    assert calls == [], "No subprocess call should happen on non-Windows platforms."


def test_windows_invokes_powershell_with_no_window(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")

    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs

        class FakeCompleted:
            returncode = 0
            stdout = ""
            stderr = ""

        return FakeCompleted()

    monkeypatch.setattr(subprocess, "run", fake_run)

    show_windows_toast("Download complete", "2 folder(s) synced successfully.")

    assert captured["command"][0] == "powershell.exe"
    assert captured["kwargs"].get("creationflags") == 0x08000000
    assert captured["kwargs"].get("timeout") is not None


def test_message_content_reaches_the_script(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")

    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command

        class FakeCompleted:
            returncode = 0
            stdout = ""
            stderr = ""

        return FakeCompleted()

    monkeypatch.setattr(subprocess, "run", fake_run)

    show_windows_toast("My Title", "My Message")

    script = captured["command"][-1]
    assert "My Title" in script
    assert "My Message" in script


def test_single_quotes_in_message_are_escaped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")

    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command

        class FakeCompleted:
            returncode = 0
            stdout = ""
            stderr = ""

        return FakeCompleted()

    monkeypatch.setattr(subprocess, "run", fake_run)

    show_windows_toast("Title", "It's done")

    script = captured["command"][-1]
    # PowerShell's escape convention for a single-quoted string is to
    # double the embedded quote.
    assert "It''s done" in script


def test_subprocess_failure_is_swallowed_not_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")

    def failing_run(*args, **kwargs):
        raise OSError("powershell.exe not found")

    monkeypatch.setattr(subprocess, "run", failing_run)

    # Must not raise - notifications are best-effort only.
    show_windows_toast("Title", "Message")