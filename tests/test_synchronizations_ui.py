"""User journeys for one list and ordered destinations, using synthetic folders."""
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

from PySide6.QtCore import Qt

from backend.services.cloud_service import CloudService
from backend.services.configuration_service import ConfigurationService
from src.cloud_models import ConnectionConfig, RemoteJobConfig
from src.config import FolderSyncConfig
from src.sync_groups import SyncDestinationConfig, SyncGroupConfig
from ui.pages.synchronizations import SynchronizationsPage
from ui.widgets.synchronization_editor import LOCAL_STORAGE, SynchronizationEditor


def configuration(tmp_path):
    path = tmp_path / "config.json"
    path.write_bytes((Path(__file__).resolve().parents[1] / "packaging/default-config.json").read_bytes())
    service = ConfigurationService(path)
    local, target = tmp_path / "saves", tmp_path / "target"
    local.mkdir()
    target.mkdir()
    legacy = FolderSyncConfig("existing-folder", "Existing saves", True, str(local),
                              str(target), 80, True, True)
    service.save(replace(service.get_app_config(), folders=[legacy]))
    return service, local, target


def test_one_list_shows_legacy_and_groups_without_duplicate_destinations(qapp, tmp_path):
    config, local, _ = configuration(tmp_path)
    remote = ConnectionConfig("drive", "Google Drive", "drive", "EverySync")
    job = RemoteJobConfig("remote", "Online saves", str(local), "drive", "Saves")
    group = SyncGroupConfig("group", "Game saves", str(local), [SyncDestinationConfig("remote")])
    config.save(replace(config.get_app_config(), connections=[remote], remote_jobs=[job], sync_groups=[group]))
    page = SynchronizationsPage(config, CloudService(config))
    assert page.activity_list.topLevelItemCount() == 2
    assert {page.activity_list.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole)
            for i in range(2)} == {"existing-folder", "group"}
    page.search_edit.setText("Google")
    assert sum(not page.activity_list.topLevelItem(i).isHidden() for i in range(2)) == 1


def test_editor_creates_mixed_destinations_and_persists_priority(qapp, tmp_path):
    config, local, target = configuration(tmp_path)
    connection = ConnectionConfig("drive", "Google Drive", "drive", "EverySync")
    config.save(replace(config.get_app_config(), connections=[connection]))
    editor = SynchronizationEditor(config)
    editor.name_edit.setText("Mixed saves")
    editor.local_edit.setText(str(local))
    editor.add_destination(LOCAL_STORAGE, str(target.parent / "new-target"))
    editor.add_destination("drive", "Game/Saves")
    editor.destination_table.selectRow(1)
    editor.move_destination(-1)
    assert editor.save_activity()
    config.reload()
    saved = config.get_app_config()
    assert len(saved.sync_groups) == 1
    group = saved.sync_groups[0]
    assert group.name == "Mixed saves"
    leaves = {job.id: job for job in saved.remote_jobs}
    assert leaves[group.destinations[0].job_id].connection_id == "drive"
    assert group.destinations[1].job_id in {folder.id for folder in saved.folders}
    assert saved.folders[0].id == "existing-folder"


def test_editing_singleton_keeps_leaf_id_and_safety_settings(qapp, tmp_path):
    config, local, _ = configuration(tmp_path)
    original = config.get_app_config().folders[0]
    editor = SynchronizationEditor(config, "existing-folder")
    editor.name_edit.setText("Renamed saves")
    assert editor.save_activity()
    updated = config.get_app_config()
    assert updated.folders[0].id == original.id
    assert updated.folders[0].minimum_sync_percentage == original.minimum_sync_percentage
    assert updated.folders[0].verify_after_sync == original.verify_after_sync
    assert updated.sync_groups == []


def test_cancel_editor_leaves_configuration_untouched(qapp, tmp_path):
    config, _, _ = configuration(tmp_path)
    before = config.get_app_config()
    editor = SynchronizationEditor(config, "existing-folder")
    editor.name_edit.setText("Do not save")
    editor.reject()
    assert config.get_app_config() == before


def test_destination_reopen_preserves_unsaved_advanced_choices(qapp, tmp_path):
    from ui.widgets.synchronization_editor import DestinationDialog
    config, _, target = configuration(tmp_path)
    draft = dict(storage=LOCAL_STORAGE, path=str(target), threshold=47, verify=False,
                 backup=True, backup_path="C:/OneDrive/Backups", retention=23,
                 upload=True, download=False, enabled=False)
    dialog = DestinationDialog(config.get_app_config(), draft)
    assert dialog.values() == draft


def test_directional_actions_target_selected_item(qapp, tmp_path, sync_service_factory):
    config, _, _ = configuration(tmp_path)
    sync = sync_service_factory(config)
    sync.request_direction_sync = Mock(return_value=True)
    page = SynchronizationsPage(config, CloudService(config, sync_service=sync))
    page.activity_list.setCurrentItem(page.activity_list.topLevelItem(0))
    page.upload_button.click()
    sync.request_direction_sync.assert_called_with("upload", "existing-folder")
    page.download_button.click()
    sync.request_direction_sync.assert_called_with("download", "existing-folder")
    sync.set_paused(True)
    assert not page.upload_button.isEnabled()
    assert not page.download_button.isEnabled()


