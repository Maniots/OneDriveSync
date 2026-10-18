"""Integration coverage for effective settings, truthful state and persistence."""
import json
import logging
import os
import threading
import time
from dataclasses import replace
from datetime import datetime, timezone

import pytest
from backend.services.configuration_service import ConfigurationService
from backend.services.scheduler_service import SchedulerService
from backend.services.backup_service import BackupService
from backend.services.log_service import LogService
from src.config import CopyEngineSettings, GeneralSettings
from src.config import BackupSettings
from src.robocopy_manager import CopyEngine, CopyResult
from src.sync_manager import SyncManager
from src.sync_history import SyncHistory


@pytest.fixture
def configured(tmp_path):
    local, cloud = tmp_path / "local", tmp_path / "cloud"
    local.mkdir()
    cloud.mkdir()
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"general": {"verify_after_sync": False}, "folders": [
        {"id": "app", "name": "App", "local_path": str(local), "onedrive_path": str(cloud), "minimum_sync_percentage": 0}]}))
    return ConfigurationService(path), local, cloud


def test_directory_settings_control_real_copy_and_dry_run(configured):
    service, local, cloud = configured
    (local / "top.txt").write_text("top")
    (local / "nested").mkdir()
    (local / "nested" / "nested.txt").write_text("nested")
    (local / "empty").mkdir()
    settings = CopyEngineSettings(copy_subdirectories=False, copy_empty_directories=False)
    result = CopyEngine(settings, dry_run=True).run(local, cloud)
    assert "1 file(s) and 0 empty dir(s)" in result.stdout
    assert not list(cloud.iterdir())
    assert CopyEngine(settings).run(local, cloud).success
    assert (cloud / "top.txt").exists() and not (cloud / "nested").exists()
    recursive = replace(settings, copy_subdirectories=True)
    assert CopyEngine(recursive).run(local, cloud).success
    assert (cloud / "nested" / "nested.txt").exists() and not (cloud / "empty").exists()


def test_retries_recover_then_do_not_overwrite_newer_destination(configured, monkeypatch):
    import src.robocopy_manager as module
    _, local, cloud = configured
    source, target = local / "file", cloud / "file"
    source.write_text("new")
    real_copy = module._copy_single_file
    attempts, waits = [], []
    def copy(src, dst):
        attempts.append(src)
        return (False, "locked") if len(attempts) == 1 else real_copy(src, dst)
    monkeypatch.setattr(module, "_copy_single_file", copy)
    monkeypatch.setattr(module.time, "sleep", waits.append)
    engine = CopyEngine(CopyEngineSettings(retry_count=2, retry_wait_seconds=3))
    assert engine.run(local, cloud).success
    assert len(attempts) == 2 and waits == [3]
    target.write_text("newest")
    os.utime(target, (time.time() + 30, time.time() + 30))
    engine.run(local, cloud)
    assert target.read_text() == "newest" and len(attempts) == 2


def test_file_multithreading_executes_independent_copies_concurrently(configured, monkeypatch):
    import src.robocopy_manager as module
    _, local, cloud = configured
    for name in ("a", "b"):
        (local / name).write_text(name)
    barrier, threads = threading.Barrier(2), set()
    real_copy = module._copy_single_file
    def copy(src, dst):
        threads.add(threading.get_ident())
        barrier.wait(timeout=3)
        return real_copy(src, dst)
    monkeypatch.setattr(module, "_copy_single_file", copy)
    assert CopyEngine(CopyEngineSettings(multithreading=2, retry_count=0)).run(local, cloud).success
    assert len(threads) == 2 and len(list(cloud.iterdir())) == 2


def test_fat_precision_setting_changes_comparison_without_overwriting_newer(configured):
    _, local, cloud = configured
    a, b = local / "file", cloud / "file"
    a.write_text("same")
    b.write_text("same")
    os.utime(a, (100, 100))
    os.utime(b, (99, 99))
    assert not CopyEngine(CopyEngineSettings(fat_file_times=True)).compare_files(a, b)[0]
    assert CopyEngine(CopyEngineSettings(fat_file_times=False)).compare_files(a, b)[0]
    os.utime(b, (101, 101))
    assert not CopyEngine(CopyEngineSettings(fat_file_times=False)).compare_files(a, b)[0]


def test_copy_failure_propagates_to_folder_and_cli_result(configured, monkeypatch):
    service, local, cloud = configured
    failure = CopyResult(local, cloud, 8, False, "", "six files failed", False)
    monkeypatch.setattr(CopyEngine, "run", lambda *args, **kwargs: failure)
    outcomes = SyncManager(service.get_app_config(), service.history_path).run_shutdown_sync()
    assert not outcomes[0].succeeded and "six files failed" in outcomes[0].message
    from src.sync_runner import _exit_code_for_outcomes
    assert _exit_code_for_outcomes(outcomes) == 1
    assert not SyncHistory(service.history_path).recent()[0]["outcomes"][0]["succeeded"]


