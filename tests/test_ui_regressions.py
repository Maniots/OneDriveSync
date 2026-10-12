"""Functional regressions for shared UI sync state and core path contracts."""
import json
import os
import threading
import time
from dataclasses import replace
from pathlib import Path
import zipfile

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QTimer
from PySide6.QtWidgets import QMessageBox

from backend.services.configuration_service import ConfigurationService
from backend.services.log_service import LogService
from backend.services.monitor_service import MonitorService
from backend.services.scheduler_service import SchedulerService
from backend.services.sync_service import SyncService
from src.config_manager import ConfigManager
from src.exceptions import ConfigurationError, PathValidationError
from src.robocopy_manager import CopyEngine
from ui.main_window import MainWindow
from ui.pages.scheduler import SchedulerPage
from ui.workers import sync_worker as worker_module


@pytest.fixture
def configuration(tmp_path, monkeypatch):
    local = tmp_path / "local" / "app"
    cloud = tmp_path / "OneDrive" / "app"
    local.mkdir(parents=True)
    cloud.mkdir(parents=True)
    monkeypatch.setenv("OneDrive", str(cloud.parent))
    monkeypatch.setenv("APPDATA", str(local.parent))
    data = {
        "general": {"dry_run": False, "verify_after_sync": True},
        "sync": {"startup": {"enabled": True, "direction": "download"},
                 "shutdown": {"enabled": True, "direction": "upload"}},
        "folders": [{"id": "app", "name": "App", "enabled": True,
                     "local_path": "%APPDATA%/app", "onedrive_path": "%OneDrive%/app",
                     "minimum_sync_percentage": 80, "verify_after_sync": True,
                     "create_destination": True}]
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data))
    return ConfigurationService(path), local, cloud, path


def spin_until(qapp, condition, seconds=5):
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.001)
    qapp.processEvents()
    assert condition(), "Qt operation did not finish in time"


def test_configuration_roundtrip_preserves_variables_and_accepts_path_inputs(configuration):
    service, local, cloud, path = configuration
    config = service.get_app_config()
    service.save(config)
    saved = json.loads(path.read_text())
    assert saved["folders"][0]["local_path"] == "%APPDATA%/app"
    assert saved["folders"][0]["onedrive_path"] == "%OneDrive%/app"
    folder = config.folders[0]
    assert folder.local_path_resolved == local
    assert folder.onedrive_path_resolved == cloud
    changed = replace(folder, local_path=local, onedrive_path=cloud)
    service.save(replace(config, folders=[changed]))
    assert ConfigManager(path).load().folders[0].local_path_resolved == local


def test_invalid_save_preserves_existing_configuration(configuration):
    service, local, cloud, path = configuration
    before = path.read_bytes()
    config = service.get_app_config()
    folder = replace(config.folders[0], local_path=config.folders[0].onedrive_path)
    with pytest.raises((ConfigurationError, PathValidationError)):
        service.save(replace(config, folders=[folder]))
    assert path.read_bytes() == before
    assert service.get_app_config() is config
    assert list(path.parent.glob(".config.json.*.tmp")) == []


def test_monitor_service_reads_real_manager_status(configuration, monkeypatch):
    service, *_ = configuration
    status = {"status": "running", "pid": 123, "last_detected_event": "shutdown"}
    monkeypatch.setattr(ConfigManager, "get_shutdown_monitor_status", lambda self: status)
    assert MonitorService(service).get_status() == status


def test_sync_service_copies_json_paths_and_creates_preupload_backup(qapp, configuration):
    service, local, cloud, path = configuration
    (local / "save.txt").write_text("new save")
    (cloud / "save.txt").write_text("old save")
    os.utime(cloud / "save.txt", (time.time() - 10, time.time() - 10))
    data = json.loads(path.read_text())
    data["folders"][0]["backup"] = {"enabled": True, "backup_path": "%OneDrive%/Backups", "retention_days": 7}
    path.write_text(json.dumps(data))
    service.reload()
    sync = SyncService(service)
    completed, failures = [], []
    sync.completed.connect(completed.append)
    sync.failed.connect(failures.append)
    assert sync.request_sync("shutdown")
    spin_until(qapp, lambda: not sync.is_syncing)
    assert not failures
    assert len(completed) == 1 and completed[0][0].succeeded
    assert (cloud / "save.txt").read_text() == "new save"
    archives = list((cloud.parent / "Backups" / "app").glob("*.zip"))
    assert len(archives) == 1
    with zipfile.ZipFile(archives[0]) as archive:
        assert archive.read("save.txt") == b"old save"


