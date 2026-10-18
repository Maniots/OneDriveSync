import hashlib
import io
import json
import sys
import time
from pathlib import Path
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pytest
from PySide6.QtCore import QObject, QTimer, Signal

from src.app_info import REPOSITORY
from src.updater import API_URL, AvailableUpdate, CheckResult, UpdateClient, UpdateError, version_key
from backend.services.update_service import UpdateService
from ui.pages.about import AboutPage


@pytest.fixture
def release_data():
    payload = b"isolated executable bytes"
    version, tag = "1.1.0.10", "master-10"
    filename = f"EverySync-Setup-{version}.exe"
    base = f"https://github.com/{REPOSITORY}/releases/download/{tag}/"
    manifest = {"schema": 1, "channel": "master", "repository": REPOSITORY,
                "version": version, "commit": "a" * 40, "installer": filename,
                "sha256": hashlib.sha256(payload).hexdigest(), "size": len(payload)}
    release = {"tag_name": tag, "draft": False, "prerelease": False,
               "assets": [{"name": "update.json", "browser_download_url": base + "update.json"},
                          {"name": filename, "size": len(payload), "browser_download_url": base + filename}]}
    return payload, manifest, release


def client_for(tmp_path, data, change_payload=None):
    payload, manifest, release = data
    requests = []
    def open_response(request, timeout):
        requests.append(request.full_url)
        if request.full_url == API_URL:
            contents = json.dumps(release).encode()
        elif request.full_url.endswith("update.json"):
            contents = json.dumps(manifest).encode()
        else:
            contents = payload if change_payload is None else change_payload
        return io.BytesIO(contents)
    return UpdateClient("1.1.0.2", tmp_path, open_response), requests


def spin(qapp, condition, seconds=5):
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(.001)
    qapp.processEvents()
    assert condition()


def test_check_and_verified_download(tmp_path, release_data):
    client, requests = client_for(tmp_path, release_data)
    result = client.check()
    assert result.status == "available" and result.update.version == "1.1.0.10"
    percentages = []
    installer = client.download(result.update, percentages.append)
    assert installer.read_bytes() == release_data[0]
    assert percentages[-1] == 100
    assert len(requests) == 3
    client.current_version = "1.1.0.11"
    assert client.check().status == "current"


@pytest.mark.parametrize("field,value", [("version", "../bad"), ("sha256", "bad"),
                                         ("size", True), ("size", 0), ("size", 300 * 1024**2),
                                         ("repository", "other/repository"), ("channel", "preview"),
                                         ("installer", "../../unsafe.exe"),
                                         ("installer", "EverySync-Setup-9.9.9.9.exe"), ("commit", "x")])
def test_rejects_invalid_manifest(tmp_path, release_data, field, value):
    release_data[1][field] = value
    client, requests = client_for(tmp_path, release_data)
    with pytest.raises(UpdateError):
        client.check()
    assert len(requests) <= 2


@pytest.mark.parametrize("url", ["http://github.com/unsafe", "https://evil.example/file", "https://github.com/other/repo/releases/download/master-10/file"])
def test_rejects_external_asset_origin(tmp_path, release_data, url):
    release_data[2]["assets"][0]["browser_download_url"] = url
    client, requests = client_for(tmp_path, release_data)
    with pytest.raises(UpdateError):
        client.check()
    assert requests == [API_URL]


@pytest.mark.parametrize("payload", [b"truncated", b"corrupt replacement bytes", b"x" * 100])
def test_hash_and_length_failure_never_leaves_an_executable(tmp_path, release_data, payload):
    client, _ = client_for(tmp_path, release_data, payload)
    result = client.check()
    with pytest.raises(UpdateError):
        client.download(result.update)
    assert not list(tmp_path.rglob("*.exe"))
    assert not list(tmp_path.rglob("*.part"))


def test_no_release_and_network_error(tmp_path):
    def unavailable(request, timeout):
        raise HTTPError(request.full_url, 404, "not found", None, None)
    client = UpdateClient(root=tmp_path, opener=unavailable)
    assert client.check().status == "no_release"
    client.opener = lambda *args, **kwargs: (_ for _ in ()).throw(URLError("offline"))
    with pytest.raises(UpdateError, match="internet"):
        client.check()


def test_numeric_versions_and_preferences(tmp_path):
    assert version_key("1.1.0.10") > version_key("1.1.0.2")
    assert version_key("1.1.0") == version_key("1.1.0.0")
    client = UpdateClient(root=tmp_path)
    assert not client.load_automatic()
    client.save_automatic(True)
    assert client.load_automatic()
    client.save_automatic(False)
    assert not client.load_automatic()


def test_manifest_release_notes_are_bounded_and_kept_as_plain_text(tmp_path, release_data):
    release_data[1]["changes"] = "New version: <b>Force sync</b>"
    client, _ = client_for(tmp_path, release_data)
    assert client.check().update.changes == "New version: <b>Force sync</b>"
    release_data[1]["changes"] = "a" * 4097
    with pytest.raises(UpdateError, match="release notes"):
        client.check()


def test_async_check_remains_responsive_and_duplicate_requests_are_ignored(qapp, tmp_path, release_data):
    client, _ = client_for(tmp_path, release_data)
    real_check = client.check
    def slow_check():
        time.sleep(.05)
        return real_check()
    client.check = slow_check
    service = UpdateService(client=client)
    page = AboutPage(update_service=service)
    ticks = []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start(1)
    try:
        assert service.check()
        assert not service.check()
        assert not page.check_updates_button.isEnabled()
        spin(qapp, lambda: not service.busy)
        assert ticks and service.state == "available"
        assert "1.1.0.10" in page.update_status.text()
    finally:
        timer.stop()
        service.wait_for_finished()
        page.close()


