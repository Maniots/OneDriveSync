from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QHBoxLayout,
    QHeaderView,
    QApplication,
    QFileDialog,
    QMessageBox,
    QComboBox,
    QFrame,
    QFormLayout,
    QLineEdit,
    QSizePolicy,
    QSplitter,
    QScrollArea,
    QStackedWidget,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QStyle,
)
from PySide6.QtCore import Qt, QTimer, QThread, QUrl, Slot
from PySide6.QtGui import QColor, QDesktopServices, QFont, QPainter, QPalette
from backend.services.configuration_service import ConfigurationService
from backend.services.backup_service import BackupService
from ..resources.icons import get_icon
from ..themes import colors, spacing
from ..workers.backup_worker import BackupWorker
from shiboken6 import isValid
import datetime
from pathlib import Path


class _ArchiveNameLabel(QLabel):
    """Elide long filenames while retaining their full accessible text."""
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setFont(self.font())
        painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        text = self.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideMiddle, self.contentsRect().width())
        painter.drawText(self.contentsRect(), Qt.AlignmentFlag.AlignVCenter, text)


class _ArchiveDelegate(QStyledItemDelegate):
    """Keep folder names prominent and archive filenames secondary."""
    def paint(self, painter, option, index):
        info = index.data(Qt.ItemDataRole.UserRole)
        if not info:
            return super().paint(painter, option, index)
        styled = QStyleOptionViewItem(option)
        self.initStyleOption(styled, index)
        styled.text = ""
        style = option.widget.style() if option.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, styled, painter, option.widget)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.save()
        font = QFont(option.font)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor(colors.SELECTED_TEXT if selected else colors.TEXT_PRIMARY))
        title = option.rect.adjusted(12, 6, -12, -30)
        painter.drawText(title, Qt.AlignmentFlag.AlignVCenter,
            painter.fontMetrics().elidedText(info["folder_name"], Qt.TextElideMode.ElideRight, title.width()))
        font.setWeight(QFont.Weight.Normal)
        font.setPointSize(9)
        painter.setFont(font)
        painter.setPen(QColor(colors.SECONDARY if selected else colors.TEXT_SECONDARY))
        caption = option.rect.adjusted(12, 31, -12, -6)
        painter.drawText(caption, Qt.AlignmentFlag.AlignVCenter,
            painter.fontMetrics().elidedText(Path(info["path"]).name, Qt.TextElideMode.ElideRight, caption.width()))
        painter.restore()


