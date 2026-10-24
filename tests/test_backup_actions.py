"""Real archive safety and visible backup action regressions."""

import json
import os
import stat
import subprocess
import threading
import time
import zipfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QFileDialog, QMessageBox
from shiboken6 import isValid

from backend.services.backup_service import BackupService
from backend.services.configuration_service import ConfigurationService
from src.single_instance import acquire_single_instance_lock
from ui.pages.backups import BackupsPage
from ui.pages import backups as page_module
from backend.services import backup_service as service_module


@pytest.fixture
def backup_setup(tmp_path, monkeypatch):
    local = tmp_path / "local"
    cloud = tmp_path / "OneDrive"
    local.mkdir()
    cloud.mkdir()
    managed = cloud / "archives" / "app"
    managed.mkdir(parents=True)
    monkeypatch.setenv("OneDrive", str(cloud))
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "general": {"dry_run": False},
        "folders": [{"id": "app", "name": "App", "enabled": True,
                     "local_path": str(local), "onedrive_path": str(cloud / "app"),
                     "backup": {"enabled": True, "backup_path": str(managed.parent), "retention_days": 30}}]
    }))
    config = ConfigurationService(config_path)
    assert config.get_app_config() is not None
    service = BackupService(config)
    # Exercise the real lock without touching the application's production lock.
    lock = tmp_path / "sync.lock"
    monkeypatch.setattr(service_module, "acquire_single_instance_lock",
                        lambda unused: acquire_single_instance_lock(lock))
    target = tmp_path / "restore"
    target.mkdir()
    archive = managed / "app_2026-10-12.zip"
    return config, service, archive, target, lock


def write_zip(path, entries):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, contents in entries:
            archive.writestr(name, contents)


def test_restore_protects_other_folders_managed_archives_even_when_disabled(backup_setup):
    config_service, service, archive, target, _ = backup_setup
    config = config_service.get_app_config()
    other = replace(config.folders[0], id="other", name="Other", enabled=False,
                    local_path=target, onedrive_path=archive.parents[2] / "other",
                    backup=replace(config.folders[0].backup, enabled=False))
    config_service.save(replace(config, folders=[config.folders[0], other]))
    other_dir = archive.parent.parent / "other"
    other_dir.mkdir()
    other_archive = other_dir / "other_2026-10-12.zip"
    write_zip(other_archive, [("original", "preserve")])
    before = other_archive.read_bytes()
    write_zip(archive, [(other_archive.name, "not a zip")])
    with pytest.raises(ValueError, match="managed backup"):
        service.restore_backup("app", archive, other_dir)
    assert other_archive.read_bytes() == before


def spin_until(app, condition):
    deadline = time.monotonic() + 5
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.001)
    app.processEvents()
    assert condition(), "Backup worker did not finish"


def make_directory_link(link, destination):
    if os.name == "nt":
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(destination)],
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    else:
        link.symlink_to(destination, target_is_directory=True)


def test_restore_overwrites_matching_files_keeps_unrelated_and_creates_empty_directories(backup_setup):
    _, service, archive, target, _ = backup_setup
    write_zip(archive, [("saved.txt", "new"), ("nested/file.txt", "nested"), ("empty/", "")])
    (target / "saved.txt").write_text("old")
    (target / "unrelated.txt").write_text("keep")
    assert service.restore_backup("app", archive, target) == 2
    assert (target / "saved.txt").read_text() == "new"
    assert (target / "nested/file.txt").read_text() == "nested"
    assert (target / "unrelated.txt").read_text() == "keep"
    assert (target / "empty").is_dir()
    assert list(target.rglob(".restore-*")) == []


@pytest.mark.parametrize("name", ["../outside.txt", "/outside.txt", "C:/outside.txt", "C:outside.txt",
                                 "//server/share/file", "\\\\server\\share\\file", "nested\\..\\outside.txt",
                                 "file.txt:stream", "nested/../file", "./file", "nested//file", "CON.txt",
                                 "folder/LPT1", "folder/file. ", "folder/file.", "folder/COM¹.txt"])
def test_malicious_member_rejects_entire_restore_before_any_destination_writes(backup_setup, name):
    _, service, archive, target, _ = backup_setup
    outside = target.parent / "outside.txt"
    outside.write_text("outside unchanged")
    (target / "saved.txt").write_text("old")
    write_zip(archive, [("saved.txt", "replacement"), (name, "malicious")])
    with pytest.raises(ValueError):
        service.restore_backup("app", archive, target)
    assert (target / "saved.txt").read_text() == "old"
    assert outside.read_text() == "outside unchanged"
    assert sorted(path.name for path in target.iterdir()) == ["saved.txt"]