def test_dry_run_does_not_copy_or_create_backup(qapp, configuration):
    service, local, cloud, path = configuration
    (local / "save.txt").write_text("local")
    (cloud / "save.txt").write_text("cloud")
    data = json.loads(path.read_text())
    data["general"]["dry_run"] = True
    data["folders"][0]["backup"] = {"enabled": True, "backup_path": "%OneDrive%/Backups", "retention_days": 7}
    path.write_text(json.dumps(data))
    service.reload()
    sync = SyncService(service)
    completed = []
    sync.completed.connect(completed.append)
    assert sync.request_sync("shutdown")
    spin_until(qapp, lambda: not sync.is_syncing)
    assert completed[0][0].succeeded
    assert (local / "save.txt").read_text() == "local"
    assert (cloud / "save.txt").read_text() == "cloud"
    assert not (cloud.parent / "Backups").exists()


def test_dashboard_and_tray_share_background_sync_pause_and_safe_exit(qapp, configuration, monkeypatch):
    service, local, cloud, _ = configuration
    (local / "save.txt").write_text("new save")
    window = MainWindow(configuration_service=service)
    sync = window.sync_service
    dashboard = window.content_stack.widget(0)
    entered, release = threading.Event(), threading.Event()
    original_run = CopyEngine.run
    thread_ids = []

    def delayed_run(engine, *args, **kwargs):
        thread_ids.append(threading.get_ident())
        entered.set()
        assert release.wait(5), "test did not release copy"
        return original_run(engine, *args, **kwargs)

    monkeypatch.setattr(CopyEngine, "run", delayed_run)
    quits, ticks, completed = [], [], []
    monkeypatch.setattr(qapp, "quit", lambda: quits.append(True))
    sync.completed.connect(completed.append)
    try:
        window.sync_now()
        QTimer.singleShot(0, lambda: ticks.append(True))
        spin_until(qapp, entered.is_set)
        assert ticks and len(thread_ids) == 1
        assert thread_ids[0] != threading.get_ident()
        assert not dashboard.startup_button.isEnabled()
        assert not window.sync_now_action.isEnabled()
        assert not sync.request_sync("startup")
        window.toggle_pause_resume()
        assert sync.is_paused
        window.exit_application()
        assert not quits
        release.set()
        spin_until(qapp, lambda: not sync.is_syncing)
        assert quits == [True]
        assert len(completed) == 1
        assert (cloud / "save.txt").read_text() == "new save"
        assert "successfully" in window.tray_icon.toolTip()
        assert "successfully" in dashboard.status_label.text()
        assert not dashboard.shutdown_button.isEnabled()
        window._exit_requested = False
        window.toggle_pause_resume()
        assert dashboard.shutdown_button.isEnabled()
        assert window.sync_now_action.isEnabled()
    finally:
        release.set()
        sync.wait_for_finished()
        window.tray_icon.hide()
        window.close()


def test_failed_folder_does_not_block_others_and_ui_reports_errors(qapp, configuration):
    service, local, cloud, path = configuration
    (cloud / "save.txt").write_text("download")
    data = json.loads(path.read_text())
    bad = dict(data["folders"][0], id="missing", name="Missing", onedrive_path=str(path.parent / "absent"))
    data["folders"].insert(0, bad)
    path.write_text(json.dumps(data))
    service.reload()
    window = MainWindow(configuration_service=service)
    sync = window.sync_service
    dashboard = window.content_stack.widget(0)
    completed = []
    sync.completed.connect(completed.append)
    try:
        dashboard.start_startup_sync()
        spin_until(qapp, lambda: not sync.is_syncing)
        assert [o.succeeded for o in completed[0]] == [False, True]
        assert (local / "save.txt").read_text() == "download"
        assert "errors" in dashboard.status_label.text()
        assert "errors" in window.tray_icon.toolTip()
        dashboard.update_data()
        assert "errors" in dashboard.status_label.text()
        assert dashboard.chart_data == [1]
    finally:
        sync.wait_for_finished()
        window.tray_icon.hide()
        window.close()


