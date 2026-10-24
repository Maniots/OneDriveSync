"""Bounded client for an authenticated, app-owned rclone process."""
from __future__ import annotations

import base64
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import time
import threading
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, ProxyHandler, build_opener
from uuid import uuid4

from .cloud_credentials import CredentialStore
from .cloud_identity import AccountIdentityError, fetch_account_identity
from .cloud_models import validate_relative_path, validate_local_path, validate_id
from .exceptions import OneDrivePCSyncError
from .single_instance import acquire_single_instance_lock
from .cloud_providers import setup_parameters


_ONEDRIVE_ACCESS_SCOPES = "Files.Read Files.ReadWrite Files.Read.All Files.ReadWrite.All Sites.Read.All offline_access User.Read"


class CloudSyncError(OneDrivePCSyncError):
    pass


class CloudNotFound(CloudSyncError):
    pass


class CloudUnavailable(CloudSyncError):
    """Bounded transport connectivity failure, never an account rejection."""


class CloudCancelled(CloudSyncError):
    """An explicit cancellation; it must never cause fallback."""


@dataclass(frozen=True)
class FileEntry:
    size: int
    modified: float
    hashes: dict

    def same_content(self, other):
        if self.size != other.size:
            return False
        common = self.hashes.keys() & other.hashes.keys()
        return all(self.hashes[key] == other.hashes[key] for key in common) if common else None


def rclone_executable():
    if getattr(sys, "frozen", False):
        candidate = Path(sys.executable).parent / "rclone.exe"
    else:
        candidate = Path(__file__).resolve().parents[1] / "build/tools/rclone/rclone-v1.75.2-windows-amd64/rclone.exe"
        override = os.environ.get("EVERYSYNC_RCLONE")
        if override:
            candidate = Path(override)
    if not candidate.is_file():
        raise CloudSyncError("Cloud engine is missing. Reinstall EverySync or run scripts/Prepare-Rclone.ps1 for development.")
    return candidate.resolve()


def scoped_fs(connection, relative_path="", *, metadata=False):
    relative_path = validate_relative_path(relative_path, allow_empty=True, allow_metadata=metadata)
    if connection.provider == "local":
        root = validate_local_path(connection.root)
        target = root.joinpath(*relative_path.split("/")) if relative_path else root
        # Validate descendants immediately before handing them to the engine.
        for parent in (target, *target.parents):
            if parent == root.parent:
                break
            if parent.is_symlink() or parent.is_junction():
                raise CloudSyncError("Local destination contains a link or junction.")
        if not target.resolve().is_relative_to(root):
            raise CloudSyncError("Local destination escapes its configured root.")
        return str(target)
    return f"es_{connection.id}:{connection.root}" + (f"/{relative_path}" if relative_path else "")


