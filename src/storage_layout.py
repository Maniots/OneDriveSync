"""Shared names for synchronization folders and their sibling backup tree."""
from dataclasses import replace
from pathlib import Path, PurePosixPath

from .cloud_models import validate_id, validate_local_path, validate_relative_path

SYNC_ROOT = "EverySync"
BACKUP_ROOT = "EverySync Backups"


def sync_folder_name(name):
    validate_relative_path(name)
    if "/" in name:
        raise ValueError("The synchronization name must be a single folder name.")
    return name


def connection_sync_root(root, *, local=False):
    """The selected folder is the parent; selecting EverySync is idempotent."""
    if local:
        path = validate_local_path(root)
        return str(path if path.name == SYNC_ROOT else path / SYNC_ROOT)
    validate_relative_path(root)
    return root if PurePosixPath(root).name == SYNC_ROOT else f"{root}/{SYNC_ROOT}"


def local_sync_paths(parent, name):
    name = sync_folder_name(name)
    selected = validate_local_path(parent)
    if selected.name == name and selected.parent.name == SYNC_ROOT:
        return selected, selected.parent.parent / BACKUP_ROOT
    root = Path(connection_sync_root(parent, local=True))
    return root / name, root.parent / BACKUP_ROOT


def remote_sync_path(connection, name):
    name = sync_folder_name(name)
    root = Path(connection.root) if connection.provider == "local" else PurePosixPath(connection.root)
    return name if root.name == SYNC_ROOT else f"{SYNC_ROOT}/{name}"


def backup_location(connection, name):
    """Keep backups beside EverySync, within the same account/bucket/share."""
    name = sync_folder_name(name)
    root = Path(connection.root) if connection.provider == "local" else PurePosixPath(connection.root)
    backup_root = root.parent / BACKUP_ROOT if root.name == SYNC_ROOT else root / BACKUP_ROOT
    return replace(connection, root=str(backup_root)), name


def snapshot_directory(connection, job):
    """Legacy display names may be unsuitable as folder names; keep their ID tree."""
    try:
        sync_folder_name(job.name)
    except ValueError:
        return connection, f".everysync/backups/{validate_id(job.id)}", False
    backup_connection, name = backup_location(connection, job.name)
    return backup_connection, name, True
