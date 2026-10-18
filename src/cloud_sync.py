"""Additive cloud synchronization with verified snapshots and retry state.

Inventories are checked again immediately before writes. Provider operations
remain best effort against concurrent writers on other computers; this local
baseline is neither a distributed lock nor a cross-provider transaction.
Deferred work is recovered in its saved direction before a later normal run
can process the same job in the opposite direction.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import re
from uuid import uuid4

from .cloud_models import validate_id, validate_local_path, validate_relative_path
from .cloud_state import CloudState
from .config import SyncDirection
from .rclone_transport import RcloneTransport, FileEntry, CloudSyncError, scoped_fs
from .sync_manager import FolderSyncOutcome
from .utils import calculate_sync_percentage


class CloudSyncRunner:
    def __init__(self, config, state_root, transport_factory=None):
        self.config = config
        self.root = Path(state_root)
        self.transport_factory = transport_factory or RcloneTransport

    def _connection(self, job):
        connections = [item for item in self.config.connections if item.id == job.connection_id]
        if len(connections) != 1:
            raise CloudSyncError("The job's connection is missing or ambiguous.")
        return connections[0]

    def _identity(self, job, connection):
        return {"provider": connection.provider, "connection_id": connection.id,
                "root": connection.root, "remote_path": job.remote_path,
                "local_path": str(job.local_path_resolved)}

    def _paths(self, job, connection):
        local, remote = str(job.local_path_resolved), scoped_fs(connection, job.remote_path)
        if connection.provider == "local":
            # Include the connection root because it also contains snapshots.
            root, source = validate_local_path(connection.root), Path(local)
            if root.is_relative_to(source) or source.is_relative_to(root):
                raise CloudSyncError("The local source and connection root must not overlap.")
        return local, remote

    @staticmethod
    def _inventory(client, fs, *, allow_missing=False):
        result = client.inventory(fs, allow_missing=allow_missing)
        canonical = {}
        for name, item in result.items():
            validate_relative_path(name)
            # A durable baseline must compare actual bytes, including when a
            # provider exposes no native hash or the user disables verification.
            digest = item.hashes.get("sha256")
            if not digest:
                digest = client.operation("operations/hashsumfile", {
                    "fs": fs, "remote": name, "hashType": "SHA-256", "download": True}).get("hash")
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
                raise CloudSyncError("The provider cannot verify file content. Synchronization was stopped.")
            canonical[name] = FileEntry(item.size, item.modified, {"sha256": digest.lower()})
        return canonical

    @staticmethod
    def _same(first, second):
        if first is None or second is None:
            return first is second
        return first.same_content(second) is True

    @classmethod
    def _unchanged(cls, before, after):
        return before.keys() == after.keys() and all(
            cls._same(item, after[name]) and item.modified == after[name].modified
            for name, item in before.items())

    @staticmethod
    def _serialize(inventory):
        return {name: asdict(entry) for name, entry in inventory.items()}

    @staticmethod
    def _deserialize(inventory):
        if not isinstance(inventory, dict):
            raise CloudSyncError("Cloud baseline is invalid. Recover it before synchronizing.")
        return {validate_relative_path(name): FileEntry(**item) for name, item in inventory.items()}

    @staticmethod
    def _validate_destination(root, inventory):
        root = validate_local_path(root)
        for name in inventory:
            validate_relative_path(name)
            target = root.joinpath(*name.split("/"))
            if not target.resolve().is_relative_to(root):
                raise CloudSyncError("A provider file escapes the selected local folder.")
            for parent in (target, *target.parents):
                if parent == root.parent:
                    break
                try:
                    info = parent.lstat()
                except FileNotFoundError:
                    continue
                if parent.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise CloudSyncError("The local destination contains a symbolic link or reparse point.")

    def _inventories(self, client, connection, local, remote, direction, bidirectional):
        # A missing/unauthorized account root must never become an empty folder.
        client.test(connection)
        local_inventory = self._inventory(client, local, allow_missing=bidirectional or direction == SyncDirection.DOWNLOAD)
        remote_inventory = self._inventory(client, remote, allow_missing=bidirectional or direction == SyncDirection.UPLOAD)
        # Windows treats case aliases as the same path. Check both endpoints
        # together before planning so an apparent addition cannot overwrite a
        # different, newer counterpart or merge ambiguously named directories.
        names, files, directories = {}, set(), set()
        for path in local_inventory.keys() | remote_inventory.keys():
            parts = path.split("/")
            for count in range(1, len(parts) + 1):
                prefix = "/".join(parts[:count])
                key = prefix.casefold()
                is_file = count == len(parts)
                if ((key in names and names[key] != prefix)
                        or (is_file and key in directories)
                        or (not is_file and key in files)):
                    raise CloudSyncError("Local and remote folders have ambiguous case or file/directory names. Rename them before retrying.")
                names[key] = prefix
                (files if is_file else directories).add(key)
        self._validate_destination(Path(local), remote_inventory)
        return local_inventory, remote_inventory

    def _plan(self, job, direction, local, remote, baseline):
        upload, download = [], []
        if not job.bidirectional:
            source, destination = (local, remote) if direction == SyncDirection.UPLOAD else (remote, local)
            paths = [name for name, item in source.items()
                     if name not in destination or (not self._same(item, destination[name])
                                                    and item.modified >= destination[name].modified)]
            return (paths, []) if direction == SyncDirection.UPLOAD else ([], paths)
        old_local = self._deserialize(baseline["local"]) if baseline else {}
        old_remote = self._deserialize(baseline["remote"]) if baseline else {}
        conflicts = []
        for name in sorted(local.keys() | remote.keys()):
            left, right = local.get(name), remote.get(name)
            if self._same(left, right):
                continue
            if left is None:
                download.append(name)  # Never propagate deletions.
            elif right is None:
                upload.append(name)
            elif baseline and self._same(left, old_local.get(name)) and not self._same(right, old_remote.get(name)):
                download.append(name)
            elif baseline and self._same(right, old_remote.get(name)) and not self._same(left, old_local.get(name)):
                upload.append(name)
            else:
                conflicts.append(name)
        if conflicts:
            raise CloudSyncError(f"Sync conflict in {len(conflicts)} file(s). Both versions were preserved; compare them before retrying.")
        return upload, download

    def _snapshot(self, client, state, record, job, connection, remote, inventory):
        if not inventory:
            return
        run_id = "r" + uuid4().hex
        destination = scoped_fs(connection, f".everysync/backups/{job.id}/{run_id}", metadata=True)
        client.copy(remote, destination, paths=sorted(inventory))
        client.check(remote, destination, paths=sorted(inventory))
        snapshot_inventory = self._inventory(client, destination)
        if snapshot_inventory.keys() != inventory.keys() or any(
                not self._same(item, snapshot_inventory[name]) for name, item in inventory.items()):
            raise CloudSyncError("Snapshot verification failed. Upload was stopped.")
        # Publish only after successful verification and a durable atomic save.
        record["snapshots"].append({"run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(), "files": self._serialize(inventory)})
        state.save()

    def _run_job(self, client, job, direction, state, *, ignore_threshold=False):
        connection = self._connection(job)
        local, remote = self._paths(job, connection)
        record = state.job(job.id, self._identity(job, connection))
        pending = record.get("pending")
        if pending and pending["direction"] != direction.value:
            raise CloudSyncError(f"A pending {pending['direction']} must finish before synchronization in the opposite direction.")
        before_local, before_remote = self._inventories(client, connection, local, remote, direction, job.bidirectional)
        destination = before_remote if direction == SyncDirection.UPLOAD else before_local
        if destination and not ignore_threshold and (not job.bidirectional or before_local and before_remote):
            ratio = calculate_sync_percentage(len(before_local), len(before_remote))
            if ratio < job.minimum_sync_percentage:
                raise CloudSyncError(f"Safety threshold exceeded: file-count ratio {ratio:.1f}% is below {job.minimum_sync_percentage:g}%.")
        upload, download = self._plan(job, direction, before_local, before_remote, record.get("baseline"))
        if self.config.general.dry_run:
            return f"Dry run: {len(upload)} upload(s), {len(download)} download(s); no files or baseline changed."
        record["pending"] = {"direction": direction.value, "created_at": datetime.now(timezone.utc).isoformat()}
        state.save()
        # Observe changes again before starting the snapshot or any live write.
        current_local, current_remote = self._inventories(client, connection, local, remote, direction, job.bidirectional)
        if not self._unchanged(before_local, current_local) or not self._unchanged(before_remote, current_remote):
            raise CloudSyncError("Files changed while planning synchronization. No live files were overwritten; retry.")
        if upload and job.backup_enabled:
            self._snapshot(client, state, record, job, connection, remote, before_remote)
            current_local, current_remote = self._inventories(client, connection, local, remote, direction, job.bidirectional)
            if not self._unchanged(before_local, current_local) or not self._unchanged(before_remote, current_remote):
                raise CloudSyncError("Files changed while creating the snapshot. Live synchronization was stopped; retry.")
        self._validate_destination(Path(local), before_remote)
        if upload:
            client.copy(local, remote, paths=upload)
            client.check(local, remote, paths=upload)
        if download:
            client.copy(remote, local, paths=download)
            client.check(remote, local, paths=download)
        after_local = self._inventory(client, local, allow_missing=True)
        after_remote = self._inventory(client, remote, allow_missing=True)
        if job.bidirectional and (after_local.keys() != after_remote.keys() or any(
                not self._same(item, after_remote[name]) for name, item in after_local.items())):
            raise CloudSyncError("Content verification failed; baseline was preserved for a safe retry.")
        previous_baseline, previous_pending = record["baseline"], record["pending"]
        record["baseline"] = {"local": self._serialize(after_local), "remote": self._serialize(after_remote)}
        record["pending"] = None
        try:
            state.save()
        except Exception:
            # A later job's save must not accidentally publish this failed
            # commit from the shared in-memory state.
            record["baseline"], record["pending"] = previous_baseline, previous_pending
            raise
        return f"Sync completed: {len(upload)} upload(s), {len(download)} download(s). Destination-only files were preserved."

    def run(self, direction, *, ignore_threshold_for=None, defer=False):
        direction = SyncDirection(direction)
        jobs = [job for job in self.config.remote_jobs if job.enabled]
        if not jobs:
            return []
        outcomes = []
        def outcome(job, success, message):
            outcomes.append(FolderSyncOutcome(job.id, job.name, direction, success, message,
                                            job.id == ignore_threshold_for))
        try:
            state = CloudState(self.root)
        except CloudSyncError as error:
            return [FolderSyncOutcome(job.id, job.name, direction, False, str(error)) for job in jobs]
        if defer:
            for job in jobs:
                try:
                    record = state.job(job.id, self._identity(job, self._connection(job)))
                    if not self.config.general.dry_run:
                        if record.get("pending") and record["pending"]["direction"] != direction.value:
                            raise CloudSyncError("An opposite-direction cloud operation is already pending. Complete it before shutdown upload.")
                        record["pending"] = {"direction": direction.value, "created_at": datetime.now(timezone.utc).isoformat()}
                        state.save()
                    outcome(job, True, "Cloud synchronization queued for the next normal run; no network process started during session shutdown.")
                except (CloudSyncError, ValueError, OSError) as error:
                    outcome(job, False, str(error))
            return outcomes
        try:
            with self.transport_factory(self.root) as client:
                for job in jobs:
                    recovery_direction = None
                    try:
                        record = state.job(job.id, self._identity(job, self._connection(job)))
                        pending = record.get("pending")
                        recovery_message = ""
                        if pending and pending["direction"] != direction.value:
                            recovery_direction = SyncDirection(pending["direction"])
                            pending_message = self._run_job(client, job, recovery_direction, state,
                                ignore_threshold=job.id == ignore_threshold_for)
                            if self.config.general.dry_run:
                                outcome(job, True, f"Dry run of pending {recovery_direction.value}: {pending_message} Requested {direction.value} waits until pending work completes.")
                                continue
                            recovery_message = f"Recovered pending {recovery_direction.value}. "
                            recovery_direction = None
                        message = self._run_job(client, job, direction, state,
                                                ignore_threshold=job.id == ignore_threshold_for)
                        outcome(job, True, recovery_message + message)
                    except Exception as error:
                        # Never leak raw provider responses or credentials.
                        message = str(error) if isinstance(error, (CloudSyncError, ValueError)) else "Cloud synchronization failed. Check access, network and local state, then retry."
                        if recovery_direction is not None:
                            message = f"Pending {recovery_direction.value} recovery failed. Requested {direction.value} was stopped. {message}"
                        outcome(job, False, message)
        except Exception as error:
            message = str(error) if isinstance(error, CloudSyncError) else "The cloud engine could not start. Check its installation and credentials."
            outcomes.extend(FolderSyncOutcome(job.id, job.name, direction, False, message)
                            for job in jobs[len(outcomes):])
        return outcomes

    def _snapshot_record(self, job_id):
        validate_id(job_id)
        jobs = [job for job in self.config.remote_jobs if job.id == job_id]
        if len(jobs) != 1:
            raise CloudSyncError("The snapshot's job no longer exists.")
        job = jobs[0]
        connection = self._connection(job)
        state = CloudState(self.root)
        record = state.job(job.id, self._identity(job, connection))
        return job, connection, record

    def list_snapshots(self, job_id):
        _, _, record = self._snapshot_record(job_id)
        return [dict(item) for item in record.get("snapshots", [])]

    def restore(self, job_id, run_id, target):
        validate_id(run_id)
        job, connection, record = self._snapshot_record(job_id)
        selected = [item for item in record.get("snapshots", []) if item.get("run_id") == run_id]
        if len(selected) != 1:
            raise CloudSyncError("A verified snapshot with this ID is not available.")
        target = validate_local_path(target)
        if target.exists() and any(target.iterdir()):
            raise CloudSyncError("Choose an empty local folder for snapshot recovery.")
        inventory = self._deserialize(selected[0]["files"])
        self._validate_destination(target, inventory)
        source = scoped_fs(connection, f".everysync/backups/{job.id}/{run_id}", metadata=True)
        with self.transport_factory(self.root) as client:
            current = self._inventory(client, source)
            if current.keys() != inventory.keys() or any(not self._same(item, current[name]) for name, item in inventory.items()):
                raise CloudSyncError("The snapshot has changed or is incomplete. Recovery was stopped.")
            client.copy(source, str(target), paths=sorted(inventory))
            client.check(source, str(target), paths=sorted(inventory))
            recovered = self._inventory(client, str(target))
            if recovered.keys() != inventory.keys() or any(
                    not self._same(item, recovered[name]) for name, item in inventory.items()):
                raise CloudSyncError("Recovery content differs from the verified snapshot. Keep the recovery folder for inspection and retry into a new empty folder.")


CloudSyncCoordinator = CloudSyncRunner
