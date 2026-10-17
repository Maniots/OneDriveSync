"""Release identity and the installer alias consumed by pre-rebranding clients."""
import hashlib
import io
import json
import sys

import pytest

from scripts import release_metadata
from src.app_info import BASE_VERSION, REPOSITORY
from src.updater import API_URL, UpdateClient


@pytest.fixture
def release_root(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "packaging").mkdir()
    (tmp_path / "dist/installer").mkdir(parents=True)
    monkeypatch.setattr(release_metadata, "ROOT", tmp_path)
    monkeypatch.setattr(release_metadata, "release_notes", lambda: "EverySync release")
    monkeypatch.setattr(release_metadata.subprocess, "check_output", lambda *a, **k: "a" * 40)
    return tmp_path


def build(monkeypatch, number=42):
    monkeypatch.setattr(sys, "argv", ["release_metadata.py", "build", "--build-number", str(number)])
    release_metadata.main()


@pytest.mark.skipif(sys.platform != "win32", reason="PyInstaller Windows resource parser")
def test_windows_product_metadata_uses_brand_and_legacy_executable(release_root, monkeypatch):
    build(monkeypatch)
    from PyInstaller.utils.win32.versioninfo import load_version_info_from_text_file
    version = load_version_info_from_text_file(str(release_root / "packaging/build-version-info.txt"))
    fields = {entry.name: entry.val for entry in version.kids[0].kids[0].kids}
    assert fields["ProductName"] == "EverySync"
    assert fields["FileDescription"] == "EverySync"
    assert fields["OriginalFilename"] == "OneDrivePCSync.exe"
    assert fields["ProductVersion"] == fields["FileVersion"] == f"{BASE_VERSION}.42"
    major, minor, patch = map(int, BASE_VERSION.split("."))
    assert version.ffi.fileVersionMS == (major << 16) + minor
    assert version.ffi.fileVersionLS == (patch << 16) + 42
    assert version.ffi.productVersionMS == version.ffi.fileVersionMS
    assert version.ffi.productVersionLS == version.ffi.fileVersionLS


def test_manifest_publishes_identical_alias_readable_by_old_updater(release_root, monkeypatch):
    build(monkeypatch)
    version = f"{BASE_VERSION}.42"
    directory = release_root / "dist/installer"
    payload = b"canonical EverySync installer bytes"
    canonical = directory / f"EverySync-Setup-{version}.exe"
    canonical.write_bytes(payload)
    legacy = directory / f"OneDrivePCSync-Setup-{version}.exe"
    legacy.write_bytes(b"outdated alias must be replaced")
    monkeypatch.setattr(sys, "argv", ["release_metadata.py", "manifest"])
    release_metadata.main()
    assert legacy.read_bytes() == canonical.read_bytes()
    manifest = json.loads((directory / "update.json").read_text(encoding="utf-8"))
    assert manifest["installer"] == legacy.name
    assert manifest["sha256"] == hashlib.sha256(payload).hexdigest()
    assert manifest["size"] == len(payload)
    tag = "master-42"
    base = f"https://github.com/{REPOSITORY}/releases/download/{tag}/"
    release = {"tag_name": tag, "draft": False, "prerelease": False, "assets": [
        {"name": name, "size": size, "browser_download_url": base + name}
        for name, size in [("update.json", (directory / "update.json").stat().st_size),
                           (legacy.name, len(payload)), (canonical.name, len(payload))]]}
    def opener(request, timeout):
        data = json.dumps(release if request.full_url == API_URL else manifest).encode() if (
            request.full_url == API_URL or request.full_url.endswith("update.json")) else payload
        return io.BytesIO(data)
    client = UpdateClient("1.3.1.4", release_root / "client", opener)
    result = client.check()
    assert result.status == "available"
    assert client.download(result.update).read_bytes() == payload


@pytest.mark.parametrize("number", [-1, 65536])
def test_build_rejects_invalid_windows_version_component(release_root, monkeypatch, number):
    with pytest.raises(SystemExit):
        build(monkeypatch, number)
    assert not (release_root / "src/build-info.json").exists()