def test_parallel_folder_jobs_preserve_outcome_order_and_history(configured, tmp_path, monkeypatch):
    service, local, cloud = configured
    other_local, other_cloud = tmp_path / "other", tmp_path / "other-cloud"
    other_local.mkdir()
    other_cloud.mkdir()
    config = service.get_app_config()
    other = replace(config.folders[0], id="other", name="Other", local_path=other_local, onedrive_path=other_cloud)
    config = replace(config, general=replace(config.general, max_parallel_jobs=2), folders=[config.folders[0], other])
    barrier = threading.Barrier(2)
    def copy(self, source, destination, **kwargs):
        barrier.wait(timeout=3)
        return CopyResult(source, destination, 1, True, "", "", False)
    monkeypatch.setattr(CopyEngine, "run", copy)
    outcomes = SyncManager(config, service.history_path).run_shutdown_sync()
    assert all(o.succeeded for o in outcomes)
    assert [o.folder_id for o in outcomes] == ["app", "other"]
    assert set(SyncHistory(service.history_path).latest_folders()) == {"app", "other"}


@pytest.mark.parametrize("field,value", [("retry_count", -1), ("retry_wait_seconds", 61), ("multithreading", 0)])
def test_invalid_tuning_is_rejected(field, value):
    with pytest.raises(ValueError):
        CopyEngineSettings(**{field: value})


def test_logger_reconfigures_handlers_without_duplication(tmp_path):
    from src.logger import setup_logger
    logger = setup_logger(tmp_path / "logs", "INFO")
    handlers = list(logger.handlers)
    same = setup_logger(tmp_path / "logs", "DEBUG")
    assert same is logger and logger.level == logging.DEBUG
    assert logger.handlers == handlers and all(h.level == logging.DEBUG for h in handlers)
    setup_logger(tmp_path / "logs", "INFO")


def test_log_filters_include_every_supported_level(tmp_path):
    path = tmp_path / "logs"
    levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "SUCCESS"]
    path.write_text("\n".join(f"2026-10-12 12:00:00 | {level:<8} | test | message" for level in levels))
    service = LogService(path)
    entries = service.get_log_entries()
    assert [r[1] for r in service.filter_entries(entries, show_success=True)] == levels
    assert [r[1] for r in service.filter_entries(entries, show_debug=False, show_critical=False)] == ["INFO", "WARNING", "ERROR"]


def test_scheduler_reads_disabled_state_and_real_trigger_json(configured, monkeypatch):
    service, *_ = configured
    scheduler = SchedulerService(service)
    payload = {"exists": True, "enabled": False, "status": "Disabled", "last_run_time": None, "next_run_time": None,
               "triggers": [{"type": 9, "delay": "PT7M", "interval": "PT40M"}]}
    calls = []
    def query(command, **kwargs):
        calls.append(command)
        return json.dumps(payload)
    monkeypatch.setattr("backend.services.scheduler_service.subprocess.check_output", query)
    assert scheduler.get_startup_sync_info()["enabled"] == "Disabled"
    assert scheduler.get_startup_sync_info()["delay"] == "7 minutes"
    assert len(calls) == 1 and "-EncodedCommand" in calls[0]
    assert scheduler.get_periodic_sync_info()["interval"] == "40 minutes"
    config = service.get_app_config()
    service.save(replace(config, sync=replace(config.sync, shutdown=replace(config.sync.shutdown, direction=config.sync.startup.direction))))
    assert scheduler.get_periodic_sync_info()["direction"] == "Download"


def test_history_drives_folder_and_dashboard_state_across_services(qapp, configured, sync_service_factory, monkeypatch):
    from ui.pages.folders import FoldersPage
    from ui.widgets.folder_card import FolderCard
    from ui.pages.dashboard import DashboardPage
    service, local, cloud = configured
    (local / "file").write_text("saved")
    outcomes = SyncManager(service.get_app_config(), service.history_path).run_shutdown_sync()
    sync = sync_service_factory(service)
    scheduler = SchedulerService(service)
    monkeypatch.setattr(scheduler, "get_scheduler_summary", lambda: {"periodic": {"enabled": "Enabled", "next_run_time": "2026-10-13T12:00:00+00:00"}})
    folder_page = FoldersPage(service, sync_service=sync)
    card = folder_page.findChild(FolderCard)
    assert card.folder_data["sync_status"] == "Success" and card.folder_data["last_sync"] != "Never"
    dashboard = DashboardPage(service, sync, BackupService(service), scheduler, None, None)
    assert dashboard.last_sync_label.text() != "Never"
    assert dashboard.next_sync_label.text() != "N/A" and "GB free" in dashboard.storage_label.text()
    assert dashboard.chart_data == [1]
    folder_page.close()
    dashboard.close()


