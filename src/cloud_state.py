"""Atomic local bookkeeping; credentials never enter synchronization state.

The existing application synchronization lock owns this file. This is not a
distributed lock: a second computer can still change a provider concurrently.
"""
from __future__ import annotations

import json
import math
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

from .cloud_models import PROVIDERS, validate_id, validate_relative_path
from .rclone_transport import CloudSyncError


class CloudState:
    def __init__(self, root):
        self.path = Path(root) / "state.json"
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self.data = {"version": 1, "jobs": {}}
        except (OSError, ValueError):
            raise CloudSyncError("Cloud state cannot be read. Recover the state file before synchronizing.") from None
        if (not isinstance(self.data, dict) or self.data.get("version") != 1
                or not isinstance(self.data.get("jobs"), dict)):
            raise CloudSyncError("Cloud state is invalid or from an unsupported version.")
        try:
            for job_id, record in self.data["jobs"].items():
                validate_id(job_id)
                self._validate_record(record)
        except (TypeError, ValueError, KeyError, AttributeError):
            raise CloudSyncError("Cloud job state is invalid. Recover the state file before synchronizing.") from None

    @staticmethod
    def _validate_inventory(inventory):
        if not isinstance(inventory, dict):
            raise ValueError("Invalid inventory")
        seen = set()
        for name, entry in inventory.items():
            validate_relative_path(name)
            if name.casefold() in seen or not isinstance(entry, dict):
                raise ValueError("Ambiguous inventory")
            seen.add(name.casefold())
            size, modified, hashes = entry["size"], entry["modified"], entry["hashes"]
            if (isinstance(size, bool) or not isinstance(size, int) or size < 0
                    or isinstance(modified, bool) or not isinstance(modified, (float, int))
                    or not math.isfinite(modified) or not isinstance(hashes, dict)
                    or not isinstance(hashes.get("sha256"), str)
                    or not re.fullmatch(r"[0-9a-f]{64}", hashes["sha256"])):
                raise ValueError("Invalid content fingerprint")

    @classmethod
    def _validate_record(cls, record):
        if not isinstance(record, dict):
            raise ValueError("Invalid record")
        identity = record["identity"]
        if (not isinstance(identity, dict) or identity.get("provider") not in PROVIDERS
                or any(not isinstance(identity.get(key), str) or not identity[key]
                       for key in ("connection_id", "root", "remote_path", "local_path"))):
            raise ValueError("Invalid identity")
        validate_id(identity["connection_id"])
        validate_relative_path(identity["remote_path"])
        baseline = record["baseline"]
        if baseline is not None:
            cls._validate_inventory(baseline["local"])
            cls._validate_inventory(baseline["remote"])
        pending = record["pending"]
        if pending is not None:
            if not isinstance(pending, dict) or pending.get("direction") not in {"upload", "download"}:
                raise ValueError("Invalid pending direction")
            datetime.fromisoformat(pending["created_at"])
        snapshots = record["snapshots"]
        if not isinstance(snapshots, list):
            raise ValueError("Invalid snapshots")
        ids = set()
        for snapshot in snapshots:
            validate_id(snapshot["run_id"])
            if "folder_name" in snapshot:
                from .storage_layout import sync_folder_name
                sync_folder_name(snapshot["folder_name"])
            if snapshot["run_id"] in ids:
                raise ValueError("Duplicate snapshot")
            ids.add(snapshot["run_id"])
            datetime.fromisoformat(snapshot["created_at"])
            cls._validate_inventory(snapshot["files"])

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=".state-", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(self.data, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)

    def job(self, job_id, identity):
        current = self.data["jobs"].get(job_id)
        if current is not None and not isinstance(current, dict):
            raise CloudSyncError("Cloud job state is invalid. Recover its state before retrying.")
        if current and current.get("identity") != identity:
            if current.get("pending"):
                raise CloudSyncError("This job has pending work for its previous connection. Restore that configuration before retrying.")
            current = None
        if current is None:
            current = {"identity": identity, "baseline": None, "pending": None, "snapshots": []}
            self.data["jobs"][job_id] = current
        return current
