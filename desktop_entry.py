"""Windowless Windows entry point: desktop, scheduled sync and monitor."""
from __future__ import annotations

import argparse
import faulthandler
import json
import sys
import traceback
from pathlib import Path

from src.runtime_paths import data_root, default_config_path, ensure_default_config, log_dir
from src.app_info import APP_NAME, VERSION


def parse_arguments(argv):
    parser = argparse.ArgumentParser(description="EverySync desktop application")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--mode", choices=["startup", "shutdown"])
    action.add_argument("--monitor", action="store_true")
    action.add_argument("--init-config", action="store_true")
    action.add_argument("--record-install", type=Path, metavar="DATA_DIRECTORY")
    action.add_argument("--diagnostics", type=Path, metavar="REPORT.json")
    action.add_argument("--smoke-test", type=Path, metavar="REPORT.json")
    action.add_argument("--interaction-test", type=Path, metavar="REPORT.json")
    action.add_argument("--force-sync-test", type=Path, metavar="REPORT.json")
    action.add_argument("--check-updates", action="store_true")
    action.add_argument("--update", action="store_true")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--version", action="version", version=VERSION)
    args = parser.parse_args(argv)
    if args.force_sync_test and args.config is None:
        parser.error("--force-sync-test requires an explicit isolated --config")
    if args.monitor and (args.config or args.dry_run):
        parser.error("The monitor uses the shared application configuration")
    if args.dry_run and not args.mode:
        parser.error("--dry-run requires --mode")
    return args


def write_diagnostics(path: Path, smoke_test: bool, config_path: Path,
                      native_interaction: bool = False, force_sync_test: bool = False) -> int:
    """Exercise bundled imports/resources and optionally a real Qt window."""
    from src.config_manager import ConfigManager
    from src.runtime_paths import sync_lock_path
    import PySide6
    import qtawesome
    import pyqtgraph
    import win32gui

    config = ConfigManager(config_path).load()
    resources = Path(__file__).resolve().parent / "ui" / "resources"
    report = {
        "product_name": APP_NAME,
        "version": VERSION, "frozen": bool(getattr(sys, "frozen", False)),
        "executable": sys.executable, "data_root": str(data_root()),
        "config": str(config_path), "logs": str(log_dir()),
        "sync_lock": str(sync_lock_path()), "folder_count": len(config.folders),
        "qt_version": PySide6.__version__, "win32gui": win32gui.__name__,
        "resources_present": all((resources / name).is_file() for name in
                                 ("check.svg", "chevron-down.svg", "chevron-up.svg", "app.svg", "app.png")),
    }
    if not report["resources_present"]:
        raise RuntimeError("Bundled UI resources are missing")
    if smoke_test:
        import os
        os.environ["QT_QPA_PLATFORM"] = "windows" if native_interaction else "offscreen"
        from PySide6.QtWidgets import QApplication
        from backend.services.configuration_service import ConfigurationService
        from ui.main_window import MainWindow
        from ui.themes.theme import get_dark_theme

        app = QApplication.instance() or QApplication([sys.argv[0]])
        app.setStyleSheet(get_dark_theme())
        icon = qtawesome.icon("fa5s.cloud")
        if icon.isNull():
            raise RuntimeError("Bundled icon font is missing")
        window = MainWindow(configuration_service=ConfigurationService(config_path))
        window.show()
        app.processEvents()
        if window.windowTitle() != APP_NAME or window.windowIcon().isNull():
            raise RuntimeError("EverySync window branding is missing")
        report["branding_verified"] = True
        if window.configuration_service.get_app_config() is None:
            raise RuntimeError("Desktop configuration failed to load")
        if window.config_error:
            raise RuntimeError(window.config_error)
        if native_interaction:
            if force_sync_test:
                exercise_force_sync(app, window, path, report)
            exercise_startup_setting(window, report)
            exercise_navigation(app, window, report)
            from PySide6.QtWidgets import QScrollArea
            window.nav_list.setCurrentRow(6)
            app.processEvents()
            about_scroll = window.content_stack.widget(6).findChild(QScrollArea)
            about_scroll.verticalScrollBar().setValue(about_scroll.verticalScrollBar().maximum())
            app.processEvents()
            path.parent.mkdir(parents=True, exist_ok=True)
            if not window.grab().save(str(path.with_suffix(".about.png"))):
                raise RuntimeError("Could not render the update history")
            window.nav_list.setCurrentRow(5)
            app.processEvents()
        screenshot = path.with_suffix(".png")
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        if not window.grab().save(str(screenshot)):
            raise RuntimeError("Could not render the desktop window")
        report["ui_rendered"] = True
        window.prepare_for_exit()
        window.hide()
        window.deleteLater()
        app.processEvents()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0


