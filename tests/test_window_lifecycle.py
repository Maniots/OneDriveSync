import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QSystemTrayIcon

from backend.services.configuration_service import ConfigurationService
from ui.main_window import MainWindow


@pytest.mark.parametrize("explicit_exit,syncing,accepted,notifies", [
    (True, False, True, False),
    (True, True, False, False),
    (False, False, False, True),
])
def test_close_preserves_exit_and_tray_intent(qapp, tmp_path, monkeypatch,
                                             explicit_exit, syncing, accepted, notifies):
    config = tmp_path / "config.json"
    config.write_bytes((Path(__file__).resolve().parents[1] / "packaging/default-config.json").read_bytes())
    window = MainWindow(configuration_service=ConfigurationService(config))
    quit_app = Mock()
    monkeypatch.setattr(qapp, "quit", quit_app)
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: True)
    monkeypatch.setattr(window.tray_icon, "isVisible", lambda: True)
    notification = Mock()
    monkeypatch.setattr(window.tray_icon, "showMessage", notification)
    monkeypatch.setattr(type(window.sync_service), "is_syncing", property(lambda self: syncing))
    try:
        if explicit_exit:
            window.exit_application()
        event = QCloseEvent()
        window.closeEvent(event)
        assert event.isAccepted() == accepted
        assert notification.called == notifies
        assert quit_app.call_count == int(explicit_exit and not syncing)
    finally:
        window.prepare_for_exit()
        window.tray_icon.hide()
        window.hide()


@pytest.mark.skipif(sys.platform != "win32", reason="Native Windows visibility")
def test_activation_restores_window_hidden_by_windows():
    # Windows can hide the HWND while Qt still considers its widget visible.
    # Exercise the shipping activation method in its own native event loop.
    probe = r'''
import json
import sys
import win32gui
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMainWindow
from ui.main_window import MainWindow

app = QApplication([])
window = QMainWindow()
window.setWindowTitle("EverySync visibility regression")
window.show()
def restore():
    win32gui.ShowWindow(int(window.winId()), 0)
    assert window.isVisible() and not win32gui.IsWindowVisible(int(window.winId()))
    MainWindow.show_and_activate(window)
    QTimer.singleShot(50, verify)
def verify():
    visible = bool(win32gui.IsWindowVisible(int(window.winId())))
    print(json.dumps({"windows_visible": visible}), flush=True)
    app.exit(0 if visible else 1)
QTimer.singleShot(50, restore)
raise SystemExit(app.exec())
'''
    result = subprocess.run([sys.executable, "-c", probe],
                            env=dict(os.environ, QT_QPA_PLATFORM="windows"),
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["windows_visible"]
