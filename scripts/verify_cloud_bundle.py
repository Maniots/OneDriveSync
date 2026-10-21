"""Exercise the shipping EXE and bundled cloud engine with isolated local storage.

This checks DPAPI, encrypted configuration, transfer/recovery and snapshots. It
does not certify OAuth or any real cloud account. No production data is touched.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))


def verify_group_bundle(executable: Path, root: Path, engine: Path) -> dict:
    """Exercise the frozen group coordinator with disposable mixed endpoints."""
    from src.sync_history import SyncHistory

    assert engine.is_file()
    fixture = root / "grouped"
    fixture.mkdir()
    local, provider, folder = [fixture / name for name in ("source", "provider", "folder")]
    for path in (local, provider, folder):
        path.mkdir()
    provider_copy, folder_copy = provider / "Game", folder / "Game"
    config_path = fixture / "config.json"
    config = json.loads((PROJECT / "packaging/default-config.json").read_text())
    config["general"]["dry_run"] = False
    config.setdefault("copy_engine", {})["copy_subdirectories"] = True
    config["folders"] = [{"id": "foldercopy", "name": "Second folder copy", "enabled": True,
                           "local_path": str(local), "onedrive_path": str(folder_copy),
                           "minimum_sync_percentage": 0, "verify_after_sync": True,
                           "create_destination": True}]
    config["connections"] = [{"id": "groupfixture", "name": "Isolated group provider",
                               "provider": "local", "root": str(provider)}]
    config["remote_jobs"] = [{"id": "providercopy", "name": "First provider copy",
                               "connection_id": "groupfixture", "local_path": str(local),
                               "remote_path": "Game", "minimum_sync_percentage": 0,
                               "backup_enabled": True}]
    config["sync_groups"] = [{"id": "groupfixture", "name": "Frozen mixed activity",
                               "local_path": str(local), "destinations": [
                                   {"job_id": "providercopy"}, {"job_id": "foldercopy"}]}]
    config_path.write_text(json.dumps(config), encoding="utf-8")

    def run(mode, *args):
        result = subprocess.run([str(executable), "--config", str(config_path), "--mode", mode, *args],
                                cwd=fixture, env=dict(os.environ, LOCALAPPDATA=str(fixture / "user")),
                                timeout=120, creationflags=subprocess.CREATE_NO_WINDOW)
        assert result.returncode == 0, f"Frozen grouped {mode} failed; fixture={fixture}"

    def summary():
        latest = SyncHistory(config_path.with_suffix(".history.sqlite3")).recent(1)[0]
        return next(item for item in latest["outcomes"] if item["folder_id"] == "groupfixture")

    (local / "save.txt").write_text("verified mixed generation", encoding="utf-8")
    run("shutdown")
    for target in (provider_copy, folder_copy):
        assert (target / "save.txt").read_text() == "verified mixed generation"
    state_root = config_path.with_suffix(".cloud")
    ledger_path, state_path = state_root / "groups.json", state_root / "state.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))["groups"]["groupfixture"]
    assert ledger["pending"] is None and len(ledger["destinations"]) == 2
    assert all(item["status"] == "complete" and item["generation"] == ledger["generation"]
               for item in ledger["destinations"].values())
    assert summary()["succeeded"]

    (local / "save.txt").unlink()
    run("startup")
    assert (local / "save.txt").read_text() == "verified mixed generation"
    assert "Downloaded from First provider copy" in summary()["message"]

    # Remove only the activity, preserving its accessible account/volume root.
    assert provider_copy.resolve().parent == provider.resolve() and provider.resolve().is_relative_to(root.resolve())
    shutil.rmtree(provider_copy)
    (local / "save.txt").unlink()
    run("startup")
    assert (local / "save.txt").read_text() == "verified mixed generation"
    message = summary()["message"]
    assert "Downloaded from Second folder copy" in message and "absent" in message

    before_ledger, before_state = ledger_path.read_bytes(), state_path.read_bytes()
    before_destination = (folder_copy / "save.txt").read_bytes()
    (local / "save.txt").write_text("preview only; never transfer", encoding="utf-8")
    run("shutdown", "--dry-run")
    assert ledger_path.read_bytes() == before_ledger and state_path.read_bytes() == before_state
    assert not provider_copy.exists() and (folder_copy / "save.txt").read_bytes() == before_destination
    assert (local / "save.txt").read_text() == "preview only; never transfer"
    return {"frozen_group_upload_all": True, "frozen_group_priority_download": True,
            "frozen_group_absence_fallback": True, "frozen_group_dry_run": True}


def verify(executable: Path, root: Path) -> dict:
    from src.cloud_sync import CloudSyncRunner
    from src.config_manager import ConfigManager
    from src.rclone_transport import RcloneTransport

    assert executable.is_file()
    engine = executable.parent / "rclone.exe"
    assert engine.is_file() and (executable.parent / "rclone-LICENSE.txt").is_file()
    local, remote = root / "local", root / "remote"
    local.mkdir()
    (remote / "Game").mkdir(parents=True)
    config_path = root / "config.json"
    config = json.loads((PROJECT / "packaging/default-config.json").read_text())
    config["connections"] = [{"id": "fixture", "name": "Isolated fixture", "provider": "local", "root": str(remote)}]
    config["remote_jobs"] = [{"id": "saves", "name": "Saves", "connection_id": "fixture",
                              "local_path": str(local), "remote_path": "Game", "minimum_sync_percentage": 0,
                              "backup_enabled": True}]

    def save():
        config_path.write_text(json.dumps(config), encoding="utf-8")

    def write(path, content, modified):
        path.write_text(content, encoding="utf-8")
        os.utime(path, (modified, modified))

    def run(mode, *args, expected=0):
        result = subprocess.run([str(executable), "--config", str(config_path), "--mode", mode, *args],
                                cwd=root, env=dict(os.environ, LOCALAPPDATA=str(root / "user")),
                                timeout=120, creationflags=subprocess.CREATE_NO_WINDOW)
        assert result.returncode == expected, f"Frozen {mode} returned {result.returncode}, expected {expected}; fixture={root}"

    save()
    write(local / "save.txt", "new save", 1700000100)
    write(remote / "Game/save.txt", "old save", 1700000000)
    write(remote / "Game/extra.txt", "keep me", 1700000000)
    # A newer destination must survive even when another selected file is copied.
    write(local / "newer.txt", "old local", 1700000000)
    write(remote / "Game/newer.txt", "new remote", 1700000200)
    run("shutdown")
    assert (remote / "Game/save.txt").read_text() == "new save"
    assert (remote / "Game/extra.txt").read_text() == "keep me"
    assert (remote / "Game/newer.txt").read_text() == "new remote"
    cloud_root = config_path.with_suffix(".cloud")
    assert b"RCLONE_ENCRYPT_V0:" in (cloud_root / "rclone.conf").read_bytes()[:256]
    assert (cloud_root / "rclone-key.dpapi").is_file()
    factory = lambda path: RcloneTransport(path, executable=engine)
    runner = CloudSyncRunner(ConfigManager(config_path).load(), cloud_root, factory)
    snapshots = runner.list_snapshots("saves")
    assert snapshots
    restored = root / "restored"
    restored.mkdir()
    runner.restore("saves", snapshots[0]["run_id"], restored)
    assert (restored / "save.txt").read_text() == "old save"
    assert (restored / "extra.txt").read_text() == "keep me"
    write(remote / "Game/save.txt", "downloaded save", 1700000300)
    run("startup")
    assert (local / "save.txt").read_text() == "downloaded save"
    state_path = cloud_root / "state.json"
    before = state_path.read_bytes()
    write(local / "save.txt", "preview only", 1700000400)
    run("shutdown", "--dry-run")
    assert state_path.read_bytes() == before
    assert (remote / "Game/save.txt").read_text() == "downloaded save"
    # Persisted shutdown work is recovered before the next download.
    runner.run("upload", defer=True)
    run("startup")
    assert (local / "save.txt").read_text() == "preview only"
    assert (remote / "Game/save.txt").read_text() == "preview only"
    config["remote_jobs"][0]["bidirectional"] = True
    save()
    run("shutdown")
    write(local / "save.txt", "local conflict", 1700000500)
    write(remote / "Game/save.txt", "remote conflict", 1700000600)
    run("shutdown", expected=1)
    assert (local / "save.txt").read_text() == "local conflict"
    assert (remote / "Game/save.txt").read_text() == "remote conflict"
    grouped = verify_group_bundle(executable, root, engine)
    return {"frozen_cloud_transfer": True, "newer_destination_preserved": True, "destination_extras_preserved": True,
            "dpapi_and_encrypted_config": True, "snapshot_restore": True, "dry_run_preserved": True,
            "pending_upload_recovered_before_download": True, "bidirectional_conflict_preserved": True,
            "real_cloud_accounts_tested": False, **grouped}


if __name__ == "__main__":
    validation_root = PROJECT / "build"
    validation_root.mkdir(exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="cloud-acceptance-", dir=validation_root)).resolve()
    result = verify(Path(sys.argv[1]).resolve(), root)
    print(json.dumps(result, indent=2))
    # Only remove our own successful, isolated fixture. Keep failures for diagnosis.
    assert root.parent == validation_root.resolve() and root.name.startswith("cloud-acceptance-")
    shutil.rmtree(root)
