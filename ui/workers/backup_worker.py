"""Restore a managed archive without blocking the GUI event loop."""

from PySide6.QtCore import QObject, Signal, Slot


class BackupWorker(QObject):
    completed = Signal(int)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, backup_service, folder_id, archive_path, target_path):
        super().__init__()
        self._service = backup_service
        self._folder_id = folder_id
        self._archive_path = archive_path
        self._target_path = target_path

    @Slot()
    def run(self):
        try:
            count = self._service.restore_backup(self._folder_id, self._archive_path, self._target_path)
            self.completed.emit(count)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()