def exercise_force_sync(app, window, path, report):
    """Exercise the real button/modal/worker on explicitly isolated fixtures."""
    import time
    import zipfile
    from PySide6.QtCore import QTimer, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QMessageBox
    from ui.widgets.folder_card import FolderCard

    folder, = window.configuration_service.get_app_config().folders
    assert folder.id == "__acceptance_force__"
    assert folder.local_path_resolved.is_relative_to(path.parent.resolve())
    assert folder.onedrive_path_resolved.is_relative_to(path.parent.resolve())
    window.nav_list.setCurrentRow(1)
    page = window.content_stack.widget(1)
    sync = window.sync_service
    def card():
        return page.findChildren(FolderCard)[-1]
    def finish():
        deadline = time.monotonic() + 10
        while sync.is_syncing and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.001)
        assert not sync.is_syncing
        app.processEvents()
    QTest.mouseClick(card().sync_now_button, Qt.MouseButton.LeftButton)
    finish()
    assert not sync.get_history()[0]["outcomes"][0]["succeeded"]
    target = folder.onedrive_path_resolved / "save.txt"
    assert target.read_text() == "old"
    dialogs = []
    def answer(choice):
        dialog = app.activeModalWidget()
        assert isinstance(dialog, QMessageBox)
        assert dialog.defaultButton() == dialog.button(QMessageBox.StandardButton.No)
        dialogs.append(dialog.text())
        QTest.mouseClick(dialog.button(choice), Qt.MouseButton.LeftButton)
    QTimer.singleShot(0, lambda: answer(QMessageBox.StandardButton.No))
    QTest.mouseClick(card().force_sync_button, Qt.MouseButton.LeftButton)
    assert not sync.is_syncing and target.read_text() == "old"
    QTimer.singleShot(0, lambda: answer(QMessageBox.StandardButton.Yes))
    QTest.mouseClick(card().force_sync_button, Qt.MouseButton.LeftButton)
    finish()
    assert target.read_text() == "new"
    assert len(dialogs) == 2 and "80%" in dialogs[0]
    assert sync.get_history()[0]["outcomes"][0]["threshold_bypassed"]
    archives = list((folder.backup.backup_path_resolved / folder.id).glob("*.zip"))
    assert len(archives) == 1
    with zipfile.ZipFile(archives[0]) as archive:
        assert archive.read("save.txt") == b"old"
    assert folder.minimum_sync_percentage == 80
    report["native_force_sync_verified"] = True


def exercise_startup_setting(window, report):
    """Use an isolated Run value to verify the shipping Settings control."""
    import os
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from backend.services.app_startup_service import AppStartupService

    page = window.content_stack.widget(5)
    original = page.startup_service
    service = AppStartupService(value_name=f"OneDrivePCSync-Validation-{os.getpid()}")
    page.startup_service = service
    window.nav_list.setCurrentRow(5)
    page.refresh_startup()
    try:
        assert page.run_at_startup_check.isEnabled()
        QTest.keyClick(page.run_at_startup_check, Qt.Key.Key_Space)
        assert page.run_at_startup_check.isChecked() and service.is_enabled()
        assert AppStartupService(value_name=service.value_name).is_enabled()
        page.refresh_startup()
        assert page.run_at_startup_check.isChecked()
        QTest.keyClick(page.run_at_startup_check, Qt.Key.Key_Space)
        assert not page.run_at_startup_check.isChecked() and not service.is_enabled()
        report["startup_setting_verified"] = True
    finally:
        service.set_enabled(False)
        page.startup_service = original
        page.refresh_startup()