def test_external_sync_lock_prevents_ui_copy(qapp, configuration, monkeypatch):
    service, local, cloud, _ = configuration
    (local / "save.txt").write_text("local")
    monkeypatch.setattr(worker_module, "acquire_single_instance_lock", lambda path: None)
    sync = SyncService(service)
    failures = []
    sync.failed.connect(failures.append)
    assert sync.request_sync("shutdown")
    spin_until(qapp, lambda: not sync.is_syncing)
    assert "already running" in failures[0]
    assert not (cloud / "save.txt").exists()


def test_paused_or_disabled_sync_does_not_write(qapp, configuration):
    service, local, cloud, _ = configuration
    (local / "save.txt").write_text("local")
    sync = SyncService(service)
    sync.set_paused(True)
    assert not sync.request_sync("shutdown")
    sync.set_paused(False)
    config = service.get_app_config()
    service.save(replace(config, sync=replace(config.sync, shutdown=replace(config.sync.shutdown, enabled=False))))
    assert not sync.request_sync("shutdown")
    assert not sync.is_syncing
    assert not (cloud / "save.txt").exists()


def test_scheduler_recovers_without_deleted_widgets_or_implicit_writes(qapp, configuration, monkeypatch):
    config_service, *_ = configuration

    class Scheduler:
        _TASK_NAMES = SchedulerService._TASK_NAMES
        summary = None
        writes = []

        def get_scheduler_summary(self):
            return self.summary

        def set_task_enabled(self, task, enabled):
            self.writes.append((task, enabled))
            self.summary[task]["enabled"] = "Enabled" if enabled else "Disabled"
            return True

    scheduler = Scheduler()
    monitor = MonitorService(config_service)
    page = SchedulerPage(config_service, scheduler, monitor)
    dialogs = []

    def confirm(*args):
        dialogs.append(True)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", confirm)
    try:
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        page.update_shutdown_monitor_status()
        assert page.monitor_status_label.text() == "Unknown"
        scheduler.summary = {name: {"enabled": "Enabled", "exists": True,
                                   "last_run_time": None, "next_run_time": None}
                             for name in ("startup", "periodic", "workstation_lock")}
        page.load_scheduler_data()
        assert page.startup_enabled_checkbox.isChecked()
        assert page.startup_last_run_label.text() == "N/A"
        assert page.error_label.isHidden()
        assert not dialogs and not scheduler.writes
        page.startup_enabled_checkbox.setChecked(False)
        assert scheduler.writes == [("startup", False)]
        assert len(dialogs) == 1
        assert not page.startup_enabled_checkbox.isChecked()
    finally:
        page.close()


def test_log_viewer_reads_padded_standard_log_levels(qapp, tmp_path):
    path = tmp_path / "app.log"
    path.write_text("2026-10-12 11:00:00 | INFO     | onedrive_pcsync | Copied save\n")
    entries = LogService(path).get_log_entries()
    assert len(entries) == 1
    assert entries[0][1:] == ("INFO", "[onedrive_pcsync] Copied save")


def test_folder_actions_persist_filter_and_sync_only_selected_folder(qapp, configuration, monkeypatch):
    service, local, cloud, path = configuration
    window = MainWindow(configuration_service=service)
    page = window.content_stack.widget(1)
    sync = window.sync_service
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    other_local = local.parent / "other"
    other_local.mkdir()
    (local / "selected.txt").write_text("selected")
    (other_local / "other.txt").write_text("other")
    data = {"id": "other", "name": "Other App", "enabled": True,
            "local_path": str(other_local), "onedrive_path": "%OneDrive%/other",
            "minimum_sync_percentage": 80, "verify_after_sync": True, "create_destination": True}
    try:
        page.save_folder_data(data)
        assert not warnings
        assert len(ConfigManager(path).load().folders) == 2
        page.on_folder_toggle_requested("other", False)
        assert not service.get_app_config().folders[1].enabled
        page.filter_combo.setCurrentText("Disabled")
        assert page.folders_layout.count() == 1
        page.search_input.setText("not found")
        assert page.folders_layout.count() == 0
        page.search_input.clear()
        data["name"] = "Renamed App"
        page.save_folder_data(data, original_id="other")
        assert service.get_app_config().folders[1].name == "Renamed App"
        assert len(service.get_app_config().folders) == 2
        page.on_folder_sync_requested("app")
        spin_until(qapp, lambda: not sync.is_syncing)
        assert (cloud / "selected.txt").read_text() == "selected"
        assert not (cloud.parent / "other" / "other.txt").exists()
        before = path.read_bytes()
        page.save_folder_data(data)  # duplicate ID must not alter the saved config
        assert warnings and path.read_bytes() == before
    finally:
        sync.wait_for_finished()
        window.tray_icon.hide()
        window.close()


