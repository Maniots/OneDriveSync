"""Explicit synchronization ownership; leaves keep their original identities."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .cloud_models import validate_id, validate_local_path
from .exceptions import ConfigurationError

if TYPE_CHECKING:
    from .config import AppConfig


@dataclass(frozen=True)
class SyncDestinationConfig:
    job_id: str
    upload_enabled: bool = True
    download_enabled: bool = True

    def __post_init__(self):
        if not isinstance(self.job_id, str) or not self.job_id.strip():
            raise ValueError("A destination must reference an existing job ID")
        for name in ("upload_enabled", "download_enabled"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be a boolean")
        if not self.upload_enabled and not self.download_enabled:
            raise ValueError("A destination must participate in upload or download")


@dataclass(frozen=True)
class SyncGroupConfig:
    id: str
    name: str
    local_path: str
    destinations: list[SyncDestinationConfig]
    enabled: bool = True
    fallback_on_unavailable: bool = False
    allow_untracked_download: bool = False

    def __post_init__(self):
        validate_id(self.id)
        if not isinstance(self.name, str) or not self.name.strip() or any(ord(c) < 32 for c in self.name):
            raise ValueError("A nonempty group name is required")
        if not isinstance(self.local_path, str) or not self.local_path.strip():
            raise ValueError("A group requires a local folder")
        validate_local_path(self.local_path)
        if not isinstance(self.destinations, list) or not self.destinations or any(
                not isinstance(item, SyncDestinationConfig) for item in self.destinations):
            raise ValueError("A group requires an ordered list of destinations")
        for name in ("enabled", "fallback_on_unavailable", "allow_untracked_download"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be a boolean")

    @property
    def local_path_resolved(self) -> Path:
        return validate_local_path(self.local_path)


def grouped_job_ids(config: AppConfig) -> set[str]:
    """Disabled groups still own their leaves, preventing implicit execution."""
    return {destination.job_id for group in config.sync_groups for destination in group.destinations}


def destination_identity(config: AppConfig, leaf) -> dict:
    """Canonical endpoint identity for evidence/UI; never contacts a provider."""
    if hasattr(leaf, "onedrive_path_resolved"):
        return {"kind": "folder", "local_path": str(leaf.local_path_resolved),
                "root": str(validate_local_path(leaf.onedrive_path)), "remote_path": "",
                "connection_id": "", "provider": "local"}
    connections = [item for item in config.connections if item.id == leaf.connection_id]
    if len(connections) != 1:
        raise ConfigurationError("The destination's connection is missing or ambiguous")
    connection = connections[0]
    root = str(validate_local_path(connection.root)) if connection.provider == "local" else connection.root
    return {"kind": "remote", "local_path": str(leaf.local_path_resolved), "root": root,
            "remote_path": leaf.remote_path, "connection_id": connection.id, "provider": connection.provider}


def validate_groups(config: AppConfig) -> None:
    leaves = {item.id: item for item in [*config.folders, *config.remote_jobs]}
    connections = {item.id: item for item in config.connections}
    ids, references = set(leaves), set()
    for group in config.sync_groups:
        if group.id in ids:
            raise ConfigurationError("Duplicate group ID or collision with an existing job")
        ids.add(group.id)
        source = group.local_path_resolved
        # Compare only actual data/backup roots, not a provider's account root.
        roots = [("filesystem", source)]
        for destination in group.destinations:
            if destination.job_id in references:
                raise ConfigurationError("A destination cannot belong to multiple groups or appear twice")
            references.add(destination.job_id)
            leaf = leaves.get(destination.job_id)
            if leaf is None:
                raise ConfigurationError("A group references an unknown destination")
            if validate_local_path(leaf.local_path) != source:
                raise ConfigurationError("All destinations in a group must use the same local folder")
            if getattr(leaf, "bidirectional", False):
                raise ConfigurationError("A bidirectional job must remain an independent synchronization")
            if hasattr(leaf, "onedrive_path_resolved"):
                if not config.copy_engine.copy_subdirectories:
                    raise ConfigurationError("Groups with local folder destinations require 'Copy subdirectories' to be enabled. Independent legacy folders keep their current setting.")
                roots.append(("filesystem", validate_local_path(leaf.onedrive_path)))
                if leaf.backup and leaf.backup.enabled:
                    backup_root = validate_local_path(leaf.backup.backup_path)
                    backup = (backup_root / leaf.id).resolve()
                    if not backup.is_relative_to(backup_root) or backup == backup_root:
                        raise ConfigurationError("The legacy backup ID escapes its configured backup folder")
                    roots.append(("filesystem", backup))
            else:
                connection = connections.get(leaf.connection_id)
                if connection is None:
                    raise ConfigurationError("A group destination references an unknown connection")
                if connection.provider == "local":
                    root = validate_local_path(connection.root)
                    if root.is_relative_to(source) or source.is_relative_to(root):
                        raise ConfigurationError("The local connection and group source cannot overlap")
                    roots.append(("filesystem", root.joinpath(*leaf.remote_path.split("/"))))
                    if leaf.backup_enabled:
                        roots.append(("filesystem", root / ".everysync" / "backups" / leaf.id))
                else:
                    scope = f"provider:{connection.provider}:{connection.id}"
                    roots.append((scope, Path(connection.root) / leaf.remote_path))
                    if leaf.backup_enabled:
                        roots.append((scope, Path(connection.root) / ".everysync" / "backups" / leaf.id))
        for index, (scope, first) in enumerate(roots):
            for other_scope, second in roots[index + 1:]:
                if scope == other_scope and (first.is_relative_to(second) or second.is_relative_to(first)):
                    raise ConfigurationError("A group's source, destinations and backup folders must not overlap")


def validate_pending_edits(previous: AppConfig | None, candidate: AppConfig, state_root: Path) -> None:
    """Refuse edits that would detach unresolved work from its original owner.

    Display/order changes are harmless. Pending endpoint/membership/direction
    changes must wait for completion; editing is never a state-reset mechanism.
    """
    from .cloud_state import CloudState
    from .group_state import GroupState
    from .rclone_transport import CloudSyncError

    def ownership(config):
        if config is None:
            return {}, {}, {}
        leaves = {item.id: item for item in [*config.folders, *config.remote_jobs]}
        groups = {group.id: group for group in config.sync_groups}
        owners = {d.job_id: group.id for group in config.sync_groups for d in group.destinations}
        return leaves, groups, owners

    old_leaves, old_groups, old_owners = ownership(previous)
    leaves, groups, owners = ownership(candidate)
    try:
        # Readers distinguish FileNotFound from access/corruption. A preceding
        # Path.exists() check would suppress PermissionError on Python 3.14.
        ledger, state = GroupState(state_root), CloudState(state_root)
        for group_id, record in ledger.data["groups"].items():
            if not record["pending"] and not any(item["status"] == "incomplete"
                                                  for item in record["destinations"].values()):
                continue
            group = groups.get(group_id)
            if group is None or str(group.local_path_resolved) != record["source"]:
                raise ConfigurationError("Complete pending group work before removing it or changing its local folder")
            identities = {d.job_id: destination_identity(candidate, leaves[d.job_id]) for d in group.destinations}
            if record["pending"] and identities != record["pending"]["identities"]:
                raise ConfigurationError("Complete pending group work before changing its destinations")
            for job_id, item in record["destinations"].items():
                if item["status"] == "incomplete" and identities.get(job_id) != item["identity"]:
                    raise ConfigurationError("An incomplete destination cannot be detached or changed before recovery")
            old = old_groups.get(group_id)
            if old is not None:
                before = {d.job_id: (d.upload_enabled, d.download_enabled) for d in old.destinations}
                after = {d.job_id: (d.upload_enabled, d.download_enabled) for d in group.destinations}
                if before != after:
                    raise ConfigurationError("Complete pending work before changing destination participation")
        for job_id, record in state.data["jobs"].items():
            if not record["pending"]:
                continue
            leaf = leaves.get(job_id)
            if leaf is None or not hasattr(leaf, "connection_id"):
                raise ConfigurationError("A cloud destination has pending work and cannot be removed")
            identity = destination_identity(candidate, leaf)
            expected = {key: identity[key] for key in ("provider", "connection_id", "root", "remote_path", "local_path")}
            # Existing CloudState preserves the configured provider root text;
            # group identity deliberately resolves local endpoint roots.
            connection = next(item for item in candidate.connections if item.id == leaf.connection_id)
            expected["root"] = connection.root
            if expected != record["identity"] or old_owners.get(job_id) != owners.get(job_id):
                raise ConfigurationError("Complete pending cloud work before changing its endpoint or group")
            old = old_leaves.get(job_id)
            if old is not None and getattr(old, "bidirectional", False) != leaf.bidirectional:
                raise ConfigurationError("Complete pending cloud work before changing its direction mode")
    except CloudSyncError as error:
        raise ConfigurationError(str(error)) from error