def exercise_navigation(app, window, report):
    """Test real native clicks across startup and manual update completion."""
    from PySide6.QtCore import QElapsedTimer, QTimer, Qt
    from PySide6.QtTest import QTest

    elapsed = QElapsedTimer()
    elapsed.start()
    timer = QTimer(window)
    timer.setInterval(250)
    clicks = 0
    manual_check = False
    errors = []

    def step():
        nonlocal clicks, manual_check
        try:
            if elapsed.elapsed() > 60000:
                raise TimeoutError("Native navigation/update test timed out")
            index = (clicks + 1) % window.nav_list.count()
            item = window.nav_list.item(index)
            QTest.mouseClick(window.nav_list.viewport(), Qt.MouseButton.LeftButton,
                             pos=window.nav_list.visualItemRect(item).center())
            assert window.nav_list.currentRow() == index
            assert window.content_stack.currentIndex() == index
            assert window.header_title.text() == item.text()
            clicks += 1
            service = window.update_service
            if clicks >= 28 and not service.busy and not service.initial_check.isActive():
                if not manual_check:
                    window.nav_list.setCurrentRow(6)
                    window.content_stack.widget(6).check_updates_button.click()
                    assert service.busy
                    manual_check = True
                else:
                    report.update(native_navigation_clicks=clicks,
                                  startup_update_state=service.state,
                                  manual_update_check_verified=True)
                    timer.stop()
                    app.quit()
        except Exception as exc:
            errors.append(exc)
            timer.stop()
            app.exit(1)

    timer.timeout.connect(step)
    timer.start()
    result = app.exec()
    window.prepare_for_exit()
    if errors:
        raise errors[0]
    if result:
        raise RuntimeError(f"Native interaction test returned {result}")


def main(argv=None) -> int:
    args = parse_arguments(sys.argv[1:] if argv is None else argv)
    if args.record_install:
        from src.app_info import build_info, release_notes
        from src.installation_history import InstallationHistory
        info = build_info()
        InstallationHistory(args.record_install / "updates").record(info["version"], info["commit"], release_notes())
        return 0
    if args.init_config:
        ensure_default_config()
        return 0
    # An explicit config is never silently replaced by a default.
    if getattr(sys, "frozen", False) and args.config is None:
        ensure_default_config()
    if args.diagnostics or args.smoke_test or args.interaction_test or args.force_sync_test:
        return write_diagnostics(args.diagnostics or args.smoke_test or args.interaction_test or args.force_sync_test,
                                 bool(args.smoke_test or args.interaction_test or args.force_sync_test),
                                 args.config or default_config_path(), bool(args.interaction_test or args.force_sync_test),
                                 bool(args.force_sync_test))
    if args.mode:
        from main import main as sync_main
        sync_args = ["--mode", args.mode]
        if args.config:
            sync_args += ["--config", str(args.config)]
        if args.dry_run:
            sync_args += ["--dry-run"]
        return sync_main(sync_args)
    if args.monitor:
        from src.shutdown_monitor import main as monitor_main
        return monitor_main()
    from ui.app import main as ui_main
    ui_args = ["--config", str(args.config)] if args.config else []
    if args.check_updates or args.update:
        ui_args += ["--updates"]
    if args.update:
        ui_args += ["--install-update"]
    return ui_main(ui_args)


def launch() -> int:
    # Keep the file open for native Qt/Python failures, which bypass except.
    log_dir().mkdir(parents=True, exist_ok=True)
    with (log_dir() / "desktop_native_crash.log").open("a", encoding="utf-8") as native_log:
        faulthandler.enable(native_log, all_threads=True)
        try:
            return _launch()
        finally:
            faulthandler.disable()


def _launch() -> int:
    try:
        return main()
    except Exception:
        log_dir().mkdir(parents=True, exist_ok=True)
        crash_log = log_dir() / "desktop_crash.log"
        with crash_log.open("a", encoding="utf-8") as handle:
            traceback.print_exc(file=handle)
        # Background task failures belong in logs. A desktop startup failure
        # also needs an actionable message when no console exists.
        if len(sys.argv) == 1 and sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, f"Avvio non riuscito. Dettagli: {crash_log}",
                                            "EverySync", 0x10)
        return 2


if __name__ == "__main__":
    raise SystemExit(launch())
