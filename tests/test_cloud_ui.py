import json
import time
import threading
from dataclasses import replace
from pathlib import Path

from backend.services.configuration_service import ConfigurationService
from backend.services.cloud_service import CloudService
from src.cloud_models import ConnectionConfig, RemoteJobConfig
from ui.pages.connections import ConnectionsPage
from ui.pages.cloud_sync import CloudSyncPage
from src.rclone_transport import CloudSyncError


def spin(qapp, done):
    deadline = time.monotonic() + 5
    while not done() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(.002)
    assert done()


def configuration(tmp_path):
    path = tmp_path / "config.json"
    path.write_bytes((Path(__file__).resolve().parents[1] / "packaging/default-config.json").read_bytes())
    return ConfigurationService(path)


def test_guided_local_connection_and_job_save(qapp, tmp_path):
    config = configuration(tmp_path)
    remote, local = tmp_path / "remote", tmp_path / "local"
    remote.mkdir()
    local.mkdir()
    class Client:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def configure(self, *args, **kwargs): return {}
        def test(self, *args): return {"item": {"IsDir": True}}
    service = CloudService(config, transport_factory=lambda *args, **kwargs: Client())
    page = ConnectionsPage(config, service)
    service.setParent(page)
    page.provider_combo.setCurrentIndex(page.provider_combo.findData("local"))
    page.name_edit.setText("NAS test")
    page.root_edit.setText(str(remote))
    page.connect_button.click()
    spin(qapp, lambda: not service.busy)
    assert len(config.get_app_config().connections) == 1
    jobs = CloudSyncPage(config, service)
    jobs.name_edit.setText("Saves")
    jobs.local_edit.setText(str(local))
    jobs.remote_edit.setText("Game/Saves")
    jobs.save_button.click()
    assert len(config.get_app_config().remote_jobs) == 1
    saved = json.loads((tmp_path / "config.json").read_text())
    assert saved["connections"][0]["provider"] == "local"
    assert saved["remote_jobs"][0]["remote_path"] == "Game/Saves"
    service.wait_for_finished()


def test_provider_fields_mask_secrets_and_guide_oauth(qapp, tmp_path):
    config = configuration(tmp_path)
    page = ConnectionsPage(config, CloudService(config))
    page.provider_combo.setCurrentIndex(page.provider_combo.findData("drive"))
    assert "client_id" in page.option_inputs
    from PySide6.QtWidgets import QLineEdit
    assert page.option_inputs["client_secret"].echoMode() == QLineEdit.EchoMode.Password
    assert "OAuth" in page.provider_hint.text()
    assert page.provider_combo.findData("onedrive") >= 0
    assert page.provider_combo.findData("s3") >= 0


def test_delete_connection_in_use_preserves_configuration(qapp, tmp_path):
    config = configuration(tmp_path)
    local, remote = tmp_path / "local", tmp_path / "remote"
    local.mkdir()
    remote.mkdir()
    connection = ConnectionConfig("nas", "NAS", "local", str(remote))
    job = RemoteJobConfig("saves", "Saves", str(local), "nas", "Game")
    config.save(replace(config.get_app_config(), connections=[connection], remote_jobs=[job]))
    service = CloudService(config)
    try:
        service.remove_connection("nas")
    except ValueError as error:
        assert "job" in str(error).lower()
    else:
        raise AssertionError("Connection used by a job was removed")
    assert config.get_app_config().connections == [connection]


def test_main_window_appends_cloud_pages_preserving_existing_navigation(qapp, tmp_path):
    from ui.main_window import MainWindow
    window = MainWindow(configuration_service=configuration(tmp_path))
    try:
        assert [window.nav_list.item(i).text() for i in range(7)] == [
            "Dashboard", "Folders", "Backups", "Scheduler", "Logs", "Settings", "About"]
        assert window.nav_list.item(7).text() == "Connections"
        assert window.nav_list.item(8).text() == "Cloud Sync"
        window.nav_list.setCurrentRow(7)
        assert isinstance(window.content_stack.currentWidget(), ConnectionsPage)
        window.nav_list.setCurrentRow(8)
        assert isinstance(window.content_stack.currentWidget(), CloudSyncPage)
    finally:
        window.prepare_for_exit()
        window.tray_icon.hide()
        window.hide()


