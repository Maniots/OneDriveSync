import os
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock
from pathlib import Path

import pytest

from src.cloud_credentials import CredentialStore
from src.rclone_transport import RcloneTransport, CloudSyncError


@pytest.fixture
def transport(tmp_path):
    executable = Path(os.environ.get("EVERYSYNC_RCLONE", "build/tools/rclone/rclone-v1.75.2-windows-amd64/rclone.exe"))
    if not executable.is_file():
        pytest.skip("Run scripts/Prepare-Rclone.ps1 for native transport tests")
    store = CredentialStore(tmp_path / "credentials", protect=lambda b: b[::-1], unprotect=lambda b: b[::-1])
    with RcloneTransport(store.root, executable=executable.resolve(), credentials=store) as client:
        yield client


def test_native_copy_preserves_extra_and_newer_files(transport, tmp_path):
    source, destination = tmp_path / "source", tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    (source / "save.txt").write_text("new save")
    (source / "newer.txt").write_text("old source")
    (destination / "extra.txt").write_text("keep extra")
    (destination / "newer.txt").write_text("keep newer")
    os.utime(source / "newer.txt", (1000000000, 1000000000))
    os.utime(destination / "newer.txt", (2000000000, 2000000000))
    before = transport.inventory(str(source))
    assert before["save.txt"].size == 8
    transport.copy(str(source), str(destination), update=True)
    assert (destination / "save.txt").read_text() == "new save"
    assert (destination / "extra.txt").read_text() == "keep extra"
    assert (destination / "newer.txt").read_text() == "keep newer"
    transport.check(str(source), str(destination), paths=["save.txt"])
    assert b"RCLONE_ENCRYPT_V0:" in (transport.root / "rclone.conf").read_bytes()


def test_native_dry_run_and_confirmed_missing_directory(transport, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "save.txt").write_text("data")
    destination = tmp_path / "absent"
    assert transport.inventory(str(destination), allow_missing=True) == {}
    transport.copy(str(source), str(destination), dry_run=True)
    assert not destination.exists()
    with pytest.raises(CloudSyncError):
        transport.inventory(str(destination))


def test_native_verification_fails_for_same_size_wrong_contents(transport, tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "data.txt").write_text("good")
    (target / "data.txt").write_text("evil")
    with pytest.raises(CloudSyncError, match="verif"):
        transport.check(str(source), str(target), paths=["data.txt"])


def test_native_selected_copy_transfers_different_bytes_with_equal_size_and_time(transport, tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "save").write_bytes(b"good")
    (target / "save").write_bytes(b"evil")
    (source / "untouched").write_bytes(b"source")
    (target / "untouched").write_bytes(b"retain")
    for path in (source / "save", target / "save"):
        os.utime(path, (1000000000, 1000000000))
    transport.copy(str(source), str(target), paths=["save"])
    assert (target / "save").read_bytes() == b"good"
    assert (target / "untouched").read_bytes() == b"retain"
    transport.check(str(source), str(target), paths=["save"])


@pytest.mark.parametrize("item,list_response", [
    ({}, {"list": []}),
    ({"item": {"IsDir": True}}, {}),
    ({"item": {"IsDir": True}}, {"list": [{"Path": "file", "Size": True, "ModTime": "2026-10-18T00:00:00Z", "Hashes": {}}]}),
    ({"item": {"IsDir": True}}, {"list": [{"Path": "file", "Size": 1, "ModTime": "2026-10-18T00:00:00", "Hashes": {}}]}),
    ({"item": {"IsDir": True}}, {"list": [{"Path": "file", "Size": 1, "ModTime": "2026-10-18T00:00:00Z", "Hashes": {"sha256": "not-a-hash"}}]}),
])
def test_inventory_rejects_incomplete_or_invalid_metadata(tmp_path, monkeypatch, item, list_response):
    client = RcloneTransport(tmp_path, executable=tmp_path / "unused")
    monkeypatch.setattr(client, "call", lambda *args, **kwargs: item)
    monkeypatch.setattr(client, "operation", lambda *args, **kwargs: list_response)
    with pytest.raises(CloudSyncError):
        client.inventory("configured:folder", allow_missing=True)


