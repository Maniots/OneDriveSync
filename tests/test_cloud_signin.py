"""Integrated account login must not publish a connection before folder choice."""
from dataclasses import replace

import pytest

from src.cloud_models import ConnectionConfig
from src.rclone_transport import CloudSyncError, RcloneTransport
from tests.test_cloud_ui import configuration, spin, SetupFactory
from backend.services.cloud_service import CloudService
from ui.pages.connections import ConnectionsPage


def test_browser_question_is_automatic_but_drive_choice_is_explicit(qapp, tmp_path):
    factory = SetupFactory([
        {"State": "local", "Option": {"Name": "config_is_local", "Default": True}},
        {"State": "drive", "Option": {"Name": "config_driveid", "Help": "Choose your drive"}},
    ])
    service = CloudService(configuration(tmp_path), transport_factory=factory, parent=qapp)
    completed = []
    service.completed.connect(lambda action, value: completed.append(value))
    service.configure_connection(ConnectionConfig("account", "Account", "onedrive", "EverySync"), {})
    spin(qapp, lambda: not service.busy)
    assert len(factory.calls) == 2
    assert factory.calls[1] == {"state": "local", "answer": "true"}
    assert completed[0]["question"]["Option"]["Name"] == "config_driveid"
    service.wait_for_finished()


def test_authorized_account_waits_for_root_choice_and_cancel_preserves_existing(qapp, tmp_path):
    config = configuration(tmp_path)
    existing = ConnectionConfig("existing", "Existing", "dropbox", "EverySync")
    config.save(replace(config.get_app_config(), connections=[existing]))
    factory = SetupFactory([{}])
    service = CloudService(config, transport_factory=factory, parent=qapp)
    completed = []
    service.completed.connect(lambda action, value: completed.append(value))
    pending = ConnectionConfig("pending", "Pending", "onedrive", "EverySync")
    service.configure_connection(pending, {}, choose_root=True)
    spin(qapp, lambda: not service.busy)
    assert config.get_app_config().connections == [existing]
    assert completed[0]["choose_root"] is True
    service.cancel()
    spin(qapp, lambda: not service.busy)
    assert factory.deleted == ["es_pending"]
    assert config.get_app_config().connections == [existing]


def test_selected_root_is_verified_before_publishing(qapp, tmp_path):
    config = configuration(tmp_path)
    factory = SetupFactory([{}])
    service = CloudService(config, transport_factory=factory, parent=qapp)
    service.configure_connection(ConnectionConfig("account", "Account", "onedrive", "EverySync"), {}, choose_root=True)
    spin(qapp, lambda: not service.busy)
    service.choose_connection_root("Saves/MyGame")
    spin(qapp, lambda: not service.busy)
    assert config.get_app_config().connections[0].root == "Saves/MyGame"
    assert service.pending_connection is None


def test_folder_listing_rejects_remote_path_injection(tmp_path, monkeypatch):
    client = RcloneTransport(tmp_path, executable=tmp_path / "unused")
    calls = []
    monkeypatch.setattr(client, "operation", lambda *args: calls.append(args) or {"list": []})
    account = ConnectionConfig("account", "Account", "onedrive", "EverySync")
    with pytest.raises(ValueError):
        client.folders(account, "../other:root")
    assert not calls


def test_internal_google_import_does_not_open_normal_token_options(tmp_path, monkeypatch):
    client = RcloneTransport(tmp_path, executable=tmp_path / "unused")
    calls = []
    monkeypatch.setattr(client, "operation", lambda *args: calls.append(args) or {})
    account = ConnectionConfig("account", "Account", "drive", "EverySync")
    client.configure_google(account, {"client_id": "desktop.apps.googleusercontent.com", "client_secret": "desktop"},
                            {"access_token": "private", "refresh_token": "refresh", "expiry": "2027-01-01T00:00:00Z", "token_type": "Bearer"})
    assert calls[0][1]["parameters"]["client_id"] == "desktop.apps.googleusercontent.com"
    assert '"refresh_token": "refresh"' in calls[0][1]["parameters"]["token"]
    with pytest.raises(CloudSyncError, match="option"):
        client.configure(account, {"token": "private"})


def test_oauth_page_signs_in_then_browses_and_saves_folder(qapp, tmp_path):
    config = configuration(tmp_path)
    factory = SetupFactory([{}])
    service = CloudService(config, transport_factory=factory)
    page = ConnectionsPage(config, service)
    service.setParent(page)
    page.provider_combo.setCurrentIndex(page.provider_combo.findData("onedrive"))
    assert page.connect_button.text() == "Sign in with Microsoft"
    assert page.options_widget.isHidden()
    assert page.root_controls.isHidden()
    page.connect_button.click()
    spin(qapp, lambda: not service.busy)
    assert not config.get_app_config().connections
    assert not page.folder_group.isHidden()
    assert page.folder_list.count() == 2
    page.folder_list.setCurrentRow(1)
    assert page.cloud_root_edit.text() == "Settings"
    page.open_cloud_folder(page.folder_list.item(0))
    spin(qapp, lambda: not service.busy)
    assert page.cloud_root_edit.text() == "Games"
    page.save_root_button.click()
    spin(qapp, lambda: not service.busy)
    assert config.get_app_config().connections[0].root == "Games/EverySync"
    assert config.get_app_config().connections[0].name == "OneDrive online"
    assert page.folder_group.isHidden()


