"""Managed destinations and backups use the visible synchronization name."""
from dataclasses import replace
from pathlib import Path

import pytest

from src.backup_manager import BackupManager
from src.cloud_models import ConnectionConfig
from src.cloud_sync import CloudSyncRunner
from src.config import SyncDirection
from tests.test_cloud_sync import FilesTransport, setup
from tests.test_synchronizations_ui import configuration
from ui.widgets.synchronization_editor import LOCAL_STORAGE, SynchronizationEditor


def test_new_destinations_use_one_managed_tree(qapp, tmp_path, monkeypatch):
    config, local, target = configuration(tmp_path)
    monkeypatch.setenv("OneDrive", str(target))
    connection = ConnectionConfig("drive", "Drive", "drive", "EverySync")
    config.save(replace(config.get_app_config(), connections=[connection]))
    editor = SynchronizationEditor(config)
    editor.name_edit.setText("Game saves")
    editor.local_edit.setText(str(local))
    editor.add_destination(LOCAL_STORAGE, str(target), backup=True, backup_path="", retention=7)
    editor.add_destination("drive", "arbitrary/subfolder")
    editor.update_summary()
    assert "EverySync" in editor.summary_label.text()
    assert editor.save_activity(), editor.error_label.text()
    config.reload()
    saved = config.get_app_config()
    folder = saved.folders[-1]
    assert Path(folder.onedrive_path) == target / "EverySync" / "Game saves"
    assert saved.remote_jobs[0].remote_path == "Game saves"
    destination = Path(folder.onedrive_path)
    destination.mkdir(parents=True)
    (destination / "save.dat").write_text("old save")
    archive = BackupManager(dry_run=False).create_backup(folder.id, folder.backup, destination)
    assert archive.parent == target / "EverySync Backups" / "Game saves"
    from backend.services.backup_service import BackupService
    backups = BackupService(config)
    assert backups.get_archive_path(folder.id, archive) == archive
    assert backups.get_backup_info(folder.id)[0]["path"] == str(archive)


@pytest.mark.parametrize("name", ["../escape", "Game/Saves", "CON", "Bad:name"])
def test_new_sync_rejects_names_that_are_not_safe_folder_names(qapp, tmp_path, name):
    config, local, target = configuration(tmp_path)
    editor = SynchronizationEditor(config)
    editor.name_edit.setText(name)
    editor.local_edit.setText(str(local))
    editor.add_destination(LOCAL_STORAGE, str(target))
    before = config.get_app_config()
    assert not editor.save_activity()
    assert config.get_app_config() == before


def test_connections_append_managed_root_once(qapp, tmp_path, monkeypatch):
    from unittest.mock import Mock
    from backend.services.cloud_service import CloudService
    from ui.pages.connections import ConnectionsPage
    config, _, target = configuration(tmp_path)
    service = CloudService(config)
    service.configure_connection = Mock()
    page = ConnectionsPage(config, service)
    page.provider_combo.setCurrentIndex(page.provider_combo.findData("local"))
    page.name_edit.setText("NAS")
    page.root_edit.setText(str(target))
    page.connect_account()
    assert Path(service.configure_connection.call_args.args[0].root) == target / "EverySync"
    service.choose_connection_root = Mock()
    for selected in ("Games", "Games/EverySync"):
        page.cloud_root_edit.setText(selected)
        page.save_cloud_root()
        assert service.choose_connection_root.call_args.args[0] == "Games/EverySync"


def test_cloud_named_snapshot_is_a_sibling_and_survives_rename(setup):
    config, local, remote, state = setup
    connection = replace(config.connections[0], root=str(remote.parent / "EverySync"))
    job = replace(config.remote_jobs[0], name="Game saves", remote_path="Game saves")
    config = replace(config, connections=[connection], remote_jobs=[job])
    remote = Path(connection.root) / job.remote_path
    remote.mkdir(parents=True)
    (remote / "save.dat").write_text("old save")
    (local / "save.dat").write_text("new save")
    import os
    os.utime(remote / "save.dat", (100, 100))
    engine = CloudSyncRunner(config, state, transport_factory=lambda root: FilesTransport())
    assert engine.run(SyncDirection.UPLOAD)[0].succeeded
    snapshot = engine.list_snapshots(job.id)[0]
    expected = remote.parent.parent / "EverySync Backups" / "Game saves" / snapshot["run_id"]
    assert (expected / "save.dat").read_text() == "old save"
    renamed = replace(config, remote_jobs=[replace(job, name="Renamed saves")])
    engine = CloudSyncRunner(renamed, state, transport_factory=lambda root: FilesTransport())
    restored = local.parent / "restored"
    engine.restore(job.id, snapshot["run_id"], restored)
    assert (restored / "save.dat").read_text() == "old save"


