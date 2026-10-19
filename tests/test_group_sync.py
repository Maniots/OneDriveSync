"""Whole-folder hierarchy behavior over disposable local filesystem endpoints."""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import shutil

import pytest

from src.cloud_models import ConnectionConfig, RemoteJobConfig
from src.config import FolderSyncConfig, SyncDirection
from src.config_manager import ConfigManager
from src.group_sync import GroupSyncRunner
from src.rclone_transport import CloudNotFound, CloudSyncError, CloudUnavailable, FileEntry
from src.sync_groups import SyncGroupConfig, SyncDestinationConfig


class FilesTransport:
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def test(self, connection):
        if not Path(connection.root).is_dir(): raise CloudUnavailable("Root unavailable")
    def inventory(self, fs, *, allow_missing=False):
        root = Path(fs)
        if not root.is_dir():
            if allow_missing: return {}
            raise CloudNotFound("Activity absent")
        return {p.relative_to(root).as_posix(): FileEntry(p.stat().st_size, p.stat().st_mtime,
            {"sha256": hashlib.sha256(p.read_bytes()).hexdigest()}) for p in root.rglob("*") if p.is_file()}
    def copy(self, source, destination, *, paths=None, **kwargs):
        for name in paths if paths is not None else self.inventory(source):
            target = Path(destination) / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(Path(source) / name, target)
    def check(self, source, destination, *, paths=None):
        before, after = self.inventory(source), self.inventory(destination)
        assert all(name in after and before[name].same_content(after[name]) is True
                   for name in (paths if paths is not None else before))


@pytest.fixture
def setup(tmp_path):
    config = ConfigManager(Path(__file__).resolve().parents[1] / "packaging/default-config.json").load()
    local, first, second = [tmp_path / name for name in ("source", "first", "second")]
    for path in (local, first, second): path.mkdir()
    leaf = FolderSyncConfig("folder", "Folder", True, str(local), str(first / "game"), 0, True, True)
    job = RemoteJobConfig("remote", "Remote", str(local), "provider", "game", minimum_sync_percentage=0)
    group = SyncGroupConfig("group", "Saves", str(local), [SyncDestinationConfig("folder"), SyncDestinationConfig("remote")])
    config = replace(config, folders=[leaf], connections=[ConnectionConfig("provider", "Provider", "local", str(second))],
                     remote_jobs=[job], sync_groups=[group], general=replace(config.general, dry_run=False))
    return config, local, first / "game", second / "game", tmp_path / "state"


def engine(setup, client=None, **changes):
    config, _, _, _, state = setup
    config = replace(config, **changes)
    return GroupSyncRunner(config, state, transport_factory=lambda root: client or FilesTransport())


def run(setup, direction="upload", client=None, group=None, **changes):
    return engine(setup, client, **changes).run(group or setup[0].sync_groups[0], SyncDirection(direction))


def test_mixed_upload_verifies_every_destination_and_keeps_leaf_ids(setup):
    config, local, first, second, state = setup
    (local / "save").write_text("generation one")
    results = run(setup)
    assert [item.folder_id for item in results] == ["folder", "remote", "group"]
    assert all(item.succeeded for item in results)
    assert (first / "save").read_bytes() == (second / "save").read_bytes() == (local / "save").read_bytes()
    ledger = json.loads((state / "groups.json").read_text())["groups"]["group"]
    assert ledger["pending"] is None
    assert all(item["status"] == "complete" for item in ledger["destinations"].values())


def test_partial_upload_cannot_download_old_copy_even_with_unknown_opt_in(setup):
    config, local, first, second, state = setup
    (local / "save").write_text("good")
    class Broken(FilesTransport):
        def copy(self, source, destination, **kwargs):
            raise CloudSyncError("Upload refused")
    result = run(setup, client=Broken())
    assert result[0].succeeded and not result[-1].succeeded
    assert "1/2" in result[-1].message
    result = run(setup, "download", group=replace(config.sync_groups[0], allow_untracked_download=True))
    assert not result[-1].succeeded and "pending upload" in result[-1].message.lower()
    assert (local / "save").read_text() == "good"


def test_missing_first_source_falls_back_as_whole_folder_with_opt_in(setup):
    config, local, first, second, state = setup
    second.mkdir()
    (second / "save").write_text("remote")
    result = run(setup, "download", group=replace(config.sync_groups[0], allow_untracked_download=True))
    assert result[-1].succeeded
    assert "Remote" in result[-1].message and "absent" in result[-1].message.lower()
    assert (local / "save").read_text() == "remote"