class BackupsPage(QWidget):
    def __init__(self, config_service: ConfigurationService, backup_service: BackupService, parent=None):
        super().__init__(parent)
        self.config_service = config_service
        self.backup_service = backup_service
        self.backup_data = []  # List of backup info dicts for the table
        self._thread = None
        self._worker = None
        self._operation_result = None
        self._thread_cleanup = None
        self.setup_ui()
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.timeout.connect(self.load_configuration_data)
        if hasattr(self.config_service, "changed"):
            self.config_service.changed.connect(self.load_configuration_data)
        QApplication.instance().aboutToQuit.connect(self.wait_for_finished)
        # Load configuration data if backend is available
        app_config = self.config_service.get_app_config()
        if app_config:
            self.refresh_timer.start(0)
        else:
            self.show_no_config_message()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(spacing.LARGE, spacing.MEDIUM, spacing.LARGE, spacing.MEDIUM)
        layout.setSpacing(spacing.SMALL)

        header = QHBoxLayout()
        heading = QVBoxLayout()
        heading.setSpacing(6)
        title = QLabel("Saved backups")
        title.setProperty("h2", "true")
        heading.addWidget(title)
        description = QLabel("Find a previous version and restore the files you need.")
        description.setProperty("description", "true")
        description.setWordWrap(True)
        heading.addWidget(description)
        header.addLayout(heading, 1)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setIcon(get_icon("refresh"))
        self.refresh_btn.setToolTip("Refresh the backup library")
        self.refresh_btn.clicked.connect(self.refresh_backups)
        header.addWidget(self.refresh_btn, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        filters = QHBoxLayout()
        filters.setSpacing(spacing.XSMALL)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search folders or archives…")
        self.search_edit.setAccessibleName("Search backup library")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self.apply_filters)
        filters.addWidget(self.search_edit, 1)
        self.folder_filter = QComboBox()
        self.folder_filter.setAccessibleName("Filter backups by folder")
        self.folder_filter.addItem("All folders", None)
        self.folder_filter.setMinimumWidth(160)
        self.folder_filter.currentIndexChanged.connect(self.apply_filters)
        filters.addWidget(self.folder_filter)
        layout.addLayout(filters)

        history = QHBoxLayout()
        history_title = QLabel("Archive history")
        history_title.setProperty("h3", "true")
        history.addWidget(history_title)
        history.addStretch()
        self.summary_label = QLabel("Loading backups…")
        self.summary_label.setProperty("description", "true")
        history.addWidget(self.summary_label)
        layout.addLayout(history)

        self.dry_run_notice = QLabel("Dry run is on. You can browse archives; restore and delete are disabled.")
        self.dry_run_notice.setProperty("statusWarning", "true")
        self.dry_run_notice.setWordWrap(True)
        self.dry_run_notice.hide()
        layout.addWidget(self.dry_run_notice)
        self.error_label = QLabel()
        self.error_label.setTextFormat(Qt.TextFormat.PlainText)
        self.error_label.setProperty("statusError", "true")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(spacing.SMALL)
        self.list_stack = QStackedWidget()
        self.list_stack.setMinimumWidth(320)
        self.table = QTableWidget(0, 3)
        self.table.setAccessibleName("Backup archives, newest first")
        self.table.setHorizontalHeaderLabels(["Folder / archive", "Created", "Size"])
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.table.horizontalHeaderItem(2).setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 115)
        self.table.setColumnWidth(2, 82)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setAlternatingRowColors(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(64)
        self.table.setItemDelegateForColumn(0, _ArchiveDelegate(self.table))
        self.table.itemSelectionChanged.connect(self.update_selection)
        self.list_stack.addWidget(self.table)

        self.empty_state = QFrame()
        self.empty_state.setProperty("card", "true")
        empty = QVBoxLayout(self.empty_state)
        empty.setContentsMargins(spacing.MEDIUM, spacing.MEDIUM, spacing.MEDIUM, spacing.MEDIUM)
        empty.addStretch()
        empty_icon = QLabel()
        empty_icon.setPixmap(get_icon("backups").pixmap(40, 40))
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.addWidget(empty_icon)
        self.empty_title = QLabel("Loading backups…")
        self.empty_title.setProperty("h3", "true")
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.addWidget(self.empty_title)
        self.empty_description = QLabel()
        self.empty_description.setProperty("description", "true")
        self.empty_description.setWordWrap(True)
        self.empty_description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.addWidget(self.empty_description)
        self.clear_filters_btn = QPushButton("Clear filters")
        self.clear_filters_btn.clicked.connect(self.clear_filters)
        empty.addWidget(self.clear_filters_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        self.clear_filters_btn.hide()
        empty.addStretch()
        self.list_stack.addWidget(self.empty_state)
        self.list_stack.setCurrentWidget(self.empty_state)
        self.splitter.addWidget(self.list_stack)

        self.detail_card = QFrame()
        self.detail_card.setProperty("card", "true")
        self.detail_card.setMinimumWidth(260)
        self.detail_card.setMaximumWidth(300)
        detail = QVBoxLayout(self.detail_card)
        detail.setContentsMargins(spacing.MEDIUM, spacing.SMALL, spacing.MEDIUM, spacing.SMALL)
        detail.setSpacing(spacing.XSMALL)
        metadata_scroll = QScrollArea()
        metadata_scroll.setWidgetResizable(True)
        metadata_scroll.setMinimumHeight(80)
        metadata_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        metadata_scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget { background: transparent; }")
        metadata_body = QWidget()
        metadata_body.setObjectName("backupMetadata")
        metadata_body.setStyleSheet("QWidget#backupMetadata { background: transparent; }")
        metadata_layout = QVBoxLayout(metadata_body)
        metadata_layout.setContentsMargins(0, 0, 0, 0)
        metadata_layout.setSpacing(spacing.SMALL)
        eyebrow = QLabel("SELECTED BACKUP")
        eyebrow.setProperty("eyebrow", "true")
        metadata_layout.addWidget(eyebrow)
        self.detail_title = QLabel("Select a backup")
        self.detail_title.setProperty("h3", "true")
        self.detail_title.setTextFormat(Qt.TextFormat.PlainText)
        self.detail_title.setWordWrap(True)
        metadata_layout.addWidget(self.detail_title)
        self.detail_archive = _ArchiveNameLabel("Choose an archive to see its details.")
        self.detail_archive.setProperty("description", "true")
        self.detail_archive.setTextFormat(Qt.TextFormat.PlainText)
        self.detail_archive.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        metadata_layout.addWidget(self.detail_archive)
        metadata = QFormLayout()
        metadata.setSpacing(spacing.XSMALL)
        self.detail_date = QLabel("—")
        self.detail_size = QLabel("—")
        metadata.addRow("Created", self.detail_date)
        metadata.addRow("Archive size", self.detail_size)
        metadata_layout.addLayout(metadata)
        location_label = QLabel("Archive location")
        location_label.setProperty("description", "true")
        metadata_layout.addWidget(location_label)
        self.location_edit = QLineEdit()
        self.location_edit.setReadOnly(True)
        self.location_edit.setAccessibleName("Selected backup archive path")
        metadata_layout.addWidget(self.location_edit)
        metadata_layout.addStretch()
        metadata_scroll.setWidget(metadata_body)
        detail.addWidget(metadata_scroll, 1)
        self.restore_note = QLabel("Choose a destination when you restore. Files with matching names will be overwritten.")
        self.restore_note.setProperty("description", "true")
        self.restore_note.setWordWrap(True)
        detail.addWidget(self.restore_note)
        self.restore_btn = QPushButton("Restore backup")
        self.restore_btn.setIcon(get_icon("restore"))
        self.restore_btn.setProperty("primary", "true")
        self.restore_btn.clicked.connect(lambda: self._selected_action("restore_backup"))
        detail.addWidget(self.restore_btn)
        self.open_btn = QPushButton("Open location")
        self.open_btn.setIcon(get_icon("open"))
        self.open_btn.clicked.connect(lambda: self._selected_action("open_backup"))
        detail.addWidget(self.open_btn)
        self.delete_btn = QPushButton("Delete archive")
        self.delete_btn.setObjectName("deleteArchive")
        self.delete_btn.setStyleSheet(f"QPushButton#deleteArchive {{ color: {colors.ERROR}; background: transparent; border-color: transparent; }} QPushButton#deleteArchive:hover {{ background: {colors.HOVER}; border-color: {colors.BORDER}; }} QPushButton#deleteArchive:disabled {{ color: {colors.TEXT_DISABLED}; }} QPushButton#deleteArchive:focus {{ border-color: {colors.FOCUS}; }}")
        self.delete_btn.clicked.connect(lambda: self._selected_action("delete_backup"))
        detail.addWidget(self.delete_btn)
        self.splitter.addWidget(self.detail_card)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([600, 280])
        layout.addWidget(self.splitter, 1)

        self.status_label = QLabel("Loading backups…")
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setProperty("description", "true")
        layout.addWidget(self.status_label)
        self.update_selection()

    @Slot()
    def load_configuration_data(self):
        """Refresh the library without losing the selected archive or filters."""
        if self._thread is not None:
            return
        selected = self.selected_backup()
        selected_path = selected["path"] if selected else None
        try:
            app_config = self.config_service.get_app_config()
            if not app_config:
                self.show_no_config_message()
                return
            self.backup_data = []
            folder_filter = self.folder_filter.currentData()
            self.folder_filter.blockSignals(True)
            try:
                self.folder_filter.clear()
                self.folder_filter.addItem("All folders", None)
                for folder in app_config.folders:
                    if folder.backup and folder.backup.enabled:
                        self.folder_filter.addItem(folder.name, folder.id)
                        self.backup_data.extend({**info, "folder_id": folder.id, "folder_name": folder.name}
                            for info in self.backup_service.get_backup_info_formatted(folder.id))
                self.folder_filter.setCurrentIndex(max(0, self.folder_filter.findData(folder_filter)))
            finally:
                self.folder_filter.blockSignals(False)
            self.backup_data.sort(key=lambda info: (info["timestamp"], info["folder_name"].casefold(), info["path"]), reverse=True)
            self.table.blockSignals(True)
            try:
                self.table.clearSelection()
                self.table.setCurrentCell(-1, -1)
                self.table.setRowCount(len(self.backup_data))
                for row, info in enumerate(self.backup_data):
                    folder_item = QTableWidgetItem(info["folder_name"] + "\n" + Path(info["path"]).name)
                    folder_item.setData(Qt.ItemDataRole.UserRole, info)
                    folder_item.setToolTip(info["folder_name"] + "\n" + info["path"])
                    self.table.setItem(row, 0, folder_item)
                    created = QTableWidgetItem(self.calculate_age(info["timestamp"]) + "\n" + info["timestamp"])
                    created.setToolTip("Archive date: " + info["timestamp"])
                    self.table.setItem(row, 1, created)
                    size = QTableWidgetItem(info["size"])
                    size.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    self.table.setItem(row, 2, size)
            finally:
                self.table.blockSignals(False)
            self.error_label.hide()
            self.dry_run_notice.setVisible(app_config.general.dry_run)
            self.apply_filters()
            visible = [row for row in range(self.table.rowCount()) if not self.table.isRowHidden(row)]
            chosen = next((row for row in visible if self.backup_data[row]["path"] == selected_path),
                          visible[0] if visible else None)
            if chosen is not None:
                self.table.setCurrentCell(chosen, 0)
                self.table.selectRow(chosen)
            self.update_selection()
            self.status_label.setText(f"Found {len(self.backup_data)} backup(s)" if self.backup_data else "No backups found")
        except Exception as error:
            self.show_error(f"Error loading backup data: {error}")

    def selected_backup(self):
        row = self.table.currentRow()
        if row < 0 or self.table.isRowHidden(row) or not self.table.selectionModel().isRowSelected(row):
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _selected_action(self, method):
        info = self.selected_backup()
        if info is not None and self._thread is None:
            getattr(self, method)(info["folder_id"], info["path"])

    def update_selection(self):
        info = self.selected_backup()
        config = self.config_service.get_app_config()
        dry_run = bool(config and config.general.dry_run)
        active = info is not None and self._thread is None
        self.restore_btn.setEnabled(active and not dry_run)
        self.open_btn.setEnabled(active)
        self.delete_btn.setEnabled(active and not dry_run)
        self.restore_btn.setToolTip("Restore is disabled in dry-run mode" if dry_run else "Restore the selected archive into a folder you choose")
        self.delete_btn.setToolTip("Deletion is disabled in dry-run mode" if dry_run else "Permanently delete the selected archive")
        self.detail_title.setText(info["folder_name"] if info else "Select a backup")
        self.detail_archive.setText(Path(info["path"]).name if info else "Choose an archive to see its details.")
        self.detail_archive.setToolTip(info["path"] if info else "")
        self.detail_date.setText(info["timestamp"] if info else "—")
        self.detail_size.setText(info["size"] if info else "—")
        self.location_edit.setText(info["path"] if info else "")
        self.location_edit.setCursorPosition(0)
        self.location_edit.setToolTip(info["path"] if info else "")

    def apply_filters(self, *args):
        query = self.search_edit.text().strip().casefold()
        folder_id = self.folder_filter.currentData()
        visible = 0
        for row in range(self.table.rowCount()):
            info = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            matches = (folder_id is None or folder_id == info["folder_id"]) and (
                not query or query in " ".join((info["folder_name"], info["timestamp"], info["path"])).casefold())
            self.table.setRowHidden(row, not matches)
            visible += matches
        if self.table.currentRow() >= 0 and self.table.isRowHidden(self.table.currentRow()):
            self.table.clearSelection()
            self.table.setCurrentCell(-1, -1)
        total = len(self.backup_data)
        folders = len({info["folder_id"] for info in self.backup_data})
        self.summary_label.setText(f"{visible} of {total} archives" if visible != total else
            f"{total} {'archive' if total == 1 else 'archives'} · {folders} {'folder' if folders == 1 else 'folders'}")
        self.list_stack.setCurrentWidget(self.table if visible else self.empty_state)
        self.detail_card.setVisible(bool(visible))
        self.empty_title.setText("No matching backups" if total else "No backups yet")
        self.empty_description.setText("Try another search or folder, or clear your filters." if total else
            "Archives appear here when a synchronization creates a backup. Enable backups for a folder to keep previous versions.")
        self.clear_filters_btn.setVisible(bool(query or folder_id is not None))
        self.update_selection()

    def clear_filters(self):
        self.search_edit.clear()
        self.folder_filter.setCurrentIndex(0)

    def calculate_age(self, timestamp_str: str) -> str:
        """Calculate age from timestamp string (YYYY-MM-DD) and return a human-readable string."""
        try:
            backup_date = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d").date()
            today = datetime.date.today()
            delta = today - backup_date
            if delta.days == 0:
                return "Today"
            elif delta.days == 1:
                return "Yesterday"
            elif delta.days < 7:
                return f"{delta.days} days ago"
            elif delta.days < 30:
                weeks = delta.days // 7
                return f"{weeks} week{'s' if weeks > 1 else ''} ago"
            else:
                months = delta.days // 30
                return f"{months} month{'s' if months > 1 else ''} ago"
        except Exception:
            return "Unknown"

    def refresh_backups(self):
        """Refresh the backup table."""
        self.load_configuration_data()

    def _action_error(self, message):
        # Keep the rows available after a recoverable operation failure.
        self.error_label.setText(message)
        self.error_label.show()
        self.status_label.setText(message)

    def open_backup(self, folder_id, archive_path):
        if self._thread is not None:
            return
        try:
            archive = self.backup_service.get_archive_path(folder_id, archive_path)
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(archive.parent))):
                raise RuntimeError("The backup directory could not be opened")
            self.error_label.hide()
            self.status_label.setText(f"Opened {archive.parent}")
        except Exception as exc:
            self._action_error(f"Unable to open backup: {exc}")

    def delete_backup(self, folder_id, archive_path):
        if self._thread is not None:
            return
        try:
            archive = self.backup_service.get_archive_path(folder_id, archive_path)
            answer = QMessageBox.question(
                self, "Delete backup", f"Permanently delete this backup archive?\n\n{archive}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
            self.backup_service.delete_backup(folder_id, archive)
            self.load_configuration_data()
            self.status_label.setText(f"Deleted {archive.name}")
        except Exception as exc:
            self._action_error(f"Unable to delete backup: {exc}")

    def restore_backup(self, folder_id, archive_path):
        if self._thread is not None:
            return
        try:
            archive = self.backup_service.get_archive_path(folder_id, archive_path)
            target = QFileDialog.getExistingDirectory(self, "Choose restore directory")
            if not target:
                return
            answer = QMessageBox.question(
                self, "Restore backup",
                f"Restore {archive.name} into:\n{target}\n\n"
                "Existing files with matching names will be overwritten. Other files will be retained.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
            self.error_label.hide()
            self.status_label.setText(f"Restoring {archive.name}…")
            self.refresh_btn.setEnabled(False)
            self.table.setEnabled(False)
            self.search_edit.setEnabled(False)
            self.folder_filter.setEnabled(False)
            self._operation_result = None
            # Application ownership also protects against page removal during a restore.
            self._thread = QThread(QApplication.instance())
            self._worker = BackupWorker(self.backup_service, folder_id, str(archive), target)
            self.update_selection()
            self._worker.moveToThread(self._thread)
            self._thread.started.connect(self._worker.run)
            self._worker.completed.connect(self._restore_completed)
            self._worker.failed.connect(self._restore_failed)
            self._worker.finished.connect(self._thread.quit, Qt.ConnectionType.DirectConnection)
            self._worker.finished.connect(self._worker.deleteLater)
            self._thread.finished.connect(self._restore_finished)
            self._thread.finished.connect(self._thread.deleteLater)
            # A page can be disposed before QApplication exits. The closure
            # remains connected independently of the page's QObject lifetime.
            thread = self._thread
            self._thread_cleanup = lambda: thread.wait() if isValid(thread) and thread.isRunning() else None
            self.destroyed.connect(self._thread_cleanup)
            self._thread.start()
        except Exception as exc:
            self.refresh_btn.setEnabled(True)
            self.table.setEnabled(True)
            self.search_edit.setEnabled(True)
            self.folder_filter.setEnabled(True)
            self.update_selection()
            self._action_error(f"Unable to restore backup: {exc}")

    @Slot(int)
    def _restore_completed(self, count):
        self._operation_result = (True, f"Restored {count} file(s)")

    @Slot(str)
    def _restore_failed(self, message):
        self._operation_result = (False, f"Unable to restore backup: {message}")

    @Slot()
    def _restore_finished(self):
        if self._thread_cleanup is not None:
            self.destroyed.disconnect(self._thread_cleanup)
            self._thread_cleanup = None
        self._worker = None
        self._thread = None
        self.refresh_btn.setEnabled(True)
        self.table.setEnabled(True)
        self.search_edit.setEnabled(True)
        self.folder_filter.setEnabled(True)
        self.load_configuration_data()
        if self._operation_result:
            success, message = self._operation_result
            if success:
                self.status_label.setText(message)
            else:
                self._action_error(message)

    @Slot()
    def wait_for_finished(self):
        if self._thread is not None:
            self._thread.wait()

    def show_no_config_message(self):
        """Show a message when no configuration is available."""
        self.show_error("No configuration available. Backup information cannot be displayed.")

    def show_error(self, message):
        """Show an error message."""
        self.table.setRowCount(0)
        self.backup_data = []
        self.list_stack.setCurrentWidget(self.empty_state)
        self.detail_card.hide()
        self.empty_title.setText("Backups couldn't be loaded")
        self.empty_description.setText("Check the backup location and configuration, then choose Refresh to retry.")
        self.clear_filters_btn.hide()
        self.summary_label.setText("Library unavailable")
        self.update_selection()
        self.error_label.setText(message)
        self.error_label.show()
        self.status_label.setText(message)

    # For compatibility with the existing MainWindow, we keep the config_backend argument
    # even though we don't use it.
