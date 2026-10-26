"""Connected-account details must be real, asynchronous and distinct from folders."""
from dataclasses import replace
import json
import threading

import pytest
from PySide6.QtCore import Qt

from backend.services.cloud_service import CloudService
from src.cloud_models import ConnectionConfig, RemoteJobConfig
from src.rclone_transport import CloudSyncError
from tests.test_cloud_ui import configuration, spin
from ui.pages.connections import ConnectionsPage


@pytest.fixture
def accounts(qapp, tmp_path):
    config = configuration(tmp_path)
    google = ConnectionConfig("google", "Google Drive", "drive", "EverySync")
    microsoft = ConnectionConfig("microsoft", "Work", "onedrive", "Apps")
    config.save(replace(config.get_app_config(), connections=[google, microsoft]))
    calls = []
    profiles = {"google": {"name": "Sample Player", "email": "player@example.test"},
                "microsoft": {"name": "Sample Work Account"}}
    class Client:
        def __init__(self, event): self.event = event
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def test(self, connection): pass
        def account_info(self, connection):
            calls.append(connection.id)
            value = profiles[connection.id]
            if isinstance(value, Exception): raise value
            return value(self) if callable(value) else value
    service = CloudService(config, transport_factory=lambda *a, cancel_event=None, **k: Client(cancel_event), parent=qapp)
    yield config, service, calls, profiles, google, microsoft
    service.wait_for_finished()


def test_existing_accounts_load_without_configuration_changes_and_are_cached(accounts, qapp, tmp_path):
    config, service, calls, _, _, _ = accounts
    before = (tmp_path / "config.json").read_bytes()
    assert service.refresh_account_identities()
    spin(qapp, lambda: not service.busy)
    assert service.account_identities["google"] == {
        "name": "Sample Player", "email": "player@example.test", "status": "available"}
    assert service.account_identities["microsoft"]["name"] == "Sample Work Account"
    assert "email" not in service.account_identities["microsoft"]
    assert not service.refresh_account_identities()
    assert calls == ["google", "microsoft"]
    assert (tmp_path / "config.json").read_bytes() == before


def test_unavailable_identity_does_not_hide_other_accounts(accounts, qapp):
    config, service, calls, profiles, google, microsoft = accounts
    profiles["google"] = CloudSyncError("Profile unavailable")
    service.refresh_account_identities()
    spin(qapp, lambda: not service.busy)
    assert service.account_identities["google"] == {"status": "unavailable"}
    assert service.account_identities["microsoft"]["status"] == "available"
    assert config.get_app_config().connections == [google, microsoft]


def test_verification_retries_identity_without_changing_its_completed_payload(accounts, qapp):
    _, service, calls, profiles, google, _ = accounts
    profiles["google"] = CloudSyncError("Profile unavailable")
    completed, errors = [], []
    service.completed.connect(lambda *args: completed.append(args))
    service.failed.connect(errors.append)
    service.test_connection(google)
    spin(qapp, lambda: not service.busy)
    assert completed == [("test", "google")]
    assert not errors
    assert service.account_identities["google"]["status"] == "unavailable"
    profiles["google"] = {"email": "retry@example.test"}
    service.test_connection(google)
    spin(qapp, lambda: not service.busy)
    assert service.account_identities["google"]["email"] == "retry@example.test"
    assert calls == ["google", "google"]


def test_explicit_microsoft_consent_updates_account_without_rewriting_configuration(accounts, qapp, tmp_path):
    config, service, _, _, _, microsoft = accounts
    local = tmp_path / "saves"
    local.mkdir()
    job = RemoteJobConfig("saves", "Game saves", str(local), microsoft.id, "Game")
    config.save(replace(config.get_app_config(), remote_jobs=[job]))
    client = service.transport_factory()
    client.authorize_account_identity = lambda connection: {"name": "Microsoft User", "email": "ms@example.test"}
    service.transport_factory = lambda *a, **k: client
    before = (tmp_path / "config.json").read_bytes()
    completed = []
    service.completed.connect(lambda *args: completed.append(args))
    service.authorize_account_identity(microsoft)
    spin(qapp, lambda: not service.busy)
    assert completed == [("authorize_account", microsoft.id)]
    assert service.account_identities[microsoft.id] == {
        "status": "available", "name": "Microsoft User", "email": "ms@example.test"}
    assert (tmp_path / "config.json").read_bytes() == before
    assert config.get_app_config().remote_jobs == [job]


