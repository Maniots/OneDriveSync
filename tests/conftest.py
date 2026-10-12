"""Keep Qt alive until widgets and queued thread cleanup are disposed."""
import gc
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_application = None


@pytest.fixture(scope="session")
def qapp():
    global _application
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication
    _application = QApplication.instance() or QApplication([])
    yield _application
    for widget in _application.topLevelWidgets():
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    _application.processEvents()
    gc.collect()
