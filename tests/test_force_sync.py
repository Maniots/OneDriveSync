import json
import os
import time
import zipfile
from dataclasses import replace

import pytest
from PySide6.QtWidgets import QMessageBox

from backend.services.configuration_service import ConfigurationService
from backend.services.sync_service import SyncService
from src.exceptions import BackupError, VerificationError
from src.sync_manager import SyncManager
from ui.pages.folders import FoldersPage
from ui.widgets.folder_card import FolderCard


@pytest.fixture
def pair(tmp_path, monkeypatch):
    local, cloud = tmp_path / "local/app", tmp_path / "OneDrive/app"
    local.mkdir(parents=True)
    cloud.mkdir(parents=True)
    (local / "save.txt").write_text("new")
    (cloud / "save.txt").write_text("old")
    os.utime(cloud / "save.txt", (time.time() - 10, time.time() - 10))
    for n in range(20):
        (cloud / f"preserved-{n}.txt").write_text("keep")
    monkeypatch.setenv("OneDrive", str(cloud.parent))
    data = {"general": {"dry_run": False},
            "sync": {"startup": {"enabled": True, "direction": "download"},
                     "shutdown": {"enabled": True, "direction": "upload"}},
            "folders": [{"id": "app", "name": "App", "enabled": True,
                         "local_path": str(local), "onedrive_path": str(cloud),
                         "minimum_sync_percentage": 80,
                         "backup": {"enabled": True, "backup_path": str(cloud.parent / "Backups"), "retention_days": 7}}]}
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data))
    return ConfigurationService(path), local, cloud, path


def wait(qapp, sync):
    deadline = time.monotonic() + 5
    while sync.is_syncing and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(.001)
    assert not sync.is_syncing


def test_forced_sync_is_one_run_keeps_backup_and_configuration(qapp, pair):
    service, local, cloud, path = pair
    before = path.read_bytes()
    sync = SyncService(service)
    assert sync.request_sync("shutdown", folder_id="app")
    wait(qapp, sync)
    assert (cloud / "save.txt").read_text() == "old"
    assert sync.request_sync("shutdown", folder_id="app", ignore_threshold=True)
    wait(qapp, sync)
    assert (cloud / "save.txt").read_text() == "new"
    assert (cloud / "preserved-0.txt").exists()
    archives = list((cloud.parent / "Backups/app").glob("*.zip"))
    assert len(archives) == 1
    with zipfile.ZipFile(archives[0]) as archive:
        assert archive.read("save.txt") == b"old"
    assert sync.get_history()[0]["outcomes"][0]["threshold_bypassed"]
    assert path.read_bytes() == before
    assert sync.request_sync("shutdown", folder_id="app")
    wait(qapp, sync)
    assert not sync.get_history()[0]["outcomes"][0]["succeeded"]
    assert not sync.get_history()[0]["outcomes"][0]["threshold_bypassed"]


def test_override_applies_only_to_selected_folder(pair):
    service, _, _, _ = pair
    config = service.get_app_config()
    second = replace(config.folders[0], id="other", backup=None)
    outcomes = SyncManager(replace(config, folders=[config.folders[0], second])).run_shutdown_sync(ignore_threshold_for="app")
    assert [o.succeeded for o in outcomes] == [True, False]
    assert [o.threshold_bypassed for o in outcomes] == [True, False]


def test_reusing_manager_does_not_reuse_override(pair):
    service, _, _, _ = pair
    manager = SyncManager(service.get_app_config())
    assert manager.run_shutdown_sync(ignore_threshold_for="app")[0].succeeded
    assert not manager.run_shutdown_sync()[0].succeeded


@pytest.mark.parametrize("failure", ["path", "backup", "verification", "dry_run"])
def test_force_does_not_disable_other_protections(pair, monkeypatch, failure):
    service, _, cloud, _ = pair
    config = service.get_app_config()
    if failure == "path":
        config = replace(config, folders=[replace(config.folders[0], local_path="C:\\")])
    if failure == "dry_run":
        config = replace(config, general=replace(config.general, dry_run=True))
    manager = SyncManager(config)
    if failure == "backup":
        monkeypatch.setattr(manager._backup, "create_backup", lambda *args: (_ for _ in ()).throw(BackupError("Backup failed")))
    if failure == "verification":
        monkeypatch.setattr(manager, "_verify_after_sync", lambda *args: (_ for _ in ()).throw(VerificationError("Verification failed")))
    outcome, = manager.run_shutdown_sync(ignore_threshold_for="app")
    assert outcome.succeeded == (failure == "dry_run")
    if failure != "verification":
        assert (cloud / "save.txt").read_text() == "old"


def test_force_requires_folder_and_respects_pause_disabled_and_external_lock(qapp, pair, monkeypatch):
    service, _, cloud, _ = pair
    sync = SyncService(service)
    assert not sync.request_sync("shutdown", ignore_threshold=True)
    sync.set_paused(True)
    assert not sync.request_sync("shutdown", folder_id="app", ignore_threshold=True)
    sync.set_paused(False)
    monkeypatch.setattr("ui.workers.sync_worker.acquire_single_instance_lock", lambda path: None)
    assert sync.request_sync("shutdown", folder_id="app", ignore_threshold=True)
    wait(qapp, sync)
    assert (cloud / "save.txt").read_text() == "old"
    config = service.get_app_config()
    service.save(replace(config, folders=[replace(config.folders[0], enabled=False)]))
    assert not sync.request_sync("shutdown", folder_id="app", ignore_threshold=True)


def test_folder_button_requires_confirmation_and_disables_when_busy(qapp, pair, monkeypatch):
    service, _, cloud, _ = pair
    sync = SyncService(service)
    page = FoldersPage(service, sync_service=sync)
    card = page.findChildren(FolderCard)[0]
    confirmations = []
    def answer(*args):
        confirmations.append(args)
        return QMessageBox.StandardButton.No
    monkeypatch.setattr(QMessageBox, "question", answer)
    card.force_sync_button.click()
    assert not sync.is_syncing and (cloud / "save.txt").read_text() == "old"
    assert "From:" in confirmations[0][2] and "80%" in confirmations[0][2]
    assert confirmations[0][-1] == QMessageBox.StandardButton.No
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    card.force_sync_button.click()
    assert sync.is_syncing and not card.force_sync_button.isEnabled()
    assert not sync.request_sync("shutdown", folder_id="app", ignore_threshold=True)
    wait(qapp, sync)
    assert (cloud / "save.txt").read_text() == "new"
