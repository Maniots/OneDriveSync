from unittest.mock import Mock

import pytest

from src.cloud_models import ConnectionConfig
from src.rclone_transport import CloudSyncError, RcloneTransport
from tests.test_cloud_ui import setup_page, spin


def choices():
    return {"State": "driveid_final", "Option": {
        "Name": "config_driveid", "Default": "denied", "Exclusive": False,
        "Examples": [{"Value": value, "Help": value.title()} for value in
                     ("denied", "personal", "unknown", "shared", "personal")],
    }}


def test_only_accessible_supported_drives_are_offered(tmp_path, monkeypatch):
    client = RcloneTransport(tmp_path, executable=tmp_path / "unused")
    probes = []
    def operation(method, payload):
        if method == "config/create":
            return choices()
        assert method == "config/update"
        assert payload["name"] == "es_pending"
        assert payload["parameters"] == {}
        assert payload["opt"]["state"] == "driveid_final"
        candidate = payload["opt"]["result"]
        probes.append(candidate)
        if candidate == "denied":
            return {"State": "choose_type", "Error": "fixture-sensitive-error", "Option": None}
        return {"State": "driveid_final_end", "Option": {"Name": "config_drive_ok"}}
    def metadata(method, payload):
        assert method == "config/get" and payload == {"name": "es_pending"}
        return {"drive_type": {"personal": "personal", "shared": "documentLibrary"}.get(probes[-1], "unsupported"),
                "token": "fixture-secret-token"}
    monkeypatch.setattr(client, "operation", operation)
    monkeypatch.setattr(client, "call", metadata)
    result = client.configure(ConnectionConfig("pending", "Pending", "onedrive", "EverySync"), {})
    assert [item["Value"] for item in result["Option"]["Examples"]] == ["personal", "shared"]
    assert result["Option"]["Exclusive"] is True
    assert result["Option"]["Default"] == "personal"
    assert result["State"] == "driveid_final"
    assert probes == ["denied", "personal", "unknown", "shared"]
    assert "fixture-sensitive-error" not in str(result)
    assert "fixture-secret-token" not in str(result)


def test_no_eligible_drives_returns_retry_without_answer_input(tmp_path, monkeypatch):
    client = RcloneTransport(tmp_path, executable=tmp_path / "unused")
    monkeypatch.setattr(client, "operation", Mock(side_effect=[choices()] + [
        {"State": "choose_type", "Error": "access denied", "Option": None}] * 4))
    result = client.configure(ConnectionConfig("pending", "Pending", "onedrive", "EverySync"), {})
    assert result["Option"] is None
    assert result["State"] == "choose_type"
    assert "accessible" in result["Error"]


def test_probe_transport_failure_is_not_reported_as_empty_success(tmp_path, monkeypatch):
    client = RcloneTransport(tmp_path, executable=tmp_path / "unused")
    monkeypatch.setattr(client, "operation", Mock(side_effect=[choices(), CloudSyncError("cancelled")]))
    with pytest.raises(CloudSyncError, match="cancelled"):
        client.configure(ConnectionConfig("pending", "Pending", "onedrive", "EverySync"), {})


def test_unlisted_drive_or_different_state_cannot_bypass_offered_choices(qapp, tmp_path):
    question = choices()
    question["Option"]["Examples"] = [{"Value": "personal", "Help": "Personal"}]
    question["Option"]["Exclusive"] = True
    _, factory, service, page = setup_page(tmp_path, [question])
    page.connect_button.click()
    spin(qapp, lambda: not service.busy)
    for state, answer in [("driveid_final", "denied"), ("driveid_final_end", "true")]:
        with pytest.raises(ValueError, match="available OneDrive"):
            service.configure_connection(page.pending, {}, state=state, answer=answer)
    assert len(factory.calls) == 1
    service.wait_for_finished()
