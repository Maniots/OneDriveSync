"""Cloud jobs share the established execution, selection, and shutdown owners."""
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

from backend.services.configuration_service import ConfigurationService
from backend.services.sync_service import SyncService
from src.cloud_models import ConnectionConfig, RemoteJobConfig
from src.config_manager import ConfigManager
from src.config import SyncDirection
from src.sync_manager import SyncManager, FolderSyncOutcome


def configure(tmp_path):
    path = tmp_path / "custom.json"
    path.write_bytes((Path(__file__).resolve().parents[1] / "packaging/default-config.json").read_bytes())
    service = ConfigurationService(path)
    config = service.get_app_config()
    connection = ConnectionConfig("fixture", "Fixture", "local", str(tmp_path / "remote"))
    job = RemoteJobConfig("saves", "Saves", str(tmp_path / "local"), "fixture", "game")
    service.save(replace(config, connections=[connection], remote_jobs=[job]))
    return service, path


def test_manager_runs_cloud_after_legacy_and_records_shared_history(tmp_path, monkeypatch):
    from src.sync_history import SyncHistory
    service, path = configure(tmp_path)
    config = replace(service.get_app_config(), folders=[])
    expected = FolderSyncOutcome("saves", "Saves", SyncDirection.UPLOAD, True, "Queued")
    runner = Mock()
    runner.run.return_value = [expected]
    factory = Mock(return_value=runner)
    monkeypatch.setattr("src.cloud_sync.CloudSyncRunner", factory)
    history = path.with_suffix(".history.sqlite3")
    manager = SyncManager(config, history_path=history, cloud_root=path.with_suffix(".cloud"), defer_remote=True)
    assert manager.run_shutdown_sync() == [expected]
    factory.assert_called_once_with(config, path.with_suffix(".cloud"))
    runner.run.assert_called_once_with(SyncDirection.UPLOAD, ignore_threshold_for=None, defer=True)
    assert SyncHistory(history).recent()[0]["outcomes"][0]["folder_id"] == "saves"


def test_ui_selection_targets_exactly_one_cloud_job(qapp, tmp_path):
    service, path = configure(tmp_path)
    sync = SyncService(service)
    selected = sync._prepare_sync("shutdown", "saves")
    assert selected is not None
    assert selected.folders == []
    assert [job.id for job in selected.remote_jobs] == ["saves"]
    assert selected.connections == service.get_app_config().connections
    assert sync.cloud_root == service.cloud_root == path.with_suffix(".cloud")
    sync._is_syncing = False


def test_cli_passes_chosen_config_state_and_shutdown_policy(tmp_path, monkeypatch):
    from src import sync_runner
    _, path = configure(tmp_path)
    factory = Mock()
    factory.return_value.run_shutdown_sync.return_value = []
    monkeypatch.setattr(sync_runner, "SyncManager", factory)
    monkeypatch.setattr(sync_runner, "setup_logger", Mock())
    assert sync_runner.run_sync("shutdown", path, defer_remote=True) == 0
    assert factory.call_args.kwargs["cloud_root"] == path.with_suffix(".cloud")
    assert factory.call_args.kwargs["defer_remote"] is True


def test_session_shutdown_queues_remote_work_without_network(monkeypatch):
    from src import shutdown_monitor
    lock = Mock()
    run = Mock(return_value=0)
    monkeypatch.setattr(shutdown_monitor, "acquire_single_instance_lock", lambda path: lock)
    monkeypatch.setattr(shutdown_monitor, "run_sync", run)
    assert shutdown_monitor._run_shutdown_sync() == 0
    assert run.call_args.kwargs["defer_remote"] is True
    lock.close.assert_called_once()


def test_cloud_local_changes_enter_existing_debounced_monitor(qapp, tmp_path):
    import time
    service, path = configure(tmp_path)
    config = service.get_app_config()
    local = config.remote_jobs[0].local_path_resolved
    local.mkdir()
    service.save(replace(config, copy_engine=replace(config.copy_engine, monitor_mode=True)))
    sync = SyncService(service)
    sync.set_paused(True)
    (local / "changed").write_text("new save")
    deadline = time.monotonic() + 2
    while not sync._monitor_dirty and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(.01)
    assert sync._monitor_dirty
    assert not sync.is_syncing
    sync._monitor_timer.stop()
    sync._poll_timer.stop()