def test_settings_apply_keeps_newly_added_folders(qapp, configuration, monkeypatch):
    service, local, cloud, _ = configuration
    window = MainWindow(configuration_service=service)
    settings = window.content_stack.widget(5)
    config = service.get_app_config()
    added = replace(config.folders[0], id="new", name="New", local_path=str(local.parent / "new"),
                    onedrive_path=str(cloud.parent / "new"))
    service.save(replace(config, folders=[*config.folders, added]))
    monkeypatch.setattr(QMessageBox, "information", lambda *args: QMessageBox.StandardButton.Ok)
    try:
        settings.on_apply_clicked()
        assert [f.id for f in service.get_app_config().folders] == ["app", "new"]
        assert settings.status_label.text() == "Settings saved successfully"
    finally:
        window.tray_icon.hide()
        window.close()


def test_wizard_edit_defaults_expand_paths_and_accept_windows_drive(qapp, configuration, monkeypatch):
    from ui.widgets.add_folder_wizard import AddFolderWizard
    service, local, cloud, _ = configuration
    data = {"id": "app", "name": "App", "enabled": False,
            "local_path": "%APPDATA%/app", "onedrive_path": "%OneDrive%/app",
            "minimum_sync_percentage": 90, "backup_enabled": True,
            "backup_path": "%OneDrive%/Backups", "backup_retention_days": 14}
    wizard = AddFolderWizard(folder_data=data)
    try:
        for page in (wizard.page_basic_info, wizard.page_local_folder, wizard.page_onedrive_folder,
                     wizard.page_safety, wizard.page_backup):
            page.initializePage()
        assert wizard.page_basic_info.get_data()["id"] == "app"
        assert not wizard.page_basic_info.get_data()["enabled"]
        assert wizard.page_local_folder.validatePage()
        assert wizard.page_safety.get_data()["minimum_sync_percentage"] == 90
        assert wizard.page_backup.get_data()["backup_retention_days"] == 14
        wizard.page_onedrive_folder.path_edit.setText("C:\\Users\\Me\\OneDrive\\app")
        assert wizard.page_onedrive_folder.validatePage()
        wizard.page_backup.backup_path_edit.setText("C:\\Users\\Me\\OneDrive\\Backups")
        assert wizard.page_backup.validatePage()
        wizard.page_onedrive_folder.path_edit.setText("PCSync/app")
        assert wizard.page_onedrive_folder.get_data()["onedrive_path"] == "%OneDrive%/PCSync/app"
        monkeypatch.delenv("OneDrive")
        wizard.page_onedrive_folder.path_edit.setText("%OneDrive%/app")
        assert wizard.page_onedrive_folder.get_data()["onedrive_path"] == "%OneDrive%/app"
    finally:
        wizard.close()


def test_launcher_accepts_temporary_configuration(qapp, configuration, monkeypatch):
    from ui.app import main
    _, _, _, path = configuration

    def check_window():
        windows = [w for w in qapp.topLevelWidgets() if isinstance(w, MainWindow) and w.isVisible()]
        assert any(w.config_error is None and w.content_stack.count() == 7 for w in windows)
        return 0

    monkeypatch.setattr(qapp, "exec", check_window)
    assert main(["--config", str(path)]) == 0


def test_synchronous_service_api_keeps_existing_copy_behavior(qapp, configuration):
    service, local, cloud, _ = configuration
    (cloud / "save.txt").write_text("download")
    sync = SyncService(service)
    finished = []
    sync.finished.connect(lambda: finished.append(True))
    outcomes = sync.start_startup_sync()
    assert len(outcomes) == 1 and outcomes[0].succeeded
    assert (local / "save.txt").read_text() == "download"
    assert finished == [True] and not sync.is_syncing
