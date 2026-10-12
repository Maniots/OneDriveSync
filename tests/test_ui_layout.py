"""Rendered regressions for navigation, long paths and minimum-size layouts."""
import json
from pathlib import Path

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QScrollArea, QSystemTrayIcon

from backend.services.configuration_service import ConfigurationService
from backend.services.log_service import LogService
from ui.main_window import MainWindow
from ui.themes.theme import get_dark_theme
from ui.widgets.folder_card import FolderCard
from ui.widgets.sync_chart import SyncChartWidget
from tests.conftest import dispose_qt_widgets


@pytest.fixture
def rendered_window(qapp, tmp_path, monkeypatch):
    previous_style = qapp.styleSheet()
    previous_widgets = {id(widget) for widget in qapp.topLevelWidgets()}
    # The offscreen Windows plugin does not discover installed system fonts.
    for font in ('segoeui.ttf', 'segoeuib.ttf', 'seguisb.ttf'):
        path = Path('C:/Windows/Fonts') / font
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))
    qapp.setStyleSheet(get_dark_theme())
    monkeypatch.setattr(QSystemTrayIcon, 'isSystemTrayAvailable', lambda: False)
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'general': {'dry_run': True}, 'folders': [
        {'id': 'sample', 'name': 'Sample folder', 'enabled': True,
         'local_path': str(tmp_path / 'local'), 'onedrive_path': str(tmp_path / 'cloud'),
         'minimum_sync_percentage': 80, 'create_destination': True}]}))
    window = MainWindow(configuration_service=ConfigurationService(config),
                        log_service=LogService(tmp_path / 'preview.log'))
    for timer in window.findChildren(QTimer):
        timer.stop()
    window.resize(1100, 700)
    window.show()
    qapp.processEvents()
    yield window
    window.tray_icon.hide()
    window.close()
    # Destroy the rendered window before replacing its application-wide style.
    # Qt reports combo popups as top-level widgets even though the window owns them.
    dispose_qt_widgets(qapp, [window])
    dispose_qt_widgets(qapp, [widget for widget in qapp.topLevelWidgets()
                             if id(widget) not in previous_widgets])
    qapp.setStyleSheet(previous_style)


def test_header_navigation_and_log_controls_fit_minimum_window(qapp, rendered_window):
    window = rendered_window
    title = window.header_title
    assert title.height() >= title.sizeHint().height()
    assert window.header.rect().contains(title.geometry())
    window.nav_list.setFocus()
    QTest.keyClick(window.nav_list, Qt.Key.Key_Down)
    qapp.processEvents()
    assert window.content_stack.currentIndex() == 1
    assert window.header_title.text() == 'Folders'

    window.nav_list.setCurrentRow(4)
    qapp.processEvents()
    page = window.content_stack.currentWidget()
    for control in (page.search_input, page.date_combo, page.refresh_btn, page.copy_btn,
                    page.info_cb, page.warning_cb, page.error_cb, page.success_cb, page.autoscroll_cb):
        assert control.isVisible()
        assert control.width() >= control.minimumSizeHint().width()
        assert control.parentWidget().rect().contains(control.geometry())
    assert window.size().width() == 1100


def test_folder_paths_wrap_without_horizontal_overflow(qapp, rendered_window):
    window = rendered_window
    window.nav_list.setCurrentRow(1)
    page = window.content_stack.currentWidget()
    card = page.findChild(FolderCard)
    for label in card.findChildren(QLabel):
        if label.toolTip() and label.wordWrap():
            label.setText('C:\\' + 'a-long-directory-name\\' * 24 + 'settings.json')
    qapp.processEvents()
    scroll = page.findChild(QScrollArea)
    assert scroll.horizontalScrollBar().maximum() == 0
    assert card.width() <= scroll.viewport().width()
    assert card.sync_now_button.isVisible()


def test_scheduler_bottom_controls_remain_reachable(qapp, rendered_window):
    window = rendered_window
    window.nav_list.setCurrentRow(3)
    page = window.content_stack.currentWidget()
    qapp.processEvents()
    scroll = page.findChild(QScrollArea)
    assert scroll.verticalScrollBar().maximum() > 0
    scroll.ensureWidgetVisible(page.last_error_label)
    qapp.processEvents()
    point = page.last_error_label.mapTo(scroll.viewport(), page.last_error_label.rect().center())
    assert scroll.viewport().rect().contains(point)
    assert scroll.horizontalScrollBar().maximum() == 0


def test_chart_empty_state_tracks_real_data(qapp):
    chart = SyncChartWidget()
    chart.show()
    assert not chart.empty_label.isHidden()
    chart.set_data([0, 1], [2, 3])
    assert chart.empty_label.isHidden()
    chart.set_data([0], [])
    assert not chart.empty_label.isHidden()
    chart.set_data([0], [1])
    chart.clear_data()
    assert not chart.empty_label.isHidden()
