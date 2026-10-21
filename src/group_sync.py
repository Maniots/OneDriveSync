"""Fan-out uploads and one whole-source download, with per-PC evidence.

The caller owns the application lock. Leaf engines retain their thresholds,
backups and additive semantics; this coordinator adds provenance and routing.
"""
from __future__ import annotations

from contextlib import ExitStack
from dataclasses import asdict, replace
import hashlib
import os
from pathlib import Path
import stat
import threading
from uuid import uuid4

from .cloud_models import validate_local_path, validate_relative_path
from .cloud_state import CloudState
from .cloud_sync import CloudSyncRunner
from .config import SyncDirection
from .exceptions import OneDrivePCSyncError
from .group_state import GroupState
from .rclone_transport import (CloudCancelled, CloudNotFound, CloudSyncError,
                               CloudUnavailable, FileEntry, RcloneTransport, scoped_fs)
from .sync_groups import validate_groups, destination_identity
from .sync_manager import FolderSyncOutcome


class SourceChanged(CloudSyncError):
    pass


def filesystem_inventory(path, *, allow_missing=False):
    """Read exact file bytes, rejecting links, aliases and unsafe metadata."""
    root = validate_local_path(path)
    try:
        root_stat = root.stat()
    except FileNotFoundError:
        if allow_missing:
            return {}
        raise CloudSyncError("The selected source folder does not exist.") from None
    if not stat.S_ISDIR(root_stat.st_mode):
        raise CloudSyncError("The selected source must be a directory.")
    result, aliases, files, directories = {}, {}, set(), set()
    def walk(directory):
        # pathlib.rglob may suppress inaccessible-directory errors. Complete
        # evidence needs every directory read to succeed, including empties.
        with os.scandir(directory) as entries:
            children = sorted(entries, key=lambda entry: entry.name)
        for entry in children:
            metadata = entry.stat(follow_symlinks=False)
            if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, "st_file_attributes", 0) & 0x400:
                raise CloudSyncError("A group folder contains a symbolic link or reparse point.")
            yield Path(entry.path), metadata
            if stat.S_ISDIR(metadata.st_mode):
                yield from walk(entry.path)
    for item, metadata in walk(root):
        metadata = item.lstat()
        if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, "st_file_attributes", 0) & 0x400:
            raise CloudSyncError("A group folder contains a symbolic link or reparse point.")
        name = validate_relative_path(item.relative_to(root).as_posix())
        parts = name.split("/")
        for count in range(1, len(parts) + 1):
            prefix = "/".join(parts[:count]); key = prefix.casefold()
            is_file = count == len(parts) and stat.S_ISREG(metadata.st_mode)
            if ((key in aliases and aliases[key] != prefix) or is_file and key in directories
                    or not is_file and key in files):
                raise CloudSyncError("A group folder contains ambiguous case or file/directory names.")
            aliases[key] = prefix
            (files if is_file else directories).add(key)
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise CloudSyncError("A group folder contains an unsupported file type.")
        digest = hashlib.sha256()
        with item.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        after = item.stat()
        if (metadata.st_size, metadata.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise SourceChanged("Source files changed while reading. Retry after writes finish.")
        result[name] = FileEntry(after.st_size, after.st_mtime, {"sha256": digest.hexdigest()})
    return result


class GroupSyncRunner:
    def __init__(self, config, state_root, *, transport_factory=None, local_runner=None, cancel_event=None):
        self.config, self.root = config, Path(state_root)
        self.transport_factory = transport_factory or RcloneTransport
        self.local_runner = local_runner
        self.cancel_event = cancel_event or threading.Event()
        self.cloud = CloudSyncRunner(config, self.root, transport_factory=self.transport_factory)

    @staticmethod
    def _same(first, second):
        return first.keys() == second.keys() and all(
            item.same_content(second[name]) is True for name, item in first.items())

    @staticmethod
    def _serialized(inventory):
        return {name: asdict(item) for name, item in inventory.items()}

    @staticmethod
    def _safe_message(error):
        return str(error) if isinstance(error, (OneDrivePCSyncError, ValueError)) else (
            "Synchronization failed. Check folder access and local state, then retry.")

    def _probe(self, leaf, client, *, allow_missing=False):
        if hasattr(leaf, "onedrive_path_resolved"):
            target = validate_local_path(leaf.onedrive_path)
            # An offline drive or missing parent cannot prove activity absence.
            try:
                parent_stat = target.parent.stat()
            except FileNotFoundError:
                raise CloudUnavailable("The destination's volume or parent folder is unavailable.")
            if not stat.S_ISDIR(parent_stat.st_mode):
                raise CloudSyncError("The destination parent must be a directory.")
            try:
                target_stat = target.stat()
            except FileNotFoundError:
                # Confirm that the parent has not disappeared since validation.
                try:
                    target.parent.stat()
                except FileNotFoundError:
                    raise CloudUnavailable("The destination parent became unavailable.") from None
                if allow_missing:
                    return {}
                raise CloudNotFound("The activity folder is absent.")
            if not stat.S_ISDIR(target_stat.st_mode):
                raise CloudSyncError("The activity path must be a directory.")
            return filesystem_inventory(target)
        connection = self.cloud._connection(leaf)
        try:
            client.test(connection)
        except CloudNotFound:
            raise CloudSyncError("The account or connection root is absent; activity absence cannot be confirmed.") from None
        return self.cloud._inventory(client, scoped_fs(connection, leaf.remote_path), allow_missing=allow_missing)

    def _leaf(self, leaf, direction, client, cloud_state):
        if hasattr(leaf, "onedrive_path_resolved"):
            validate_local_path(leaf.local_path)
            validate_local_path(leaf.onedrive_path)
            if self.local_runner is None:
                from .sync_manager import SyncManager
                # Reuse the lock-owned safety engine directly, never run_*.
                self.local_runner = SyncManager(self.config)._sync_single_folder
            return self.local_runner(leaf, direction)
        message = self.cloud._run_job(client, leaf, direction, cloud_state)
        return FolderSyncOutcome(leaf.id, leaf.name, direction, True, message)

    def _preflight(self, group, direction, leaves, identities, ledger, cloud_state):
        record = ledger.bind(group, identities)
        pending = record["pending"]
        if pending and pending["direction"] != direction.value:
            raise CloudSyncError(f"A pending {pending['direction']} must finish before the opposite group direction.")
        pending_downloads = []
        for destination in group.destinations:
            leaf = leaves[destination.job_id]
            if hasattr(leaf, "connection_id"):
                item = cloud_state.job(leaf.id, self.cloud._identity(leaf, self.cloud._connection(leaf)))
                pending = item.get("pending")
                if pending and pending["direction"] != direction.value:
                    raise CloudSyncError(f"Destination '{leaf.name}' has a pending {pending['direction']}; the whole group was stopped.")
                if pending and pending["direction"] == "download":
                    pending_downloads.append(leaf.id)
        if len(pending_downloads) > 1:
            raise CloudSyncError("Multiple destinations have pending downloads. Recover them separately before using this hierarchy.")
        if pending_downloads:
            pinned = record["pending"].get("selected_id") if record["pending"] else None
            if pinned is not None and pinned != pending_downloads[0]:
                raise CloudSyncError("Group and destination pending download sources disagree. Restore the original configuration before recovery.")
            if record["pending"] is None:
                record["pending"] = ledger.pending(direction, identities)
            record["pending"]["selected_id"] = pending_downloads[0]
            # Existing leaf pending metadata predates group bookkeeping. The
            # leaf runner has no immutable source fingerprint to establish a
            # coherent retry: refuse adoption instead of inventing evidence.
            if "selected_inventory" not in record["pending"]:
                raise CloudSyncError("A destination has a pending download without group source evidence. Complete that original download before adopting it into this hierarchy.")
        return record

    def run(self, group, direction, *, defer=False):
        direction = SyncDirection(direction)
        outcomes = []
        def summary(success, message):
            return [*outcomes, FolderSyncOutcome(group.id, group.name, direction, success, message)]
        try:
            if self.cancel_event.is_set():
                raise CloudCancelled("Synchronization cancelled before starting; files were preserved.")
            effective = replace(self.config, sync_groups=[item for item in self.config.sync_groups if item.id != group.id] + [group])
            validate_groups(effective)
            if not group.enabled:
                raise CloudSyncError("This synchronization is disabled.")
            leaves = {item.id: item for item in [*self.config.folders, *self.config.remote_jobs]}
            identities = {d.job_id: destination_identity(self.config, leaves[d.job_id]) for d in group.destinations}
            ledger, cloud_state = GroupState(self.root), CloudState(self.root)
            record = self._preflight(group, direction, leaves, identities, ledger, cloud_state)
            selected = [leaves[d.job_id] for d in group.destinations
                        if leaves[d.job_id].enabled and getattr(d, f"{direction.value}_enabled")]
            if not selected:
                raise CloudSyncError(f"No enabled destination participates in {direction.value}.")
            if defer:
                if not self.config.general.dry_run:
                    if record["pending"] is None:
                        record["pending"] = ledger.pending(direction, identities)
                    ledger.save()
                return summary(True, "Group queued in its saved direction; no network process started during session shutdown.")
            with ExitStack() as stack:
                client = None
                def get_client():
                    nonlocal client
                    if client is None:
                        client = stack.enter_context(self.transport_factory(self.root))
                    return client
                if direction == SyncDirection.UPLOAD:
                    return self._upload(group, selected, identities, record, ledger, cloud_state, get_client, outcomes, summary)
                return self._download(group, selected, identities, record, ledger, cloud_state, get_client, outcomes, summary)
        except Exception as error:
            return summary(False, self._safe_message(error))

    def _upload(self, group, selected, identities, record, ledger, cloud_state, get_client, outcomes, summary):
        source = filesystem_inventory(group.local_path_resolved)
        dry_run = self.config.general.dry_run
        generation = "g" + uuid4().hex
        if not dry_run:
            record["generation"] = generation
            record["source_inventory"] = self._serialized(source)
            record["pending"] = ledger.pending(SyncDirection.UPLOAD, identities)
            for leaf in selected:
                record["destinations"][leaf.id] = {"identity": identities[leaf.id], "generation": generation,
                    "status": "incomplete", "inventory": {}}
            # This save must finish before any leaf can write.
            ledger.save()
        succeeded = 0
        for leaf in selected:
            try:
                if self.cancel_event.is_set():
                    raise CloudCancelled("Synchronization stopped after the current destination; remaining uploads are incomplete.")
                if not self._same(source, filesystem_inventory(group.local_path_resolved)):
                    raise SourceChanged("The local source changed during this generation. Further uploads were stopped.")
                client = get_client() if hasattr(leaf, "connection_id") else None
                outcome = self._leaf(leaf, SyncDirection.UPLOAD, client, cloud_state)
                if not outcome.succeeded:
                    raise CloudSyncError(outcome.message)
                if not dry_run:
                    if not self._same(source, filesystem_inventory(group.local_path_resolved)):
                        raise SourceChanged("The local source changed during upload. This copy remains incomplete.")
                    destination = self._probe(leaf, client)
                    if any(name not in destination or item.same_content(destination[name]) is not True
                           for name, item in source.items()):
                        raise CloudSyncError("Destination content does not match this generation; its copy remains incomplete. Newer destination files may have been protected.")
                    if not self._same(source, filesystem_inventory(group.local_path_resolved)):
                        raise SourceChanged("The source changed during destination verification. Further uploads were stopped.")
                    item = record["destinations"][leaf.id]
                    item["inventory"], item["status"] = self._serialized(destination), "complete"
                    try:
                        ledger.save()
                    except Exception:
                        item["status"], item["inventory"] = "incomplete", {}
                        raise
                outcomes.append(outcome)
                succeeded += 1
            except Exception as error:
                outcomes.append(FolderSyncOutcome(leaf.id, leaf.name, SyncDirection.UPLOAD, False, self._safe_message(error)))
                if isinstance(error, (SourceChanged, CloudCancelled)):
                    break
        complete = succeeded == len(selected) and (dry_run or not any(
            item["status"] == "incomplete" for item in record["destinations"].values()))
        if complete and not dry_run:
            record["pending"] = None
            try:
                ledger.save()
            except Exception:
                record["pending"] = ledger.pending(SyncDirection.UPLOAD, identities)
                raise
        prefix = "Dry run: " if dry_run else ""
        return summary(complete, f"{prefix}Updated {succeeded}/{len(selected)} destinations. "
                       + ("Generation verified on this PC." if complete and not dry_run else
                          "No files or evidence changed." if dry_run else "Incomplete upload must be retried before downloading."))

    def _download(self, group, selected, identities, record, ledger, cloud_state, get_client, outcomes, summary):
        reasons = []
        pinned = record["pending"].get("selected_id") if record["pending"] else None
        pinned_inventory = self.cloud._deserialize(record["pending"]["selected_inventory"]) if pinned else None
        if pinned:
            selected = [leaf for leaf in selected if leaf.id == pinned]
            if not selected:
                raise CloudSyncError("The pending download source is disabled. Enable it before retrying.")
        for leaf in selected:
            if self.cancel_event.is_set():
                raise CloudCancelled("Download cancelled before starting; local files were preserved.")
            evidence = record["destinations"].get(leaf.id)
            if evidence:
                if evidence["status"] != "complete":
                    raise CloudSyncError(f"{leaf.name}: incomplete copy. Complete its upload before downloading.")
                if evidence["generation"] != record["generation"]:
                    raise CloudSyncError(f"{leaf.name}: prior generation. Upload a current copy before downloading.")
            try:
                client = get_client() if hasattr(leaf, "connection_id") else None
                inventory = self._probe(leaf, client)
            except CloudNotFound:
                if pinned:
                    raise CloudSyncError("The pending download source is absent. No other source can continue a partially started download.") from None
                reasons.append(f"{leaf.name}: activity folder absent")
                continue
            except CloudUnavailable:
                if pinned or not group.fallback_on_unavailable:
                    raise
                reasons.append(f"{leaf.name}: unavailable (fallback enabled)")
                continue
            if evidence:
                known = self.cloud._deserialize(evidence["inventory"])
                tracked = self._same(known, inventory)
            else:
                tracked = False
            if pinned_inventory is not None and not self._same(pinned_inventory, inventory):
                raise CloudSyncError("The pending download source changed since its first write. Restore its original inventory before retrying; no other generation was merged.")
            if inventory and not tracked and not group.allow_untracked_download:
                raise CloudSyncError(f"{leaf.name}: freshness unknown on this PC. Upload first or explicitly allow untracked copies in Advanced settings.")
            # An existing empty folder is a result, never a fallback candidate.
            if not inventory:
                if pinned:
                    raise CloudSyncError("The pending download source is now empty. Recover its original copy before completing this download.")
                if record["pending"] and not self.config.general.dry_run:
                    record["pending"] = None
                    ledger.save()
                return summary(True, f"{leaf.name}: source exists but is empty; local files were preserved. " + "; ".join(reasons))
            # Revalidate immediately before the writing leaf, including known bytes.
            current = self._probe(leaf, client)
            if not self._same(inventory, current):
                raise SourceChanged(f"{leaf.name}: source changed before download. Local files were preserved.")
            if self.cancel_event.is_set():
                raise CloudCancelled("Download cancelled before starting; local files were preserved.")
            if not self.config.general.dry_run:
                record["pending"] = ledger.pending(SyncDirection.DOWNLOAD, identities)
                record["pending"]["selected_id"] = leaf.id
                record["pending"]["selected_inventory"] = self._serialized(inventory)
                ledger.save()
            # No fallback is permitted after this point, regardless of error type.
            outcome = self._leaf(leaf, SyncDirection.DOWNLOAD, client, cloud_state)
            outcomes.append(outcome)
            if not outcome.succeeded:
                return summary(False, f"Download from {leaf.name} failed. No other source was used. {outcome.message}")
            if not self.config.general.dry_run:
                after = filesystem_inventory(group.local_path_resolved)
                if any(name not in after or item.same_content(after[name]) is not True
                       for name, item in inventory.items()):
                    raise CloudSyncError(f"Download from {leaf.name} is incomplete. Newer local files may have been protected; inspect them before retrying.")
                if not self._same(inventory, self._probe(leaf, client)):
                    raise SourceChanged(f"{leaf.name}: source changed during download. No fallback was attempted.")
                record["pending"] = None
                ledger.save()
            freshness = "verified on this PC" if tracked else "freshness unknown"
            prefix = "Dry run: would download" if self.config.general.dry_run else "Downloaded"
            return summary(True, f"{prefix} from {leaf.name} ({freshness}). " + "; ".join(reasons))
        return summary(False, "No complete source was found; local files were preserved. " + "; ".join(reasons))