def test_download_waits_for_ui_sync_before_launching_installer(qapp, tmp_path, release_data):
    class SyncState(QObject):
        state_changed = Signal()
        is_syncing = True
    sync = SyncState()
    client, _ = client_for(tmp_path, release_data)
    client.launch_install = Mock()
    service = UpdateService(sync, client)
    service.can_install = True
    try:
        assert service.check(install=True)
        spin(qapp, lambda: service.state == "ready")
        client.launch_install.assert_not_called()
        assert "synchronization finishes" in service.message
        sync.is_syncing = False
        sync.state_changed.emit()
        client.launch_install.assert_called_once()
        assert service.state == "installing"
    finally:
        service.wait_for_finished()


def test_installer_waits_for_cloud_restore_and_retries_when_it_finishes(qapp, tmp_path, release_data):
    class CloudState(QObject):
        busy_changed = Signal(bool)
        busy = True
    cloud = CloudState()
    client, _ = client_for(tmp_path, release_data)
    client.launch_install = Mock()
    service = UpdateService(client=client, cloud_service=cloud)
    service.can_install = True
    try:
        assert service.check(install=True)
        spin(qapp, lambda: service.state == "ready")
        client.launch_install.assert_not_called()
        cloud.busy = False
        cloud.busy_changed.emit(False)
        client.launch_install.assert_called_once()
        assert service.state == "installing"
    finally:
        service.wait_for_finished()


def test_error_state_allows_retry_without_installing(qapp, tmp_path):
    client = UpdateClient(root=tmp_path)
    client.check = Mock(side_effect=[UpdateError("Offline, retry later"), CheckResult("current")])
    service = UpdateService(client=client)
    page = AboutPage(update_service=service)
    try:
        service.check()
        spin(qapp, lambda: service.state == "error")
        assert page.check_updates_button.isEnabled()
        assert "Offline" in page.update_status.text()
        service.check()
        spin(qapp, lambda: service.state == "current")
        assert "latest" in page.update_status.text()
        assert not page.install_update_button.isEnabled()
    finally:
        service.wait_for_finished()
        page.close()


def test_update_result_is_published_after_native_worker_disposal(qapp, tmp_path, monkeypatch):
    from PySide6.QtCore import Qt
    from threading import Event
    from backend.services import update_service

    disposed = Event()

    def finish_disposal():
        # Emulate native cleanup still running after finished was emitted.
        time.sleep(.05)
        disposed.set()

    original = update_service._UpdateWorker

    class SlowDisposalWorker(original):
        def __init__(self, *args):
            super().__init__(*args)
            self.destroyed.connect(finish_disposal, Qt.ConnectionType.DirectConnection)

    monkeypatch.setattr(update_service, "_UpdateWorker", SlowDisposalWorker)
    client = UpdateClient(root=tmp_path)
    client.check = Mock(return_value=CheckResult("current"))
    service = UpdateService(client=client)
    terminal_states = []
    service.changed.connect(lambda: terminal_states.append(disposed.is_set())
                            if service.state == "current" else None)
    try:
        assert service.check()
        spin(qapp, lambda: not service.busy)
        assert terminal_states == [True]
    finally:
        service.wait_for_finished()


def test_shutdown_monitor_respects_the_update_and_sync_lock(monkeypatch):
    from src import shutdown_monitor as monitor
    monkeypatch.setattr(monitor, "acquire_single_instance_lock", lambda path: None)
    run = Mock()
    monkeypatch.setattr(monitor, "run_sync", run)
    with pytest.raises(RuntimeError, match="update"):
        monitor._run_shutdown_sync()
    run.assert_not_called()


def test_exit_during_check_cannot_download_or_install(qapp, tmp_path, release_data):
    client, _ = client_for(tmp_path, release_data)
    real_check = client.check
    def slow_check():
        time.sleep(.05)
        return real_check()
    client.check = slow_check
    client.download = Mock()
    client.launch_install = Mock()
    service = UpdateService(client=client)
    service.can_install = True
    assert service.check(install=True)
    service.wait_for_finished()
    spin(qapp, lambda: service._thread is None)
    client.download.assert_not_called()
    client.launch_install.assert_not_called()
    assert not service.check()


@pytest.mark.parametrize("command,expected", [("--check-updates", ["--updates"]),
                                             ("--update", ["--updates", "--install-update"])])
def test_desktop_update_commands_open_the_requested_flow(monkeypatch, command, expected):
    import desktop_entry
    import ui.app
    open_ui = Mock(return_value=0)
    monkeypatch.setattr(ui.app, "main", open_ui)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert desktop_entry.main([command]) == 0
    open_ui.assert_called_once_with(expected)


def test_window_deletion_closes_native_chart_before_scene_teardown(qapp, tmp_path):
    from PySide6.QtCore import QCoreApplication, QEvent
    from shiboken6 import isValid
    from backend.services.configuration_service import ConfigurationService
    from ui.main_window import MainWindow
    template = Path(__file__).resolve().parents[1] / "packaging/default-config.json"
    path = tmp_path / "config.json"
    path.write_bytes(template.read_bytes())
    window = MainWindow(configuration_service=ConfigurationService(path))
    from pyqtgraph import PlotWidget
    chart, = window.findChildren(PlotWidget)
    updater = window.update_service
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()
    assert not isValid(window) and not isValid(chart)
    assert updater._closing
