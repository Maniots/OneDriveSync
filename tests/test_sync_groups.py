"""Explicit ownership and immutable legacy configuration compatibility."""
from dataclasses import replace
from pathlib import Path

import pytest

from src.config import FolderSyncConfig
from src.config_manager import ConfigManager
from src.exceptions import ConfigurationError
from src.sync_groups import SyncDestinationConfig, SyncGroupConfig, validate_groups


@pytest.fixture
def grouped(tmp_path):
    config = ConfigManager(Path(__file__).resolve().parents[1] / "packaging/default-config.json").load()
    local = tmp_path / "source"
    leaves = [FolderSyncConfig(f"legacy {n}", f"Destination {n}", True, str(local),
               str(tmp_path / f"target{n}"), 0, True, True) for n in range(2)]
    group = SyncGroupConfig("saves", "Saves", str(local),
                            [SyncDestinationConfig(item.id) for item in leaves])
    return replace(config, folders=leaves, connections=[], remote_jobs=[], sync_groups=[group])


def test_group_roundtrip_preserves_legacy_leaf_ids_settings_and_priority(grouped, tmp_path):
    manager = ConfigManager(tmp_path / "config.json")
    manager.save(grouped)
    loaded = manager.load()
    assert loaded == grouped
    assert [d.job_id for d in loaded.sync_groups[0].destinations] == ["legacy 0", "legacy 1"]


@pytest.mark.parametrize("change", [
    lambda g: replace(g, destinations=[SyncDestinationConfig("missing")]),
    lambda g: replace(g, local_path=str(Path(g.local_path).parent / "other")),
    lambda g: replace(g, destinations=g.destinations * 2),
])
def test_rejects_invalid_ownership(grouped, change):
    with pytest.raises((ValueError, ConfigurationError)):
        validate_groups(replace(grouped, sync_groups=[change(grouped.sync_groups[0])]))


def test_cross_destination_overlap_rejected(grouped):
    bad = replace(grouped.folders[1], onedrive_path=str(Path(grouped.folders[0].onedrive_path) / "nested"))
    with pytest.raises((ValueError, ConfigurationError)):
        validate_groups(replace(grouped, folders=[grouped.folders[0], bad]))


def test_legacy_without_groups_saves_without_new_section(grouped, tmp_path):
    manager = ConfigManager(tmp_path / "config.json")
    manager.save(replace(grouped, sync_groups=[]))
    assert '"sync_groups"' not in manager.config_path.read_text()


@pytest.mark.parametrize("kwargs", [{"enabled": 1}, {"fallback_on_unavailable": "false"},
                                    {"allow_untracked_download": None}, {"name": " "}])
def test_strict_group_inputs(grouped, kwargs):
    with pytest.raises(ValueError):
        replace(grouped.sync_groups[0], **kwargs)


@pytest.mark.parametrize("edit", ["remove_group", "remove_destination", "endpoint", "participation", "source"])
def test_pending_topology_edits_cannot_replace_saved_configuration(grouped, tmp_path, edit):
    from src.group_sync import GroupSyncRunner
    manager = ConfigManager(tmp_path / "settings.json")
    manager.save(grouped)
    baseline = manager.config_path.read_bytes()
    state = manager.config_path.with_suffix(".cloud")
    assert GroupSyncRunner(grouped, state).run(grouped.sync_groups[0], "upload", defer=True)[-1].succeeded
    group = grouped.sync_groups[0]
    if edit == "remove_group":
        candidate = replace(grouped, sync_groups=[])
    elif edit == "remove_destination":
        candidate = replace(grouped, sync_groups=[replace(group, destinations=group.destinations[:1])])
    elif edit == "endpoint":
        candidate = replace(grouped, folders=[replace(grouped.folders[0], onedrive_path=str(tmp_path / "other")), grouped.folders[1]])
    elif edit == "participation":
        candidate = replace(grouped, sync_groups=[replace(group, destinations=[replace(group.destinations[0], upload_enabled=False), group.destinations[1]])])
    else:
        candidate = replace(grouped, folders=[replace(item, local_path=str(tmp_path / "newsource")) for item in grouped.folders],
                            sync_groups=[replace(group, local_path=str(tmp_path / "newsource"))])
    with pytest.raises(ConfigurationError):
        manager.save(candidate)
    assert manager.config_path.read_bytes() == baseline


def test_pending_allows_names_priority_and_group_disable_without_detaching(grouped, tmp_path):
    from src.group_sync import GroupSyncRunner
    manager = ConfigManager(tmp_path / "settings.json")
    manager.save(grouped)
    state = manager.config_path.with_suffix(".cloud")
    assert GroupSyncRunner(grouped, state).run(grouped.sync_groups[0], "upload", defer=True)[-1].succeeded
    candidate = replace(grouped, sync_groups=[replace(grouped.sync_groups[0], name="Display only", enabled=False,
                                                       destinations=list(reversed(grouped.sync_groups[0].destinations)))])
    manager.save(candidate)
    assert manager.load() == candidate


def test_no_bidirectional_leaf_can_be_grouped(grouped, tmp_path):
    from src.cloud_models import ConnectionConfig, RemoteJobConfig
    job = RemoteJobConfig("bidir", "Both ways", str(grouped.folders[0].local_path), "provider", "game", bidirectional=True)
    group = replace(grouped.sync_groups[0], destinations=[SyncDestinationConfig("bidir")])
    candidate = replace(grouped, folders=[], remote_jobs=[job], connections=[ConnectionConfig("provider", "Provider", "local", str(tmp_path / "root"))], sync_groups=[group])
    with pytest.raises(ConfigurationError):
        validate_groups(candidate)


def test_nonrecursive_group_is_rejected_before_replacing_config(grouped, tmp_path):
    manager = ConfigManager(tmp_path / "settings.json")
    manager.save(grouped)
    baseline = manager.config_path.read_bytes()
    with pytest.raises(ConfigurationError, match="Copy subdirectories"):
        manager.save(replace(grouped, copy_engine=replace(grouped.copy_engine, copy_subdirectories=False)))
    assert manager.config_path.read_bytes() == baseline
