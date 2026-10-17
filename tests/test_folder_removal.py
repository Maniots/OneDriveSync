"""Removing a sync pair must preserve files and the remaining configuration."""
import json
from dataclasses import replace

import pytest
from PySide6.QtWidgets import QMessageBox

from backend.services.configuration_service import ConfigurationService
from backend.services.sync_service import SyncService
from src.config_manager import ConfigManager
from ui.pages.folders import FoldersPage


@pytest.fixture
def folders_page(qapp, tmp_path):
    local, cloud = tmp_path / "local" / "app", tmp_path / "cloud" / "app"
    local.mkdir(parents=True)
    cloud.mkdir(parents=True)
    (local / "save.txt").write_text("local data")
    (cloud / "save.txt").write_text("cloud data")
    backup = tmp_path / "existing-backup.zip"
    backup.write_bytes(b"backup data")
    folders = [{"id": name, "name": name.title(), "enabled": name == "app",
                "local_path": str(local.parent / name), "onedrive_path": str(cloud.parent / name)}
               for name in ("app", "other")]
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"general": {"dry_run": True}, "folders": folders}))
    service = ConfigurationService(path)
    sync = SyncService(service)
    page = FoldersPage(service, sync_service=sync)
    return page, service, sync, path, local, cloud, backup


@pytest.mark.parametrize("confirmed", [False, True])
def test_delete_requires_confirmation_and_preserves_files(folders_page, monkeypatch, confirmed):
    page, service, _, path, local, cloud, backup = folders_page
    original = path.read_bytes()
    questions = []
    def answer(*args):
        questions.append(args)
        return QMessageBox.StandardButton.Yes if confirmed else QMessageBox.StandardButton.No
    monkeypatch.setattr(QMessageBox, "question", answer)
    card = page.folders_layout.itemAt(0).widget()
    card.delete_button.click()
    assert "App" in questions[0][2]
    assert "files" in questions[0][2].lower()
    assert questions[0][-1] == QMessageBox.StandardButton.No
    assert (local / "save.txt").read_text() == "local data"
    assert (cloud / "save.txt").read_text() == "cloud data"
    assert backup.read_bytes() == b"backup data"
    if confirmed:
        assert [folder.id for folder in ConfigManager(path).load().folders] == ["other"]
        assert [folder.id for folder in service.get_app_config().folders] == ["other"]
        assert page.folders_layout.count() == 1
    else:
        assert path.read_bytes() == original


def test_delete_failed_save_keeps_card_and_allows_retry(folders_page, monkeypatch):
    page, service, _, path, *_ = folders_page
    original = path.read_bytes()
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))
    with monkeypatch.context() as failure:
        def cannot_save(config):
            raise PermissionError("Configuration is read-only")
        failure.setattr(service, "save", cannot_save)
        page.folders_layout.itemAt(0).widget().delete_button.click()
    assert warnings and "read-only" in warnings[0][2]
    assert path.read_bytes() == original
    assert page.folders_layout.count() == 2
    page.folders_layout.itemAt(0).widget().delete_button.click()
    assert [folder.id for folder in ConfigManager(path).load().folders] == ["other"]


def test_delete_busy_guard_and_recheck_after_confirmation(folders_page, monkeypatch):
    page, service, sync, path, *_ = folders_page
    original = path.read_bytes()
    questions = []
    monkeypatch.setattr(QMessageBox, "question", lambda *args: questions.append(args))
    with monkeypatch.context() as busy:
        busy.setattr(SyncService, "is_syncing", property(lambda self: True))
        sync.state_changed.emit()
        assert not page.folders_layout.itemAt(0).widget().delete_button.isEnabled()
        page.on_folder_delete_requested("app")
        assert not questions
    def start_sync(*args):
        monkeypatch.setattr(SyncService, "is_syncing", property(lambda self: True))
        return QMessageBox.StandardButton.Yes
    monkeypatch.setattr(QMessageBox, "question", start_sync)
    page.on_folder_delete_requested("app")
    assert path.read_bytes() == original


def test_delete_last_disabled_folder_while_paused_shows_empty_state(folders_page, monkeypatch):
    page, service, sync, path, *_ = folders_page
    config = service.get_app_config()
    service.save(replace(config, folders=[config.folders[1]]))
    sync.set_paused(True)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    page.folders_layout.itemAt(0).widget().delete_button.click()
    assert ConfigManager(path).load().folders == []
    assert service.get_app_config().folders == []
    assert page.folders == []
