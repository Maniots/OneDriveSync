"""
tests/test_sync.py

Tests for the safety-critical logic used by src.sync_manager:
dangerous-root-path detection and the file-count percentage threshold.
Also exercises SyncManager end-to-end against real temp directories
using dry_run=True so no files are ever actually copied by these tests.

Run with: pytest tests/test_sync.py -v
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from src.config import (
    AppConfig,
    FolderSyncConfig,
    GeneralSettings,
    RobocopySettings,
    SyncDirection,
    SyncSettings,
    SyncTriggerSettings,
)
from src.exceptions import SyncThresholdExceededError
from src.robocopy_manager import RobocopyManager, RobocopyResult
from src.sync_manager import SyncManager
from src.utils import calculate_sync_percentage, is_dangerous_root_path


def _stub_successful_robocopy_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace RobocopyManager.run with a stub that always succeeds.

    sync_manager.py's own safety checks (path validation, percentage
    threshold) run BEFORE robocopy is ever invoked, so these tests can
    safely stub out the actual copy engine - robocopy itself is a
    Windows-only executable that isn't available in this environment.
    RobocopyManager's own command-building and exit-code logic is
    covered separately in test_robocopy.py.
    """

    def fake_run(self: RobocopyManager, source: Path, destination: Path) -> RobocopyResult:
        return RobocopyResult(
            source=source,
            destination=destination,
            exit_code=0,
            success=True,
            stdout="",
            stderr="",
            dry_run=self._dry_run,
        )

    monkeypatch.setattr(RobocopyManager, "run", fake_run)


# --- Pure safety-logic tests -------------------------------------------------


@pytest.mark.parametrize(
    "raw_path",
    [
        r"C:\Users\john\AppData",
        r"C:\Users\john\AppData\Local",
        r"C:\Users\john\AppData\Roaming",
        r"C:\Users\john\AppData\LocalLow",
        r"C:\Users\john",
        "C:\\",
    ],
)
def test_dangerous_roots_are_detected(raw_path: str) -> None:
    assert is_dangerous_root_path(Path(raw_path)) is True


@pytest.mark.parametrize(
    "raw_path",
    [
        r"C:\Users\john\AppData\Roaming\EldenRing",
        r"C:\Users\john\OneDrive\PCSync\AppData\Roaming\EldenRing",
        r"C:\Users\john\AppData\Roaming\Opera Software\Opera GX Stable",
    ],
)
def test_safe_paths_are_not_flagged(raw_path: str) -> None:
    assert is_dangerous_root_path(Path(raw_path)) is False


def test_percentage_ratio_is_symmetric_and_safe() -> None:
    assert calculate_sync_percentage(1000, 950) == pytest.approx(95.0)
    assert calculate_sync_percentage(950, 1000) == pytest.approx(95.0)


def test_percentage_ratio_flags_dangerous_mismatch() -> None:
    assert calculate_sync_percentage(5, 5000) == pytest.approx(0.1)


# --- End-to-end SyncManager tests (dry_run, real temp dirs) -----------------


def _make_config(tmp_path: Path, minimum_sync_percentage: float = 80.0) -> AppConfig:
    general = GeneralSettings(dry_run=True, verify_after_sync=False, create_destination=True)
    sync = SyncSettings(
        startup=SyncTriggerSettings(enabled=True, direction=SyncDirection.DOWNLOAD),
        shutdown=SyncTriggerSettings(enabled=True, direction=SyncDirection.UPLOAD),
    )
    robocopy = RobocopySettings()
    folder = FolderSyncConfig(
        id="test_folder",
        name="Test Folder",
        enabled=True,
        local_path=tmp_path / "Local" / "TestApp",
        onedrive_path=tmp_path / "OneDrive" / "TestApp",
        minimum_sync_percentage=minimum_sync_percentage,
        verify_after_sync=False,
        create_destination=True,
    )
    return AppConfig(general=general, sync=sync, robocopy=robocopy, folders=[folder])


def _populate(directory: Path, file_count: int) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for i in range(file_count):
        (directory / f"file_{i}.txt").write_text("data", encoding="utf-8")


def test_first_time_sync_to_empty_destination_is_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_successful_robocopy_run(monkeypatch)
    config = _make_config(tmp_path)
    _populate(config.folders[0].local_path, file_count=10)
    # Destination intentionally left empty/non-existent.

    manager = SyncManager(config)
    outcomes = manager.run_shutdown_sync()  # upload: local -> onedrive

    assert len(outcomes) == 1
    assert outcomes[0].succeeded is True


def test_sync_below_threshold_is_aborted(tmp_path: Path) -> None:
    config = _make_config(tmp_path, minimum_sync_percentage=80.0)
    _populate(config.folders[0].local_path, file_count=5)
    _populate(config.folders[0].onedrive_path, file_count=5000)

    manager = SyncManager(config)
    outcomes = manager.run_shutdown_sync()

    assert len(outcomes) == 1
    assert outcomes[0].succeeded is False
    assert "safety threshold" in outcomes[0].message


def test_sync_within_threshold_proceeds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_successful_robocopy_run(monkeypatch)
    config = _make_config(tmp_path, minimum_sync_percentage=80.0)
    _populate(config.folders[0].local_path, file_count=1000)
    _populate(config.folders[0].onedrive_path, file_count=950)

    manager = SyncManager(config)
    outcomes = manager.run_shutdown_sync()

    assert len(outcomes) == 1
    assert outcomes[0].succeeded is True


def test_disabled_folder_is_skipped(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    disabled_folder = replace(config.folders[0], enabled=False)
    config = replace(config, folders=[disabled_folder])

    manager = SyncManager(config)
    outcomes = manager.run_startup_sync()

    assert outcomes == []