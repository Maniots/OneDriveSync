"""Qt coordinator for asynchronous checking, download and deferred install."""
import os
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot, Qt

from src.updater import UpdateClient


class _UpdateWorker(QObject):
    completed = Signal(object)
    failed = Signal(str)
    progress = Signal(int)
    finished = Signal()

    def __init__(self, client, update=None):
        super().__init__()
        self.client, self.update = client, update

    @Slot()
    def run(self):
        try:
            result = (self.client.download(self.update, self.progress.emit)
                      if self.update is not None else self.client.check())
            self.completed.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()


class UpdateService(QObject):
    changed = Signal()
    available = Signal(str)
    install_started = Signal()

    def __init__(self, sync_service=None, client=None, parent=None, *, cloud_service=None):
        super().__init__(parent)
        self.client = client or UpdateClient()
        self.sync_service = sync_service
        self.cloud_service = cloud_service
        self.state = "idle"
        self.message = "Check for new versions of EverySync."
        self.update = None
        self.installer: Path | None = None
        self.progress = 0
        self.automatic = self.client.load_automatic()
        last_install = self.client.last_install_result()
        if last_install.get("status") == "failed":
            self.message = "The last update failed. " + str(last_install.get("message", "Please retry."))
        self.can_install = bool(getattr(sys, "frozen", False) and sys.platform == "win32")
        self._thread = self._worker = None
        self._result = self._error = None
        self._install_after_check = False
        self._install_requested = False
        self._notified = set()
        self._closing = False
        self.timer = QTimer(self)
        self.timer.setInterval(4 * 60 * 60 * 1000)
        self.timer.timeout.connect(self.check)
        self.initial_check = QTimer(self)
        self.initial_check.setSingleShot(True)
        self.initial_check.timeout.connect(self.check)
        if self.can_install and os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            self.initial_check.start(5000)
            self.timer.start()
        if sync_service is not None and hasattr(sync_service, "state_changed"):
            sync_service.state_changed.connect(self.install_when_idle)
        if cloud_service is not None:
            cloud_service.busy_changed.connect(self.install_when_idle)

    @property
    def busy(self):
        return self._thread is not None or self.state == "installing"

    def _start(self, update=None):
        if self.busy or self._closing:
            return False
        self._result = self._error = None
        self.progress = 0
        self.state = "downloading" if update else "checking"
        self.message = "Downloading update…" if update else "Checking for updates…"
        self._thread = QThread(self)
        self._worker = _UpdateWorker(self.client, update)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.completed.connect(self._save_result)
        self._worker.failed.connect(self._save_error)
        self._worker.progress.connect(self._show_progress)
        self._worker.finished.connect(self._thread.quit, Qt.ConnectionType.DirectConnection)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._finish)
        self._thread.finished.connect(self._thread.deleteLater)
        self.changed.emit()
        self._thread.start()
        return True

    @Slot()
    def check(self, install=False):
        if self.busy or self.state == "ready":
            return False
        self._install_after_check = bool(install)
        return self._start()

    @Slot(object)
    def _save_result(self, result):
        self._result = result

    @Slot(str)
    def _save_error(self, message):
        self._error = message

    @Slot(int)
    def _show_progress(self, percent):
        self.progress = percent
        self.changed.emit()

    @Slot()
    def _finish(self):
        action = self.state
        # finished is emitted before Qt completes deferred worker deletion.
        # Join before releasing wrappers, which Shiboken also uses on exit.
        if self._thread is not None:
            self._thread.wait()
        self._thread = self._worker = None
        if self._closing:
            return
        if self._error:
            self.state, self.message = "error", self._error
            self._install_requested = self._install_after_check = False
            self.changed.emit()
            return
        if action == "checking":
            result = self._result
            self.update = result.update
            self.state = result.status
            messages = {"current": "You have the latest version.",
                        "no_release": "No Windows release has been published yet.",
                        "available": f"Version {result.update.version} is available." if result.update else ""}
            self.message = messages[self.state]
            self.changed.emit()
            if self.update:
                if self.update.version not in self._notified:
                    self._notified.add(self.update.version)
                    self.available.emit(self.update.version)
                if self.automatic or self._install_after_check:
                    self.download_and_install()
        elif action == "downloading":
            self.installer = self._result
            self.state = "ready"
            self.message = "Update verified and ready to install."
            self.changed.emit()
            self.install_when_idle()

    @Slot()
    def download_and_install(self):
        if not self.can_install or self.update is None or self.busy:
            return False
        self._install_requested = True
        if self.state == "ready" and self.installer:
            self.install_when_idle()
            return True
        self.installer = None
        return self._start(self.update)

    @Slot()
    def install_when_idle(self):
        if self.state != "ready" or not self._install_requested:
            return
        if ((self.sync_service is not None and getattr(self.sync_service, "is_syncing", False))
                or (self.cloud_service is not None and self.cloud_service.busy)):
            self.message = "The update will install when synchronization finishes."
            self.changed.emit()
            return
        try:
            self.client.launch_install(self.installer, self.update)
        except Exception as exc:
            self.state, self.message = "error", str(exc)
            self._install_requested = False
            self.changed.emit()
            return
        self.state, self.message = "installing", "Installing update. The app will restart."
        self.changed.emit()
        self.install_started.emit()

    @Slot(bool)
    def set_automatic(self, enabled):
        try:
            self.client.save_automatic(enabled)
        except OSError:
            self.state, self.message = "error", "Cannot save update preferences. Please retry."
            self.changed.emit()
            return
        self.automatic = bool(enabled)
        self.changed.emit()
        if enabled and self.update and not self.busy:
            self.download_and_install()

    @Slot()
    def wait_for_finished(self):
        self._closing = True
        self.timer.stop()
        self.initial_check.stop()
        if self._thread is not None:
            # Completion signals are delivered by the GUI thread. Waiting is
            # only used on exit; do not run completion/install callbacks here.
            self._thread.quit()
            self._thread.wait()
