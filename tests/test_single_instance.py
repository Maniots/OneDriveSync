"""
tests/test_single_instance.py

Tests for src.single_instance: verifies that a second attempt to acquire
the lock fails while the first holder is still alive, and succeeds again
once released - the core guarantee that prevents two scheduled tasks
(e.g. the delayed startup download and the periodic upload) from running
robocopy concurrently in opposite directions against the same folder.

The real lock implementation uses msvcrt (Windows-only), so these tests
inject a fake msvcrt module via sys.modules so the Windows code path can
be exercised and verified on any platform, including in CI. The fake uses
only os.fstat() (portable, standard library, no platform-specific module
required) to identify the underlying file, rather than relying on any
OS-specific locking primitive.

Run with: pytest tests/test_single_instance.py -v
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from src.single_instance import acquire_single_instance_lock


class _FakeMsvcrt:
    """A minimal, fully portable stand-in for the msvcrt module's locking().

    Tracks which underlying files (identified by (device, inode) via
    os.fstat - standard library, no platform-specific module needed) are
    currently "locked" in a simple set, so tests can exercise the real
    Windows code path in src.single_instance (which does `import msvcrt`
    internally) without needing real Windows or any Unix-only module like
    fcntl - Python's import statement checks sys.modules first, so
    injecting this object there satisfies the import on any platform.

    Because this is a same-process fake rather than a real OS lock, it
    cannot observe a file handle actually being closed. Call release_all()
    to explicitly simulate the OS releasing all locks (what real Windows
    does automatically when a locked file handle is closed).
    """

    LK_NBLCK = 2  # matches the real msvcrt module's constant value

    def __init__(self) -> None:
        self._locked_keys: set[tuple[int, int]] = set()

    def locking(self, fd: int, mode: int, nbytes: int) -> None:
        stat_result = os.fstat(fd)
        key = (stat_result.st_dev, stat_result.st_ino)
        if key in self._locked_keys:
            raise OSError("Fake lock already held (simulating a real OS lock conflict).")
        self._locked_keys.add(key)

    def release_all(self) -> None:
        self._locked_keys.clear()


@pytest.fixture()
def fake_windows(monkeypatch: pytest.MonkeyPatch) -> _FakeMsvcrt:
    """Force the Windows code path and inject a fake msvcrt module."""
    fake_msvcrt = _FakeMsvcrt()
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)
    return fake_msvcrt


def test_second_acquisition_fails_while_first_is_held(
    tmp_path: Path, fake_windows: _FakeMsvcrt
) -> None:
    lock_path = tmp_path / "test.lock"

    first_handle = acquire_single_instance_lock(lock_path)
    assert first_handle is not None, "First acquisition should succeed."

    second_handle = acquire_single_instance_lock(lock_path)
    assert second_handle is None, (
        "Second acquisition must fail while the first instance still holds "
        "the lock - this is what prevents two scheduled tasks (e.g. startup "
        "download and periodic upload) from running robocopy concurrently."
    )

    first_handle.close()


def test_lock_can_be_reacquired_after_release(
    tmp_path: Path, fake_windows: _FakeMsvcrt
) -> None:
    lock_path = tmp_path / "test.lock"

    first_handle = acquire_single_instance_lock(lock_path)
    assert first_handle is not None
    first_handle.close()
    # The real OS releases the lock automatically when the handle is
    # closed. This fake can't observe that event on its own, so we
    # simulate it explicitly here.
    fake_windows.release_all()

    second_handle = acquire_single_instance_lock(lock_path)
    assert second_handle is not None, (
        "Once the first instance releases the lock (e.g. process exit after "
        "a sync finishes), a subsequent run must be able to acquire it."
    )
    second_handle.close()


def test_lock_file_is_created_if_missing(tmp_path: Path, fake_windows: _FakeMsvcrt) -> None:
    lock_path = tmp_path / "nested" / "does_not_exist_yet.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    handle = acquire_single_instance_lock(lock_path)
    assert handle is not None
    assert lock_path.exists()
    handle.close()


def test_non_windows_platforms_do_not_enforce_locking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    lock_path = tmp_path / "test.lock"

    first_handle = acquire_single_instance_lock(lock_path)
    second_handle = acquire_single_instance_lock(lock_path)

    assert first_handle is not None
    assert second_handle is not None, (
        "Non-Windows platforms intentionally don't enforce single-instance "
        "locking (it exists specifically as a Windows Task Scheduler safety net)."
    )

    first_handle.close()
    second_handle.close()