class RcloneTransport:
    _METHODS = frozenset({"core/version", "core/quit", "config/create", "config/update",
                         "config/delete", "config/get", "config/oauthstatus", "config/oauthstop",
                         "operations/stat", "operations/list", "operations/hashsumfile",
                         "operations/copyfile", "operations/mkdir", "sync/copy", "job/status", "job/stop"})

    def __init__(self, root, *, executable=None, credentials=None, timeout=300, cancel_event=None):
        self.root = Path(root)
        self.executable = Path(executable) if executable else rclone_executable()
        self.credentials = credentials or CredentialStore(self.root)
        self.timeout = timeout
        self.cancel_event = cancel_event or threading.Event()
        self._process = None
        self._lock = None
        self._opener = build_opener(ProxyHandler({}))
        self._url = None
        self._auth = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.close()

    def start(self):
        if self._process is not None:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        password = self.credentials.password()
        self._lock = acquire_single_instance_lock(self.root / "rclone.lock")
        if self._lock is None:
            raise CloudSyncError("Cloud engine is busy. Wait for the current operation and retry.")
        try:
            config = self.root / "rclone.conf"
            env = {key: value for key, value in os.environ.items() if not key.upper().startswith("RCLONE_")}
            env.update(RCLONE_CONFIG_PASS=password, RCLONE_ASK_PASSWORD="false")
            flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
            if not config.exists():
                # Encrypt an empty config before any account secret can be stored.
                config.touch()
                result = subprocess.run([str(self.executable), "--config", str(config), "config", "encryption", "set"],
                                        input=password + "\n" + password + "\n", text=True,
                                        capture_output=True, timeout=15, env=env, **flags)
                if result.returncode or b"RCLONE_ENCRYPT_V0:" not in config.read_bytes():
                    config.unlink(missing_ok=True)
                    raise CloudSyncError("Cannot initialize the encrypted cloud configuration.")
            if b"RCLONE_ENCRYPT_V0:" not in config.read_bytes()[:256]:
                raise CloudSyncError("Cloud configuration must be encrypted. Restore its protected copy before retrying.")
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            secret = secrets.token_urlsafe(48)
            self._url = f"http://127.0.0.1:{port}/"
            self._auth = "Basic " + base64.b64encode(f"everysync:{secret}".encode()).decode()
            env.update(RCLONE_RC_USER="everysync", RCLONE_RC_PASS=secret)
            self._process = subprocess.Popen([str(self.executable), "rcd", "--config", str(config),
                                              "--rc-addr", f"127.0.0.1:{port}", "--log-level", "ERROR"],
                                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                             stderr=subprocess.DEVNULL, env=env, **flags)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if self._process.poll() is not None:
                    break
                try:
                    self.call("core/version", timeout=1)
                    return
                except CloudSyncError:
                    time.sleep(.05)
            raise CloudSyncError("Cannot start the cloud engine. Check this user's credentials and retry.")
        except BaseException:
            self.close()
            raise

    def call(self, method, payload=None, *, timeout=20):
        if method not in self._METHODS or self._url is None:
            raise CloudSyncError("Cloud operation is unavailable.")
        request = Request(self._url + method, data=json.dumps(payload or {}).encode(),
                          headers={"Authorization": self._auth, "Content-Type": "application/json"})
        try:
            with self._opener.open(request, timeout=timeout) as response:
                value = json.load(response)
            if not isinstance(value, dict):
                raise CloudSyncError("Cloud engine returned an invalid response.")
            return value
        except HTTPError as error:
            # Raw provider error bodies may contain tokens and signed URLs.
            if error.code == 404 and method in {"operations/stat", "operations/list"}:
                try:
                    detail = json.loads(error.read(65536)).get("error")
                except (ValueError, AttributeError):
                    detail = None
                if detail in {"directory not found", "object not found"}:
                    raise CloudNotFound("The synchronization folder does not exist.") from None
            raise CloudSyncError(f"Cloud operation failed (HTTP {error.code}). Check access, network and connection settings.") from None
        except (URLError, TimeoutError, OSError):
            raise CloudUnavailable("Cloud engine is unavailable or timed out. Check the connection and retry.") from None
        except ValueError:
            raise CloudSyncError("Cloud engine returned malformed metadata. Check the connection and retry.") from None

    def operation(self, method, payload):
        result = self.call(method, dict(payload, _async=True))
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if self.cancel_event.is_set():
                if method in {"config/create", "config/update"}:
                    try:
                        self.call("config/oauthstop", {})
                    except CloudSyncError:
                        pass  # A completed OAuth listener reports no active login.
                self.call("job/stop", {"jobid": result["jobid"]})
                raise CloudCancelled("Cloud operation cancelled.")
            status = self.call("job/status", {"jobid": result["jobid"]})
            if status.get("finished"):
                if not status.get("success"):
                    raise CloudSyncError("Cloud operation failed. Check account access, available space and network, then retry.")
                return status.get("output", {})
            time.sleep(.05)
        if method in {"config/create", "config/update"}:
            try:
                self.call("config/oauthstop", {})
            except CloudSyncError:
                pass
        self.call("job/stop", {"jobid": result["jobid"]})
        raise CloudUnavailable("Cloud operation timed out; unfinished work can be retried.")

    def inventory(self, fs, *, allow_missing=False):
        # Stat returns null for a confirmed missing directory; failures raise.
        try:
            stat = self.call("operations/stat", {"fs": fs, "remote": ""})
            if "item" not in stat or (stat["item"] is not None and not isinstance(stat["item"], dict)):
                raise CloudSyncError("Cloud engine returned an incomplete folder response.")
            item = stat["item"]
        except CloudNotFound:
            if allow_missing:
                return {}
            raise
        if item is None:
            if allow_missing:
                return {}
            raise CloudNotFound("The synchronization folder does not exist.")
        if item.get("IsDir") is not True:
            raise CloudSyncError("The synchronization path must be a folder.")
        response = self.operation("operations/list", {"fs": fs, "remote": "", "opt": {
            "recurse": True, "filesOnly": True, "showHash": True, "noMimeType": True}})
        files, names, prefixes, directories = {}, set(), {}, set()
        if "list" not in response or not isinstance(response["list"], list):
            raise CloudSyncError("Cloud engine returned an incomplete file listing.")
        for item in response["list"]:
            try:
                path = validate_relative_path(item["Path"])
            except (KeyError, TypeError, ValueError):
                raise CloudSyncError("Cloud folder contains an unsafe file path.") from None
            if path.casefold() in names:
                raise CloudSyncError("Remote folder has duplicate or case-colliding names.")
            parts = path.split("/")
            for count in range(1, len(parts) + 1):
                prefix = "/".join(parts[:count])
                key = prefix.casefold()
                if (key in prefixes and prefixes[key] != prefix
                    or count < len(parts) and key in names
                    or count == len(parts) and key in directories):
                    raise CloudSyncError("Remote folder has ambiguous file or directory names.")
                prefixes[key] = prefix
                if count < len(parts):
                    directories.add(key)
            names.add(path.casefold())
            size = item.get("Size")
            if type(size) is not int or size < 0:
                raise CloudSyncError("Remote folder contains an invalid file size.")
            try:
                modified = datetime.fromisoformat(item["ModTime"].replace("Z", "+00:00"))
                if modified.utcoffset() is None:
                    raise ValueError("timezone missing")
                hashes = {}
                raw_hashes = item.get("Hashes", {})
                if not isinstance(raw_hashes, dict):
                    raise ValueError("hashes invalid")
                for key, value in raw_hashes.items():
                    key = str(key).lower().replace("-", "")
                    if not value:
                        continue
                    length = {"md5": 32, "sha1": 40, "sha256": 64, "sha512": 128}.get(key)
                    if length:
                        if not isinstance(value, str) or not re.fullmatch(f"[0-9a-fA-F]{{{length}}}", value):
                            raise ValueError("hash invalid")
                        hashes[key] = value.lower()
                files[path] = FileEntry(size, modified.timestamp(), hashes)
            except (KeyError, TypeError, ValueError, OverflowError):
                raise CloudSyncError("Remote folder contains invalid time or checksum metadata.") from None
        return files

    def copy(self, source, destination, *, dry_run=False, update=False, paths=None):
        config = {"DryRun": dry_run, "UpdateOlder": update, "Retries": 2, "LowLevelRetries": 2}
        if paths is None:
            return self.operation("sync/copy", {"srcFs": source, "dstFs": destination, "_config": config})
        # The coordinator already selected these files by verified content.
        # Equal size/mtime does not imply equal bytes (e.g. restored saves).
        config["IgnoreTimes"] = True
        for path in paths:
            validate_relative_path(path)
            self.operation("operations/copyfile", {"srcFs": source, "srcRemote": path,
                                                    "dstFs": destination, "dstRemote": path, "_config": config})

    def check(self, source, destination, *, paths=None):
        before, after = self.inventory(source), self.inventory(destination)
        for path in before if paths is None else paths:
            if path not in before or path not in after or before[path].same_content(after[path]) is False:
                raise CloudSyncError("Content verification failed; the copied files do not match.")
            if before[path].same_content(after[path]) is None:
                hashes = [self.operation("operations/hashsumfile", {"fs": fs, "remote": path,
                           "hashType": "SHA-256", "download": True}).get("hash") for fs in (source, destination)]
                if (not all(isinstance(value, str) and re.fullmatch("[0-9a-fA-F]{64}", value) for value in hashes)
                        or hashes[0].lower() != hashes[1].lower()):
                    raise CloudSyncError("Content verification failed; the copied files do not match.")

    def configure(self, connection, parameters, *, state=None, answer=None):
        try:
            parameters = setup_parameters(connection.provider, parameters)
        except ValueError as error:
            raise CloudSyncError(str(error)) from None
        if connection.provider == "onedrive" and state is None:
            parameters["access_scopes"] = _ONEDRIVE_ACCESS_SCOPES
        options = {"nonInteractive": True, "obscure": True}
        if state is not None:
            options.update({"continue": True, "state": state, "result": answer or ""})
        payload = {"name": "es_" + connection.id, "parameters": parameters, "opt": options}
        method = "config/update" if state is not None else "config/create"
        if state is None:
            payload["type"] = connection.provider
        result = self.operation(method, payload)
        if connection.provider == "onedrive" and (result.get("Option") or {}).get("Name") == "config_driveid":
            result = self._eligible_onedrive_drives(connection, result)
        return result

    def _eligible_onedrive_drives(self, connection, question):
        """Read each candidate root through the engine, using only this pending remote."""
        option = question["Option"]
        eligible, seen = [], set()
        deadline = time.monotonic() + self.timeout
        for item in option.get("Examples") or []:
            if self.cancel_event.is_set():
                raise CloudSyncError("Account operation cancelled.")
            if time.monotonic() >= deadline:
                raise CloudSyncError("Checking OneDrive storage timed out. Cancel and sign in again.")
            identifier = item.get("Value")
            if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9!_-]+", identifier):
                continue
            if identifier in seen:
                continue
            seen.add(identifier)
            # A successful driveid_final reads /drives/{id}/root and stores
            # drive_id/type locally. Reapply the user's eventual choice later.
            probe = self.operation("config/update", {"name": "es_" + connection.id, "parameters": {},
                "opt": {"nonInteractive": True, "obscure": True, "continue": True,
                        "state": question["State"], "result": identifier}})
            if probe.get("Error") or (probe.get("Option") or {}).get("Name") != "config_drive_ok":
                continue
            # config/get may contain credentials: retain only the type and
            # never attach its response to a setup question or error.
            drive_type = self.call("config/get", {"name": "es_" + connection.id}).get("drive_type")
            if drive_type in {"personal", "business", "documentLibrary"}:
                eligible.append({"Value": identifier, "Help": item.get("Help") or identifier})
        if not eligible:
            return {"State": "choose_type", "Option": None,
                    "Error": "No accessible compatible drives found. Retry to check OneDrive access again."}
        default = option.get("Default")
        if default not in {item["Value"] for item in eligible}:
            default = eligible[0]["Value"]
        return dict(question, Option=dict(option, Examples=eligible, Exclusive=True, Default=default))

    def configure_google(self, connection, parameters, token):
        """Import only a native login result; user setup cannot supply tokens."""
        if connection.provider != "drive":
            raise CloudSyncError("Google authorization requires a Google Drive connection.")
        parameters = setup_parameters("drive", parameters)
        if (not isinstance(token, dict) or not token.get("access_token") or not token.get("refresh_token")
                or not token.get("expiry") or token.get("token_type") != "Bearer"):
            raise CloudSyncError("Google authorization did not return a usable account token. Sign in again.")
        return self.operation("config/create", {"name": "es_" + connection.id, "type": "drive",
            "parameters": dict(parameters, token=json.dumps(token), scope="drive", config_refresh_token="false"),
            "opt": {"nonInteractive": True, "obscure": True}})

    def folders(self, connection, path=""):
        path = validate_relative_path(path, allow_empty=True)
        if connection.provider not in {"onedrive", "drive", "dropbox"}:
            raise CloudSyncError("Folder selection requires an authorized cloud account.")
        response = self.operation("operations/list", {"fs": f"es_{connection.id}:{path}",
            "remote": "", "opt": {"recurse": False, "dirsOnly": True}})
        entries = response.get("list")
        if not isinstance(entries, list):
            raise CloudSyncError("Could not read the cloud folder list. Retry or choose a folder path.")
        names = []
        for item in entries:
            if not isinstance(item, dict) or item.get("IsDir") is not True:
                raise CloudSyncError("The cloud returned an invalid folder list.")
            name = item.get("Path")
            if isinstance(name, str) and name.casefold() == ".everysync":
                continue
            try:
                validate_relative_path(name)
                if "/" in name:
                    raise ValueError()
            except ValueError:
                # Such names cannot be synchronized safely on Windows.
                continue
            names.append(name)
        if len(set(name.casefold() for name in names)) != len(names):
            raise CloudSyncError("Cloud folders have ambiguous names on Windows. Choose another parent folder.")
        return sorted(names, key=str.casefold)

    def test(self, connection):
        response = self.call("operations/stat", {"fs": scoped_fs(connection), "remote": ""})
        if "item" in response and response["item"] is None:
            raise CloudNotFound("The connection root does not exist.")
        if not isinstance(response.get("item"), dict) or response["item"].get("IsDir") is not True:
            raise CloudSyncError("The connection root does not exist or cannot be read.")
        return response

    def authorize_account_identity(self, connection):
        """Explicit Microsoft consent; preserve saved credentials until verified."""
        unavailable = "Could not show the Microsoft account. Retry sign-in and allow profile access."

        def check_cancel():
            if self.cancel_event.is_set():
                raise CloudCancelled("Account operation cancelled.")

        try:
            validate_id(connection.id)
        except ValueError:
            raise CloudSyncError(unavailable) from None
        if connection.provider != "onedrive":
            raise CloudSyncError("Profile authorization is available for Microsoft accounts only.")
        check_cancel()
        name = "es_" + connection.id
        config = self.call("config/get", {"name": name})
        if (config.get("type") != "onedrive" or not config.get("drive_id")
                or config.get("drive_type") not in {"personal", "business", "documentLibrary"}
                or config.get("region", "global") != "global"
                or config.get("client_credentials", "false") == "true"):
            raise CloudSyncError(unavailable)
        scopes = (config.get("access_scopes") or _ONEDRIVE_ACCESS_SCOPES).split()
        # rclone's disable_site_permission replaces the entire scope list,
        # dropping User.Read. Preserve its effective storage scopes explicitly.
        if config.get("disable_site_permission") == "true":
            scopes = [scope for scope in _ONEDRIVE_ACCESS_SCOPES.split() if scope != "Sites.Read.All"]
        scopes = " ".join(dict.fromkeys([*scopes, "User.Read"]))
        staged = replace(connection, id="profile_" + uuid4().hex)
        staged_name = "es_" + staged.id
        parameters = {key: value for key, value in config.items()
                      if key not in {"type", "token"} and not key.startswith("config_")}
        parameters.update(access_scopes=scopes, disable_site_permission="false", config_is_local="true")
        check_cancel()
        try:
            result = self.operation("config/create", {"name": staged_name, "type": "onedrive",
                "parameters": parameters, "opt": {"nonInteractive": True, "noObscure": True}})
            check_cancel()
            # OAuth is complete when OneDrive asks for storage type. The
            # existing drive is already copied; do not discover/select another.
            if (result.get("Error") or (result.get("Option") or {}).get("Name") != "config_type"):
                raise CloudSyncError(unavailable)
            self.test(staged)
            details = self.account_info(staged)
            if not details:
                raise CloudSyncError(unavailable)
            check_cancel()
            updated = self.call("config/get", {"name": staged_name})
            raw_token = updated.get("token")
            try:
                token = json.loads(raw_token) if isinstance(raw_token, str) and len(raw_token) <= 65536 else None
            except (ValueError, RecursionError):
                token = None
            if (not isinstance(token, dict) or not isinstance(token.get("access_token"), str)
                    or not token["access_token"]):
                raise CloudSyncError(unavailable)
        finally:
            # Cleanup must succeed before the saved connection can be changed.
            self.call("config/delete", {"name": staged_name})
        check_cancel()
        result = self.call("config/update", {"name": name,
            "parameters": {"token": raw_token, "access_scopes": scopes,
                           "disable_site_permission": "false", "config_refresh_token": "false"},
            "opt": {"nonInteractive": True, "noObscure": True}})
        if result.get("Error"):
            raise CloudSyncError(unavailable)
        return details

    def account_info(self, connection):
        """Read optional account labels without exporting credentials."""
        if connection.provider not in {"drive", "onedrive", "dropbox"}:
            return {}
        unavailable = "Account details are unavailable. Verify access and retry."

        def check_cancel():
            if self.cancel_event.is_set():
                raise CloudSyncError("Account operation cancelled.")

        try:
            validate_id(connection.id)
            check_cancel()
            response = self.call("operations/stat", {"fs": scoped_fs(connection), "remote": ""}, timeout=3)
            check_cancel()
            if not isinstance(response.get("item"), dict) or response["item"].get("IsDir") is not True:
                raise CloudSyncError(unavailable)
            config = self.call("config/get", {"name": "es_" + connection.id}, timeout=3)
            check_cancel()
            if config.get("type") != connection.provider:
                raise CloudSyncError(unavailable)
            raw_token = config.get("token")
            if not isinstance(raw_token, str) or len(raw_token) > 65536:
                raise CloudSyncError(unavailable)
            token = json.loads(raw_token)
            if not isinstance(token, dict) or not isinstance(token.get("access_token"), str) or not token["access_token"]:
                raise CloudSyncError(unavailable)
            result = fetch_account_identity(connection.provider, token["access_token"], self.cancel_event)
            check_cancel()
            return result
        except AccountIdentityError:
            check_cancel()
            raise CloudSyncError(unavailable) from None
        except (ValueError, TypeError, RecursionError):
            raise CloudSyncError(unavailable) from None

    def close(self):
        if self._process is not None:
            if self._process.poll() is None:
                try:
                    self.call("core/quit", timeout=1)
                except CloudSyncError:
                    pass
                try:
                    self._process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._process.terminate()
                    self._process.wait(timeout=3)
            self._process = None
        if self._lock is not None:
            self._lock.close()
            self._lock = None
