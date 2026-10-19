"""Atomic per-PC generation evidence, owned by the application's sync lock."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from copy import deepcopy
from datetime import datetime, timezone

from .cloud_models import validate_id
from .cloud_state import CloudState
from .rclone_transport import CloudSyncError


class GroupState:
    @staticmethod
    def _validate_identity(identity):
        if (not isinstance(identity, dict) or identity.get("kind") not in {"folder", "remote"}
                or any(not isinstance(identity.get(key), str) for key in
                       ("local_path", "root", "remote_path", "connection_id", "provider"))
                or not identity["local_path"] or not identity["root"]):
            raise ValueError("Invalid endpoint")

    def __init__(self, root):
        self.path = Path(root) / "groups.json"
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self.data = {"version": 1, "groups": {}}
        except (OSError, ValueError):
            raise CloudSyncError("Group evidence cannot be read. Recover groups.json before synchronizing.") from None
        try:
            if (not isinstance(self.data, dict) or self.data.get("version") != 1
                    or not isinstance(self.data.get("groups"), dict)):
                raise ValueError("Unsupported state")
            for group_id, record in self.data["groups"].items():
                validate_id(group_id)
                if not isinstance(record["source"], str) or not record["source"]:
                    raise ValueError("Missing source")
                if record["generation"] is not None:
                    validate_id(record["generation"])
                if record["source_inventory"] is not None:
                    CloudState._validate_inventory(record["source_inventory"])
                pending = record["pending"]
                if pending is not None:
                    if pending["direction"] not in {"upload", "download"}:
                        raise ValueError("Invalid direction")
                    datetime.fromisoformat(pending["created_at"])
                    if not isinstance(pending.get("identities"), dict):
                        raise ValueError("Missing pending identities")
                    for identity in pending["identities"].values():
                        self._validate_identity(identity)
                    if pending.get("selected_id") is not None and pending["selected_id"] not in pending["identities"]:
                        raise ValueError("Invalid pending source")
                    if pending.get("selected_id") is not None:
                        CloudState._validate_inventory(pending["selected_inventory"])
                if not isinstance(record["destinations"], dict):
                    raise ValueError("Invalid destinations")
                for job_id, item in record["destinations"].items():
                    if not isinstance(job_id, str) or not job_id:
                        raise ValueError("Invalid job")
                    identity = item["identity"]
                    self._validate_identity(identity)
                    validate_id(item["generation"])
                    if item["status"] not in {"complete", "incomplete"}:
                        raise ValueError("Invalid completeness")
                    CloudState._validate_inventory(item["inventory"])
                if any(item["status"] == "incomplete" for item in record["destinations"].values()):
                    if not pending or pending["direction"] != "upload":
                        raise ValueError("Incomplete evidence must retain pending upload")
        except (ValueError, TypeError, KeyError, AttributeError):
            raise CloudSyncError("Group evidence is invalid or unsupported. Recover groups.json before synchronizing.") from None

    @staticmethod
    def pending(direction, identities):
        return {"direction": direction.value, "created_at": datetime.now(timezone.utc).isoformat(),
                "identities": identities}

    def bind(self, group, identities):
        records = self.data["groups"]
        inherited_prior = {}
        # Reassignment/renaming cannot hide an earlier incomplete attempt.
        for group_id, previous in records.items():
            matching_endpoint = any(item["identity"] in identities.values()
                                    for item in previous["destinations"].values())
            if previous["pending"]:
                matching_endpoint = matching_endpoint or any(
                    identity in identities.values() for identity in previous["pending"]["identities"].values())
            if group_id != group.id and (matching_endpoint or any(job_id in identities for job_id in previous["destinations"])):
                if previous["pending"] or any(item["status"] == "incomplete"
                                             for item in previous["destinations"].values()):
                    raise CloudSyncError("A destination has pending work in its previous group. Restore that group before retrying.")
            if group_id != group.id:
                for item in previous["destinations"].values():
                    if item["status"] == "complete" and item["generation"] != previous["generation"]:
                        for job_id, identity in identities.items():
                            if item["identity"] == identity:
                                inherited_prior[job_id] = deepcopy(item)
        record = records.get(group.id)
        if record and record["source"] != str(group.local_path_resolved):
            if record["pending"] or any(item["status"] == "incomplete" for item in record["destinations"].values()):
                raise CloudSyncError("This group has pending work for its previous local folder. Restore that configuration before retrying.")
            record = None
        if record is None:
            record = {"source": str(group.local_path_resolved), "generation": None, "source_inventory": None,
                      "pending": None, "destinations": {}}
            records[group.id] = record
        if record["pending"] and record["pending"]["identities"] != identities:
            raise CloudSyncError("This group has pending work for previous endpoints. Restore those destinations before retrying.")
        for job_id, item in list(record["destinations"].items()):
            if item["status"] == "incomplete" and identities.get(job_id) != item["identity"]:
                raise CloudSyncError("A destination has incomplete work for its previous endpoint. Restore it before retrying.")
            if identities.get(job_id) != item["identity"]:
                del record["destinations"][job_id]
        for job_id, item in inherited_prior.items():
            record["destinations"].setdefault(job_id, item)
        return record

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=".groups-", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(self.data, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)
