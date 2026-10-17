"""Persistence and safety boundaries for additive cloud configuration."""
import json
import os
import subprocess
from dataclasses import replace

import pytest

from backend.services.configuration_service import ConfigurationService
from src.config_manager import ConfigManager
from src.exceptions import ConfigurationError


def cloud_raw(tmp_path):
    return {
        "folders": [],
        "connections": [{"id": "office", "name": "Office", "provider": "onedrive", "root": "EverySync"}],
        "remote_jobs": [{"id": "saves", "name": "Game saves", "local_path": str(tmp_path / "saves"),
                         "connection_id": "office", "remote_path": "Games/Saves"}],
    }


def write_config(tmp_path, raw):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return ConfigManager(path)


def test_cloud_roundtrip_and_local_fixture(tmp_path):
    from src.cloud_models import ConnectionConfig, RemoteJobConfig

    manager = write_config(tmp_path, cloud_raw(tmp_path))
    config = manager.load()
    assert config.connections == [ConnectionConfig("office", "Office", "onedrive", "EverySync")]
    assert config.remote_jobs == [RemoteJobConfig("saves", "Game saves", str(tmp_path / "saves"), "office", "Games/Saves")]
    assert config.remote_jobs[0].local_path_resolved == (tmp_path / "saves").resolve()
    manager.save(config)
    assert manager.load() == config
    local = replace(config.connections[0], provider="local", root=str(tmp_path / "remote"))
    manager.save(replace(config, connections=[local]))
    assert manager.load().connections == [local]


def test_legacy_config_shape_and_arbitrary_folder_ids_survive(tmp_path):
    raw = {"folders": [{"id": "Old Folder.ID-1", "local_path": str(tmp_path / "a"), "onedrive_path": str(tmp_path / "b")}]}
    manager = write_config(tmp_path, raw)
    config = manager.load()
    assert config.connections == [] and config.remote_jobs == []
    manager.save(config)
    saved = json.loads(manager.config_path.read_text(encoding="utf-8"))
    assert "connections" not in saved and "remote_jobs" not in saved
    assert saved["folders"][0]["id"] == "Old Folder.ID-1"


@pytest.mark.parametrize("mutation", [
    lambda r: r["connections"].append(r["connections"][0].copy()),
    lambda r: r["remote_jobs"].append(r["remote_jobs"][0].copy()),
    lambda r: r["remote_jobs"][0].update(connection_id="missing"),
    lambda r: r["connections"][0].update(id="Bad-ID"),
    lambda r: r["connections"][0].update(provider="unknown"),
    lambda r: r["connections"][0].update(token="secret"),
    lambda r: r["remote_jobs"][0].update(password="secret"),
    lambda r: r["remote_jobs"][0].update(enabled="false"),
    lambda r: r["remote_jobs"][0].update(minimum_sync_percentage=101),
    lambda r: r["remote_jobs"][0].update(minimum_sync_percentage=float("nan")),
])
def test_invalid_cloud_config_is_rejected(tmp_path, mutation):
    raw = cloud_raw(tmp_path)
    mutation(raw)
    with pytest.raises(ConfigurationError):
        write_config(tmp_path, raw).load()


def test_remote_and_legacy_ids_share_uniqueness(tmp_path):
    raw = cloud_raw(tmp_path)
    raw["folders"] = [{"id": "saves", "local_path": str(tmp_path / "a"), "onedrive_path": str(tmp_path / "b")}]
    with pytest.raises(ConfigurationError):
        write_config(tmp_path, raw).load()


@pytest.mark.parametrize("path", ["", ".", "..", "a/../b", "/root", "C:/drive", "remote:path", "a\\b", "a//b",
                                 "a/./b", ".everysync/backup", "a/.EVERYSYNC", "NUL", "con.txt", "COM1/file",
                                 "name.", "name ", "a\x00b", "a?b", "a*b"])
def test_remote_paths_are_scoped_and_windows_safe(tmp_path, path):
    raw = cloud_raw(tmp_path)
    raw["remote_jobs"][0]["remote_path"] = path
    with pytest.raises(ConfigurationError):
        write_config(tmp_path, raw).load()


@pytest.mark.parametrize("bucket", ["ab", "BadBucket", "bucket..name", "192.168.0.1", "-bucket", "bucket-"])
def test_s3_root_rejects_invalid_bucket_names(tmp_path, bucket):
    raw = cloud_raw(tmp_path)
    raw["connections"][0].update(provider="s3", root=bucket + "/saves")
    with pytest.raises(ConfigurationError):
        write_config(tmp_path, raw).load()


