"""Public master-release updates; no repository credentials are shipped."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from src.app_info import REPOSITORY, VERSION
from src.runtime_paths import data_root

MAX_INSTALLER_SIZE = 250 * 1024 * 1024
API_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"


class UpdateError(Exception):
    pass


def version_key(value: str) -> tuple[int, ...]:
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,5}\.\d{1,5}\.\d{1,5}(?:\.\d{1,5})?", value):
        raise UpdateError("Invalid update version.")
    components = tuple(map(int, value.split(".")))
    if any(part > 65535 for part in components):
        raise UpdateError("Invalid update version.")
    return components + (0,) * (4 - len(components))


@dataclass(frozen=True)
class AvailableUpdate:
    version: str
    commit: str
    filename: str
    url: str
    sha256: str
    size: int
    changes: str = ""


@dataclass(frozen=True)
class CheckResult:
    status: str
    update: AvailableUpdate | None = None


def _validate_asset_url(url: str, tag: str) -> None:
    parsed = urlparse(url)
    prefix = f"/{REPOSITORY}/releases/download/{tag}/"
    if (parsed.scheme != "https" or parsed.netloc != "github.com" or
            not parsed.path.startswith(prefix) or parsed.query or parsed.fragment):
        raise UpdateError("Update download is not from the application's repository.")


class UpdateClient:
    def __init__(self, current_version=VERSION, root: Path | None = None, opener=None):
        self.current_version = current_version
        self.root = root if root is not None else data_root() / "updates"
        self.opener = opener or urlopen

    def _open(self, url):
        request = Request(url, headers={"User-Agent": "EverySync-Updater",
                                       "Accept": "application/vnd.github+json"})
        try:
            return self.opener(request, timeout=20)
        except (OSError, URLError) as exc:
            if isinstance(exc, HTTPError):
                raise
            raise UpdateError("Cannot connect. Check your internet connection and try again.") from exc

    def _json(self, url: str, limit: int):
        with self._open(url) as response:
            contents = response.read(limit + 1)
        if len(contents) > limit:
            raise UpdateError("Update information is too large.")
        try:
            value = json.loads(contents)
        except (ValueError, UnicodeError) as exc:
            raise UpdateError("Update information is invalid. Try again later.") from exc
        if not isinstance(value, dict):
            raise UpdateError("Update information is invalid. Try again later.")
        return value

    def check(self) -> CheckResult:
        try:
            release = self._json(API_URL, 1024 * 1024)
        except HTTPError as exc:
            if exc.code == 404:
                return CheckResult("no_release")
            raise UpdateError("Cannot check updates right now. Try again later.") from exc
        tag = release.get("tag_name", "")
        if (release.get("draft") or release.get("prerelease") or
                not isinstance(tag, str) or not re.fullmatch(r"master-\d+", tag)):
            raise UpdateError("The latest release is not a supported master build.")
        asset_list = release.get("assets")
        if not isinstance(asset_list, list):
            raise UpdateError("The update package is incomplete. Try again later.")
        assets = {asset.get("name"): asset for asset in asset_list
                  if isinstance(asset, dict) and isinstance(asset.get("name"), str)}
        manifest_asset = assets.get("update.json")
        if not manifest_asset:
            raise UpdateError("The update package is incomplete. Try again later.")
        manifest_url = manifest_asset.get("browser_download_url", "")
        _validate_asset_url(manifest_url, tag)
        try:
            manifest = self._json(manifest_url, 8192)
        except HTTPError as exc:
            raise UpdateError("Cannot retrieve update information. Try again later.") from exc
        version = manifest.get("version")
        latest = version_key(version)
        filename = f"EverySync-Setup-{version}.exe"
        if (manifest.get("schema") != 1 or manifest.get("channel") != "master" or
                manifest.get("repository") != REPOSITORY or manifest.get("installer") != filename or
                not re.fullmatch(r"[a-f0-9]{40}", str(manifest.get("commit", ""))) or
                not re.fullmatch(r"[a-f0-9]{64}", str(manifest.get("sha256", "")))):
            raise UpdateError("Update information is invalid. Try again later.")
        size = manifest.get("size")
        if isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= MAX_INSTALLER_SIZE:
            raise UpdateError("Update package size is invalid.")
        asset = assets.get(filename)
        if not asset or asset.get("size") != size:
            raise UpdateError("The update package is incomplete. Try again later.")
        url = asset.get("browser_download_url", "")
        _validate_asset_url(url, tag)
        changes = manifest.get("changes", "")
        if not isinstance(changes, str) or len(changes.encode("utf-8")) > 4096:
            raise UpdateError("Update release notes are invalid.")
        update = AvailableUpdate(version, manifest["commit"], filename, url, manifest["sha256"], size, changes)
        if latest <= version_key(self.current_version):
            return CheckResult("current")
        return CheckResult("available", update)

    def download(self, update: AvailableUpdate, progress=None) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        directory = Path(tempfile.mkdtemp(prefix=f"{update.version}-", dir=self.root))
        partial = directory / (update.filename + ".part")
        destination = directory / update.filename
        digest, count = hashlib.sha256(), 0
        try:
            with self._open(update.url) as response, partial.open("wb") as handle:
                while block := response.read(1024 * 1024):
                    count += len(block)
                    if count > update.size:
                        raise UpdateError("Update download exceeds its declared size.")
                    digest.update(block)
                    handle.write(block)
                    if progress:
                        progress(int(count * 100 / update.size))
            if count != update.size or digest.hexdigest() != update.sha256:
                raise UpdateError("Update download did not pass verification. Please retry.")
            partial.replace(destination)
            return destination
        except Exception:
            partial.unlink(missing_ok=True)
            raise

    def load_automatic(self) -> bool:
        try:
            value = json.loads((self.root / "preferences.json").read_text())
            return value.get("automatic") is True
        except (OSError, ValueError, AttributeError):
            return False

    def last_install_result(self) -> dict:
        try:
            value = json.loads((self.root / "result.json").read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def installation_history(self):
        from src.installation_history import InstallationHistory
        return InstallationHistory(self.root).recent()

    def save_automatic(self, enabled: bool):
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "preferences.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"automatic": bool(enabled)}), encoding="utf-8")
        temporary.replace(path)

    def launch_install(self, installer: Path, update: AvailableUpdate) -> None:
        if not getattr(sys, "frozen", False) or sys.platform != "win32":
            raise UpdateError("Install updates from the installed Windows app.")
        if installer.stat().st_size != update.size:
            raise UpdateError("The downloaded installer has changed. Please retry.")
        with installer.open("rb") as handle:
            if hashlib.file_digest(handle, "sha256").hexdigest() != update.sha256:
                raise UpdateError("The downloaded installer has changed. Please retry.")
        helper = installer.parent / "Apply-Update.ps1"
        shutil.copyfile(Path(__file__).resolve().parent.parent / "packaging/Apply-Update.ps1", helper)
        powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        subprocess.Popen([str(powershell), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(helper),
                          "-Installer", str(installer), "-ApplicationExe", sys.executable,
                          "-ParentPid", str(os.getpid()), "-ExpectedHash", update.sha256,
                          "-ExpectedVersion", update.version, "-DataDirectory", str(data_root())],
                         creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)
