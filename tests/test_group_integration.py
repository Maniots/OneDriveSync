"""Manual/background routing and native rclone local-provider integration."""
from dataclasses import replace
from pathlib import Path
import time

import pytest

from backend.services.configuration_service import ConfigurationService
from src.cloud_models import ConnectionConfig, RemoteJobConfig
from src.config import FolderSyncConfig, SyncDirection
from src.config_manager import ConfigManager
from src.sync_groups import SyncDestinationConfig, SyncGroupConfig
from src.group_sync import GroupSyncRunner


@pytest.fixture
def configuration(tmp_path):
    config = ConfigManager(Path(__file__).resolve().parents[1] / "packaging/default-config.json").load()
    local, first, second = [tmp_path / name for name in ("source", "first", "second")]
    for path in (local, first, second): path.mkdir()
    leaves = [FolderSyncConfig(f"leaf{n}", f"Destination {n}", True, str(local), str(target / "game"), 0, True, True)
              for n, target in enumerate((first, second))]
    group = SyncGroupConfig("group", "Game", str(local), [SyncDestinationConfig(leaf.id) for leaf in leaves])
    config = replace(config, folders=leaves, connections=[], remote_jobs=[], sync_groups=[group],
                     general=replace(config.general, dry_run=False))
    path = tmp_path / "settings.json"
    ConfigManager(path).save(config)
    return ConfigurationService(path), local, first, second


def wait(qapp, sync):
    deadline = time.monotonic() + 10
    while sync.is_syncing and time.monotonic() < deadline:
        qapp.processEvents(); time.sleep(.001)
    assert not sync.is_syncing


def test_manual_group_direction_works_with_disabled_opposite_scheduled_trigger_and_no_persistence(qapp, configuration, sync_service_factory):
    service, local, first, second = configuration
    config = service.get_app_config()
    config = replace(config, sync=replace(config.sync, shutdown=replace(config.sync.shutdown, enabled=False, direction=SyncDirection.DOWNLOAD)))
    service.save(config)
    before = service._config_manager.config_path.read_bytes()
    (local / "save").write_text("manual upload")
    sync = sync_service_factory(service)
    assert sync.request_direction_sync("upload", "group")
    assert sync.active_direction == SyncDirection.UPLOAD
    wait(qapp, sync)
    assert sync.active_direction is None
    assert (first / "game/save").read_text() == (second / "game/save").read_text() == "manual upload"
    assert service._config_manager.config_path.read_bytes() == before
    assert not sync.request_sync("shutdown", "group")


def test_old_api_rejects_grouped_leaf_and_cannot_trigger_siblings(qapp, configuration, sync_service_factory):
    service, local, first, second = configuration
    (local / "save").write_text("source")
    sync = sync_service_factory(service)
    failures = []; sync.failed.connect(failures.append)
    assert not sync.request_direction_sync("upload", None)
    assert not sync.request_sync("shutdown", "leaf0")
    assert not sync.request_direction_sync("upload", "leaf0")
    assert not (first / "game").exists() and not (second / "game").exists()
    assert "parent activity" in failures[-1]


def test_manual_group_respects_disabled_leaf_and_busy_pause_external_lock(qapp, configuration, sync_service_factory, monkeypatch):
    service, local, first, second = configuration
    config = service.get_app_config()
    service.save(replace(config, folders=[config.folders[0], replace(config.folders[1], enabled=False)]))
    (local / "save").write_text("source")
    sync = sync_service_factory(service)
    sync.set_paused(True)
    assert not sync.request_direction_sync("upload", "group")
    sync.set_paused(False)
    monkeypatch.setattr("ui.workers.sync_worker.acquire_single_instance_lock", lambda path: None)
    assert sync.request_direction_sync("upload", "group")
    assert not sync.request_direction_sync("upload", "group")
    wait(qapp, sync)
    assert not (first / "game").exists() and not (second / "game").exists()


def test_implicit_manual_singleton_does_not_create_group(qapp, configuration, sync_service_factory):
    service, local, first, second = configuration
    service.save(replace(service.get_app_config(), sync_groups=[]))
    (local / "save").write_text("singleton")
    before = service._config_manager.config_path.read_bytes()
    sync = sync_service_factory(service)
    assert sync.request_direction_sync("upload", "leaf0")
    wait(qapp, sync)
    assert (first / "game/save").read_text() == "singleton"
    assert not (second / "game").exists()
    assert service._config_manager.config_path.read_bytes() == before


def test_native_rclone_local_provider_group_upload_and_verified_download(configuration, tmp_path):
    from src.rclone_transport import rclone_executable
    rclone_executable()  # An explicit preparation failure is not a test skip.
    service, local, first, second = configuration
    config = service.get_app_config()
    job = RemoteJobConfig("native", "Native provider", str(local), "provider", "game", minimum_sync_percentage=0)
    group = replace(config.sync_groups[0], destinations=[SyncDestinationConfig("leaf0"), SyncDestinationConfig("native")])
    config = replace(config, folders=config.folders[:1], remote_jobs=[job],
                     connections=[ConnectionConfig("provider", "Filesystem", "local", str(second))], sync_groups=[group])
    (local / "save").write_text("native generation")
    coordinator = GroupSyncRunner(config, tmp_path / "native-state")
    outcomes = coordinator.run(group, "upload")
    assert all(item.succeeded for item in outcomes), [item.message for item in outcomes]
    assert (first / "game/save").read_text() == (second / "game/save").read_text() == "native generation"
    (local / "save").unlink()
    # Native remote is now the first source, with its same verified identity.
    group = replace(group, destinations=list(reversed(group.destinations)))
    outcomes = coordinator.run(group, "download")
    assert all(item.succeeded for item in outcomes), [item.message for item in outcomes]
    assert (local / "save").read_text() == "native generation"
