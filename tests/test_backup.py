"""
tests/test_backup.py

Tests for the automatic pre-upload backup feature: config validation
(backups must live inside OneDrive, never on local disk), archive
creation, retention pruning, and end-to-end wiring into SyncManager so a
backup happens before every UPLOAD and never before a DOWNLOAD.

Run with: pytest tests/test_backup.py -v
"""

from __future__ import annotations

import json
import os
import time
import zipfile
from pathlib import Path

import pytest

from src.backup_manager import BackupManager
from src.config import (
    AppConfig,
    BackupSettings,
    FolderSyncConfig,
    GeneralSettings,
    RobocopySettings,
    SyncDirection,
    SyncSettings,
    SyncTriggerSettings,
)
from src.config_manager import ConfigManager
from src.exceptions import ConfigurationError
from src.robocopy_manager import RobocopyManager, RobocopyResult
from src.sync_manager import SyncManager
from src.utils import is_under_onedrive_root


# --- Config validation: backups must live inside OneDrive -------------------


def _base_config_dict() -> dict:
    return {
        "general": {
            "log_level": "INFO",
            "dry_run": True,
            "verify_after_sync": False,
            "create_destination": True,
            "max_parallel_jobs": 1,
        },
        "sync": {
            "startup": {"enabled": True, "direction": "download"},
            "shutdown": {"enabled": True, "direction": "upload"},
        },
        "robocopy": {
            "retry_count": 2,
            "retry_wait_seconds": 2,
            "multithreading": 8,
            "copy_subdirectories": True,
            "copy_empty_directories": True,
            "exclude_junctions": True,
            "fat_file_times": True,
            "monitor_mode": False,
        },
        "folders": [],
    }


def test_backup_path_outside_onedrive_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OneDrive", str(tmp_path / "OneDrive"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))

    config_dict = _base_config_dict()
    config_dict["folders"] = [
        {
            "id": "elden_ring",
            "name": "Elden Ring Save",
            "enabled": True,
            "local_path": "%APPDATA%\\EldenRing",
            "onedrive_path": "%OneDrive%\\PCSync\\AppData\\Roaming\\EldenRing",
            "minimum_sync_percentage": 80,
            "verify_after_sync": True,
            "create_destination": True,
            "backup": {
                "enabled": True,
                # Deliberately a LOCAL disk path, not under %OneDrive% - must be rejected.
                "backup_path": str(tmp_path / "LocalBackups"),
                "retention_days": 7,
            },
        }
    ]
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config_dict), encoding="utf-8")

    with pytest.raises(ConfigurationError):
        ConfigManager(config_path).load()


def test_backup_path_inside_onedrive_is_accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    onedrive_root = tmp_path / "OneDrive"
    monkeypatch.setenv("OneDrive", str(onedrive_root))
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))

    config_dict = _base_config_dict()
    config_dict["folders"] = [
        {
            "id": "elden_ring",
            "name": "Elden Ring Save",
            "enabled": True,
            "local_path": "%APPDATA%\\EldenRing",
            "onedrive_path": "%OneDrive%\\PCSync\\AppData\\Roaming\\EldenRing",
            "minimum_sync_percentage": 80,
            "verify_after_sync": True,
            "create_destination": True,
            "backup": {
                "enabled": True,
                "backup_path": "%OneDrive%/PCSync/Backups",
                "retention_days": 7,
            },
        }
    ]
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config_dict), encoding="utf-8")

    config = ConfigManager(config_path).load()
    folder = config.folders[0]

    assert folder.backup is not None
    assert folder.backup.enabled is True
    assert is_under_onedrive_root(folder.backup.backup_path)


def test_backup_missing_backup_path_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OneDrive", str(tmp_path / "OneDrive"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))

    config_dict = _base_config_dict()
    config_dict["folders"] = [
        {
            "id": "elden_ring",
            "name": "Elden Ring Save",
            "enabled": True,
            "local_path": "%APPDATA%\\EldenRing",
            "onedrive_path": "%OneDrive%\\PCSync\\AppData\\Roaming\\EldenRing",
            "minimum_sync_percentage": 80,
            "verify_after_sync": True,
            "create_destination": True,
            "backup": {"enabled": True, "retention_days": 7},
        }
    ]
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config_dict), encoding="utf-8")

    with pytest.raises(ConfigurationError):
        ConfigManager(config_path).load()