def test_corruption_in_later_member_preserves_original_file(backup_setup):
    _, service, archive, target, _ = backup_setup
    write_zip(archive, [("saved.txt", "replacement"), ("second.txt", "unique-corrupt-data")])
    data = bytearray(archive.read_bytes())
    offset = data.index(b"unique-corrupt-data")
    data[offset] ^= 1
    archive.write_bytes(data)
    (target / "saved.txt").write_text("old")
    with pytest.raises(zipfile.BadZipFile, match="CRC"):
        service.restore_backup("app", archive, target)
    assert (target / "saved.txt").read_text() == "old"
    assert not (target / "second.txt").exists()


def test_midway_atomic_replace_failure_rolls_back_originals_and_new_files(backup_setup, monkeypatch):
    _, service, archive, target, _ = backup_setup
    write_zip(archive, [("saved.txt", "replacement"), ("new/nested.txt", "new"), ("second.txt", "replacement")])
    (target / "saved.txt").write_text("old one")
    (target / "second.txt").write_text("old two")
    original_replace = service_module.os.replace
    failed = False

    def fail_once(source, destination):
        nonlocal failed
        if Path(destination) == target / "second.txt" and not failed:
            failed = True
            raise OSError("injected write failure")
        original_replace(source, destination)

    monkeypatch.setattr(service_module.os, "replace", fail_once)
    with pytest.raises(OSError, match="injected"):
        service.restore_backup("app", archive, target)
    assert failed
    assert (target / "saved.txt").read_text() == "old one"
    assert (target / "second.txt").read_text() == "old two"
    assert not (target / "new").exists()
    assert list(target.rglob(".restore-*")) == []


def test_rollback_failure_retains_original_recovery_copy_and_reports_location(backup_setup, monkeypatch):
    _, service, archive, target, _ = backup_setup
    write_zip(archive, [("saved.txt", "replacement"), ("second.txt", "second")])
    (target / "saved.txt").write_text("original")
    recovery = target.parent / "recovery"
    recovery.mkdir()
    monkeypatch.setattr(service_module.tempfile, "mkdtemp", lambda **kwargs: str(recovery))
    original_copy = service._atomic_copy

    def fail_commit_and_rollback(source, destination):
        if source.name in ("new-1", "old-0"):
            raise OSError("disk unavailable")
        original_copy(source, destination)

    monkeypatch.setattr(service, "_atomic_copy", fail_commit_and_rollback)
    with pytest.raises(RuntimeError, match="Recovery copies retained") as failure:
        service.restore_backup("app", archive, target)
    assert str(recovery) in str(failure.value)
    assert (recovery / "old-0").read_text() == "original"
    assert not (target / "second.txt").exists()


@pytest.mark.parametrize("entries", [[("saved.txt", "one"), ("SAVED.txt", "two")],
                                     [("parent", "file"), ("parent/nested", "nested")]])
def test_duplicate_and_file_parent_conflicts_rejected_before_writes(backup_setup, entries):
    _, service, archive, target, _ = backup_setup
    write_zip(archive, entries)
    with pytest.raises(ValueError):
        service.restore_backup("app", archive, target)
    assert list(target.iterdir()) == []


def test_symlink_member_rejected(backup_setup):
    _, service, archive, target, _ = backup_setup
    link = zipfile.ZipInfo("link")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    write_zip(archive, [("safe.txt", "safe"), (link, "../outside")])
    with pytest.raises(ValueError, match="links"):
        service.restore_backup("app", archive, target)
    assert list(target.iterdir()) == []


def test_existing_destination_junction_does_not_write_outside_target(backup_setup):
    _, service, archive, target, _ = backup_setup
    outside = target.parent / "outside"
    outside.mkdir()
    (outside / "original.txt").write_text("keep")
    make_directory_link(target / "linked", outside)
    write_zip(archive, [("first.txt", "first"), ("linked/original.txt", "malicious")])
    with pytest.raises(ValueError, match="reparse"):
        service.restore_backup("app", archive, target)
    assert (outside / "original.txt").read_text() == "keep"
    assert not (target / "first.txt").exists()


def test_managed_directory_junction_rejected(backup_setup):
    config, service, archive, target, _ = backup_setup
    outside = target.parent / "outside-archives"
    outside.mkdir()
    write_zip(outside / archive.name, [("file", "keep")])
    archive.parent.rmdir()
    make_directory_link(archive.parent, outside)
    with pytest.raises(ValueError, match="reparse"):
        service.delete_backup("app", archive)
    assert (outside / archive.name).exists()


