"""Dispose test-owned Qt widgets before their application and timers."""
import gc
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_application = None


def dispose_sync_services(app, services):
    """Stop test-owned controllers even when Python reference cycles survive."""
    from PySide6.QtCore import QCoreApplication, QEvent, QTimer
    from shiboken6 import isValid

    for service in services:
        if not isValid(service):
            continue
        for timer in service.findChildren(QTimer):
            if isValid(timer):
                timer.stop()
        service.wait_for_finished()
        service.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


@pytest.fixture
def sync_service_factory(qapp):
    from backend.services.sync_service import SyncService

    services = []

    def create(config_service):
        service = SyncService(config_service)
        services.append(service)
        return service

    yield create
    dispose_sync_services(qapp, services)


def dispose_qt_widgets(app, widgets):
    from PySide6.QtCore import QCoreApplication, QEvent, QTimer
    from shiboken6 import isValid

    valid_ids = {id(widget) for widget in widgets if isValid(widget)}
    # A native child may already have been destroyed by its parent. A Python
    # wrapper in an earlier snapshot is not evidence that its C++ object lives.
    for widget in widgets:
        if not isValid(widget):
            continue
        ancestor = widget.parentWidget()
        while ancestor is not None and id(ancestor) not in valid_ids:
            ancestor = ancestor.parentWidget()
        if ancestor is not None:
            continue  # The parent owns native deletion of this menu/window.
        service = getattr(widget, "sync_service", None)
        if getattr(service, "is_syncing", False):
            service.wait_for_finished()
        updater = getattr(widget, "update_service", None)
        if updater is not None:
            updater.wait_for_finished()
        from pyqtgraph import PlotWidget
        charts = ([widget] if isinstance(widget, PlotWidget) else widget.findChildren(PlotWidget))
        for chart in charts:
            if isValid(chart) and chart.plotItem is not None:
                chart.close()
                chart.deleteLater()
        for timer in widget.findChildren(QTimer):
            if isValid(timer):
                timer.stop()
        widget.hide()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


@pytest.fixture(scope="session")
def qapp():
    global _application
    from PySide6.QtWidgets import QApplication
    _application = QApplication.instance() or QApplication([])
    yield _application
    dispose_qt_widgets(_application, _application.topLevelWidgets())
    gc.collect()


@pytest.fixture(autouse=True)
def dispose_test_widgets(request):
    if "qapp" not in request.fixturenames:
        yield
        return
    app = request.getfixturevalue("qapp")
    before = app.topLevelWidgets()
    previous_ids = {id(widget) for widget in before}
    yield
    dispose_qt_widgets(app, [widget for widget in app.topLevelWidgets()
                            if id(widget) not in previous_ids])
