"""Installed entry points must agree on paths and preserve user data."""
import json
import sys
from pathlib import Path

import pytest

from src import runtime_paths
from src.config_manager import ConfigManager


def test_source_paths_are_independent_of_working_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert runtime_paths.default_config_path() == runtime_paths.SOURCE_ROOT / "config.json"
    assert runtime_paths.sync_lock_path().parent == runtime_paths.SOURCE_ROOT


def test_frozen_first_run_preserves_configuration(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "User Data"))
    path = runtime_paths.ensure_default_config()
    assert ConfigManager(path).load().folders == []
    custom = json.loads(path.read_text())
    custom["general"]["dry_run"] = True
    path.write_text(json.dumps(custom))
    original = path.read_bytes()
    assert runtime_paths.ensure_default_config() == path
    assert path.read_bytes() == original
    assert runtime_paths.log_dir().parent == path.parent
    assert runtime_paths.sync_lock_path().parent == path.parent


def test_installed_services_use_shared_data_directory(monkeypatch, tmp_path, qapp):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    path = runtime_paths.ensure_default_config()
    from backend.services.configuration_service import ConfigurationService
    from backend.services.log_service import LogService
    service = ConfigurationService()
    assert service.get_app_config() is not None
    assert service.history_path == path.with_suffix(".history.sqlite3")
    assert LogService()._log_path == runtime_paths.log_dir() / "onedrive_pcsync.log"
    status = {"status": "running", "pid": 123}
    (path.parent / "shutdown_monitor_status.json").write_text(json.dumps(status))
    assert service.get_shutdown_monitor_status() == status


def test_desktop_dispatches_sync_with_explicit_config_and_dry_run(monkeypatch, tmp_path):
    import main as sync_entry
    import desktop_entry
    observed = []
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sync_entry, "main", lambda argv: observed.append(argv) or 1)
    path = tmp_path / "custom.json"
    assert desktop_entry.main(["--mode", "shutdown", "--config", str(path), "--dry-run"]) == 1
    assert observed == [["--mode", "shutdown", "--config", str(path), "--dry-run"]]


def test_desktop_rejects_ambiguous_actions():
    import desktop_entry
    with pytest.raises(SystemExit):
        desktop_entry.parse_arguments(["--monitor", "--mode", "startup"])
    with pytest.raises(SystemExit):
        desktop_entry.parse_arguments(["--monitor", "--config", "ignored.json"])


@pytest.mark.skipif(sys.platform != "win32", reason="Native monitor requires Windows")
def test_shutdown_monitor_imports_its_native_dependencies():
    from src import shutdown_monitor
    assert shutdown_monitor.win32gui is not None
    assert shutdown_monitor.win32api is not None
    assert shutdown_monitor.win32con is not None


def test_monitor_persists_completed_sync_status(monkeypatch):
    from src import shutdown_monitor as module
    snapshots = []
    monkeypatch.setattr(module, "run_sync", lambda **kwargs: 0)
    monkeypatch.setattr(module, "_emergency_log", lambda message: None)
    monkeypatch.setattr(module, "_write_status", snapshots.append)
    monitor = module.ShutdownMonitorWindow()
    assert monitor._window_proc(0, module.WM_QUERYENDSESSION, 0, 0) == 1
    assert snapshots[-1]["last_detected_event"]
    assert snapshots[-1]["last_shutdown_sync"]
    assert snapshots[-1]["last_error"] is None


def test_windowless_logging_has_no_console_handler(monkeypatch, tmp_path):
    import logging
    from src import logger
    root = logging.getLogger(logger._ROOT_LOGGER_NAME)
    previous = root.handlers[:]
    previous_initialized = logger._LOGGER_INITIALIZED
    monkeypatch.setattr(sys, "stdout", None)
    root.handlers = []
    logger._LOGGER_INITIALIZED = False
    try:
        result = logger.setup_logger(tmp_path)
        assert len(result.handlers) == 1
        result.info("Windowless application can log")
        assert "Windowless application" in (tmp_path / "onedrive_pcsync.log").read_text()
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers = previous
        logger._LOGGER_INITIALIZED = previous_initialized