class SetupClient:
    def __init__(self, owner, cancel_event):
        self.owner, self.cancel_event = owner, cancel_event
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def configure(self, connection, parameters, **kwargs):
        self.owner.remotes.add(connection.id)
        self.owner.calls.append(kwargs)
        response = self.owner.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response(self) if callable(response) else response
    def test(self, connection): pass
    def call(self, method, payload):
        assert method == "config/delete"
        if self.owner.delete_failures:
            self.owner.delete_failures -= 1
            raise CloudSyncError("Cleanup unavailable")
        self.owner.deleted.append(payload["name"])
        self.owner.remotes.discard(payload["name"][3:])
        return {}


class SetupFactory:
    def __init__(self, responses):
        self.responses, self.remotes, self.deleted, self.calls = responses, set(), [], []
        self.delete_failures = 0
    def __call__(self, *args, cancel_event=None, **kwargs):
        return SetupClient(self, cancel_event)


def setup_page(tmp_path, responses):
    config = configuration(tmp_path)
    factory = SetupFactory(responses)
    service = CloudService(config, transport_factory=factory)
    page = ConnectionsPage(config, service)
    service.setParent(page)
    page.provider_combo.setCurrentIndex(page.provider_combo.findData("onedrive"))
    page.name_edit.setText("Personal")
    page.root_edit.setText("EverySync")
    return config, factory, service, page


def test_guided_oauth_questions_keep_secrets_masked_and_save_only_after_completion(qapp, tmp_path):
    from PySide6.QtWidgets import QLineEdit
    config, factory, service, page = setup_page(tmp_path, [
        {"State": "browser", "Option": {"Help": "Open browser?", "Exclusive": True,
          "Examples": [{"Value": "true", "Help": "Use this computer"}]}},
        {"State": "secret", "Option": {"Help": "Authorization answer", "IsPassword": True,
          "Default": "private-default"}, "Error": "private-provider-token"}, {}])
    page.connect_button.click()
    spin(qapp, lambda: not service.busy)
    assert not config.get_app_config().connections
    assert page.answer_combo.currentData() == "true"
    page.continue_button.click()
    spin(qapp, lambda: not service.busy)
    assert page.answer_edit.echoMode() == QLineEdit.EchoMode.Password
    assert page.answer_edit.text() == ""
    assert "private-provider-token" not in page.question_label.text()
    page.answer_edit.setText("private-answer")
    page.continue_button.click()
    spin(qapp, lambda: not service.busy)
    assert len(config.get_app_config().connections) == 1
    assert factory.calls[-1] == {"state": "secret", "answer": "private-answer"}
    assert page.answer_edit.text() == ""
    assert "private-answer" not in (tmp_path / "config.json").read_text()


def test_cancel_pending_question_removes_only_pending_credentials(qapp, tmp_path):
    config, factory, service, page = setup_page(tmp_path, [
        {"State": "browser", "Option": {"Help": "Continue sign-in"}}])
    established = ConnectionConfig("existing", "Existing", "onedrive", "EverySync")
    config.save(replace(config.get_app_config(), connections=[established]))
    factory.remotes.add("existing")
    page.connect_button.click()
    spin(qapp, lambda: not service.busy)
    pending = page.pending.id
    page.cancel_button.click()
    spin(qapp, lambda: not service.busy)
    assert factory.remotes == {"existing"}
    assert factory.deleted == ["es_" + pending]
    assert config.get_app_config().connections == [established]


def test_cancel_finished_worker_before_gui_callback_cannot_save_connection(qapp, tmp_path):
    config, factory, service, page = setup_page(tmp_path, [{}])
    page.connect_button.click()
    service._task.wait()
    pending = page.pending.id
    page.cancel_button.click()
    spin(qapp, lambda: not service.busy)
    assert not config.get_app_config().connections
    assert factory.deleted == ["es_" + pending]


def test_exit_cleans_idle_pending_setup(qapp, tmp_path):
    config, factory, service, page = setup_page(tmp_path, [
        {"State": "browser", "Option": {"Help": "Continue sign-in"}}])
    page.connect_button.click()
    spin(qapp, lambda: not service.busy)
    service.wait_for_finished()
    assert not factory.remotes
    assert not config.get_app_config().connections


def test_exit_waits_for_active_restore_without_cancelling_it(qapp, tmp_path):
    service = CloudService(configuration(tmp_path))
    started = threading.Event()
    observed = []
    def restore(event):
        started.set()
        time.sleep(.03)
        observed.append(event.is_set())
    service._submit("restore", restore)
    assert started.wait(2)
    service.wait_for_finished()
    assert observed == [False]
    assert not service.busy