def test_microsoft_consent_action_is_selected_explicit_and_cancellable(accounts, qapp):
    config, service, calls, _, google, microsoft = accounts
    entered = threading.Event()
    def authorize(connection):
        entered.set()
        assert service._task.cancel_event.wait(3)
        raise CloudSyncError("Account operation cancelled.")
    client = service.transport_factory()
    client.authorize_account_identity = authorize
    service.transport_factory = lambda *a, **k: client
    page = ConnectionsPage(config, service)
    assert page.authorize_button.isHidden()
    page.connection_table.selectRow(0)
    assert page.authorize_button.isHidden()
    page.connection_table.selectRow(1)
    assert not page.authorize_button.isHidden()
    page.authorize_button.click()
    assert entered.wait(2)
    assert "browser" in page.status_label.text().lower()
    assert not page.authorize_button.isEnabled()
    assert page.cancel_button.isEnabled()
    page.cancel_button.click()
    spin(qapp, lambda: not service.busy)
    assert config.get_app_config().connections == [google, microsoft]
    assert "cancel" in page.status_label.text().lower()
    assert page.authorize_button.isEnabled()
    assert not calls


def test_profile_consent_rejects_foreign_or_unsupported_connection(accounts):
    _, service, _, _, google, microsoft = accounts
    for connection in (google, replace(microsoft, root="Other"), replace(microsoft, id="unknown")):
        with pytest.raises(ValueError):
            service.authorize_account_identity(connection)
    assert not service.busy


def test_consent_success_is_rendered_in_selected_account_row(accounts, qapp):
    config, service, _, _, _, microsoft = accounts
    client = service.transport_factory()
    client.authorize_account_identity = lambda connection: {"name": "Microsoft User", "email": "ms@example.test"}
    service.transport_factory = lambda *a, **k: client
    page = ConnectionsPage(config, service)
    page.connection_table.selectRow(1)
    page.authorize_button.click()
    spin(qapp, lambda: not service.busy)
    assert page.selected() == microsoft
    assert page.connection_table.item(1, 1).text() == "ms@example.test\nMicrosoft User"
    assert "updated" in page.status_label.text().lower()
    assert not page.cancel_button.isEnabled()


def test_consent_failure_retains_cached_account_and_can_retry(accounts, qapp):
    _, service, _, _, _, microsoft = accounts
    before = {"status": "available", "name": "Previous account"}
    service.account_identities[microsoft.id] = dict(before)
    client = service.transport_factory()
    def denied(connection):
        raise CloudSyncError("Microsoft sign-in was denied. Retry to allow profile access.")
    client.authorize_account_identity = denied
    service.transport_factory = lambda *a, **k: client
    errors = []
    service.failed.connect(errors.append)
    service.authorize_account_identity(microsoft)
    spin(qapp, lambda: not service.busy)
    assert errors and service.account_identities[microsoft.id] == before
    client.authorize_account_identity = lambda connection: {"name": "Verified account"}
    service.authorize_account_identity(microsoft)
    spin(qapp, lambda: not service.busy)
    assert service.account_identities[microsoft.id]["name"] == "Verified account"


def test_removed_connection_does_not_get_a_late_identity(accounts, qapp):
    config, service, _, profiles, _, microsoft = accounts
    entered, release = threading.Event(), threading.Event()
    def blocked(client):
        entered.set()
        assert release.wait(3)
        return {"email": "late@example.test"}
    profiles["google"] = blocked
    try:
        service.refresh_account_identities()
        assert entered.wait(2)
        config.save(replace(config.get_app_config(), connections=[microsoft]))
    finally:
        release.set()
    spin(qapp, lambda: not service.busy)
    assert "google" not in service.account_identities


def test_cancelled_identity_is_discarded(accounts, qapp):
    _, service, _, profiles, _, _ = accounts
    entered = threading.Event()
    def blocked(client):
        entered.set()
        assert client.event.wait(3)
        return {"email": "cancelled@example.test"}
    profiles["google"] = blocked
    service.refresh_account_identities()
    assert entered.wait(2)
    service.cancel()
    spin(qapp, lambda: not service.busy)
    assert not service.account_identities


def test_cancelled_failure_preserves_previously_loaded_identity(accounts, qapp):
    _, service, _, profiles, _, _ = accounts
    before = {"google": {"email": "saved@example.test", "status": "available"}}
    service.account_identities = dict(before)
    def cancelled_failure(client):
        client.event.set()
        raise RuntimeError("simulated worker failure while exiting")
    profiles["google"] = cancelled_failure
    service.refresh_account_identities(force=True)
    spin(qapp, lambda: not service.busy)
    assert service.account_identities == before