def test_existing_plaintext_config_is_rejected_before_process_start(tmp_path, monkeypatch):
    store = CredentialStore(tmp_path, protect=lambda b: b[::-1], unprotect=lambda b: b[::-1])
    store.password()
    (tmp_path / "rclone.conf").write_text("[private]\ntoken = secret\n")
    process = Mock()
    monkeypatch.setattr("src.rclone_transport.subprocess.Popen", process)
    with pytest.raises(CloudSyncError, match="encrypt"):
        RcloneTransport(tmp_path, executable=tmp_path / "unused", credentials=store).start()
    process.assert_not_called()


def test_configuration_rejects_unregistered_provider_options(tmp_path, monkeypatch):
    from src.cloud_models import ConnectionConfig
    client = RcloneTransport(tmp_path, executable=tmp_path / "unused")
    operation = Mock()
    monkeypatch.setattr(client, "operation", operation)
    with pytest.raises(CloudSyncError, match="option"):
        client.configure(ConnectionConfig("account", "OneDrive", "onedrive", "EverySync"),
                         {"token": "private", "password_command": "unwanted-command"})
    operation.assert_not_called()


def test_native_google_token_import_keeps_pkce_token_without_second_login(transport):
    from src.cloud_models import ConnectionConfig
    result = transport.configure_google(ConnectionConfig("google", "Google", "drive", "EverySync"),
        {"client_id": "desktop.apps.googleusercontent.com", "client_secret": "desktop"},
        {"access_token": "test-access", "refresh_token": "test-refresh", "token_type": "Bearer", "expiry": "2099-01-01T00:00:00Z"})
    assert result.get("Option", {}).get("Name") not in {"config_refresh_token", "config_is_local", "config_verification_code"}


def test_native_onedrive_error_only_state_can_rediscover_drives(transport):
    from src.cloud_models import ConnectionConfig
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            if self.server.fail:
                status, value = 403, {"error": {"code": "accessDenied", "message": "Isolated fixture"}}
            else:
                drive = {"id": "fixture", "name": "Test drive", "driveType": "personal"}
                status = 200
                value = {"value": [drive]} if self.path.endswith("/drives") else drive
            body = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.fail = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = transport.operation("config/create", {
            "name": "es_onedrive", "type": "onedrive",
            "parameters": {"tenant_url": f"http://127.0.0.1:{server.server_port}", "config_type": "onedrive",
                           "config_refresh_token": "false", "token": json.dumps({"access_token": "fixture-only",
                           "refresh_token": "fixture-refresh", "token_type": "Bearer", "expiry": "2099-01-01T00:00:00Z"})},
            "opt": {"nonInteractive": True, "obscure": True}})
        assert result["State"] == "driveid"
        assert result["Option"] is None
        assert "Failed to query available drives" in result["Error"]
        server.fail = False
        result = transport.configure(ConnectionConfig("onedrive", "OneDrive", "onedrive", "EverySync"),
                                     {}, state="onedrive", answer="")
        assert not result.get("Error")
        assert result["Option"]["Name"] == "config_driveid"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("paths", [["A/first", "a/second"], ["file", "file/child"], ["file/child", "file"]])
def test_inventory_rejects_directory_aliases(tmp_path, monkeypatch, paths):
    client = RcloneTransport(tmp_path, executable=tmp_path / "unused")
    monkeypatch.setattr(client, "call", lambda *args, **kwargs: {"item": {"IsDir": True}})
    monkeypatch.setattr(client, "operation", lambda *args, **kwargs: {"list": [
        {"Path": path, "Size": 1, "ModTime": "2026-10-18T00:00:00Z", "Hashes": {}} for path in paths]})
    with pytest.raises(CloudSyncError, match="ambiguous"):
        client.inventory("configured:folder")


def test_content_verification_rejects_malformed_fallback_hash(tmp_path, monkeypatch):
    from src.rclone_transport import FileEntry
    client = RcloneTransport(tmp_path, executable=tmp_path / "unused")
    monkeypatch.setattr(client, "inventory", lambda *args, **kwargs: {"file": FileEntry(1, 1, {})})
    monkeypatch.setattr(client, "operation", lambda *args, **kwargs: {"hash": "unsupported"})
    with pytest.raises(CloudSyncError, match="verif"):
        client.check("source", "destination")