@pytest.mark.parametrize("tag", [0x9000001A, 0x9000101A, 0x9000F01A])
def test_onedrive_cloud_placeholder_tag_does_not_hide_managed_archive(backup_setup, monkeypatch, tag):
    _, service, archive, _, _ = backup_setup
    write_zip(archive, [("file", "value")])
    original_lstat = Path.lstat

    def cloud_lstat(path, *args, **kwargs):
        if path == archive or path == archive.parent:
            return SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=0x400, st_reparse_tag=tag)
        return original_lstat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", cloud_lstat)
    assert service.get_archive_path("app", archive) == archive
    assert service.get_backup_info("app")[0]["path"] == str(archive)


def test_managed_lookup_rejects_wrong_folder_name_date_and_outside_path(backup_setup):
    _, service, archive, target, _ = backup_setup
    write_zip(archive, [("file", "value")])
    with pytest.raises(ValueError):
        service.get_archive_path("other", archive)
    outside = target / archive.name
    outside.write_bytes(archive.read_bytes())
    with pytest.raises(ValueError):
        service.delete_backup("app", outside)
    invalid = archive.with_name("app_2026-99-99.zip")
    invalid.write_bytes(archive.read_bytes())
    with pytest.raises(ValueError):
        service.delete_backup("app", invalid)
    with pytest.raises(ValueError):
        service.get_archive_path("app", archive.parent / ".." / "app" / archive.name)
    assert archive.exists() and outside.exists() and invalid.exists()


def test_delete_removes_selected_archive_only(backup_setup):
    _, service, archive, target, _ = backup_setup
    other = archive.with_name("app_2026-10-11.zip")
    write_zip(archive, [("file", "selected")])
    write_zip(other, [("file", "other")])
    service.delete_backup("app", archive)
    assert not archive.exists()
    assert other.exists()


def test_dry_run_rejects_restore_and_delete_without_writes(backup_setup):
    config, service, archive, target, _ = backup_setup
    write_zip(archive, [("file", "contents")])
    config._app_config = replace(config.get_app_config(), general=replace(config.get_app_config().general, dry_run=True))
    for action in (lambda: service.delete_backup("app", archive),
                   lambda: service.restore_backup("app", archive, target)):
        with pytest.raises(RuntimeError, match="dry-run"):
            action()
    assert archive.exists() and list(target.iterdir()) == []


def test_existing_sync_lock_blocks_restore_and_delete(backup_setup, monkeypatch):
    _, service, archive, target, lock = backup_setup
    write_zip(archive, [("file", "contents")])
    if os.name != "nt":
        monkeypatch.setattr(service_module, "acquire_single_instance_lock", lambda _: None)
    handle = acquire_single_instance_lock(lock)
    try:
        for action in (lambda: service.delete_backup("app", archive),
                       lambda: service.restore_backup("app", archive, target)):
            with pytest.raises(RuntimeError, match="already running"):
                action()
    finally:
        handle.close()
    assert archive.exists() and list(target.iterdir()) == []


@pytest.mark.parametrize("target_name", ["AppData", "AppData/Local"])
def test_dangerous_restore_roots_rejected(backup_setup, target_name):
    _, service, archive, target, _ = backup_setup
    dangerous = target.parent / target_name
    dangerous.mkdir(parents=True)
    write_zip(archive, [("file", "contents")])
    with pytest.raises(ValueError, match="safe restore"):
        service.restore_backup("app", archive, dangerous)
    assert list(dangerous.iterdir()) == []


def test_action_buttons_bind_each_row_to_its_archive(qapp, backup_setup, monkeypatch):
    config, service, archive, _, _ = backup_setup
    other = archive.with_name("app_2026-10-11.zip")
    write_zip(archive, [("file", "one")])
    write_zip(other, [("file", "two")])
    page = BackupsPage(config, service)
    page.load_configuration_data()
    calls = []
    for method in ("restore_backup", "open_backup", "delete_backup"):
        monkeypatch.setattr(page, method, lambda fid, path, method=method: calls.append((method, fid, path)))
    for row, path in enumerate((archive, other)):
        page.table.selectRow(row)
        for button in (page.restore_btn, page.open_btn, page.delete_btn):
            button.click()
        assert calls[-3:] == [("restore_backup", "app", str(path)), ("open_backup", "app", str(path)),
                              ("delete_backup", "app", str(path))]


def test_open_click_opens_containing_directory(qapp, backup_setup, monkeypatch):
    config, service, archive, _, _ = backup_setup
    write_zip(archive, [("file", "one")])
    page = BackupsPage(config, service)
    page.load_configuration_data()
    opened = []
    monkeypatch.setattr(page_module.QDesktopServices, "openUrl", lambda url: opened.append(url.toLocalFile()) or True)
    page.open_btn.click()
    assert Path(opened[0]) == archive.parent


