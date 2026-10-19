import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.cloud_models import ConnectionConfig
from src.rclone_transport import CloudSyncError, RcloneTransport


def test_account_info_refreshes_existing_remote_before_reading_profile(tmp_path, monkeypatch):
    client = RcloneTransport(tmp_path, executable=tmp_path / "unused")
    connection = ConnectionConfig("google", "Google", "drive", "EverySync")
    client.call = Mock(side_effect=[{"item": {"IsDir": True}}, {
        "type": "drive", "token": json.dumps({"access_token": "fixture-token"})}])
    fetch = Mock(return_value={"name": "Ada", "email": "ada@example.test"})
    monkeypatch.setattr("src.rclone_transport.fetch_account_identity", fetch, raising=False)

    assert client.account_info(connection) == {"name": "Ada", "email": "ada@example.test"}
    assert client.call.call_args_list[0].args == (
        "operations/stat", {"fs": "es_google:EverySync", "remote": ""})
    assert client.call.call_args_list[1].args == ("config/get", {"name": "es_google"})
    assert all(0 < call.kwargs["timeout"] <= 5 for call in client.call.call_args_list)
    fetch.assert_called_once_with("drive", "fixture-token", client.cancel_event)


@pytest.mark.parametrize("provider", ["s3", "sftp", "webdav", "azureblob", "b2", "local"])
def test_unsupported_identity_does_not_read_credentials_or_network(tmp_path, provider):
    client = RcloneTransport(tmp_path, executable=tmp_path / "unused")
    client.call = Mock(side_effect=AssertionError("no remote access"))
    assert client.account_info(SimpleNamespace(provider=provider)) == {}


@pytest.mark.parametrize("config", [
    {"type": "dropbox", "token": '{"access_token":"private-fixture"}'},
    {"type": "drive"}, {"type": "drive", "token": "private-malformed"},
    {"type": "drive", "token": "[]"},
    {"type": "drive", "token": '{"access_token":""}'},
    {"type": "drive", "token": '{"access_token":123}'},
    {"type": "drive", "token": {"access_token": "private-fixture"}},
])
def test_invalid_remote_credentials_fail_without_exposing_config(tmp_path, monkeypatch, config):
    client = RcloneTransport(tmp_path, executable=tmp_path / "unused")
    client.call = Mock(side_effect=[{"item": {"IsDir": True}}, config])
    fetch = Mock(side_effect=AssertionError("no provider access"))
    monkeypatch.setattr("src.rclone_transport.fetch_account_identity", fetch)
    with pytest.raises(CloudSyncError) as caught:
        client.account_info(ConnectionConfig("google", "Google", "drive", "EverySync"))
    assert "private" not in str(caught.value)
    assert caught.value.__cause__ is None
    fetch.assert_not_called()


def test_invalid_connection_id_is_rejected_before_remote_access(tmp_path):
    client = RcloneTransport(tmp_path, executable=tmp_path / "unused")
    client.call = Mock(side_effect=AssertionError("no remote access"))
    with pytest.raises(CloudSyncError):
        client.account_info(SimpleNamespace(id="foreign:remote", provider="drive", root="EverySync"))
    client.call.assert_not_called()


@pytest.mark.parametrize("cancel_after", [0, 1, 2])
def test_account_info_cancellation_is_checked_between_remote_calls(tmp_path, monkeypatch, cancel_after):
    client = RcloneTransport(tmp_path, executable=tmp_path / "unused")
    count = 0

    def call(method, *args, **kwargs):
        nonlocal count
        count += 1
        if count == cancel_after:
            client.cancel_event.set()
        return {"item": {"IsDir": True}} if method == "operations/stat" else {
            "type": "drive", "token": '{"access_token":"fixture"}'}

    client.call = call
    if cancel_after == 0:
        client.cancel_event.set()
    fetch = Mock(side_effect=AssertionError("no profile after cancellation"))
    monkeypatch.setattr("src.rclone_transport.fetch_account_identity", fetch)
    with pytest.raises(CloudSyncError, match="cancel"):
        client.account_info(ConnectionConfig("google", "Google", "drive", "EverySync"))
    assert count == cancel_after


def test_profile_error_is_translated_without_provider_data(tmp_path, monkeypatch):
    from src.cloud_identity import AccountIdentityError
    client = RcloneTransport(tmp_path, executable=tmp_path / "unused")
    client.call = Mock(side_effect=[{"item": {"IsDir": True}}, {
        "type": "drive", "token": '{"access_token":"fixture"}'}])
    monkeypatch.setattr("src.rclone_transport.fetch_account_identity",
                        Mock(side_effect=AccountIdentityError("private-body")))
    with pytest.raises(CloudSyncError) as caught:
        client.account_info(ConnectionConfig("google", "Google", "drive", "EverySync"))
    assert "private" not in str(caught.value)