def test_google_without_app_does_not_start_remote_setup(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr("src.cloud_oauth.load_oauth_apps", lambda: {})
    monkeypatch.setattr("ui.pages.connections.load_oauth_apps", lambda: {})
    config = configuration(tmp_path)
    factory = SetupFactory([])
    service = CloudService(config, transport_factory=factory)
    page = ConnectionsPage(config, service)
    service.setParent(page)
    page.provider_combo.setCurrentIndex(page.provider_combo.findData("drive"))
    assert not page.connect_button.isEnabled()
    assert "not available" in page.provider_hint.text()
    page.advanced_button.click()
    page.option_inputs["client_id"].setText("desktop.apps.googleusercontent.com")
    page.option_inputs["client_secret"].setText("desktop")
    assert page.connect_button.isEnabled()
    assert not factory.calls


def test_google_bundled_app_signs_in_without_manual_credentials(qapp, tmp_path, monkeypatch):
    from tests.test_cloud_ui import SetupClient
    apps = {"drive": {"client_id": "desktop.apps.googleusercontent.com", "client_secret": "public-desktop"}}
    monkeypatch.setattr("src.cloud_oauth.load_oauth_apps", lambda: apps)
    monkeypatch.setattr("ui.pages.connections.load_oauth_apps", lambda: apps)
    token = {"access_token": "private-access", "refresh_token": "private-refresh", "token_type": "Bearer", "expiry": "2099-01-01T00:00:00Z"}
    observed = []
    def login(parameters, cancel_event):
        assert not cancel_event.is_set()
        observed.append(parameters)
        return token
    monkeypatch.setattr("src.cloud_oauth.google_login", login)
    class Client(SetupClient):
        def configure_google(self, connection, parameters, received_token):
            assert parameters == apps["drive"] and received_token == token
            self.owner.remotes.add(connection.id)
            return {}
    config = configuration(tmp_path)
    factory = SetupFactory([])
    service = CloudService(config, transport_factory=lambda *args, cancel_event=None, **kwargs: Client(factory, cancel_event))
    page = ConnectionsPage(config, service)
    service.setParent(page)
    page.provider_combo.setCurrentIndex(page.provider_combo.findData("drive"))
    assert page.connect_button.text() == "Sign in with Google"
    assert page.connect_button.isEnabled() and page.options_widget.isHidden()
    assert all(not edit.text() for edit in page.option_inputs.values())
    page.connect_button.click()
    spin(qapp, lambda: not service.busy)
    assert observed == [apps["drive"]]
    assert not config.get_app_config().connections
    assert not page.folder_group.isHidden()
    page.save_root_button.click()
    spin(qapp, lambda: not service.busy)
    assert config.get_app_config().connections[0].provider == "drive"
    assert "private-access" not in (tmp_path / "config.json").read_text()
    assert "private-refresh" not in (tmp_path / "config.json").read_text()


def test_root_verification_failure_keeps_authorized_account_for_retry(qapp, tmp_path):
    from tests.test_cloud_ui import SetupClient
    class Client(SetupClient):
        def test(self, connection):
            if connection.root == "Denied":
                raise CloudSyncError("Access denied. Choose another folder.")
    factory = SetupFactory([{}])
    service = CloudService(configuration(tmp_path), transport_factory=lambda *args, cancel_event=None, **kw: Client(factory, cancel_event), parent=qapp)
    service.configure_connection(ConnectionConfig("account", "Account", "onedrive", "EverySync"), {}, choose_root=True)
    spin(qapp, lambda: not service.busy)
    service.choose_connection_root("Denied")
    spin(qapp, lambda: not service.busy)
    assert service.pending_connection is not None
    service.choose_connection_root("Allowed")
    spin(qapp, lambda: not service.busy)
    assert service.config_service.get_app_config().connections[0].root == "Allowed"


def test_late_finished_signal_without_sender_is_ignored(qapp, tmp_path):
    service = CloudService(configuration(tmp_path), parent=qapp)
    service._completed()
    assert not service.busy


def test_local_folder_does_not_leak_into_oauth_root(qapp, tmp_path):
    config = configuration(tmp_path)
    factory = SetupFactory([{}])
    service = CloudService(config, transport_factory=factory)
    page = ConnectionsPage(config, service)
    service.setParent(page)
    page.root_edit.setText(str(tmp_path))
    page.provider_combo.setCurrentIndex(page.provider_combo.findData("onedrive"))
    page.connect_button.click()
    spin(qapp, lambda: not service.busy)
    assert service.pending_connection is not None
    assert page.cloud_root_edit.text() == "EverySync"
    assert not page.test_button.isEnabled()
    assert not page.remove_button.isEnabled()
    with pytest.raises(ValueError, match="Finish"):
        service.test_connection(ConnectionConfig("existing", "Existing", "onedrive", "EverySync"))
    service.wait_for_finished()