def test_local_connection_cannot_overlap_local_job_tree(tmp_path):
    raw = cloud_raw(tmp_path)
    raw["connections"][0].update(provider="local", root=str(tmp_path / "saves" / "remote"))
    with pytest.raises(ConfigurationError):
        write_config(tmp_path, raw).load()
    raw["connections"][0]["root"] = str(tmp_path)
    with pytest.raises(ConfigurationError):
        write_config(tmp_path, raw).load()


@pytest.mark.parametrize("value", ["relative/folder", "C:\\", "C:/Users/NUL", "C:/Users/bad:file", "%NOT_DEFINED%/folder"])
def test_local_path_must_be_expanded_safe_absolute(value):
    from src.cloud_models import validate_local_path

    with pytest.raises(ValueError):
        validate_local_path(value)


@pytest.mark.skipif(os.name != "nt", reason="Windows device namespaces")
@pytest.mark.parametrize("namespace", ["\\\\?\\", "\\\\.\\"])
def test_local_path_rejects_windows_device_namespace(tmp_path, namespace):
    from src.cloud_models import validate_local_path

    with pytest.raises(ValueError):
        validate_local_path(namespace + str(tmp_path))


def test_local_path_rejects_real_directory_redirect(tmp_path):
    from src.cloud_models import validate_local_path

    target = tmp_path / "target"
    target.mkdir()
    redirect = tmp_path / "redirect"
    if os.name == "nt":
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(redirect), str(target)], capture_output=True)
        assert result.returncode == 0, result.stdout + result.stderr
    else:
        redirect.symlink_to(target, target_is_directory=True)
    try:
        with pytest.raises(ValueError, match="reparse|symbolic"):
            validate_local_path(redirect / "future-child")
    finally:
        if os.name == "nt":
            redirect.rmdir()
        else:
            redirect.unlink()


def test_invalid_cloud_save_preserves_original_config(tmp_path):
    from src.cloud_models import ConnectionConfig

    manager = write_config(tmp_path, cloud_raw(tmp_path))
    config = manager.load()
    original = manager.config_path.read_bytes()
    replacement = ConnectionConfig("other", "Other account", "drive", "EverySync")
    with pytest.raises(ConfigurationError):
        manager.save(replace(config, connections=[replacement]))
    assert manager.config_path.read_bytes() == original
    assert not list(tmp_path.glob(".config.json.*.tmp"))


def test_settings_save_keeps_latest_cloud_configuration(qapp, tmp_path, monkeypatch):
    from src.cloud_models import ConnectionConfig, RemoteJobConfig
    from ui.pages.settings import SettingsPage
    from PySide6.QtWidgets import QMessageBox

    manager = write_config(tmp_path, {"folders": []})
    service = ConfigurationService(manager.config_path)
    page = SettingsPage(service)
    config = service.get_app_config()
    connection = ConnectionConfig("office", "Office", "onedrive", "EverySync")
    job = RemoteJobConfig("saves", "Game saves", str(tmp_path / "saves"), "office", "Games")
    service.save(replace(config, connections=[connection], remote_jobs=[job]))
    monkeypatch.setattr(QMessageBox, "information", lambda *args: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: pytest.fail("Settings save failed"))
    page.dry_run_check.setChecked(True)
    page.on_apply_clicked()
    saved = manager.load()
    assert saved.general.dry_run
    assert saved.connections == [connection] and saved.remote_jobs == [job]


def test_folder_edit_keeps_cloud_configuration(qapp, tmp_path, monkeypatch):
    from ui.pages.folders import FoldersPage
    from PySide6.QtWidgets import QMessageBox

    raw = cloud_raw(tmp_path)
    raw["folders"] = [{"id": "legacy", "name": "Legacy folder", "local_path": str(tmp_path / "old-local"),
                       "onedrive_path": str(tmp_path / "old-remote")}]
    manager = write_config(tmp_path, raw)
    service = ConfigurationService(manager.config_path)
    page = FoldersPage(service)
    original = service.get_app_config()
    folder = original.folders[0]
    updated = ConfigManager._app_config_to_raw_dict(original)["folders"][0]
    updated["name"] = "Updated legacy folder"
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: pytest.fail("Folder edit failed"))
    page.save_folder_data(updated, original_id=folder.id)
    saved = manager.load()
    assert saved.folders[0].name == "Updated legacy folder"
    assert saved.connections == original.connections and saved.remote_jobs == original.remote_jobs