def test_local_connection_creates_only_managed_child(qapp, tmp_path):
    from backend.services.cloud_service import CloudService
    from tests.test_cloud_ui import spin
    from src.rclone_transport import CloudNotFound
    config, _, target = configuration(tmp_path)
    class Client:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def configure(self, *args, **kwargs): return {}
        def test(self, connection):
            if not Path(connection.root).is_dir():
                raise CloudNotFound("Missing")
    service = CloudService(config, transport_factory=lambda *a, **k: Client(), parent=qapp)
    errors = []
    service.failed.connect(errors.append)
    connection = ConnectionConfig("nas", "NAS", "local", str(target / "EverySync"))
    service.configure_connection(connection, {}, create_root=True)
    spin(qapp, lambda: not service.busy)
    assert errors == []
    assert Path(connection.root).is_dir()
    assert config.get_app_config().connections == [connection]


def test_cloud_local_source_cannot_overlap_sibling_backups(setup):
    config, local, remote, state = setup
    connection = replace(config.connections[0], root=str(remote.parent / "EverySync"))
    Path(connection.root).mkdir()
    source = remote.parent / "EverySync Backups" / "Saves"
    source.mkdir(parents=True)
    job = replace(config.remote_jobs[0], local_path=str(source))
    config = replace(config, connections=[connection], remote_jobs=[job])
    engine = CloudSyncRunner(config, state, transport_factory=lambda root: FilesTransport())
    assert not engine.run(SyncDirection.UPLOAD)[0].succeeded


def test_legacy_cloud_snapshot_without_folder_marker_remains_restorable(setup):
    import json
    import shutil
    config, local, remote, state = setup
    remote.mkdir()
    (remote / "save").write_text("previous")
    (local / "addition").write_text("new")
    engine = CloudSyncRunner(config, state, transport_factory=lambda root: FilesTransport())
    assert engine.run(SyncDirection.UPLOAD)[0].succeeded
    data = json.loads((state / "state.json").read_text())
    snapshot = data["jobs"]["saves"]["snapshots"][0]
    named = remote.parent / "EverySync Backups" / snapshot.pop("folder_name") / snapshot["run_id"]
    legacy = remote.parent / ".everysync" / "backups" / "saves" / snapshot["run_id"]
    legacy.parent.mkdir(parents=True)
    shutil.move(str(named), str(legacy))
    (state / "state.json").write_text(json.dumps(data))
    restored = local.parent / "legacy-restored"
    engine.restore("saves", snapshot["run_id"], restored)
    assert (restored / "save").read_text() == "previous"


@pytest.mark.parametrize("name", ["Game / profile", "CON"])
def test_legacy_display_names_keep_usable_backups(setup, name):
    config, local, remote, state = setup
    job = replace(config.remote_jobs[0], name=name)
    config = replace(config, remote_jobs=[job])
    remote.mkdir()
    (remote / "old").write_text("keep")
    (local / "new").write_text("addition")
    engine = CloudSyncRunner(config, state, transport_factory=lambda root: FilesTransport())
    assert engine.run(SyncDirection.UPLOAD)[0].succeeded
    snapshot = engine.list_snapshots(job.id)[0]
    assert "folder_name" not in snapshot
    restored = local.parent / "restored"
    engine.restore(job.id, snapshot["run_id"], restored)
    assert (restored / "old").read_text() == "keep"


def test_disconnected_draft_has_recoverable_error(qapp, tmp_path):
    config, local, _ = configuration(tmp_path)
    connection = ConnectionConfig("drive", "Drive", "drive", "EverySync")
    config.save(replace(config.get_app_config(), connections=[connection]))
    editor = SynchronizationEditor(config)
    editor.name_edit.setText("Game saves")
    editor.local_edit.setText(str(local))
    editor.add_destination("drive", "Game saves")
    config.save(replace(config.get_app_config(), connections=[]))
    editor.name_edit.setText("New name")
    assert not editor.save_activity()
    assert "disconnected" in editor.error_label.text()