def test_delete_cancel_preserves_archive_then_confirmed_click_deletes_it(qapp, backup_setup, monkeypatch):
    config, service, archive, _, _ = backup_setup
    write_zip(archive, [("file", "one")])
    page = BackupsPage(config, service)
    page.load_configuration_data()
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
    page.delete_btn.click()
    assert archive.exists()
    assert page.table.rowCount() == 1
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    page.delete_btn.click()
    assert not archive.exists()
    assert page.table.rowCount() == 0
    assert page.status_label.text().startswith("Deleted")


def test_restore_cancel_uses_no_worker_or_writes(qapp, backup_setup, monkeypatch):
    config, service, archive, target, _ = backup_setup
    write_zip(archive, [("file", "one")])
    page = BackupsPage(config, service)
    page.load_configuration_data()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(target))
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
    page.restore_btn.click()
    assert page._thread is None
    assert list(target.iterdir()) == []


def test_dry_run_buttons_disable_mutations_keep_open_available(qapp, backup_setup):
    config, service, archive, _, _ = backup_setup
    write_zip(archive, [("file", "one")])
    config._app_config = replace(config.get_app_config(), general=replace(config.get_app_config().general, dry_run=True))
    page = BackupsPage(config, service)
    page.load_configuration_data()
    restore, open_button, delete = page.restore_btn, page.open_btn, page.delete_btn
    assert not restore.isEnabled() and not delete.isEnabled()
    assert open_button.isEnabled()
    assert "dry-run" in restore.toolTip() and "dry-run" in delete.toolTip()


def test_restore_runs_off_gui_thread_disables_actions_and_recovers_after_failure(qapp, backup_setup, monkeypatch):
    config, service, archive, target, _ = backup_setup
    write_zip(archive, [("file", "one")])
    page = BackupsPage(config, service)
    page.load_configuration_data()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(target))
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    gui_thread = threading.get_ident()
    worker_threads = []
    original_restore = service.restore_backup
    gate = threading.Event()
    started = threading.Event()

    def fail_first(*args):
        worker_threads.append(threading.get_ident())
        started.set()
        assert gate.wait(5)
        raise RuntimeError("injected restore failure")

    monkeypatch.setattr(service, "restore_backup", fail_first)
    page.restore_btn.click()
    spin_until(qapp, started.is_set)
    assert not page.refresh_btn.isEnabled() and not page.table.isEnabled()
    assert worker_threads[0] != gui_thread
    page.refresh_backups()
    assert page.table.rowCount() == 1
    gate.set()
    spin_until(qapp, lambda: page._thread is None)
    assert page.error_label.text().endswith("injected restore failure")
    assert page.refresh_btn.isEnabled() and page.table.isEnabled()
    monkeypatch.setattr(service, "restore_backup", original_restore)
    page.restore_btn.click()
    spin_until(qapp, lambda: page._thread is None)
    assert (target / "file").read_text() == "one"
    assert page.status_label.text() == "Restored 1 file(s)"


def test_shutdown_waits_for_active_backup_thread(qapp, backup_setup, monkeypatch):
    config, service, archive, target, _ = backup_setup
    write_zip(archive, [("file", "one")])
    page = BackupsPage(config, service)
    page.load_configuration_data()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(target))
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    gate = threading.Event()
    started = threading.Event()

    def blocked_restore(*args):
        started.set()
        assert gate.wait(5)
        return 0

    monkeypatch.setattr(service, "restore_backup", blocked_restore)
    page.restore_backup("app", str(archive))
    spin_until(qapp, started.is_set)
    thread = page._thread
    releaser = threading.Timer(0.05, gate.set)
    releaser.start()
    try:
        page.wait_for_finished()
        assert not thread.isRunning()
    finally:
        gate.set()
        releaser.join()
    spin_until(qapp, lambda: page._thread is None)


def test_page_disposal_waits_for_active_backup_thread(qapp, backup_setup, monkeypatch):
    config, service, archive, target, _ = backup_setup
    write_zip(archive, [("file", "one")])
    page = BackupsPage(config, service)
    page.load_configuration_data()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(target))
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    gate = threading.Event()
    started = threading.Event()

    def blocked_restore(*args):
        started.set()
        assert gate.wait(5)
        return 0

    monkeypatch.setattr(service, "restore_backup", blocked_restore)
    page.restore_backup("app", str(archive))
    spin_until(qapp, started.is_set)
    thread = page._thread
    releaser = threading.Timer(0.05, gate.set)
    releaser.start()
    try:
        page.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert not isValid(page)
        assert not thread.isRunning()
    finally:
        gate.set()
        releaser.join()
    qapp.processEvents()