def test_backup_disabled_or_absent_parses_to_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OneDrive", str(tmp_path / "OneDrive"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))

    config_dict = _base_config_dict()
    config_dict["folders"] = [
        {
            "id": "no_backup_section",
            "name": "No Backup Section",
            "enabled": True,
            "local_path": "%APPDATA%\\A",
            "onedrive_path": "%OneDrive%\\PCSync\\AppData\\Roaming\\A",
            "minimum_sync_percentage": 80,
            "verify_after_sync": True,
            "create_destination": True,
        },
        {
            "id": "explicitly_disabled",
            "name": "Explicitly Disabled",
            "enabled": True,
            "local_path": "%APPDATA%\\B",
            "onedrive_path": "%OneDrive%\\PCSync\\AppData\\Roaming\\B",
            "minimum_sync_percentage": 80,
            "verify_after_sync": True,
            "create_destination": True,
            "backup": {"enabled": False},
        },
    ]
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config_dict), encoding="utf-8")

    config = ConfigManager(config_path).load()
    assert config.folders[0].backup is None
    assert config.folders[1].backup is None


def test_backup_retention_days_must_be_positive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OneDrive", str(tmp_path / "OneDrive"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))

    config_dict = _base_config_dict()
    config_dict["folders"] = [
        {
            "id": "elden_ring",
            "name": "Elden Ring Save",
            "enabled": True,
            "local_path": "%APPDATA%\\EldenRing",
            "onedrive_path": "%OneDrive%\\PCSync\\AppData\\Roaming\\EldenRing",
            "minimum_sync_percentage": 80,
            "verify_after_sync": True,
            "create_destination": True,
            "backup": {
                "enabled": True,
                "backup_path": "%OneDrive%\\PCSync\\Backups",
                "retention_days": 0,
            },
        }
    ]
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config_dict), encoding="utf-8")

    with pytest.raises(ConfigurationError):
        ConfigManager(config_path).load()


# --- BackupManager: archive creation and retention pruning -----------------


def test_create_backup_compresses_existing_files(tmp_path: Path) -> None:
    onedrive_path = tmp_path / "OneDrive" / "PCSync" / "AppData" / "Roaming" / "EldenRing"
    onedrive_path.mkdir(parents=True)
    (onedrive_path / "save1.sl2").write_text("save data 1")
    (onedrive_path / "save2.sl2").write_text("save data 2")

    backup_settings = BackupSettings(
        enabled=True,
        backup_path=tmp_path / "OneDrive" / "PCSync" / "Backups",
        retention_days=7,
    )

    manager = BackupManager(dry_run=False)
    archive_path = manager.create_backup("elden_ring", backup_settings, onedrive_path)

    assert archive_path is not None
    assert archive_path.exists()
    with zipfile.ZipFile(archive_path) as zf:
        names = set(zf.namelist())
    assert "save1.sl2" in names
    assert "save2.sl2" in names


def test_create_backup_skips_when_destination_empty(tmp_path: Path) -> None:
    onedrive_path = tmp_path / "OneDrive" / "PCSync" / "AppData" / "Roaming" / "EldenRing"
    # Deliberately not creating any files - first-time-sync scenario.

    backup_settings = BackupSettings(
        enabled=True,
        backup_path=tmp_path / "OneDrive" / "PCSync" / "Backups",
        retention_days=7,
    )

    manager = BackupManager(dry_run=False)
    archive_path = manager.create_backup("elden_ring", backup_settings, onedrive_path)

    assert archive_path is None


def test_create_backup_dry_run_creates_no_archive(tmp_path: Path) -> None:
    onedrive_path = tmp_path / "OneDrive" / "PCSync" / "AppData" / "Roaming" / "EldenRing"
    onedrive_path.mkdir(parents=True)
    (onedrive_path / "save1.sl2").write_text("save data 1")

    backup_settings = BackupSettings(
        enabled=True,
        backup_path=tmp_path / "OneDrive" / "PCSync" / "Backups",
        retention_days=7,
    )

    manager = BackupManager(dry_run=True)
    archive_path = manager.create_backup("elden_ring", backup_settings, onedrive_path)

    assert archive_path is None
    backup_dir = backup_settings.backup_path / "elden_ring"
    assert not backup_dir.exists() or list(backup_dir.glob("*.zip")) == []