def test_existing_empty_first_is_not_a_fallback(setup):
    config, local, first, second, state = setup
    first.mkdir(); second.mkdir()
    (local / "keep").write_text("keep")
    (second / "incoming").write_text("never")
    result = run(setup, "download", group=replace(config.sync_groups[0], allow_untracked_download=True))
    assert result[-1].succeeded and "empty" in result[-1].message.lower()
    assert not (local / "incoming").exists() and (local / "keep").read_text() == "keep"


def test_unknown_requires_explicit_opt_in(setup):
    _, local, first, _, _ = setup
    first.mkdir(); (first / "save").write_text("unknown")
    result = run(setup, "download")
    assert not result[-1].succeeded and "unknown" in result[-1].message.lower()
    assert not (local / "save").exists()


def test_newer_destination_skipped_by_leaf_is_not_published_complete(setup):
    _, local, first, _, state = setup
    first.mkdir()
    (first / "save").write_text("new remote")
    (local / "save").write_text("old local")
    os.utime(local / "save", (100, 100))
    result = run(setup)
    assert not result[-1].succeeded
    assert (first / "save").read_text() == "new remote"
    ledger = json.loads((state / "groups.json").read_text())["groups"]["group"]
    assert ledger["destinations"]["folder"]["status"] == "incomplete"


def test_group_dry_run_changes_neither_state_nor_files(setup):
    config, local, first, second, state = setup
    (local / "save").write_text("planned")
    result = run(setup, general=replace(config.general, dry_run=True))
    assert all(item.succeeded for item in result)
    assert not first.exists() and not second.exists() and not state.exists()


def test_deferral_never_creates_transport_and_blocks_opposite_direction(setup):
    config, _, _, _, state = setup
    def forbidden(root): raise AssertionError("No process during shutdown")
    coordinator = GroupSyncRunner(config, state, transport_factory=forbidden)
    assert coordinator.run(config.sync_groups[0], "upload", defer=True)[-1].succeeded
    result = coordinator.run(config.sync_groups[0], "download")
    assert not result[-1].succeeded and "pending upload" in result[-1].message.lower()


def test_source_changes_stop_fanout_and_leave_attempt_incomplete(setup):
    from src.sync_manager import SyncManager
    config, local, first, second, state = setup
    (local / "save").write_text("initial")
    leaf_runner = SyncManager(config)._sync_single_folder
    def mutate(leaf, direction):
        result = leaf_runner(leaf, direction)
        (local / "save").write_text("changed during upload")
        return result
    result = GroupSyncRunner(config, state, local_runner=mutate,
                 transport_factory=lambda root: FilesTransport()).run(config.sync_groups[0], "upload")
    assert not result[-1].succeeded and len(result) == 2
    assert not second.exists()
    record = json.loads((state / "groups.json").read_text())["groups"]["group"]
    assert record["pending"]["direction"] == "upload"
    assert all(item["status"] == "incomplete" for item in record["destinations"].values())


def test_cancellation_finishes_current_destination_but_never_starts_next(setup):
    import threading
    from src.sync_manager import SyncManager
    config, local, first, second, state = setup
    (local / "save").write_text("generation")
    cancellation = threading.Event()
    leaf_runner = SyncManager(config)._sync_single_folder
    def cancel(leaf, direction):
        result = leaf_runner(leaf, direction)
        cancellation.set()
        return result
    result = GroupSyncRunner(config, state, local_runner=cancel, cancel_event=cancellation,
                 transport_factory=lambda root: FilesTransport()).run(config.sync_groups[0], "upload")
    assert result[0].succeeded and not result[-1].succeeded
    assert not second.exists()
    record = json.loads((state / "groups.json").read_text())["groups"]["group"]
    assert record["destinations"]["folder"]["status"] == "complete"
    assert record["destinations"]["remote"]["status"] == "incomplete"


@pytest.mark.parametrize("unavailable,allow,success", [(True, False, False), (True, True, True), (False, True, False)])
def test_only_typed_unavailability_can_opt_in_to_fallback(setup, unavailable, allow, success):
    config, local, first, second, state = setup
    # Put remote first so its account-root test is authoritative.
    group = replace(config.sync_groups[0], destinations=list(reversed(config.sync_groups[0].destinations)),
                    fallback_on_unavailable=allow, allow_untracked_download=True)
    first.mkdir(); (first / "save").write_text("fallback")
    class Inaccessible(FilesTransport):
        def test(self, connection):
            if unavailable: raise CloudUnavailable("Network offline")
            raise CloudSyncError("Account access denied")
    result = run(setup, "download", client=Inaccessible(), group=group)
    assert result[-1].succeeded is success
    assert (local / "save").exists() is success