def test_monitor_watches_real_file_changes_and_respects_pause(qapp, configured, sync_service_factory):
    service, local, cloud = configured
    config = service.get_app_config()
    service.save(replace(config, copy_engine=replace(config.copy_engine, monitor_mode=True)))
    sync = sync_service_factory(service)
    sync._monitor_timer.setInterval(30)
    sync.set_paused(True)
    (local / "monitored.txt").write_text("changed")
    deadline = time.monotonic() + 2
    while not sync._monitor_dirty and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(.005)
    assert sync._monitor_dirty and not (cloud / "monitored.txt").exists()
    sync.set_paused(False)
    deadline = time.monotonic() + 5
    while (not (cloud / "monitored.txt").exists() or sync.is_syncing) and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(.005)
    sync.wait_for_finished()
    assert (cloud / "monitored.txt").read_text() == "changed"
    assert sync_service_factory(service).get_folder_history()["app"]["succeeded"]


def test_failed_dry_run_remains_failed_in_folder_history(qapp, configured, sync_service_factory):
    from ui.pages.folders import FoldersPage
    from ui.widgets.folder_card import FolderCard
    service, *_ = configured
    config = replace(service.get_app_config(), general=replace(service.get_app_config().general, dry_run=True))
    folder = replace(config.folders[0], local_path=config.folders[0].local_path_resolved / "missing")
    config = replace(config, folders=[folder])
    service.save(config)
    outcomes = SyncManager(config, service.history_path).run_shutdown_sync()
    assert not outcomes[0].succeeded
    page = FoldersPage(service, sync_service=sync_service_factory(service))
    assert page.findChild(FolderCard).folder_data["sync_status"] == "Failed (dry run)"
    page.close()


def test_corrupt_history_does_not_hide_configured_folders(qapp, configured, sync_service_factory):
    from ui.pages.folders import FoldersPage
    from ui.widgets.folder_card import FolderCard
    service, *_ = configured
    service.history_path.write_bytes(b"not a database")
    sync = sync_service_factory(service)
    page = FoldersPage(service, sync_service=sync)
    assert page.findChild(FolderCard) is not None
    assert "history unavailable" in page.status_label.text().lower()
    page.close()


def test_monitored_failed_request_retains_changes_for_retry(qapp, configured, sync_service_factory, monkeypatch):
    service, *_ = configured
    config = service.get_app_config()
    service.save(replace(config, copy_engine=replace(config.copy_engine, monitor_mode=True)))
    sync = sync_service_factory(service)
    calls = []
    def request(operation):
        calls.append(operation)
        sync._is_syncing = True
        sync._on_worker_failed("Another synchronization holds the lock")
        sync._on_thread_finished()
        return True
    monkeypatch.setattr(sync, "request_sync", request)
    sync._monitor_dirty = True
    sync._run_monitored_sync()
    assert calls == ["shutdown"] and sync._monitor_dirty and sync._monitor_timer.isActive()


def test_monitor_polls_paths_when_native_registration_fails(qapp, configured, sync_service_factory, monkeypatch):
    service, local, _ = configured
    file = local / "file"
    file.write_text("initial")
    config = service.get_app_config()
    service.save(replace(config, copy_engine=replace(config.copy_engine, monitor_mode=True)))
    sync = sync_service_factory(service)
    monkeypatch.setattr(sync._watcher, "addPaths", lambda paths: paths)
    sync._refresh_monitor()
    assert str(file) in sync._unwatched_state and sync._poll_timer.isActive()
    file.write_text("changed contents")
    sync._poll_unwatched()
    assert sync._monitor_dirty


def test_scheduler_script_handles_missing_task_and_missing_folder(configured, monkeypatch):
    import base64
    service, *_ = configured
    scripts = []
    def query(command, **kwargs):
        scripts.append(base64.b64decode(command[-1]).decode("utf-16-le"))
        return json.dumps({"exists": False, "enabled": False, "status": "Not Found", "last_run_time": None, "next_run_time": None, "triggers": []})
    monkeypatch.setattr("backend.services.scheduler_service.subprocess.check_output", query)
    info = SchedulerService(service).get_startup_sync_info()
    assert info["status"] == "Not Found" and info["enabled"] == "Disabled" and not info["exists"]
    assert "-2147024894" in scripts[0] and "-2147024893" in scripts[0]