def test_exit_prevents_queued_background_identity_requests(accounts, qapp):
    _, service, calls, _, _, _ = accounts
    service.wait_for_finished()
    started = service.refresh_account_identities()
    if started:
        spin(qapp, lambda: not service.busy)
    assert not started
    assert not calls


def test_table_separates_account_from_service_and_folder_and_keeps_selection(accounts):
    config, service, _, _, google, _ = accounts
    service.account_identities = {"google": {"email": "player@example.test", "status": "available"},
                                  "microsoft": {"status": "unavailable"}}
    page = ConnectionsPage(config, service)
    table = page.connection_table
    assert [table.horizontalHeaderItem(i).text() for i in range(3)] == [
        "Service", "Connected account", "Cloud folder"]
    assert table.item(0, 0).text() == "Google Drive"
    assert table.item(0, 1).text() == "player@example.test"
    assert table.item(0, 2).text() == "EverySync"
    assert "unavailable" in table.item(1, 1).text().lower()
    assert not page.test_button.isEnabled() and not page.remove_button.isEnabled()
    table.selectRow(0)
    assert page.selected() == google
    assert page.test_button.isEnabled() and page.remove_button.isEnabled()
    page.refresh()
    assert page.selected() == google
    assert table.item(0, 0).data(Qt.ItemDataRole.UserRole) == google.id
    assert "synchronizations" in page.folder_explanation.text().lower()
    assert page.test_button.text() == "Verify access"
    assert page.remove_button.text() == "Disconnect account"
    table.clearSelection()
    assert page.selected() is None
    assert not page.test_button.isEnabled() and not page.remove_button.isEnabled()


def test_visible_page_loads_existing_accounts_once_without_stalling_gui(accounts, qapp):
    config, service, calls, profiles, _, _ = accounts
    entered, release = threading.Event(), threading.Event()
    def blocked(client):
        entered.set()
        assert release.wait(3)
        return {"email": "loaded@example.test"}
    profiles["google"] = blocked
    page = ConnectionsPage(config, service)
    try:
        page.show()
        spin(qapp, entered.is_set)
        assert "loading" in page.connection_table.item(0, 1).text().lower()
        page.refresh()
        assert page.connection_table.rowCount() == 2
    finally:
        release.set()
    spin(qapp, lambda: "loaded@example.test" in page.connection_table.item(0, 1).text())
    page.refresh()
    qapp.processEvents()
    assert calls == ["google", "microsoft"]
    page.hide()


def test_failed_background_request_stops_showing_loading_and_keeps_selection(accounts, qapp):
    config, service, calls, profiles, _, microsoft = accounts
    profiles["google"] = RuntimeError("simulated worker failure")
    page = ConnectionsPage(config, service)
    page.connection_table.selectRow(1)
    page.show()
    spin(qapp, lambda: bool(calls) and not service.busy)
    assert "unavailable" in page.connection_table.item(0, 1).text().lower()
    assert page.selected() == microsoft
    qapp.processEvents()
    assert calls == ["google"]
    assert page.test_button.isEnabled()
    page.hide()


def test_local_storage_has_no_cloud_identity_and_empty_state_is_explicit(qapp, tmp_path):
    config = configuration(tmp_path)
    def no_client(*a, **k): raise AssertionError("Local storage must not request an account profile")
    service = CloudService(config, transport_factory=no_client, parent=qapp)
    page = ConnectionsPage(config, service)
    assert "no accounts" in page.empty_accounts_label.text().lower()
    assert page.connection_table.rowCount() == 0
    root = tmp_path / "nas"
    root.mkdir()
    local = ConnectionConfig("nas", "Home NAS", "local", str(root))
    config.save(replace(config.get_app_config(), connections=[local]))
    page.refresh()
    assert "no cloud account" in page.connection_table.item(0, 1).text().lower()
    assert not service.refresh_account_identities()