def test_local_selection_does_not_duplicate_managed_folders(tmp_path):
    from src.storage_layout import local_sync_paths
    root = tmp_path / "storage"
    for selected in (root, root / "EverySync", root / "EverySync" / "Saves"):
        destination, backups = local_sync_paths(str(selected), "Saves")
        assert destination == root / "EverySync" / "Saves"
        assert backups == root / "EverySync Backups"


def test_group_source_cannot_be_inside_named_backup_tree(setup):
    from src.sync_groups import SyncGroupConfig, SyncDestinationConfig, validate_groups
    from src.exceptions import ConfigurationError
    config, _, remote, _ = setup
    connection = replace(config.connections[0], root=str(remote.parent / "EverySync"))
    source = remote.parent / "EverySync Backups" / "Saves"
    job = replace(config.remote_jobs[0], local_path=str(source))
    group = SyncGroupConfig("group", "Saves", str(source), [SyncDestinationConfig(job.id)])
    config = replace(config, connections=[connection], remote_jobs=[job], sync_groups=[group])
    with pytest.raises(ConfigurationError, match="overlap"):
        validate_groups(config)


@pytest.mark.parametrize("provider,parent", [("sftp", "storage"), ("s3", "bucket-name"),
                                           ("b2", "bucket-name"), ("azureblob", "container")])
def test_other_providers_create_only_managed_child(provider, parent):
    from backend.services.cloud_service import CloudService
    from src.rclone_transport import CloudNotFound
    calls = []
    class Client:
        created = False
        def test(self, connection):
            calls.append(("test", connection.root))
            if connection.root.endswith("/EverySync") and not self.created:
                raise CloudNotFound("Missing managed folder")
        def operation(self, method, payload):
            calls.append((method, payload))
            self.created = True
    connection = ConnectionConfig("remote", "Remote", provider, f"{parent}/EverySync")
    CloudService._verify_root(Client(), connection, True)
    assert calls == [("test", f"{parent}/EverySync"), ("test", parent),
                     ("operations/mkdir", {"fs": "es_remote:", "remote": f"{parent}/EverySync"}),
                     ("test", f"{parent}/EverySync")]


def test_bad_backup_root_stops_upload_instead_of_changing_layout(setup):
    config, local, remote, state = setup
    connection = replace(config.connections[0], root=str(remote.parent / "EverySync"))
    remote = Path(connection.root) / "game"
    remote.mkdir(parents=True)
    (remote.parent.parent / "EverySync Backups").write_text("not a folder")
    (remote / "save").write_text("previous")
    (local / "new").write_text("new")
    config = replace(config, connections=[connection])
    engine = CloudSyncRunner(config, state, transport_factory=lambda root: FilesTransport())
    assert not engine.run(SyncDirection.UPLOAD)[0].succeeded
    assert not (Path(connection.root) / ".everysync").exists()


def test_sftp_can_create_managed_folder_at_account_root():
    from backend.services.cloud_service import CloudService
    from src.rclone_transport import CloudNotFound
    class Client:
        created = False
        def test(self, connection):
            if not self.created:
                raise CloudNotFound("Missing")
        def operation(self, method, payload):
            assert method == "operations/mkdir"
            assert payload == {"fs": "es_remote:", "remote": "EverySync"}
            self.created = True
    client = Client()
    CloudService._verify_root(client, ConnectionConfig("remote", "Remote", "sftp", "EverySync"), True)
    assert client.created


def test_native_engine_creates_and_restores_named_sibling_snapshot(setup):
    import os
    config, local, remote, state = setup
    connection = replace(config.connections[0], root=str(remote.parent / "EverySync"))
    job = replace(config.remote_jobs[0], name="Game saves", remote_path="Game saves")
    config = replace(config, connections=[connection], remote_jobs=[job])
    remote = Path(connection.root) / job.remote_path
    remote.mkdir(parents=True)
    (remote / "save.dat").write_text("original")
    (local / "save.dat").write_text("replacement")
    os.utime(remote / "save.dat", (100, 100))
    engine = CloudSyncRunner(config, state)
    outcomes = engine.run(SyncDirection.UPLOAD)
    assert all(item.succeeded for item in outcomes), [item.message for item in outcomes]
    snapshot = engine.list_snapshots(job.id)[0]
    archive = remote.parent.parent / "EverySync Backups" / job.name / snapshot["run_id"]
    assert (archive / "save.dat").read_text() == "original"
    restored = local.parent / "restored"
    engine.restore(job.id, snapshot["run_id"], restored)
    assert (restored / "save.dat").read_text() == "original"