def test_cli_writes_same_history_read_by_gui(qapp, configured, sync_service_factory):
    from src.sync_runner import run_sync
    service, local, cloud = configured
    (local / "file").write_text("cli data")
    config_path = service.history_path.with_suffix("").with_suffix(".json")
    assert run_sync("shutdown", config_path) == 0
    assert (cloud / "file").read_text() == "cli data"
    assert sync_service_factory(service).get_folder_history()["app"]["succeeded"]


def test_monitor_retries_failed_folder_outcome_from_real_worker(qapp, configured, sync_service_factory, monkeypatch):
    service, local, cloud = configured
    (local / "file").write_text("source")
    config = service.get_app_config()
    service.save(replace(config, copy_engine=replace(config.copy_engine, monitor_mode=True)))
    monkeypatch.setattr(CopyEngine, "run", lambda *a, **k: CopyResult(local, cloud, 8, False, "", "locked files", False))
    sync = sync_service_factory(service)
    sync._monitor_dirty = True
    sync._run_monitored_sync()
    deadline = time.monotonic() + 5
    while sync.is_syncing and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(.005)
    sync.wait_for_finished()
    assert sync._monitor_dirty and sync._monitor_timer.isActive()
    assert not sync.get_folder_history()["app"]["succeeded"]


def test_scheduler_refresh_does_not_block_gui_and_caches_errors(qapp, configured, monkeypatch):
    from PySide6.QtCore import QTimer
    service, *_ = configured
    scheduler = SchedulerService(service)
    entered, release = threading.Event(), threading.Event()
    def summary():
        entered.set()
        assert release.wait(3)
        return {"periodic": {"enabled": "Disabled"}}
    monkeypatch.setattr(scheduler, "get_scheduler_summary", summary)
    heartbeat = []
    try:
        assert scheduler.request_refresh()
        assert entered.wait(1)
        QTimer.singleShot(0, lambda: heartbeat.append(True))
        qapp.processEvents()
        assert heartbeat and scheduler.cached_summary is None
    finally:
        release.set()
        scheduler.wait_for_finished()
        qapp.processEvents()
    assert scheduler.cached_summary["periodic"]["enabled"] == "Disabled"
    assert not scheduler.request_refresh()
    calls = []
    def broken(*args, **kwargs):
        calls.append(True)
        raise OSError("unavailable")
    monkeypatch.setattr("backend.services.scheduler_service.subprocess.check_output", broken)
    assert scheduler._get_task_info("missing") is None
    assert scheduler._get_task_info("missing") is None
    assert len(calls) == 1


def test_backup_write_root_prevents_parallel_read_of_unfinished_archive(configured, tmp_path, monkeypatch):
    import zipfile
    service, local, cloud = configured
    (local / "file").write_text("new")
    (cloud / "file").write_text("old")
    archives, copied = tmp_path / "archives", tmp_path / "copied"
    (archives / "app").mkdir(parents=True)
    copied.mkdir()
    config = service.get_app_config()
    a = replace(config.folders[0], backup=BackupSettings(True, archives, 7))
    b = replace(a, id="reader", name="Reader", local_path=archives / "app", onedrive_path=copied, backup=None)
    config = replace(config, general=replace(config.general, max_parallel_jobs=2), folders=[a, b])
    manager = SyncManager(config)
    writer_open = threading.Event()
    real_run = manager._copy_engine.run
    def compress(source, destination):
        with zipfile.ZipFile(destination, "w") as archive:
            archive.writestr("file", "old")
            writer_open.set()
            # Let an incorrectly parallel reader observe the incomplete ZIP.
            time.sleep(.1)
        writer_open.clear()
    def copy(source, destination, **kwargs):
        if source == archives / "app":
            assert not writer_open.is_set(), "Reading a ZIP before compression finishes"
        return real_run(source, destination, **kwargs)
    monkeypatch.setattr(manager._backup, "_compress_directory", compress)
    monkeypatch.setattr(manager._copy_engine, "run", copy)
    outcomes = manager.run_shutdown_sync()
    assert all(o.succeeded for o in outcomes)
    assert zipfile.is_zipfile(next(copied.glob("*.zip")))


def test_history_releases_database_file_after_write_and_read(configured):
    service, *_ = configured
    SyncManager(service.get_app_config(), service.history_path).run_shutdown_sync()
    assert SyncHistory(service.history_path).recent()
    # Windows forbids these operations when a SQLite connection leaks a handle.
    renamed = service.history_path.with_suffix(".moved.sqlite3")
    service.history_path.rename(renamed)
    renamed.unlink()
    assert not renamed.exists()