@pytest.mark.parametrize("confirmed", [True, False])
def test_disconnect_confirmation_cannot_start_background_account_loading(accounts, qapp, confirmed):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QMessageBox

    config, service, _, profiles, google, microsoft = accounts
    release = threading.Event()
    deleted = []
    factory = service.transport_factory

    def client_factory(*args, **kwargs):
        client = factory(*args, **kwargs)
        client.call = lambda method, payload: deleted.append((method, payload)) or {}
        return client

    def blocked(client):
        release.wait(3)
        return {"email": "loaded@example.test"}

    service.transport_factory = client_factory
    profiles[google.id] = blocked
    page = ConnectionsPage(config, service)
    page.connection_table.selectRow(0)
    page.show()

    def confirm():
        dialog = qapp.activeModalWidget()
        assert isinstance(dialog, QMessageBox)
        dialog.button(QMessageBox.StandardButton.Yes if confirmed else QMessageBox.StandardButton.No).click()

    QTimer.singleShot(40, confirm)
    try:
        page.remove_button.click()
    finally:
        release.set()
    spin(qapp, lambda: not service.busy)
    if not confirmed:
        assert config.get_app_config().connections == [google, microsoft]
        assert not deleted
        assert page.connection_table.rowCount() == 2
        assert page.selected_id() == google.id
        assert page.remove_button.isEnabled()
        return
    assert config.get_app_config().connections == [microsoft]
    assert deleted == [("config/delete", {"name": "es_google"})]
    assert page.connection_table.rowCount() == 1
    assert page.connection_table.item(0, 0).data(Qt.ItemDataRole.UserRole) == microsoft.id
    assert google.id not in service.account_identities
    assert page.selected_id() is None
    assert not page.remove_button.isEnabled()


def test_reload_accounts_reads_saved_connections_and_retries_cached_profiles(accounts, qapp, tmp_path):
    config, service, calls, profiles, google, microsoft = accounts
    profiles[google.id] = CloudSyncError("Profile temporarily unavailable")
    service.refresh_account_identities()
    spin(qapp, lambda: not service.busy)
    page = ConnectionsPage(config, service)
    page.connection_table.selectRow(0)
    assert "unavailable" in page.connection_table.item(0, 1).text().lower()

    path = tmp_path / "config.json"
    saved = json.loads(path.read_text())
    saved["connections"][0]["root"] = "Changed/EverySync"
    path.write_text(json.dumps(saved))
    profiles[google.id] = {"email": "reloaded@example.test"}

    page.refresh_button.click()
    spin(qapp, lambda: not service.busy)
    assert page.connection_table.item(0, 1).text() == "reloaded@example.test"
    assert page.connection_table.item(0, 2).text() == "Changed/EverySync"
    assert page.selected_id() == google.id
    assert calls == [google.id, microsoft.id, google.id, microsoft.id]
    assert page.refresh_button.isEnabled()
    assert "updated" in page.status_label.text().lower()


def test_reload_failure_keeps_accounts_visible_and_allows_retry(accounts, qapp, tmp_path):
    config, service, calls, _, google, microsoft = accounts
    page = ConnectionsPage(config, service)
    page.connection_table.selectRow(0)
    path = tmp_path / "config.json"
    saved = path.read_bytes()
    previous = config.get_app_config()
    path.write_text("{")

    page.refresh_button.click()
    assert config.get_app_config() is previous
    assert page.connection_table.rowCount() == 2
    assert page.selected_id() == google.id
    assert "not valid JSON" in page.status_label.text()
    assert not service.busy
    assert not calls
    assert page.refresh_button.isEnabled()

    path.write_bytes(saved)
    page.refresh_button.click()
    spin(qapp, lambda: not service.busy)
    assert calls == [google.id, microsoft.id]
    assert page.selected_id() == google.id


@pytest.mark.parametrize("action", ["test", "authorize_account"])
def test_account_actions_update_synchronization_table_immediately(accounts, qapp, tmp_path, action):
    from ui.pages.synchronizations import SynchronizationsPage

    config, service, _, profiles, _, microsoft = accounts
    job = RemoteJobConfig("saves", "Game saves", str(tmp_path), microsoft.id, "Game")
    config.save(replace(config.get_app_config(), remote_jobs=[job]))
    page = SynchronizationsPage(config, service)
    assert "Work" in page.destination_table.cellWidget(0, 0).text()
    profiles[microsoft.id] = {"email": "updated@example.test"}
    if action == "test":
        service.test_connection(microsoft)
    else:
        client = service.transport_factory()
        client.authorize_account_identity = lambda connection: profiles[connection.id]
        service.transport_factory = lambda *args, **kwargs: client
        service.authorize_account_identity(microsoft)
    spin(qapp, lambda: not service.busy)
    assert "updated@example.test" in page.destination_table.cellWidget(0, 0).text()