def test_removing_group_disables_detached_leaves_and_preserves_files(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    config, local, target = configuration(tmp_path)
    (local / "save.dat").write_text("keep")
    group = SyncGroupConfig("group", "Game saves", str(local), [SyncDestinationConfig("existing-folder")])
    config.save(replace(config.get_app_config(), sync_groups=[group]))
    page = SynchronizationsPage(config, CloudService(config))
    page.activity_list.setCurrentItem(page.activity_list.topLevelItem(0))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    page.remove_selected()
    assert config.get_app_config().sync_groups == []
    assert not config.get_app_config().folders[0].enabled
    assert (local / "save.dat").read_text() == "keep"


def test_existing_bidirectional_activity_remains_implicit_when_edited(qapp, tmp_path):
    config, local, _ = configuration(tmp_path)
    connection = ConnectionConfig("drive", "Google Drive", "drive", "EverySync")
    job = RemoteJobConfig("two_way", "Two-way saves", str(local), "drive", "Saves", bidirectional=True)
    config.save(replace(config.get_app_config(), connections=[connection], remote_jobs=[job]))
    editor = SynchronizationEditor(config, "two_way")
    editor.name_edit.setText("Renamed two-way saves")
    assert editor.save_activity()
    assert config.get_app_config().sync_groups == []
    assert config.get_app_config().remote_jobs[0].bidirectional
    page = SynchronizationsPage(config, CloudService(config))
    for index in range(page.activity_list.topLevelItemCount()):
        item = page.activity_list.topLevelItem(index)
        if item.data(0, Qt.ItemDataRole.UserRole) == "two_way":
            page.activity_list.setCurrentItem(item)
    assert page.upload_button.text() == "Synchronize both folders"
    assert page.download_button.isHidden()


def test_connection_named_folder_is_not_reinterpreted_as_a_filesystem_destination(qapp, tmp_path):
    config, local, _ = configuration(tmp_path)
    connection = ConnectionConfig("folder", "Cloud account", "drive", "EverySync")
    job = RemoteJobConfig("online", "Online saves", str(local), "folder", "Game/Saves")
    config.save(replace(config.get_app_config(), connections=[connection], remote_jobs=[job]))
    editor = SynchronizationEditor(config, "online")
    editor.name_edit.setText("Renamed online saves")
    assert editor.save_activity()
    saved = config.get_app_config()
    assert len(saved.folders) == 1
    assert saved.remote_jobs == [replace(job, name="Renamed online saves")]
    assert saved.sync_groups == []


def test_removed_single_destination_no_longer_prevents_disconnect(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    config, local, _ = configuration(tmp_path)
    connection = ConnectionConfig("drive", "Google Drive", "drive", "EverySync")
    job = RemoteJobConfig("remote", "Online saves", str(local), "drive", "Saves", enabled=False)
    config.save(replace(config.get_app_config(), connections=[connection], remote_jobs=[job]))
    page = SynchronizationsPage(config, CloudService(config))
    for index in range(page.activity_list.topLevelItemCount()):
        item = page.activity_list.topLevelItem(index)
        if item.data(0, Qt.ItemDataRole.UserRole) == "remote":
            page.activity_list.setCurrentItem(item)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    page.remove_selected()
    assert config.get_app_config().remote_jobs == []
    assert config.get_app_config().connections == [connection]


def test_group_copy_status_reports_incomplete_and_prior_evidence(qapp, tmp_path):
    from src.group_state import GroupState
    from src.sync_groups import destination_identity
    config, local, _ = configuration(tmp_path)
    group = SyncGroupConfig("group", "Game saves", str(local), [SyncDestinationConfig("existing-folder")])
    config.save(replace(config.get_app_config(), sync_groups=[group]))
    state = GroupState(config.cloud_root)
    record = state.bind(group, {"existing-folder": destination_identity(config.get_app_config(), config.get_app_config().folders[0])})
    record["generation"] = "v_new"
    from src.config import SyncDirection
    identities = {"existing-folder": destination_identity(config.get_app_config(), config.get_app_config().folders[0])}
    record["pending"] = GroupState.pending(SyncDirection.UPLOAD, identities)
    record["destinations"]["existing-folder"] = dict(identity=destination_identity(config.get_app_config(), config.get_app_config().folders[0]),
                                                     generation="v_new", status="incomplete", inventory={})
    state.save()
    page = SynchronizationsPage(config, CloudService(config))
    assert "Incomplete" in page.destination_table.item(0, 3).text()
    record["pending"] = None
    record["destinations"]["existing-folder"].update(generation="v_old", status="complete")
    state.save()
    page.refresh()
    assert "Prior copy" in page.destination_table.item(0, 3).text()


def test_dashboard_counts_one_partial_activity_instead_of_its_destinations(qapp, tmp_path):
    from ui.main_window import MainWindow
    from src.sync_manager import FolderSyncOutcome
    from src.config import SyncDirection
    config, local, _ = configuration(tmp_path)
    group = SyncGroupConfig("group", "Game saves", str(local), [SyncDestinationConfig("existing-folder")])
    config.save(replace(config.get_app_config(), sync_groups=[group]))
    window = MainWindow(configuration_service=config)
    try:
        dashboard = window.content_stack.widget(0)
        dashboard.on_sync_completed([
            FolderSyncOutcome("existing-folder", "Destination", SyncDirection.UPLOAD, True, "Copied"),
            FolderSyncOutcome("group", "Game saves", SyncDirection.UPLOAD, False, "Incomplete upload"),
        ])
        assert dashboard.result_label.text() == "Succeeded: 0, Failed: 1"
        assert dashboard.last_failed_label.text() == "Game saves"
    finally:
        window.prepare_for_exit()
        window.tray_icon.hide()
        window.hide()
