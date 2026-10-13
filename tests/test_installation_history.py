import json
from datetime import datetime

from src.installation_history import InstallationHistory
from src.updater import UpdateClient
from backend.services.update_service import UpdateService
from ui.pages.about import AboutPage


def test_install_history_records_dates_transitions_and_note_snapshots(tmp_path):
    history = InstallationHistory(tmp_path)
    assert history.recent() == [] and not history.path.exists()
    history.record("1.3.0.0", "a" * 40, "First release notes")
    history.record("1.3.0.1", "b" * 40, "Second release notes")
    entries = InstallationHistory(tmp_path).recent()
    assert [e["version"] for e in entries] == ["1.3.0.1", "1.3.0.0"]
    assert entries[0]["previous_version"] == "1.3.0.0"
    assert entries[0]["changes"] == "Second release notes"
    assert entries[1]["previous_version"] is None
    assert datetime.fromisoformat(entries[0]["timestamp"]).tzinfo is not None


def test_legacy_verified_result_is_imported_once_without_invented_dates(tmp_path):
    data = {"status": "installed", "version": "1.2.0.0", "time": "2026-10-13T11:04:05+02:00"}
    (tmp_path / "result.json").write_text(json.dumps(data))
    history = InstallationHistory(tmp_path)
    assert history.recent()[0]["timestamp"] == data["time"]
    assert not history.path.exists()  # Reading alone must never record an update.
    history.record("1.3.0.0", "a" * 40, "New feature")
    history.record("1.3.0.1", "b" * 40, "Fix")
    assert len(history.recent()) == 3
    assert history.recent()[-1]["timestamp"] == data["time"]


def test_failed_or_invalid_legacy_update_is_not_an_installed_version(tmp_path):
    path = tmp_path / "result.json"
    path.write_text(json.dumps({"status": "failed", "version": "1.3.0", "time": "2026-10-13"}))
    history = InstallationHistory(tmp_path)
    assert history.recent() == []
    path.write_text("broken")
    history.record("1.3.0.0", "a" * 40, "Notes")
    assert len(history.recent()) == 1 and history.recent()[0]["previous_version"] is None


def test_about_history_selection_refresh_and_error_recovery(qapp, tmp_path):
    history = InstallationHistory(tmp_path)
    history.record("1.2.0.0", "a" * 40, "Startup setting")
    history.record("1.3.0.0", "b" * 40, "Force sync")
    service = UpdateService(client=UpdateClient(root=tmp_path))
    page = AboutPage(update_service=service)
    assert page.history_table.rowCount() == 2
    assert page.history_table.item(0, 2).text() == "1.3.0.0"
    assert page.history_notes.toPlainText() == "Force sync"
    page.history_table.selectRow(1)
    assert page.history_notes.toPlainText() == "Startup setting"
    original = service.client.installation_history
    service.client.installation_history = lambda: (_ for _ in ()).throw(OSError("Unreadable history"))
    page.refresh_history()
    assert "Unreadable history" in page.history_status.text()
    service.client.installation_history = original
    page.refresh_history()
    assert page.history_table.rowCount() == 2