def test_download_error_after_write_never_tries_another_source_and_pins_retry(setup):
    config, local, first, second, state = setup
    first.mkdir(); second.mkdir()
    (first / "first").write_text("first source")
    (second / "second").write_text("must not merge")
    group = replace(config.sync_groups[0], allow_untracked_download=True)
    def partial(leaf, direction):
        (local / "first").write_text("partial")
        raise CloudUnavailable("Connection dropped after first write")
    coordinator = GroupSyncRunner(config, state, local_runner=partial, transport_factory=lambda root: FilesTransport())
    result = coordinator.run(group, "download")
    assert not result[-1].succeeded and not (local / "second").exists()
    shutil.rmtree(first)
    result = run(setup, "download", group=group)
    assert not result[-1].succeeded and not (local / "second").exists()
    assert "pending download source" in result[-1].message.lower()


def test_inventory_change_before_writing_download_blocks_local_write(setup):
    config, local, first, second, state = setup
    second.mkdir(); (second / "save").write_text("first")
    group = replace(config.sync_groups[0], destinations=list(reversed(config.sync_groups[0].destinations)),
                    allow_untracked_download=True)
    class Changes(FilesTransport):
        count = 0
        def inventory(self, fs, **kwargs):
            if str(fs) == str(second):
                self.count += 1
                if self.count == 2: (second / "save").write_text("changed")
            return super().inventory(fs, **kwargs)
    result = run(setup, "download", group=group, client=Changes())
    assert not result[-1].succeeded and "changed" in result[-1].message
    assert not (local / "save").exists()


def test_group_ledger_write_failure_prevents_all_leaf_writes(setup, monkeypatch):
    from src.group_state import GroupState
    _, local, first, second, state = setup
    (local / "save").write_text("source")
    def fail(self): raise OSError("disk full")
    monkeypatch.setattr(GroupState, "save", fail)
    assert not run(setup)[-1].succeeded
    assert not first.exists() and not second.exists()


def test_corrupt_ledger_never_becomes_untracked_opt_in(setup):
    config, local, first, second, state = setup
    first.mkdir(); (first / "save").write_text("remote")
    state.mkdir(); (state / "groups.json").write_text('{"version":999,"groups":{}}')
    result = run(setup, "download", group=replace(config.sync_groups[0], allow_untracked_download=True))
    assert not result[-1].succeeded and not (local / "save").exists()


def test_known_prior_source_never_becomes_untracked_opt_in(setup):
    config, local, first, second, state = setup
    (local / "save").write_text("first generation")
    assert run(setup)[-1].succeeded
    (local / "save").write_text("second generation")
    # Only second receives this generation; the first copy is known prior.
    group = replace(config.sync_groups[0], destinations=[replace(config.sync_groups[0].destinations[0], upload_enabled=False),
                                                         config.sync_groups[0].destinations[1]], allow_untracked_download=True)
    assert run(setup, group=group)[-1].succeeded
    result = run(setup, "download", group=group)
    assert not result[-1].succeeded and "prior generation" in result[-1].message.lower()
    assert (local / "save").read_text() == "second generation"


def test_all_leaf_pending_is_checked_before_first_local_upload(setup):
    from src.cloud_state import CloudState
    from src.cloud_sync import CloudSyncRunner
    config, local, first, second, state = setup
    (local / "save").write_text("source")
    ledger = CloudState(state)
    cloud = CloudSyncRunner(config, state)
    record = ledger.job("remote", cloud._identity(config.remote_jobs[0], config.connections[0]))
    record["pending"] = {"direction": "download", "created_at": "2026-10-19T00:00:00+00:00"}
    ledger.save()
    result = run(setup)
    assert not result[-1].succeeded and "pending download" in result[-1].message
    assert not first.exists() and not second.exists()


def test_permission_error_is_not_absence_or_unavailable_fallback(setup, monkeypatch):
    config, local, first, second, state = setup
    second.mkdir(); (second / "save").write_text("not used")
    original = Path.stat
    def deny(path, *args, **kwargs):
        if path == first:
            raise PermissionError("Denied")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "stat", deny)
    group = replace(config.sync_groups[0], allow_untracked_download=True, fallback_on_unavailable=True)
    assert not run(setup, "download", group=group)[-1].succeeded
    assert not (local / "save").exists()


def test_manager_excludes_owned_leaves_even_when_group_disabled(setup):
    from src.sync_manager import SyncManager
    config, local, first, second, state = setup
    (local / "save").write_text("source")
    config = replace(config, sync_groups=[replace(config.sync_groups[0], enabled=False)])
    assert SyncManager(config, cloud_root=state).run_shutdown_sync() == []
    assert not first.exists() and not second.exists()


