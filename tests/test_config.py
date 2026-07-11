"""
tests/test_config.py

Tests for src.config_manager: JSON loading, environment variable
expansion, and rejection of dangerous configuration values.

Run with: pytest tests/test_config.py -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.config_manager import ConfigManager
from src.exceptions import ConfigurationError, PathValidationError


@pytest.fixture()
def base_config_dict() -> dict:
    """A minimal, valid configuration dictionary to build test cases from."""
    return {
        "general": {
            "log_level": "INFO",
            "dry_run": True,
            "verify_after_sync": True,
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


def _write_config(tmp_path: Path, data: dict) -> Path:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(data), encoding="utf-8")
    return config_path


def test_load_valid_config_with_no_folders(tmp_path: Path, base_config_dict: dict) -> None:
    config_path = _write_config(tmp_path, base_config_dict)
    config = ConfigManager(config_path).load()
    assert config.general.dry_run is True
    assert config.folders == []


def test_missing_config_file_raises(tmp_path: Path) -> None:
    missing_path = tmp_path / "does_not_exist.json"
    with pytest.raises(ConfigurationError):
        ConfigManager(missing_path).load()


def test_malformed_json_raises(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{ this is not valid json", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        ConfigManager(config_path).load()


def test_env_var_expansion(tmp_path: Path, base_config_dict: dict, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
    monkeypatch.setenv("OneDrive", str(tmp_path / "OneDrive"))

    base_config_dict["folders"] = [
        {
            "id": "elden_ring",
            "name": "Elden Ring Save",
            "enabled": True,
            "local_path": "%APPDATA%\\EldenRing",
            "onedrive_path": "%OneDrive%\\PCSync\\AppData\\Roaming\\EldenRing",
            "minimum_sync_percentage": 80,
            "verify_after_sync": True,
            "create_destination": True,
        }
    ]
    config_path = _write_config(tmp_path, base_config_dict)
    config = ConfigManager(config_path).load()

    folder = config.folders[0]
    assert "%APPDATA%" not in str(folder.local_path)
    assert "%OneDrive%" not in str(folder.onedrive_path)
    assert str(folder.local_path).endswith("EldenRing")


def test_dangerous_root_local_path_is_rejected(tmp_path: Path, base_config_dict: dict, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
    monkeypatch.setenv("OneDrive", str(tmp_path / "OneDrive"))

    base_config_dict["folders"] = [
        {
            "id": "bad",
            "name": "Bad Folder",
            "enabled": True,
            "local_path": "%APPDATA%",  # forbidden: bare AppData\Roaming root
            "onedrive_path": "%OneDrive%\\PCSync\\AppData\\Roaming\\Bad",
            "minimum_sync_percentage": 80,
            "verify_after_sync": True,
            "create_destination": True,
        }
    ]
    config_path = _write_config(tmp_path, base_config_dict)

    with pytest.raises(PathValidationError):
        ConfigManager(config_path).load()


def test_identical_source_and_destination_is_rejected(tmp_path: Path, base_config_dict: dict) -> None:
    same_path = str(tmp_path / "Shared")
    base_config_dict["folders"] = [
        {
            "id": "dup",
            "name": "Duplicate Path",
            "enabled": True,
            "local_path": same_path,
            "onedrive_path": same_path,
            "minimum_sync_percentage": 80,
            "verify_after_sync": True,
            "create_destination": True,
        }
    ]
    config_path = _write_config(tmp_path, base_config_dict)

    with pytest.raises(PathValidationError):
        ConfigManager(config_path).load()


def test_duplicate_folder_ids_are_rejected(tmp_path: Path, base_config_dict: dict) -> None:
    entry = {
        "id": "same_id",
        "name": "Folder A",
        "enabled": True,
        "local_path": str(tmp_path / "Local" / "A"),
        "onedrive_path": str(tmp_path / "OneDrive" / "A"),
        "minimum_sync_percentage": 80,
        "verify_after_sync": True,
        "create_destination": True,
    }
    other = dict(entry)
    other["local_path"] = str(tmp_path / "Local" / "B")
    other["onedrive_path"] = str(tmp_path / "OneDrive" / "B")

    base_config_dict["folders"] = [entry, other]
    config_path = _write_config(tmp_path, base_config_dict)

    with pytest.raises(ConfigurationError):
        ConfigManager(config_path).load()