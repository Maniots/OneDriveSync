"""Selection and filtering keep backup actions tied to the visible archive."""
from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from tests.test_backup_actions import backup_setup, write_zip
from ui.pages.backups import BackupsPage


def test_library_search_filters_archives_and_clears_hidden_action_target(qapp, backup_setup):
    config, service, archive, _, _ = backup_setup
    older = archive.with_name("app_2026-10-11.zip")
    write_zip(archive, [("file", "one")])
    write_zip(older, [("file", "two")])
    page = BackupsPage(config, service)
    page.load_configuration_data()
    assert page.selected_backup()["path"] == str(archive)
    page.search_edit.setText("2026-10-11")
    assert page.table.isRowHidden(0)
    assert not page.table.isRowHidden(1)
    assert page.selected_backup() is None
    assert not page.restore_btn.isEnabled() and not page.open_btn.isEnabled()
    page.table.selectRow(1)
    assert page.selected_backup()["path"] == str(older)
    assert page.detail_archive.text() == older.name
    page.search_edit.setText("does not exist")
    assert page.list_stack.currentWidget() is page.empty_state
    assert page.empty_title.text() == "No matching backups"
    page.clear_filters_btn.click()
    assert not page.search_edit.text()
    assert page.list_stack.currentWidget() is page.table


def test_folder_filter_and_refresh_preserve_archive_identity(qapp, backup_setup):
    config, service, archive, _, _ = backup_setup
    write_zip(archive, [("file", "one")])
    other = replace(config.get_app_config().folders[0], id="other", name="Other app")
    config.save(replace(config.get_app_config(), folders=[config.get_app_config().folders[0], other]))
    other_archive = archive.parent.parent / "other" / "other_2026-10-13.zip"
    other_archive.parent.mkdir()
    write_zip(other_archive, [("file", "two")])
    page = BackupsPage(config, service)
    page.load_configuration_data()
    assert page.selected_backup()["folder_id"] == "other"
    page.folder_filter.setCurrentIndex(page.folder_filter.findData("app"))
    row = next(row for row in range(page.table.rowCount()) if not page.table.isRowHidden(row))
    page.table.selectRow(row)
    page.refresh_backups()
    assert page.selected_backup()["path"] == str(archive)
    assert page.folder_filter.currentData() == "app"
    assert "1 of 2" in page.summary_label.text()


def test_empty_library_explains_where_archives_come_from(qapp, backup_setup):
    config, service, _, _, _ = backup_setup
    page = BackupsPage(config, service)
    page.load_configuration_data()
    assert page.list_stack.currentWidget() is page.empty_state
    assert page.empty_title.text() == "No backups yet"
    assert "synchronization" in page.empty_description.text().lower()
    assert not page.restore_btn.isEnabled() and not page.delete_btn.isEnabled()
    assert page.error_label.isHidden()


def test_keyboard_selection_updates_details_and_actions(qapp, backup_setup, monkeypatch):
    config, service, archive, _, _ = backup_setup
    older = archive.with_name("app_2026-10-11.zip")
    write_zip(archive, [("file", "one")])
    write_zip(older, [("file", "two")])
    page = BackupsPage(config, service)
    page.show()
    qapp.processEvents()
    page.load_configuration_data()
    page.table.setFocus()
    QTest.keyClick(page.table, Qt.Key.Key_Down)
    assert page.detail_archive.text() == older.name
    calls = []
    monkeypatch.setattr(page, "restore_backup", lambda fid, path: calls.append((fid, path)))
    page.restore_btn.click()
    assert calls == [("app", str(older))]
    page.hide()