def test_changed_source_after_partial_download_cannot_merge_generations_on_retry(setup):
    config, local, first, second, state = setup
    first.mkdir(); (first / "old_save").write_text("old generation")
    group = replace(config.sync_groups[0], allow_untracked_download=True)
    def partial(leaf, direction):
        shutil.copy2(first / "old_save", local / "old_save")
        raise CloudSyncError("Interrupted")
    coordinator = GroupSyncRunner(config, state, local_runner=partial, transport_factory=lambda root: FilesTransport())
    assert not coordinator.run(group, "download")[-1].succeeded
    (first / "old_save").unlink(); (first / "different_save").write_text("new generation")
    result = run(setup, "download", group=group)
    assert not result[-1].succeeded and "source changed" in result[-1].message.lower()
    assert not (local / "different_save").exists()


def test_known_prior_evidence_survives_regrouping_and_leaf_rename(setup):
    config, local, first, second, state = setup
    (local / "save").write_text("old")
    assert run(setup)[-1].succeeded
    (local / "save").write_text("new")
    group = replace(config.sync_groups[0], destinations=[replace(config.sync_groups[0].destinations[0], upload_enabled=False),
                                                         config.sync_groups[0].destinations[1]])
    assert run(setup, group=group)[-1].succeeded
    renamed_leaf = replace(config.folders[0], id="renamed")
    new_group = replace(group, id="newgroup", allow_untracked_download=True,
                        destinations=[SyncDestinationConfig("renamed")])
    changed = replace(config, folders=[renamed_leaf], sync_groups=[new_group])
    result = GroupSyncRunner(changed, state, transport_factory=lambda root: FilesTransport()).run(new_group, "download")
    assert not result[-1].succeeded and "prior generation" in result[-1].message.lower()
    assert (local / "save").read_text() == "new"


def test_missing_account_root_never_counts_as_activity_absence(setup):
    config, local, first, second, state = setup
    first.mkdir(); (first / "save").write_text("must not use")
    group = replace(config.sync_groups[0], destinations=list(reversed(config.sync_groups[0].destinations)),
                    fallback_on_unavailable=True, allow_untracked_download=True)
    class MissingRoot(FilesTransport):
        def test(self, connection): raise CloudNotFound("Account root missing")
    result = run(setup, "download", group=group, client=MissingRoot())
    assert not result[-1].succeeded and "root" in result[-1].message.lower()
    assert not (local / "save").exists()


def test_pending_leaf_without_immutable_group_evidence_never_chooses_other_source(setup):
    from src.cloud_state import CloudState
    from src.cloud_sync import CloudSyncRunner
    config, local, first, second, state = setup
    first.mkdir(); second.mkdir()
    (first / "higher").write_text("not chosen")
    (second / "pending").write_text("in progress")
    cloud_state = CloudState(state)
    cloud = CloudSyncRunner(config, state)
    record = cloud_state.job("remote", cloud._identity(config.remote_jobs[0], config.connections[0]))
    record["pending"] = {"direction": "download", "created_at": "2026-10-19T00:00:00+00:00"}
    cloud_state.save()
    result = run(setup, "download", group=replace(config.sync_groups[0], allow_untracked_download=True))
    assert not result[-1].succeeded and "original download" in result[-1].message.lower()
    assert not list(local.iterdir())


def test_disabling_failed_leaf_cannot_clear_group_pending_or_allow_download(setup):
    config, local, first, second, state = setup
    (local / "save").write_text("source")
    class Failed(FilesTransport):
        def copy(self, *args, **kwargs): raise CloudSyncError("Failed")
    assert not run(setup, client=Failed())[-1].succeeded
    changed = replace(config, remote_jobs=[replace(config.remote_jobs[0], enabled=False)])
    coordinator = GroupSyncRunner(changed, state, transport_factory=lambda root: FilesTransport())
    assert not coordinator.run(changed.sync_groups[0], "upload")[-1].succeeded
    result = coordinator.run(changed.sync_groups[0], "download")
    assert not result[-1].succeeded and "pending upload" in result[-1].message.lower()


def test_disabled_leaf_is_preserved_and_never_uploaded(setup):
    config, local, first, second, state = setup
    (local / "save").write_text("source")
    changed = replace(config, remote_jobs=[replace(config.remote_jobs[0], enabled=False)])
    coordinator = GroupSyncRunner(changed, state, transport_factory=lambda root: FilesTransport())
    assert coordinator.run(changed.sync_groups[0], "upload")[-1].succeeded
    assert first.is_dir() and not second.exists()


def test_nonrecursive_group_fails_before_any_file_or_evidence_write(setup):
    config, local, first, second, state = setup
    (local / "save").write_text("source")
    config = replace(config, copy_engine=replace(config.copy_engine, copy_subdirectories=False))
    outcomes = GroupSyncRunner(config, state).run(config.sync_groups[0], "upload")
    assert not outcomes[-1].succeeded and "Copy subdirectories" in outcomes[-1].message
    assert not first.exists() and not second.exists() and not state.exists()
