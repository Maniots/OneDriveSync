"""One guided editor for PC folders and ordered storage destinations."""
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWizard, QWizardPage, QScrollArea, QWidget)

from src.cloud_models import RemoteJobConfig, validate_local_path, validate_relative_path
from src.config import BackupSettings, FolderSyncConfig
from src.exceptions import OneDrivePCSyncError
from src.sync_groups import SyncDestinationConfig, SyncGroupConfig
from src.storage_layout import local_sync_paths, remote_sync_path, backup_location


# Cannot collide with a validated connection ID, which starts with a letter.
LOCAL_STORAGE = "__local_folder__"


def _plain(text):
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    return label


class DestinationDialog(QDialog):
    """Choose storage and its folder without requiring a local/cloud category."""

    def __init__(self, config, draft=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Destination")
        self.resize(620, 470)
        self.draft = draft or {}
        self.config = config
        self.sync_name = parent.name_edit.text().strip() if hasattr(parent, "name_edit") else ""
        original = self.draft.get("original")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.storage_combo = QComboBox()
        self.storage_combo.setAccessibleName("Destination storage")
        self.storage_combo.addItem("Folder on this PC or network", LOCAL_STORAGE)
        for connection in config.connections:
            self.storage_combo.addItem(connection.name, connection.id)
        self.path_edit = QLineEdit(self.draft.get("path", ""))
        self.path_edit.setAccessibleName("Destination folder")
        row = QHBoxLayout()
        row.addWidget(self.path_edit)
        self.browse_button = QPushButton("Browse…")
        self.browse_button.clicked.connect(self.browse)
        row.addWidget(self.browse_button)
        form.addRow("Storage", self.storage_combo)
        form.addRow("Folder", row)
        self.hint = _plain("")
        form.addRow(self.hint)
        self.upload_check = QCheckBox("Send files to this destination")
        self.download_check = QCheckBox("Use as a download source, in priority order")
        self.upload_check.setChecked(self.draft.get("upload", True))
        self.download_check.setChecked(self.draft.get("download", True))
        form.addRow(self.upload_check)
        form.addRow(self.download_check)
        self.enabled_check = QCheckBox("Enable this destination")
        self.enabled_check.setChecked(self.draft.get("enabled", getattr(original, "enabled", True)))
        form.addRow(self.enabled_check)
        layout.addLayout(form)
        self.advanced_button = QPushButton("Advanced safety and backup settings")
        self.advanced_button.setCheckable(True)
        layout.addWidget(self.advanced_button)
        self.advanced = QGroupBox("Destination protection")
        advanced = QFormLayout(self.advanced)
        self.threshold = QSpinBox()
        self.threshold.setRange(0, 100)
        self.threshold.setSuffix("%")
        self.threshold.setValue(int(self.draft.get("threshold", getattr(original, "minimum_sync_percentage", 80))))
        self.threshold.setAccessibleName("Minimum file-count safety ratio")
        advanced.addRow("File-count safety ratio", self.threshold)
        self.verify = QCheckBox("Verify files after transfer")
        self.verify.setChecked(self.draft.get("verify", getattr(original, "verify_after_sync", True)))
        advanced.addRow(self.verify)
        self.backup = QCheckBox("Keep a backup before upload")
        original_backup = getattr(original, "backup", None)
        self.backup.setChecked(self.draft.get("backup", getattr(original, "backup_enabled", bool(original_backup and original_backup.enabled))))
        advanced.addRow(self.backup)
        self.backup_path = QLineEdit(self.draft.get("backup_path", str(original_backup.backup_path) if original_backup else ""))
        self.backup_path.setAccessibleName("Local ZIP backup folder inside OneDrive")
        self.retention = QSpinBox()
        self.retention.setRange(1, 36500)
        self.retention.setValue(self.draft.get("retention", original_backup.retention_days if original_backup else 7))
        self.retention.setAccessibleName("Local ZIP backup retention in days")
        advanced.addRow("ZIP backup folder", self.backup_path)
        advanced.addRow("ZIP retention (days)", self.retention)
        self.backup_hint = _plain("")
        advanced.addRow(self.backup_hint)
        self.advanced.setVisible(False)
        self.advanced_button.toggled.connect(self.advanced.setVisible)
        layout.addWidget(self.advanced)
        self.error_label = _plain("")
        layout.addWidget(self.error_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        requested = self.draft.get("storage", LOCAL_STORAGE)
        index = self.storage_combo.findData(requested)
        if index < 0:
            self.storage_combo.addItem("Account disconnected — choose another destination", requested)
            index = self.storage_combo.count() - 1
        self.storage_combo.setCurrentIndex(index)
        self.storage_combo.currentIndexChanged.connect(self.storage_changed)
        self.path_edit.textChanged.connect(self.update_path_hint)
        self.storage_changed()

    def storage_changed(self):
        local = self.storage_combo.currentData() == LOCAL_STORAGE
        if self.draft.get("original") is None and "backup" not in self.draft:
            self.backup.setChecked(not local)
        self.browse_button.setEnabled(local)
        managed = self.draft.get("original") is None and bool(self.sync_name)
        self.path_edit.setReadOnly(managed and not local)
        self.path_edit.setPlaceholderText("Choose a parent folder" if local else "Synchronization name")
        if managed and not local:
            connection = next((c for c in self.config.connections if c.id == self.storage_combo.currentData()), None)
            if connection:
                try:
                    self.path_edit.setText(remote_sync_path(connection, self.sync_name))
                except ValueError:
                    self.path_edit.clear()
        elif managed and local and not Path(self.path_edit.text()).is_absolute():
            self.path_edit.clear()
        self.backup_path.setEnabled(local and not managed)
        self.retention.setEnabled(local)
        self.backup_hint.setText("Local backups are ZIP archives inside your OneDrive folder." if local else
                                 "Cloud backups are verified full snapshots. Restore is available from the activity's Backups menu.")
        self.update_path_hint()

    def update_path_hint(self):
        local = self.storage_combo.currentData() == LOCAL_STORAGE
        if self.draft.get("original") is None and self.sync_name:
            try:
                if local:
                    path, backups = local_sync_paths(self.path_edit.text().strip(), self.sync_name)
                    self.backup_path.setText(str(backups / self.sync_name))
                    text = f"Destination: {path}\nBackups: {backups / self.sync_name}"
                else:
                    connection = next(c for c in self.config.connections if c.id == self.storage_combo.currentData())
                    backup_connection, name = backup_location(connection, self.sync_name)
                    text = f"Destination: {connection.root}/{remote_sync_path(connection, self.sync_name)}\nBackups: {backup_connection.root}/{name}"
            except (ValueError, OSError, StopIteration):
                text = "Choose a parent folder. EverySync/<sync name> and EverySync Backups/<sync name> are added automatically."
            self.hint.setText(text)
        else:
            self.hint.setText("Existing destination. Its saved folder and backup locations are preserved.")

    def browse(self):
        value = QFileDialog.getExistingDirectory(self, "Choose destination folder", self.path_edit.text())
        if value:
            self.path_edit.setText(value)

    def validate_and_accept(self):
        if not self.path_edit.text().strip():
            self.error_label.setText("Choose a destination folder.")
            return
        if not self.upload_check.isChecked() and not self.download_check.isChecked():
            self.error_label.setText("Enable upload or download for this destination.")
            return
        try:
            (validate_local_path if self.storage_combo.currentData() == LOCAL_STORAGE else validate_relative_path)(self.path_edit.text().strip())
        except (ValueError, OSError) as error:
            self.error_label.setText(str(error))
            self.path_edit.setFocus()
            return
        super().accept()

    def values(self):
        return dict(self.draft, storage=self.storage_combo.currentData(), path=self.path_edit.text().strip(),
                    upload=self.upload_check.isChecked(), download=self.download_check.isChecked(),
                    enabled=self.enabled_check.isChecked(),
                    threshold=self.threshold.value(), verify=self.verify.isChecked(),
                    backup=self.backup.isChecked(), backup_path=self.backup_path.text().strip(),
                    retention=self.retention.value())


class SynchronizationEditor(QWizard):
    saved = Signal(str)
    connections_requested = Signal()

    def __init__(self, config_service, item_id=None, parent=None):
        super().__init__(parent)
        self.config_service = config_service
        self.item_id = item_id
        self.group = None
        self.drafts = []
        self.original_ids = set()
        self._original_leaves = {}
        self.ensure_idle = None
        self.setWindowTitle("Edit synchronization" if item_id else "Add synchronization")
        self.resize(850, 650)
        self.setMinimumSize(720, 540)
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setButtonText(QWizard.WizardButton.FinishButton, "Save synchronization")

        source = QWizardPage()
        source.setTitle("Choose the folder on this PC")
        source.setSubTitle("Give it a name, then choose where to keep its copies.")
        form = QFormLayout(source)
        self.name_edit = QLineEdit()
        self.name_edit.setAccessibleName("Synchronization name")
        self.local_edit = QLineEdit()
        self.local_edit.setAccessibleName("Folder on this PC")
        self.local_edit.setPlaceholderText("Choose the folder you want to synchronize")
        self.local_edit.editingFinished.connect(self.suggest_name)
        local_row = QHBoxLayout()
        local_row.addWidget(self.local_edit)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.browse_local)
        local_row.addWidget(browse)
        form.addRow("Name", self.name_edit)
        form.addRow("Folder on this PC", local_row)
        self.enabled_check = QCheckBox("Enable this synchronization")
        self.enabled_check.setChecked(True)
        form.addRow(self.enabled_check)
        source.registerField("activityName*", self.name_edit)
        source.registerField("localFolder*", self.local_edit)
        self.addPage(source)

        destinations = QWizardPage()
        destinations.setTitle("Choose destinations and download priority")
        destinations.setSubTitle("Upload goes to every enabled destination. Download uses one source, from top to bottom.")
        layout = QVBoxLayout(destinations)
        self.destination_table = QTableWidget(0, 5)
        self.destination_table.setHorizontalHeaderLabels(["Priority", "Destination", "Folder", "Upload", "Download"])
        self.destination_table.setAccessibleName("Ordered synchronization destinations")
        self.destination_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.destination_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.destination_table.verticalHeader().hide()
        self.destination_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.destination_table.horizontalHeader().setStretchLastSection(True)
        self.destination_table.setColumnWidth(0, 65)
        self.destination_table.setColumnWidth(1, 155)
        self.destination_table.setColumnWidth(2, 275)
        self.destination_table.setColumnWidth(3, 70)
        self.destination_table.itemDoubleClicked.connect(lambda *_: self.edit_destination())
        layout.addWidget(self.destination_table)
        actions = QHBoxLayout()
        for text, callback in [("Add destination", self.open_destination), ("Edit", self.edit_destination),
                               ("Remove", self.remove_destination), ("Move up", lambda: self.move_destination(-1)),
                               ("Move down", lambda: self.move_destination(1))]:
            button = QPushButton(text)
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)
        connections = QPushButton("Connect another account…")
        connections.clicked.connect(self.connections_requested)
        layout.addWidget(connections)
        self.addPage(destinations)

        review = QWizardPage()
        review.setTitle("Review and save")
        review.setSubTitle("Existing files and backups are kept. You can preview transfers with Dry Run in Settings.")
        review_layout = QVBoxLayout(review)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        contents = QVBoxLayout(content)
        self.summary_label = _plain("")
        contents.addWidget(self.summary_label)
        advanced = QGroupBox("Advanced download options")
        advanced_layout = QVBoxLayout(advanced)
        self.unavailable_check = QCheckBox("Try the next source when a service is unavailable")
        advanced_layout.addWidget(self.unavailable_check)
        advanced_layout.addWidget(_plain("Access errors, incomplete copies and known older copies always stop the download."))
        self.untracked_check = QCheckBox("Allow existing copies whose freshness is unknown")
        advanced_layout.addWidget(self.untracked_check)
        advanced_layout.addWidget(_plain("Use this to download preexisting copies before the first verified upload. Freshness history belongs to this configuration on this PC; it does not certify the newest copy across computers."))
        contents.addWidget(advanced)
        contents.addStretch()
        scroll.setWidget(content)
        review_layout.addWidget(scroll)
        self.error_label = _plain("")
        review_layout.addWidget(self.error_label)
        self.addPage(review)
        self.currentIdChanged.connect(lambda *_: self.update_summary())
        self.load_item()
        self.name_edit.textChanged.connect(lambda *_: self.refresh_destinations())

    def browse_local(self):
        value = QFileDialog.getExistingDirectory(self, "Choose the folder on this PC", self.local_edit.text())
        if value:
            self.local_edit.setText(value)
            self.suggest_name()

    def suggest_name(self):
        if not self.name_edit.text().strip():
            self.name_edit.setText(Path(self.local_edit.text()).name)

    def load_item(self):
        config = self.config_service.get_app_config()
        self.group = next((group for group in config.sync_groups if group.id == self.item_id), None)
        leaves = {leaf.id: leaf for leaf in [*config.folders, *config.remote_jobs]}
        if self.group:
            self.name_edit.setText(self.group.name)
            self.local_edit.setText(self.group.local_path)
            self.enabled_check.setChecked(self.group.enabled)
            self.unavailable_check.setChecked(self.group.fallback_on_unavailable)
            self.untracked_check.setChecked(self.group.allow_untracked_download)
            targets = self.group.destinations
        elif self.item_id in leaves:
            leaf = leaves[self.item_id]
            self.name_edit.setText(leaf.name)
            self.local_edit.setText(str(leaf.local_path))
            self.enabled_check.setChecked(leaf.enabled)
            targets = [SyncDestinationConfig(leaf.id)]
        else:
            targets = []
        for target in targets:
            leaf = leaves[target.job_id]
            self.original_ids.add(leaf.id)
            self._original_leaves[leaf.id] = leaf
            self.add_destination(leaf.connection_id if isinstance(leaf, RemoteJobConfig) else LOCAL_STORAGE,
                                 leaf.remote_path if isinstance(leaf, RemoteJobConfig) else str(leaf.onedrive_path),
                                 original=leaf, upload=target.upload_enabled, download=target.download_enabled)
        if any(getattr(leaf, "bidirectional", False) for leaf in self._original_leaves.values()):
            self.unavailable_check.setEnabled(False)
            self.untracked_check.setEnabled(False)

    def add_destination(self, storage, path, **values):
        self.drafts.append(dict(dict(storage=storage, path=path, upload=True, download=True), **values))
        self.refresh_destinations(len(self.drafts) - 1)

    def open_destination(self):
        dialog = DestinationDialog(self.config_service.get_app_config(), parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.drafts.append(dialog.values())
            self.refresh_destinations(len(self.drafts) - 1)

    def edit_destination(self):
        row = self.destination_table.currentRow()
        if row < 0:
            return
        dialog = DestinationDialog(self.config_service.get_app_config(), self.drafts[row], self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.drafts[row] = dialog.values()
            self.refresh_destinations(row)

    def remove_destination(self):
        row = self.destination_table.currentRow()
        if row >= 0:
            self.drafts.pop(row)
            self.refresh_destinations(min(row, len(self.drafts) - 1))

    def move_destination(self, offset):
        row = self.destination_table.currentRow()
        other = row + offset
        if row >= 0 and 0 <= other < len(self.drafts):
            self.drafts[row], self.drafts[other] = self.drafts[other], self.drafts[row]
            self.refresh_destinations(other)

    def refresh_destinations(self, selected=0):
        config = self.config_service.get_app_config()
        connections = {connection.id: connection for connection in config.connections}
        self.destination_table.setRowCount(len(self.drafts))
        priority = 0
        for row, draft in enumerate(self.drafts):
            if draft["download"]:
                priority += 1
            connection = connections.get(draft["storage"])
            storage = ("Folder on PC / network" if draft["storage"] == LOCAL_STORAGE else
                       connection.name if connection else "Account disconnected — choose another destination")
            try:
                path = self.destination_path(draft, config)
            except (ValueError, OSError):
                path = draft["path"]
            values = [str(priority) if draft["download"] else "—", storage, path,
                      "Yes" if draft["upload"] else "No", "Yes" if draft["download"] else "No"]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.destination_table.setItem(row, column, item)
        if selected >= 0:
            self.destination_table.selectRow(selected)
        self.update_summary()

    def destination_path(self, draft, config):
        original = draft.get("original")
        if original is not None:
            original_path = original.remote_path if isinstance(original, RemoteJobConfig) else str(original.onedrive_path)
            original_storage = original.connection_id if isinstance(original, RemoteJobConfig) else LOCAL_STORAGE
            if draft["storage"] == original_storage and draft["path"] == original_path:
                return draft["path"]
        name = self.name_edit.text().strip()
        if draft["storage"] == LOCAL_STORAGE:
            return str(local_sync_paths(draft["path"], name)[0])
        connection = next((c for c in config.connections if c.id == draft["storage"]), None)
        if connection is None:
            raise ValueError("The destination account was disconnected. Choose another destination.")
        return remote_sync_path(connection, name)

    def update_summary(self):
        if not hasattr(self, "summary_label"):
            return
        config = self.config_service.get_app_config()
        connections = {connection.id: connection for connection in config.connections}
        lines = [self.name_edit.text(), f"Folder on this PC: {self.local_edit.text()}", "", "Destinations (download priority):"]
        for position, draft in enumerate(self.drafts, 1):
            connection = connections.get(draft["storage"])
            try:
                path = self.destination_path(draft, config)
            except (ValueError, OSError, StopIteration):
                path = draft["path"]
            destination = f"{connection.name}: {connection.root.rstrip('/')}/{path}" if connection else path
            lines.append(f"{position}. {destination} · Upload {'on' if draft['upload'] else 'off'} · Download {'on' if draft['download'] else 'off'}")
            if draft.get("backup", getattr(draft.get("original"), "backup_enabled", False)):
                try:
                    if connection:
                        backup_connection, folder_name = backup_location(connection, self.name_edit.text().strip())
                        lines.append(f"   Backups: {backup_connection.root}/{folder_name}")
                    elif draft.get("original") is None:
                        lines.append(f"   Backups: {local_sync_paths(draft['path'], self.name_edit.text().strip())[1] / self.name_edit.text().strip()}")
                except (ValueError, OSError):
                    pass
        if any(getattr(draft.get("original"), "bidirectional", False) for draft in self.drafts):
            lines.append("\nThis existing activity synchronizes both folders. It can keep only one destination.")
        removed = self.original_ids - {getattr(draft.get("original"), "id", None) for draft in self.drafts}
        if removed:
            lines.append("\nRemoved destinations will be disabled as separate activities. Their files, history and backups are kept.")
        self.summary_label.setText("\n".join(lines))

    def save_activity(self):
        try:
            if self.ensure_idle:
                self.ensure_idle()
            config = self.config_service.get_app_config()
            current_leaves = {leaf.id: leaf for leaf in [*config.folders, *config.remote_jobs]}
            if self.group and next((item for item in config.sync_groups if item.id == self.group.id), None) != self.group:
                raise ValueError("This synchronization changed elsewhere. Close the editor and reopen it.")
            for identifier, original in self._original_leaves.items():
                if current_leaves.get(identifier) != original:
                    raise ValueError("A destination changed elsewhere. Close the editor and reopen it.")
            name, local = self.name_edit.text().strip(), self.local_edit.text().strip()
            if not name or not local or not self.drafts:
                raise ValueError("Choose a name, a PC folder and at least one destination.")
            folders, jobs = list(config.folders), list(config.remote_jobs)
            targets = []
            for draft in self.drafts:
                path = self.destination_path(draft, config)
                original = draft.get("original")
                same_kind = original is not None and ((draft["storage"] == LOCAL_STORAGE) == isinstance(original, FolderSyncConfig))
                identifier = original.id if same_kind else ("f_" if draft["storage"] == LOCAL_STORAGE else "j_") + uuid4().hex
                common = dict(id=identifier, name=name, local_path=local,
                              enabled=draft.get("enabled", original.enabled if same_kind else True),
                              minimum_sync_percentage=draft.get("threshold", getattr(original, "minimum_sync_percentage", 80)),
                              verify_after_sync=draft.get("verify", getattr(original, "verify_after_sync", True)))
                if draft["storage"] == LOCAL_STORAGE:
                    backup = original.backup if same_kind else None
                    if "backup" in draft:
                        if draft["backup"] and (not same_kind or path != str(original.onedrive_path)):
                            backup = BackupSettings(True, Path(path).parent.parent / "EverySync Backups", draft["retention"], name)
                        else:
                            backup = (BackupSettings(True, draft["backup_path"], draft["retention"],
                                                     original.backup.directory_name if same_kind and original.backup else None)
                                      if draft["backup"] else None)
                    leaf = FolderSyncConfig(**common, onedrive_path=path,
                                            create_destination=original.create_destination if same_kind else True, backup=backup)
                    folders = [item for item in folders if item.id != identifier] + [leaf]
                else:
                    leaf = RemoteJobConfig(**common, connection_id=draft["storage"], remote_path=path,
                                           backup_enabled=draft.get("backup", getattr(original, "backup_enabled", True)),
                                           bidirectional=getattr(original, "bidirectional", False) if same_kind else False)
                    jobs = [item for item in jobs if item.id != identifier] + [leaf]
                targets.append(SyncDestinationConfig(identifier, draft["upload"], draft["download"]))
            retained = {target.job_id for target in targets}
            detached = self.original_ids - retained
            folders = [replace(item, enabled=False) if item.id in detached else item for item in folders]
            jobs = [replace(item, enabled=False) if item.id in detached else item for item in jobs]
            preserve_singleton = (self.group is None and len(targets) == 1
                                  and retained == self.original_ids
                                  and targets[0].upload_enabled and targets[0].download_enabled
                                  and not self.unavailable_check.isChecked()
                                  and not self.untracked_check.isChecked())
            if preserve_singleton:
                identifier = targets[0].job_id
                active = self.enabled_check.isChecked() and self.drafts[0].get("enabled", True)
                folders = [replace(item, enabled=active) if item.id == identifier else item for item in folders]
                jobs = [replace(item, enabled=active) if item.id == identifier else item for item in jobs]
                self.config_service.save(replace(config, folders=folders, remote_jobs=jobs))
                self.saved.emit(identifier)
                return True
            group = SyncGroupConfig(self.group.id if self.group else "g_" + uuid4().hex, name, local, targets,
                                   enabled=self.enabled_check.isChecked(),
                                   fallback_on_unavailable=self.unavailable_check.isChecked(),
                                   allow_untracked_download=self.untracked_check.isChecked())
            groups = [item for item in config.sync_groups if item.id != group.id] + [group]
            self.config_service.save(replace(config, folders=folders, remote_jobs=jobs, sync_groups=groups))
            self.saved.emit(group.id)
            return True
        except (OneDrivePCSyncError, ValueError, OSError, RuntimeError) as error:
            self.error_label.setText(str(error))
            return False

    def accept(self):
        if self.save_activity():
            super().accept()
