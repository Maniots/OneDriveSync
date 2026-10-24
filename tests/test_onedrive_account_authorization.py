"""Profile consent must preserve the existing storage connection until verified."""
from copy import deepcopy
from dataclasses import replace
import json
from unittest.mock import Mock

import pytest

from src.cloud_models import ConnectionConfig
from src.rclone_transport import CloudSyncError, RcloneTransport


@pytest.fixture
def authorization(tmp_path, monkeypatch):
    connection = ConnectionConfig("microsoft", "Work", "onedrive", "Apps/Saves")
    original = {"type": "onedrive", "drive_id": "existing-drive", "drive_type": "business",
                "client_id": "custom-app", "client_secret": "obscured-secret",
                "token": json.dumps({"access_token": "old-token"}),
                "access_scopes": "Files.ReadWrite.All offline_access"}
    remotes = {"es_microsoft": deepcopy(original)}
    calls = []
    client = RcloneTransport(tmp_path, executable=tmp_path / "unused")

    def call(method, payload, **kwargs):
        calls.append((method, deepcopy(payload)))
        name = payload["name"]
        if method == "config/get":
            return deepcopy(remotes[name])
        if method == "config/delete":
            del remotes[name]
            return {}
        assert method in {"config/create", "config/update"}
        if method == "config/create":
            assert name != "es_microsoft"
            assert "token" not in payload["parameters"]
            assert payload["parameters"]["client_secret"] == "obscured-secret"
            assert payload["opt"]["noObscure"] is True
            remotes[name] = {"type": "onedrive", **payload["parameters"],
                             "token": json.dumps({"access_token": "new-token"})}
        else:
            assert name == "es_microsoft"
            assert list(remotes) == ["es_microsoft"], "Temporary credentials must be removed first"
            assert set(payload["parameters"]) <= {
                "token", "access_scopes", "disable_site_permission", "config_refresh_token"}
            assert payload["parameters"]["config_refresh_token"] == "false"
            remotes[name].update({k: v for k, v in payload["parameters"].items()
                                  if not k.startswith("config_")})
        return {"State": "choose_type_done", "Option": {"Name": "config_type"}}

    client.call = call
    client.operation = call
    def account_info(staged):
        assert staged.id != connection.id and staged.root == connection.root
        assert remotes["es_" + staged.id]["drive_id"] == original["drive_id"]
        return {"name": "Signed-in User", "email": "user@example.test"}
    client.account_info = Mock(side_effect=account_info)
    client.test = Mock()
    return client, connection, remotes, original, calls


def test_new_onedrive_sign_in_requests_profile_access_without_changing_drive_probes(tmp_path):
    client = RcloneTransport(tmp_path, executable=tmp_path / "unused")
    client.operation = Mock(return_value={})
    client.configure(ConnectionConfig("new", "Microsoft", "onedrive", "Apps"), {})
    parameters = client.operation.call_args.args[1]["parameters"]
    assert "User.Read" in parameters["access_scopes"].split()
    assert "Files.ReadWrite.All" in parameters["access_scopes"].split()


def test_consent_replaces_only_verified_token_and_scopes(authorization):
    client, connection, remotes, original, calls = authorization
    assert client.authorize_account_identity(connection) == {
        "name": "Signed-in User", "email": "user@example.test"}
    saved = remotes["es_microsoft"]
    assert json.loads(saved["token"])["access_token"] == "new-token"
    assert saved["access_scopes"].split() == ["Files.ReadWrite.All", "offline_access", "User.Read"]
    for key in ("drive_id", "drive_type", "client_id", "client_secret"):
        assert saved[key] == original[key]
    assert list(remotes) == ["es_microsoft"]
    assert client.test.call_args.args[0].root == connection.root


@pytest.mark.parametrize("failure", ["denied", "profile", "empty", "root", "cancel", "cleanup"])
def test_failed_or_cancelled_consent_preserves_saved_credentials(authorization, failure):
    client, connection, remotes, original, calls = authorization
    if failure == "profile":
        client.account_info.side_effect = CloudSyncError("Profile unavailable")
    elif failure == "empty":
        client.account_info.side_effect = None
        client.account_info.return_value = {}
    elif failure == "root":
        client.test.side_effect = CloudSyncError("Folder unavailable; sign in with the correct account")
    elif failure == "cancel":
        def cancel(staged):
            client.cancel_event.set()
            return {"name": "Cancelled"}
        client.account_info.side_effect = cancel
    elif failure == "cleanup":
        original_call = client.call
        def cleanup_error(method, payload, **kwargs):
            if method == "config/delete":
                raise CloudSyncError("Cleanup unavailable")
            return original_call(method, payload, **kwargs)
        client.call = cleanup_error
    else:
        original_operation = client.operation
        def denied(method, payload):
            original_operation(method, payload)
            return {"State": "private", "Error": "private-provider-error"}
        client.operation = denied
    with pytest.raises(CloudSyncError) as caught:
        client.authorize_account_identity(connection)
    assert "private" not in str(caught.value)
    assert remotes["es_microsoft"] == original
    if failure != "cleanup":
        assert list(remotes) == ["es_microsoft"]


