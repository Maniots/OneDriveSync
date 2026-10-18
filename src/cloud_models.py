"""Non-secret cloud configuration and shared path validation boundaries."""
from __future__ import annotations

import ipaddress
import math
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from .utils import expand_env_vars, is_dangerous_root_path


PROVIDERS = frozenset({"local", "onedrive", "drive", "s3", "sftp", "webdav", "dropbox", "azureblob", "b2"})
_SAFE_ID = re.compile(r"[a-z][a-z0-9_]{0,47}\Z")
_DEVICE = re.compile(r"(?:con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³])(?:\..*)?\Z", re.IGNORECASE)
_INVALID_COMPONENT = re.compile(r'[<>:"\\|?*\x00-\x1f]')


def validate_id(value: str) -> str:
    """Validate an internal ID without changing legacy folder ID rules."""
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise ValueError("Cloud IDs must start with a lowercase letter and contain at most 48 lowercase letters, digits or underscores")
    return value


def _validate_component(component: str, *, allow_metadata: bool = False) -> None:
    if (not component or component in {".", ".."} or component.endswith((".", " "))
            or _INVALID_COMPONENT.search(component) or _DEVICE.fullmatch(component)):
        raise ValueError("Path contains an unsafe file or directory name")
    if not allow_metadata and component.casefold() == ".everysync":
        raise ValueError("The .everysync directory is reserved for application metadata")


def validate_relative_path(value: str, *, allow_empty: bool = False, allow_metadata: bool = False) -> str:
    """Accept canonical, slash-separated paths scoped below a connection root.

    Reject rather than silently repair ambiguous paths: provider listings and
    user input must identify the same filename on Windows and on the provider.
    Only internally constructed backup paths may opt in to metadata access.
    """
    if not isinstance(value, str):
        raise ValueError("Remote path must be a string")
    if not value:
        if allow_empty:
            return ""
        raise ValueError("Remote path cannot be empty")
    for component in value.split("/"):
        _validate_component(component, allow_metadata=allow_metadata)
    return value


def validate_local_path(value: str | Path) -> Path:
    """Expand an explicit local folder and reject unsafe or redirected roots.

    Descendant containment must also be checked immediately before transport
    writes. This validation never creates folders or follows reparse points.
    """
    if not isinstance(value, (str, Path)):
        raise ValueError("Local path must be a filesystem path")
    expanded = expand_env_vars(value)
    if not expanded or re.search(r"%[^%]+%|\$\{|\$[A-Za-z_]", expanded):
        raise ValueError("Local path contains an undefined environment variable")
    # Reject namespaces before pathlib or Win32 can normalize a device alias
    # into an apparently ordinary drive path. Both spellings bypass normal
    # filesystem parsing rules and are outside the supported path contract.
    if expanded.replace("/", "\\").startswith(("\\\\?\\", "\\\\.\\")):
        raise ValueError("Windows device paths are not supported")
    path = Path(expanded)
    if not path.is_absolute():
        raise ValueError("Local path must be absolute")
    # Windows drive/UNC anchors are not ordinary path components. Validate
    # every other component before Path.resolve() can discard '..'.
    for component in path.parts[1:]:
        _validate_component(component)
    for candidate in (path, *path.parents):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Local path cannot traverse a symbolic link or reparse point")
    resolved = path.resolve()
    if resolved == Path(resolved.anchor) or is_dangerous_root_path(resolved):
        raise ValueError("Local path must name an explicit safe subfolder")
    if resolved.exists() and not resolved.is_dir():
        raise ValueError("Local path must be a folder")
    return resolved


def _validate_name(name: str) -> None:
    if not isinstance(name, str) or not name.strip() or any(ord(char) < 32 for char in name):
        raise ValueError("A nonempty display name is required")


def _validate_bucket(root: str) -> None:
    bucket = root.split("/", 1)[0]
    if (not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket)
            or ".." in bucket or ".-" in bucket or "-." in bucket):
        raise ValueError("S3 root must start with a valid bucket name")
    try:
        ipaddress.ip_address(bucket)
    except ValueError:
        return
    raise ValueError("An S3 bucket name cannot be an IP address")


@dataclass(frozen=True)
class ConnectionConfig:
    id: str
    name: str
    provider: str
    root: str

    def __post_init__(self) -> None:
        validate_id(self.id)
        _validate_name(self.name)
        if self.provider not in PROVIDERS:
            raise ValueError("Unsupported cloud provider")
        if not isinstance(self.root, str):
            raise ValueError("Connection root must be a string")
        if self.provider == "local":
            validate_local_path(self.root)
        else:
            validate_relative_path(self.root)
            if self.provider == "s3":
                _validate_bucket(self.root)


@dataclass(frozen=True)
class RemoteJobConfig:
    id: str
    name: str
    local_path: str
    connection_id: str
    remote_path: str
    enabled: bool = True
    minimum_sync_percentage: float = 80
    verify_after_sync: bool = True
    backup_enabled: bool = True
    bidirectional: bool = False

    def __post_init__(self) -> None:
        validate_id(self.id)
        validate_id(self.connection_id)
        _validate_name(self.name)
        validate_local_path(self.local_path)
        validate_relative_path(self.remote_path)
        for name in ("enabled", "verify_after_sync", "backup_enabled", "bidirectional"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be a boolean")
        threshold = self.minimum_sync_percentage
        if (isinstance(threshold, bool) or not isinstance(threshold, (int, float))
                or not math.isfinite(threshold) or not 0 <= threshold <= 100):
            raise ValueError("minimum_sync_percentage must be a number between 0 and 100")

    @property
    def local_path_resolved(self) -> Path:
        return validate_local_path(self.local_path)
