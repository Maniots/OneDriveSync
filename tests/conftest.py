"""Dispose test-owned Qt widgets before their application and timers."""
import gc
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_application = None


def dispose_qt_widgets(app, widgets):
    from PySide6.QtCore import QCoreApplication, QEvent, QTimer
    from shiboken6 import isValid

    # A native child may already have been destroyed by its parent. A Python
    # wrapper in an earlier snapshot is not evidence that its C++ object lives.
    for widget in widgets:
        if not isValid(widget):
            continue
        service = getattr(widget, "sync_service", None)
        if getattr(service, "is_syncing", False):
            service.wait_for_finished()
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