def test_site_permission_opt_out_keeps_profile_scope_without_adding_sites(authorization):
    client, connection, remotes, original, calls = authorization
    remotes["es_microsoft"].pop("access_scopes")
    remotes["es_microsoft"]["disable_site_permission"] = "true"
    client.authorize_account_identity(connection)
    saved = remotes["es_microsoft"]
    assert saved["disable_site_permission"] == "false"
    assert "Sites.Read.All" not in saved["access_scopes"].split()
    assert "User.Read" in saved["access_scopes"].split()


@pytest.mark.parametrize("invalid", ["provider", "id", "drive", "region"])
def test_invalid_authorization_never_starts_browser(authorization, invalid):
    client, connection, remotes, original, calls = authorization
    if invalid == "provider":
        connection = replace(connection, provider="drive")
    elif invalid == "id":
        from types import SimpleNamespace
        connection = SimpleNamespace(id="foreign:remote", provider="onedrive")
    elif invalid == "drive":
        remotes["es_microsoft"].pop("drive_id")
    else:
        remotes["es_microsoft"]["region"] = "us"
    with pytest.raises(CloudSyncError):
        client.authorize_account_identity(connection)
    assert not any(method == "config/create" for method, _ in calls)


def test_real_engine_requests_profile_scope_and_cancels_without_changing_saved_remote(tmp_path):
    """Inspect only a local redirect; no browser or Microsoft request is made."""
    from contextlib import closing
    from http.client import HTTPConnection
    import threading
    import time
    from urllib.parse import parse_qs, urlsplit

    from src.cloud_credentials import CredentialStore
    from src.rclone_transport import rclone_executable

    try:
        executable = rclone_executable()
    except CloudSyncError:
        pytest.skip("The pinned rclone engine is not installed")
    credentials = CredentialStore(tmp_path, protect=lambda data: data, unprotect=lambda data: data)
    connection = ConnectionConfig("microsoft", "Microsoft", "onedrive", "Apps")
    original = {"drive_id": "fixture-drive", "drive_type": "personal",
                "token": json.dumps({"access_token": "fixture-old-token", "token_type": "Bearer",
                                     "expiry": "2099-01-01T00:00:00Z"}),
                "access_scopes": "Files.ReadWrite.All offline_access"}
    with RcloneTransport(tmp_path, executable=executable, credentials=credentials) as client:
        result = client.call("config/create", {"name": "es_microsoft", "type": "onedrive",
            "parameters": dict(original, config_refresh_token="false"),
            "opt": {"nonInteractive": True}})
        assert result["Option"]["Name"] == "config_type"
        saved = client.call("config/get", {"name": "es_microsoft"})
        operation = client.operation
        staged_names = []
        def no_browser(method, payload):
            if method == "config/create":
                payload["parameters"]["config_auth_no_browser"] = "true"
                staged_names.append(payload["name"])
            return operation(method, payload)
        client.operation = no_browser
        errors = []
        def authorize():
            try:
                client.authorize_account_identity(connection)
            except CloudSyncError as error:
                errors.append(str(error))
        thread = threading.Thread(target=authorize)
        thread.start()
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                status = client.call("config/oauthstatus", {})
                if status["status"] == "running":
                    break
                time.sleep(.02)
            assert status["status"] == "running"
            local = urlsplit(status["authUrl"])
            assert local.hostname == "127.0.0.1"
            with closing(HTTPConnection(local.hostname, local.port, timeout=2)) as http:
                http.request("GET", local.path + "?" + local.query)
                response = http.getresponse()
                assert response.status in {302, 307}
                target = urlsplit(response.getheader("Location"))
                assert target.hostname == "login.microsoftonline.com"
                scopes = parse_qs(target.query)["scope"][0].split()
                assert set(scopes) == {"Files.ReadWrite.All", "offline_access", "User.Read"}
        finally:
            client.cancel_event.set()
            thread.join(5)
        assert not thread.is_alive()
        assert errors and "cancel" in errors[0].lower()
        assert client.call("config/get", {"name": "es_microsoft"}) == saved
        assert client.call("config/get", {"name": staged_names[0]}) == {}
        assert client.call("config/oauthstatus", {})["status"] == "stopped"
        encrypted = (tmp_path / "rclone.conf").read_bytes()
        assert b"RCLONE_ENCRYPT_V0:" in encrypted and b"fixture-old-token" not in encrypted

        # Exercise actual rclone persistence after a synthetic completed login.
        # Cloud access/profile calls remain mocked; no real token is used.
        client.cancel_event.clear()
        new_token = json.dumps({"access_token": "fixture-new-token", "token_type": "Bearer",
                                "expiry": "2099-01-01T00:00:00Z"})
        def completed_login(method, payload):
            payload["parameters"].update(token=new_token, config_refresh_token="false")
            return operation(method, payload)
        client.operation = completed_login
        client.test = Mock()
        client.account_info = Mock(return_value={"name": "Verified caller"})
        assert client.authorize_account_identity(connection) == {"name": "Verified caller"}
        updated = client.call("config/get", {"name": "es_microsoft"})
        assert updated["token"] == new_token
        assert updated["drive_id"] == saved["drive_id"]
        assert updated["drive_type"] == saved["drive_type"]
        assert updated["access_scopes"].split() == ["Files.ReadWrite.All", "offline_access", "User.Read"]
        assert client.call("config/oauthstatus", {})["status"] == "stopped"
