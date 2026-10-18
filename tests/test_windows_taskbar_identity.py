import ctypes
import sys

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="Windows taskbar identity")
def test_ui_sets_stable_windows_identity_before_application_creation(monkeypatch):
    from ui import app as desktop

    shell32 = ctypes.OleDLL("shell32")
    set_id = shell32.SetCurrentProcessExplicitAppUserModelID
    set_id.argtypes = [ctypes.c_wchar_p]
    set_id.restype = ctypes.HRESULT
    get_id = shell32.GetCurrentProcessExplicitAppUserModelID
    get_id.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    get_id.restype = ctypes.HRESULT
    free = ctypes.OleDLL("ole32").CoTaskMemFree
    free.argtypes = [ctypes.c_void_p]
    free.restype = None

    def current_id():
        value = ctypes.c_void_p()
        get_id(ctypes.byref(value))
        try:
            return ctypes.wstring_at(value)
        finally:
            free(value)

    class StartupChecked(Exception):
        pass

    class Application:
        @staticmethod
        def instance():
            assert current_id() == "EverySync.Desktop"
            raise StartupChecked()

    set_id("EverySync.Test.Previous")
    monkeypatch.setattr(desktop, "QApplication", Application)
    with pytest.raises(StartupChecked):
        desktop.main([])


def test_installer_shortcuts_share_runtime_identity_and_executable_icon():
    from pathlib import Path
    from src.app_info import APP_USER_MODEL_ID

    installer = (Path(__file__).resolve().parents[1] / "packaging/windows-installer.iss").read_text()
    entries = installer.split("[Icons]", 1)[1].split("[Run]", 1)[0]
    app_shortcuts = [line for line in entries.splitlines() if 'Filename: "{app}\\{#AppExe}"' in line]
    assert len(app_shortcuts) == 2
    for shortcut in app_shortcuts:
        assert f'AppUserModelID: "{APP_USER_MODEL_ID}"' in shortcut
        assert 'IconFilename: "{app}\\{#AppExe}"' in shortcut