def test_prune_old_backups_deletes_expired_archives_only(tmp_path: Path) -> None:
    backup_dir = tmp_path / "Backups" / "elden_ring"
    backup_dir.mkdir(parents=True)

    old_archive = backup_dir / "elden_ring_20200101_000000.zip"
    old_archive.write_text("old")
    recent_archive = backup_dir / "elden_ring_20990101_000000.zip"
    recent_archive.write_text("recent")

    # Backdate the "old" archive's mtime to 30 days ago.
    thirty_days_ago = time.time() - (30 * 86400)
    os.utime(old_archive, (thirty_days_ago, thirty_days_ago))

    backup_settings = BackupSettings(
        enabled=True, backup_path=tmp_path / "Backups", retention_days=7
    )

    manager = BackupManager(dry_run=False)
    manager.prune_old_backups("elden_ring", backup_settings)

    assert not old_archive.exists()
    assert recent_archive.exists()


def test_prune_old_backups_dry_run_deletes_nothing(tmp_path: Path) -> None:
    backup_dir = tmp_path / "Backups" / "elden_ring"
    backup_dir.mkdir(parents=True)

    old_archive = backup_dir / "elden_ring_20200101_000000.zip"
    old_archive.write_text("old")
    thirty_days_ago = time.time() - (30 * 86400)
    os.utime(old_archive, (thirty_days_ago, thirty_days_ago))

    backup_settings = BackupSettings(
        enabled=True, backup_path=tmp_path / "Backups", retention_days=7
    )

    manager = BackupManager(dry_run=True)
    manager.prune_old_backups("elden_ring", backup_settings)

    assert old_archive.exists()


# --- End-to-end wiring: backups only happen before UPLOAD, never DOWNLOAD --


def _make_app_config_with_backup(tmp_path: Path, dry_run: bool) -> AppConfig:
    general = GeneralSettings(dry_run=dry_run, verify_after_sync=False, create_destination=True)
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
        minimum_sync_percentage=80.0,
        verify_after_sync=False,
        create_destination=True,
        backup=BackupSettings(
            enabled=True,
            backup_path=tmp_path / "OneDrive" / "Backups",
            retention_days=7,
        ),
    )
    return AppConfig(general=general, sync=sync, robocopy=robocopy, folders=[folder])


def _stub_successful_robocopy_run(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(self: RobocopyManager, source: Path, destination: Path) -> RobocopyResult:
        return RobocopyResult(
            source=source, destination=destination, exit_code=0,
            success=True, stdout="", stderr="", dry_run=self._dry_run,
        )
    monkeypatch.setattr(RobocopyManager, "run", fake_run)


def test_backup_is_created_before_upload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_successful_robocopy_run(monkeypatch)
    config = _make_app_config_with_backup(tmp_path, dry_run=False)

    onedrive_path = config.folders[0].onedrive_path
    onedrive_path.mkdir(parents=True)
    (onedrive_path / "existing.txt").write_text("existing OneDrive content")
    local_path = config.folders[0].local_path
    local_path.mkdir(parents=True)
    (local_path / "new.txt").write_text("newer local content")

    manager = SyncManager(config)
    outcomes = manager.run_shutdown_sync()  # upload: local -> onedrive

    assert outcomes[0].succeeded is True
    backup_dir = config.folders[0].backup.backup_path / "test_folder"
    archives = list(backup_dir.glob("*.zip"))
    assert len(archives) == 1, "Expected exactly one backup archive to be created before the upload."


def test_backup_is_not_created_before_download(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_successful_robocopy_run(monkeypatch)
    config = _make_app_config_with_backup(tmp_path, dry_run=False)

    onedrive_path = config.folders[0].onedrive_path
    onedrive_path.mkdir(parents=True)
    (onedrive_path / "existing.txt").write_text("existing OneDrive content")
    local_path = config.folders[0].local_path
    local_path.mkdir(parents=True)
    (local_path / "existing.txt").write_text("existing local content")

    manager = SyncManager(config)
    outcomes = manager.run_startup_sync()  # download: onedrive -> local

    assert outcomes[0].succeeded is True
    backup_dir = config.folders[0].backup.backup_path / "test_folder"
    assert not backup_dir.exists(), "No backup should ever be created before a DOWNLOAD."