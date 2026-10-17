from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from backend.services import app_startup_service
from backend.services.app_startup_service import AppStartupService
from backend.services.configuration_service import ConfigurationService
from ui.pages.settings import SettingsPage


class Registry:
    HKEY_CURRENT_USER = "current user"
    REG_SZ = 1
    KEY_QUERY_VALUE = 1
    KEY_SET_VALUE = 2

    def __init__(self):
        self.values = {}
        self.read_error = self.write_error = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def OpenKey(self, root, path):
        assert root == self.HKEY_CURRENT_USER and path == app_startup_service.RUN_KEY
        if self.read_error:
            raise PermissionError("Registry is unavailable")
        return self

    def CreateKeyEx(self, root, path, reserved, access):
        if self.write_error:
            raise PermissionError("Access denied")
        return self.OpenKey(root, path)

    def QueryValueEx(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        return self.values[name]

    def SetValueEx(self, key, name, reserved, kind, value):
        self.values[name] = (value, kind)

    def DeleteValue(self, key, name):
        del self.values[name]


@pytest.fixture
def startup(monkeypatch, tmp_path):
    registry = Registry()
    monkeypatch.setattr(app_startup_service, "winreg", registry)
    service = AppStartupService(tmp_path / "Installed app" / "OneDrivePCSync.exe")
    return service, registry


def test_startup_registration_quotes_exe_persists_and_only_removes_own_value(startup):
    service, registry = startup
    registry.values["OtherApp"] = ('"Other.exe"', registry.REG_SZ)
    assert not service.is_enabled()
    service.set_enabled(True)
    assert registry.values[service.value_name] == (f'"{service.executable}"', registry.REG_SZ)
    assert AppStartupService(service.executable).is_enabled()
    service.set_enabled(True)
    service.set_enabled(False)
    service.set_enabled(False)
    assert registry.values == {"OtherApp": ('"Other.exe"', registry.REG_SZ)}


@pytest.mark.parametrize("enabled", [True, False])
def test_other_installation_startup_is_preserved(startup, enabled):
    service, registry = startup
    registry.values[service.value_name] = ('"Different.exe"', registry.REG_SZ)
    with pytest.raises(RuntimeError, match="different installation"):
        service.set_enabled(enabled)
    assert registry.values[service.value_name][0] == '"Different.exe"'


def test_source_runs_cannot_register_the_python_interpreter(monkeypatch):
    monkeypatch.setattr(app_startup_service.sys, "frozen", False, raising=False)
    service = AppStartupService()
    assert not service.supported and not service.is_enabled()
    with pytest.raises(RuntimeError, match="installed Windows app"):
        service.set_enabled(True)


@pytest.fixture
def settings_page(qapp, tmp_path, startup):
    path = tmp_path / "config.json"
    template = Path(__file__).resolve().parents[1] / "packaging/default-config.json"
    path.write_bytes(template.read_bytes())
    service, _ = startup
    return SettingsPage(ConfigurationService(path), startup_service=service), path


def test_startup_checkbox_saves_immediately_and_cancel_keeps_registration(settings_page, startup):
    page, path = settings_page
    service, _ = startup
    original_config = path.read_bytes()
    page.show()
    QTest.keyClick(page.run_at_startup_check, Qt.Key.Key_Space)
    assert page.run_at_startup_check.isChecked() and service.is_enabled()
    page.on_cancel_clicked()
    assert page.run_at_startup_check.isChecked() and service.is_enabled()
    page.on_reset_clicked()
    assert service.is_enabled() and path.read_bytes() == original_config
    QTest.keyClick(page.run_at_startup_check, Qt.Key.Key_Space)
    assert not service.is_enabled()


def test_failed_startup_write_rolls_back_checkbox_and_can_retry(settings_page, startup):
    page, _ = settings_page
    service, registry = startup
    registry.write_error = True
    page.run_at_startup_check.setChecked(True)
    assert not page.run_at_startup_check.isChecked() and not service.is_enabled()
    assert "Access denied" in page.startup_status.text()
    assert not page.startup_retry_button.isHidden()
    registry.write_error = False
    page.run_at_startup_check.setChecked(True)
    assert page.run_at_startup_check.isChecked() and service.is_enabled()


def test_startup_read_failure_has_retry_and_refresh_reads_windows_state(settings_page, startup):
    page, _ = settings_page
    service, registry = startup
    registry.read_error = True
    page.refresh_startup()
    assert not page.run_at_startup_check.isEnabled()
    assert not page.startup_retry_button.isHidden()
    registry.read_error = False
    service.set_enabled(True)
    page.startup_retry_button.click()
    assert page.run_at_startup_check.isEnabled() and page.run_at_startup_check.isChecked()
    service.set_enabled(False)
    page.hide()
    page.show()
    assert not page.run_at_startup_check.isChecked()


def test_startup_remains_available_when_sync_configuration_is_missing(qapp, startup):
    class MissingConfig:
        def get_app_config(self):
            return None
    service, _ = startup
    page = SettingsPage(MissingConfig(), startup_service=service)
    page.run_at_startup_check.setChecked(True)
    assert service.is_enabled()