def test_exit_cancels_active_setup_and_discards_late_success(qapp, tmp_path):
    started = threading.Event()
    def blocked(client):
        started.set()
        assert client.cancel_event.wait(2)
        return {}
    config, factory, service, page = setup_page(tmp_path, [blocked])
    page.connect_button.click()
    assert started.wait(2)
    service.wait_for_finished()
    assert not service.busy
    assert not factory.remotes
    assert not config.get_app_config().connections
    assert page.pending is None


def test_failed_setup_cleans_credentials_and_allows_fresh_retry(qapp, tmp_path):
    config, factory, service, page = setup_page(tmp_path, [CloudSyncError("Authorization failed"), {}])
    page.connect_button.click()
    spin(qapp, lambda: not service.busy)
    assert not factory.remotes
    assert page.pending is None
    assert page.setup_group.isEnabled()
    page.connect_button.click()
    spin(qapp, lambda: not service.busy)
    assert len(config.get_app_config().connections) == 1


def test_failed_cleanup_keeps_cancel_retry_and_prevents_another_setup(qapp, tmp_path):
    config, factory, service, page = setup_page(tmp_path, [
        {"State": "browser", "Option": {"Help": "Continue sign-in"}}])
    page.connect_button.click()
    spin(qapp, lambda: not service.busy)
    factory.delete_failures = 1
    page.cancel_button.click()
    spin(qapp, lambda: not service.busy)
    assert page.pending is not None
    assert page.cancel_button.isEnabled()
    assert not page.setup_group.isEnabled()
    page.cancel_button.click()
    spin(qapp, lambda: not service.busy)
    assert page.pending is None
    assert not factory.remotes


def test_provider_guide_uses_fixed_official_oauth_walkthrough(qapp, tmp_path, monkeypatch):
    from PySide6.QtGui import QDesktopServices
    config, factory, service, page = setup_page(tmp_path, [])
    urls = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: urls.append(url.toString()))
    page.provider_combo.setCurrentIndex(page.provider_combo.findData("drive"))
    page.root_edit.setText("https://untrusted.invalid/")
    page.guide_button.click()
    assert urls == ["https://rclone.org/drive/#making-your-own-client-id"]


def test_pending_setup_exit_waits_for_sync_before_cleaning_credentials(qapp, tmp_path):
    config, factory, service, page = setup_page(tmp_path, [
        {"State": "browser", "Option": {"Help": "Continue sign-in"}}])
    page.connect_button.click()
    spin(qapp, lambda: not service.busy)
    class Sync:
        is_syncing = True
        def wait_for_finished(self): self.is_syncing = False
    service.sync_service = Sync()
    page.cancel_setup()
    assert page.pending is not None
    service.wait_for_finished()
    assert not factory.remotes
    assert not service.sync_service.is_syncing


def test_new_activity_can_reselect_previously_selected_activity(qapp, tmp_path):
    config = configuration(tmp_path)
    local, remote = tmp_path / "local", tmp_path / "remote"
    local.mkdir()
    remote.mkdir()
    connection = ConnectionConfig("nas", "NAS", "local", str(remote))
    job = RemoteJobConfig("saves", "Saved activity", str(local), "nas", "Game")
    config.save(replace(config.get_app_config(), connections=[connection], remote_jobs=[job]))
    service = CloudService(config)
    page = CloudSyncPage(config, service)
    service.setParent(page)
    page.job_list.setCurrentRow(0)
    assert page.editing_id == "saves"
    page.new_job()
    assert page.editing_id is None
    page.job_list.setCurrentRow(0)
    assert page.editing_id == "saves"
    assert page.name_edit.text() == "Saved activity"


def test_snapshot_dialog_keeps_its_original_activity(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QPushButton
    config = configuration(tmp_path)
    service = CloudService(config)
    page = CloudSyncPage(config, service)
    service.setParent(page)
    calls = []
    monkeypatch.setattr(service, "restore", lambda *args: calls.append(args))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(tmp_path))
    snapshot = {"run_id": "r_one", "created_at": "2026-10-18", "files": {}}
    page.snapshot_job = "first"
    page.completed("snapshots", [snapshot])
    first_dialog = page.snapshot_dialog
    page.snapshot_job = "second"
    page.completed("snapshots", [dict(snapshot, run_id="r_two")])
    first_dialog.findChild(QPushButton).click()
    assert calls == [("first", "r_one", str(tmp_path))]
