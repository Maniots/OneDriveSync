from PySide6.QtCore import QCoreApplication, QEvent, QTimer
from shiboken6 import isValid
import pytest

from backend.services.sync_service import SyncService
from tests import conftest


class EmptyConfiguration:
    def get_app_config(self):
        return None


def test_cleanup_cancels_timer_retained_by_restored_bound_method(qapp):
    service = SyncService(EmptyConfiguration())
    # Restoring a monkeypatched instance method can leave this self-cycle.
    service.request_sync = service.request_sync
    callbacks = []
    timer = QTimer(service)
    timer.timeout.connect(lambda: callbacks.append(True))
    timer.start(0)
    try:
        cleanup = conftest.dispose_sync_services
        cleanup(qapp, [service])
        qapp.processEvents()
        assert callbacks == [], "A service timer fired after test cleanup"
        assert not isValid(service)
        assert not isValid(timer)
        # A parent or an earlier cleanup may already have destroyed the native object.
        cleanup(qapp, [service])
    finally:
        if isValid(service):
            timer.stop()
            service.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture
def disposed_services(qapp):
    services = []
    yield services
    assert services
    assert all(not isValid(service) for service in services)


def test_factory_disposes_services_after_monkeypatch_undo(
        qapp, disposed_services, sync_service_factory, monkeypatch):
    service = sync_service_factory(EmptyConfiguration())
    disposed_services.append(service)
    monkeypatch.setattr(service, "wait_for_finished",
                        lambda: pytest.fail("Service cleanup preceded monkeypatch undo"))
    service._monitor_timer.start(30000)
