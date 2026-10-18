"""Safety behavior exercised against real files through a bounded test transport."""
import hashlib
import os
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from src.cloud_models import ConnectionConfig, RemoteJobConfig
from src.config_manager import ConfigManager
from src.config import SyncDirection
from src.rclone_transport import CloudSyncError, FileEntry
from src.cloud_sync import CloudSyncRunner


class FilesTransport:
    def test(self, connection):
        if not Path(connection.root).is_dir():
            raise CloudSyncError("Folder unavailable")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def inventory(self, fs, *, allow_missing=False):
        root = Path(fs)
        if not root.exists():
            if allow_missing:
                return {}
            raise CloudSyncError("Folder unavailable")
        return {p.relative_to(root).as_posix(): FileEntry(p.stat().st_size, p.stat().st_mtime,
                {"sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
                for p in root.rglob("*") if p.is_file()}

    def copy(self, source, destination, *, paths=None, **kwargs):
        for name in paths if paths is not None else self.inventory(source):
            target = Path(destination) / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(Path(source) / name, target)

    def check(self, source, destination, *, paths=None):
        before, after = self.inventory(source), self.inventory(destination)
        for name in paths if paths is not None else before:
            if name not in after or before[name].same_content(after[name]) is not True:
                raise CloudSyncError("Content verification failed")


@pytest.fixture
def setup(tmp_path):
    local, remote = tmp_path / "local", tmp_path / "remote"
    local.mkdir()
    remote.mkdir()
    config = ConfigManager(Path(__file__).resolve().parents[1] / "packaging/default-config.json").load()
    config = replace(config, folders=[], general=replace(config.general, dry_run=False),
        connections=[ConnectionConfig("fixture", "Fixture", "local", str(remote))],
        remote_jobs=[RemoteJobConfig("saves", "Saves", str(local), "fixture", "game", minimum_sync_percentage=0)])
    return config, local, remote / "game", tmp_path / "state"


def runner(setup, **changes):
    config, local, remote, state = setup
    config = replace(config, **changes)
    return CloudSyncRunner(config, state, transport_factory=lambda root: FilesTransport())


def test_upload_is_additive_protects_newer_and_snapshots_all_remote_files(setup):
    config, local, remote, state = setup
    remote.mkdir()
    (remote / "save").write_text("old")
    (remote / "extra").write_text("keep")
    (remote / "newer").write_text("newer remote")
    (local / "save").write_text("updated")
    (local / "newer").write_text("old local")
    os.utime(remote / "save", (100, 100))
    os.utime(local / "newer", (100, 100))
    engine = runner(setup)
    assert engine.run(SyncDirection.UPLOAD)[0].succeeded
    assert (remote / "save").read_text() == "updated"
    assert (remote / "newer").read_text() == "newer remote"
    assert (remote / "extra").read_text() == "keep"
    snapshots = engine.list_snapshots("saves")
    assert len(snapshots) == 1
    restored = local.parent / "restored"
    engine.restore("saves", snapshots[0]["run_id"], restored)
    assert (restored / "save").read_text() == "old"
    assert (restored / "extra").read_text() == "keep"


def test_dry_run_has_no_files_snapshot_or_state_changes(setup):
    config, local, remote, state = setup
    (local / "save").write_text("new")
    engine = runner(setup, general=replace(config.general, dry_run=True))
    assert engine.run(SyncDirection.UPLOAD)[0].succeeded
    assert not remote.exists()
    assert not state.exists()
    assert engine.list_snapshots("saves") == []


def test_snapshot_verification_failure_blocks_upload_and_never_offers_restore(setup):
    config, local, remote, state = setup
    remote.mkdir()
    (local / "save").write_text("new")
    (remote / "save").write_text("old")
    os.utime(remote / "save", (100, 100))
    class BadSnapshot(FilesTransport):
        def check(self, source, destination, **kwargs):
            raise CloudSyncError("Verification failed")
    engine = CloudSyncRunner(config, state, transport_factory=lambda root: BadSnapshot())
    assert not engine.run(SyncDirection.UPLOAD)[0].succeeded
    assert (remote / "save").read_text() == "old"
    assert engine.list_snapshots("saves") == []


def test_deferred_upload_starts_no_transport_and_resumes_before_incoming_download(setup):
    config, local, remote, state = setup
    remote.mkdir()
    (remote / "incoming").write_text("remote addition")
    def forbidden(root):
        raise AssertionError("Network process started during shutdown")
    engine = CloudSyncRunner(config, state, transport_factory=forbidden)
    (local / "save").write_text("pending local changes")
    assert engine.run(SyncDirection.UPLOAD, defer=True)[0].succeeded
    live_copies = []
    class Recording(FilesTransport):
        def copy(self, source, destination, **kwargs):
            if str(destination) in {str(local), str(remote)}:
                live_copies.append((source, destination))
            return super().copy(source, destination, **kwargs)
    engine = CloudSyncRunner(config, state, transport_factory=lambda root: Recording())
    result = engine.run(SyncDirection.DOWNLOAD)
    assert len(result) == 1 and result[0].succeeded
    assert "pending upload" in result[0].message.lower()
    assert (remote / "save").read_text() == "pending local changes"
    assert (local / "save").read_text() == "pending local changes"
    assert (local / "incoming").read_text() == "remote addition"
    assert live_copies == [(str(local), str(remote)), (str(remote), str(local))]


def test_bidirectional_conflict_preserves_both_versions_and_baseline(setup):
    config, local, remote, state = setup
    engine = runner(setup, remote_jobs=[replace(config.remote_jobs[0], bidirectional=True, verify_after_sync=False)])
    (local / "save").write_text("base")
    assert engine.run(SyncDirection.UPLOAD)[0].succeeded
    baseline = (state / "state.json").read_bytes()
    (local / "save").write_text("local modified")
    (remote / "save").write_text("remote modified")
    result = engine.run(SyncDirection.DOWNLOAD)[0]
    assert not result.succeeded and "conflict" in result.message.lower()
    assert (local / "save").read_text() == "local modified"
    assert (remote / "save").read_text() == "remote modified"
    import json
    assert json.loads((state / "state.json").read_text())["jobs"]["saves"]["baseline"] == json.loads(baseline)["jobs"]["saves"]["baseline"]


def test_bidirectional_no_delete_and_one_sided_changes(setup):
    config, local, remote, state = setup
    engine = runner(setup, remote_jobs=[replace(config.remote_jobs[0], bidirectional=True)])
    (local / "save").write_text("base")
    assert engine.run(SyncDirection.UPLOAD)[0].succeeded
    (remote / "save").write_text("remote changed")
    assert engine.run(SyncDirection.UPLOAD)[0].succeeded
    assert (local / "save").read_text() == "remote changed"
    (local / "save").unlink()
    assert engine.run(SyncDirection.DOWNLOAD)[0].succeeded
    assert (local / "save").read_text() == "remote changed"


def test_restore_rejects_nonempty_target_and_unknown_snapshot(setup):
    engine = runner(setup)
    with pytest.raises((ValueError, CloudSyncError)):
        engine.restore("saves", "../escape", setup[1])
    with pytest.raises(CloudSyncError):
        engine.restore("saves", "r0000", setup[1])


def test_missing_connection_root_is_not_treated_as_empty_destination(setup):
    config, local, remote, state = setup
    remote.parent.rmdir()
    (local / "save").write_text("new")
    assert not runner(setup).run(SyncDirection.UPLOAD)[0].succeeded
    assert not remote.exists()


def test_threshold_failure_is_isolated_and_can_be_overridden(setup):
    config, local, remote, state = setup
    remote.mkdir()
    (local / "one").write_text("1")
    for i in range(4):
        (remote / str(i)).write_text(str(i))
    engine = runner(setup, remote_jobs=[replace(config.remote_jobs[0], minimum_sync_percentage=80)])
    assert not engine.run(SyncDirection.UPLOAD)[0].succeeded
    outcome = engine.run(SyncDirection.UPLOAD, ignore_threshold_for="saves")[0]
    assert outcome.succeeded and outcome.threshold_bypassed


@pytest.mark.parametrize("record", [
    {"identity": {}, "baseline": None, "pending": None, "snapshots": []},
    {"identity": None, "baseline": None, "pending": None, "snapshots": []},
    {"identity": {}, "baseline": {"local": [], "remote": {}}, "pending": None, "snapshots": []},
    {"identity": {}, "baseline": None, "pending": {"direction": "delete"}, "snapshots": []},
])
def test_corrupt_job_state_blocks_sync_instead_of_resetting(setup, record):
    import json
    config, local, remote, state = setup
    state.mkdir()
    (state / "state.json").write_text(json.dumps({"version": 1, "jobs": {"saves": record}}))
    original = (state / "state.json").read_bytes()
    (local / "save").write_text("data")
    outcome = runner(setup).run(SyncDirection.UPLOAD)[0]
    assert not outcome.succeeded and "state" in outcome.message.lower()
    assert not remote.exists()
    assert (state / "state.json").read_bytes() == original


@pytest.mark.parametrize("field,value", [
    ("baseline", {"local": {"save": {"size": -1}}, "remote": {}}),
    ("pending", {"direction": "upload", "created_at": "invalid"}),
    ("snapshots", [{"run_id": "../escape", "created_at": "2026-10-18T00:00:00Z", "files": {}}]),
])
def test_nested_corrupt_state_is_rejected_with_valid_endpoint_identity(setup, field, value):
    import json
    config, local, remote, state = setup
    (local / "save").write_text("base")
    engine = runner(setup)
    assert engine.run(SyncDirection.UPLOAD)[0].succeeded
    data = json.loads((state / "state.json").read_text())
    data["jobs"]["saves"][field] = value
    (state / "state.json").write_text(json.dumps(data))
    before = (state / "state.json").read_bytes()
    (local / "save").write_text("new")
    result = engine.run(SyncDirection.UPLOAD)[0]
    assert not result.succeeded and "state" in result.message.lower()
    assert (state / "state.json").read_bytes() == before
    assert (remote / "save").read_text() == "base"


def test_failed_copy_keeps_pending_and_does_not_advance_baseline(setup):
    import json
    config, local, remote, state = setup
    (local / "save").write_text("base")
    engine = runner(setup)
    assert engine.run(SyncDirection.UPLOAD)[0].succeeded
    baseline = json.loads((state / "state.json").read_text())["jobs"]["saves"]["baseline"]
    (local / "save").write_text("updated")
    class Interrupted(FilesTransport):
        def copy(self, source, destination, **kwargs):
            if str(destination) == str(remote):
                raise CloudSyncError("Interrupted transfer; retry")
            return super().copy(source, destination, **kwargs)
    failing = CloudSyncRunner(config, state, transport_factory=lambda root: Interrupted())
    assert not failing.run(SyncDirection.UPLOAD)[0].succeeded
    record = json.loads((state / "state.json").read_text())["jobs"]["saves"]
    assert record["baseline"] == baseline and record["pending"]["direction"] == "upload"
    assert engine.run(SyncDirection.UPLOAD)[0].succeeded
    assert (remote / "save").read_text() == "updated"


def test_changed_endpoint_invalidates_bidirectional_baseline(setup):
    config, local, remote, state = setup
    config = replace(config, remote_jobs=[replace(config.remote_jobs[0], bidirectional=True)])
    (local / "save").write_text("base")
    engine = CloudSyncRunner(config, state, transport_factory=lambda root: FilesTransport())
    assert engine.run(SyncDirection.UPLOAD)[0].succeeded
    replacement = remote.parent / "other"
    replacement.mkdir()
    (replacement / "save").write_text("different account data")
    config = replace(config, remote_jobs=[replace(config.remote_jobs[0], remote_path="other")])
    moved = CloudSyncRunner(config, state, transport_factory=lambda root: FilesTransport())
    outcome = moved.run(SyncDirection.DOWNLOAD)[0]
    assert not outcome.succeeded and "conflict" in outcome.message.lower()
    assert (local / "save").read_text() == "base"


def test_download_preserves_newer_local_and_destination_only_files(setup):
    config, local, remote, state = setup
    remote.mkdir()
    (local / "save").write_text("newer local")
    (local / "extra").write_text("preserve")
    (remote / "save").write_text("older remote")
    (remote / "incoming").write_text("download")
    os.utime(remote / "save", (100, 100))
    assert runner(setup).run(SyncDirection.DOWNLOAD)[0].succeeded
    assert (local / "save").read_text() == "newer local"
    assert (local / "extra").read_text() == "preserve"
    assert (local / "incoming").read_text() == "download"


def test_native_rclone_upload_snapshot_restore_and_bidirectional_conflict(setup):
    from src.cloud_credentials import CredentialStore
    from src.rclone_transport import RcloneTransport, rclone_executable
    try:
        executable = rclone_executable()
    except CloudSyncError:
        pytest.skip("Prepare the pinned rclone binary for native acceptance")
    config, local, remote, state = setup
    config = replace(config, remote_jobs=[replace(config.remote_jobs[0], bidirectional=True)])
    def factory(root):
        credentials = CredentialStore(root, protect=lambda value: value[::-1], unprotect=lambda value: value[::-1])
        return RcloneTransport(root, executable=executable, credentials=credentials)
    engine = CloudSyncRunner(config, state, transport_factory=factory)
    (local / "save").write_text("base")
    first = engine.run(SyncDirection.UPLOAD)[0]
    assert first.succeeded, first.message
    (local / "save").write_text("local modified")
    second = engine.run(SyncDirection.UPLOAD)[0]
    assert second.succeeded, second.message
    snapshots = engine.list_snapshots("saves")
    assert len(snapshots) == 1
    target = local.parent / "recovered"
    engine.restore("saves", snapshots[0]["run_id"], target)
    assert (target / "save").read_text() == "base"
    (local / "save").write_text("local conflict")
    (remote / "save").write_text("remote conflict")
    result = engine.run(SyncDirection.DOWNLOAD)[0]
    assert not result.succeeded and "conflict" in result.message.lower()
    assert (local / "save").read_text() == "local conflict"
    assert (remote / "save").read_text() == "remote conflict"


def test_empty_source_still_respects_threshold_when_destination_has_data(setup):
    config, local, remote, state = setup
    remote.mkdir()
    (remote / "save").write_text("precious")
    engine = runner(setup, remote_jobs=[replace(config.remote_jobs[0], minimum_sync_percentage=80)])
    assert not engine.run(SyncDirection.UPLOAD)[0].succeeded
    assert engine.run(SyncDirection.UPLOAD, ignore_threshold_for="saves")[0].succeeded


def test_bidirectional_pending_recovery_preserves_conflicts_and_pending_work(setup):
    import json
    config, local, remote, state = setup
    engine = runner(setup, remote_jobs=[replace(config.remote_jobs[0], bidirectional=True)])
    (local / "save").write_text("base")
    assert engine.run(SyncDirection.UPLOAD)[0].succeeded
    (local / "save").write_text("local conflict")
    (remote / "save").write_text("remote conflict")
    assert engine.run(SyncDirection.UPLOAD, defer=True)[0].succeeded
    result = engine.run(SyncDirection.DOWNLOAD)[0]
    assert not result.succeeded and "conflict" in result.message.lower()
    assert (local / "save").read_text() == "local conflict"
    assert (remote / "save").read_text() == "remote conflict"
    assert json.loads((state / "state.json").read_text())["jobs"]["saves"]["pending"]["direction"] == "upload"


def test_failed_baseline_commit_does_not_publish_through_later_save(setup, monkeypatch):
    import json
    from src.cloud_state import CloudState
    config, local, remote, state = setup
    (local / "save").write_text("base")
    engine = runner(setup)
    assert engine.run(SyncDirection.UPLOAD)[0].succeeded
    baseline = json.loads((state / "state.json").read_text())["jobs"]["saves"]["baseline"]
    (local / "save").write_text("new local")
    original_save = CloudState.save
    instances = []
    def save(self):
        if self.data["jobs"]["saves"]["pending"] is None:
            instances.append(self)
            raise OSError("Disk write failed")
        return original_save(self)
    monkeypatch.setattr(CloudState, "save", save)
    assert not engine.run(SyncDirection.UPLOAD)[0].succeeded
    assert instances
    original_save(instances[-1])
    record = json.loads((state / "state.json").read_text())["jobs"]["saves"]
    assert record["baseline"] == baseline
    assert record["pending"]["direction"] == "upload"


def test_restore_checks_published_snapshot_when_source_changes_during_copy(setup):
    config, local, remote, state = setup
    remote.mkdir()
    (remote / "save").write_text("original snapshot")
    (local / "save").write_text("new local")
    os.utime(remote / "save", (100, 100))
    engine = runner(setup)
    assert engine.run(SyncDirection.UPLOAD)[0].succeeded
    snapshot = engine.list_snapshots("saves")[0]
    class MutatingSnapshot(FilesTransport):
        def copy(self, source, destination, **kwargs):
            (Path(source) / "save").write_text("changed after verification")
            return super().copy(source, destination, **kwargs)
    engine = CloudSyncRunner(config, state, transport_factory=lambda root: MutatingSnapshot())
    with pytest.raises(CloudSyncError, match="[Rr]ecovery|[Ss]napshot"):
        engine.restore("saves", snapshot["run_id"], local.parent / "recovery")


@pytest.mark.parametrize("digest", ["UNSUPPORTED", "deadbeef", True, "g" * 64])
def test_invalid_fallback_hash_stops_without_writing_baseline(setup, digest):
    config, local, remote, state = setup
    (local / "save").write_text("data")
    class UnsupportedHashes(FilesTransport):
        def inventory(self, fs, **kwargs):
            return {name: FileEntry(entry.size, entry.modified, {})
                    for name, entry in super().inventory(fs, **kwargs).items()}
        def operation(self, *args, **kwargs):
            return {"hash": digest}
    engine = CloudSyncRunner(config, state, transport_factory=lambda root: UnsupportedHashes())
    assert not engine.run(SyncDirection.UPLOAD)[0].succeeded
    assert not (state / "state.json").exists()
    assert not remote.exists()


def test_valid_uppercase_fallback_hash_is_canonical_lowercase():
    class Hashes:
        def inventory(self, fs, **kwargs):
            return {"save": FileEntry(1, 100, {})}
        def operation(self, *args, **kwargs):
            return {"hash": "A" * 64}
    assert CloudSyncRunner._inventory(Hashes(), "fixture")["save"].hashes == {"sha256": "a" * 64}


def test_failed_pending_recovery_blocks_requested_direction_and_keeps_pending(setup):
    import json
    config, local, remote, state = setup
    (local / "save").write_text("pending local")
    assert runner(setup).run(SyncDirection.UPLOAD, defer=True)[0].succeeded
    copies = []
    class Interrupted(FilesTransport):
        def copy(self, source, destination, **kwargs):
            copies.append((source, destination))
            raise CloudSyncError("Interrupted transfer")
    engine = CloudSyncRunner(config, state, transport_factory=lambda root: Interrupted())
    result = engine.run(SyncDirection.DOWNLOAD)[0]
    assert not result.succeeded and "pending upload" in result.message.lower()
    assert copies == [(str(local), str(remote))]
    assert (local / "save").read_text() == "pending local"
    assert json.loads((state / "state.json").read_text())["jobs"]["saves"]["pending"]["direction"] == "upload"


def test_snapshot_restore_rejects_malformed_persisted_baseline(setup):
    import json
    config, local, remote, state = setup
    remote.mkdir()
    (remote / "save").write_text("old")
    (local / "save").write_text("new")
    os.utime(remote / "save", (100, 100))
    engine = runner(setup)
    assert engine.run(SyncDirection.UPLOAD)[0].succeeded
    snapshot = engine.list_snapshots("saves")[0]
    data = json.loads((state / "state.json").read_text())
    data["jobs"]["saves"]["baseline"]["local"]["save"]["hashes"]["sha256"] = "UNSUPPORTED"
    (state / "state.json").write_text(json.dumps(data))
    target = local.parent / "recovery"
    with pytest.raises(CloudSyncError, match="state"):
        engine.restore("saves", snapshot["run_id"], target)
    assert not target.exists()


def test_dry_run_pending_recovery_changes_neither_pending_state_nor_files(setup):
    config, local, remote, state = setup
    (local / "save").write_text("pending local")
    assert runner(setup).run(SyncDirection.UPLOAD, defer=True)[0].succeeded
    before = (state / "state.json").read_bytes()
    engine = runner(setup, general=replace(config.general, dry_run=True))
    result = engine.run(SyncDirection.DOWNLOAD)[0]
    assert result.succeeded and "pending upload" in result.message.lower()
    assert "waits" in result.message.lower()
    assert not remote.exists()
    assert (state / "state.json").read_bytes() == before


@pytest.mark.parametrize("bidirectional", [False, True])
@pytest.mark.parametrize("left,right", [("save.txt", "SAVE.txt"), ("Game/local", "game/remote"), ("Game", "Game/remote")])
def test_cross_endpoint_aliases_stop_before_any_write(setup, bidirectional, left, right):
    config, local, remote, state = setup
    remote.mkdir()
    for root, name, content, modified in ((local, left, "local version", 100), (remote, right, "remote version", 200)):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        os.utime(path, (modified, modified))
    copies = []
    class Recording(FilesTransport):
        def copy(self, *args, **kwargs):
            copies.append(args)
            return super().copy(*args, **kwargs)
    config = replace(config, remote_jobs=[replace(config.remote_jobs[0], bidirectional=bidirectional)])
    result = CloudSyncRunner(config, state, lambda root: Recording()).run(SyncDirection.UPLOAD)[0]
    assert not result.succeeded
    assert not copies
    assert (local / left).read_text() == "local version"
    assert (remote / right).read_text() == "remote version"
    assert not (state / "state.json").exists()
