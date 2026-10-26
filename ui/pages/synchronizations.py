"""One workspace for folders and ordered, mixed storage destinations."""
from dataclasses import replace
from datetime import datetime

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog,
    QFileDialog, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMenu, QMessageBox, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from src.cloud_models import RemoteJobConfig
from src.cloud_providers import PROVIDER_SETUP
from src.exceptions import OneDrivePCSyncError
from src.group_state import GroupState
from src.sync_groups import destination_identity
from ..themes import spacing
from ..widgets.synchronization_editor import SynchronizationEditor


class SynchronizationsPage(QWidget):
    connections_requested = Signal()
    backups_requested = Signal()

    def __init__(self, config_service, cloud_service, parent=None):
        super().__init__(parent)
        self.config_service, self.service = config_service, cloud_service
        self.sync_service = cloud_service.sync_service
        self.editor = None
        self._resume_editor = False
        self._snapshot_job = None
        self.snapshot_dialog = None
        self.activities = {}
        self.history = {}
        self.evidence = {}
        self.evidence_error = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        scroll.setWidget(body)
        outer.addWidget(scroll)
        layout.setContentsMargins(spacing.LARGE, spacing.MEDIUM, spacing.LARGE, spacing.MEDIUM)
        layout.setSpacing(spacing.SMALL)
        description = QLabel("Keep one PC folder in several destinations. Send to all enabled destinations; download from one source in your chosen order.")
        description.setWordWrap(True)
        layout.addWidget(description)
        toolbar = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search names, folders or destinations…")
        self.search_edit.setAccessibleName("Search synchronizations")
        self.search_edit.textChanged.connect(self.filter_activities)
        toolbar.addWidget(self.search_edit, 1)
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All", "Enabled", "Disabled"])
        self.filter_combo.setAccessibleName("Filter synchronization status")
        self.filter_combo.currentIndexChanged.connect(self.filter_activities)
        toolbar.addWidget(self.filter_combo)
        self.add_button = QPushButton("Add synchronization")
        self.add_button.setProperty("primary", "true")
        self.add_button.clicked.connect(lambda: self.open_editor())
        toolbar.addWidget(self.add_button)
        layout.addLayout(toolbar)
        self.activity_list = QTreeWidget()
        self.activity_list.setAccessibleName("Synchronizations")
        self.activity_list.setHeaderLabels(["Synchronization", "Folder on this PC", "Destinations", "Last result"])
        self.activity_list.setRootIsDecorated(False)
        self.activity_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.activity_list.setMinimumHeight(125)
        self.activity_list.setMaximumHeight(300)
        self.activity_list.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.activity_list.setColumnWidth(0, 170)
        self.activity_list.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.activity_list.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.activity_list.setColumnWidth(2, 190)
        self.activity_list.header().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.activity_list.setColumnWidth(3, 145)
        self.activity_list.currentItemChanged.connect(self.show_selected)
        layout.addWidget(self.activity_list, 1)
        self.empty_label = QLabel("No synchronizations yet. Add a folder and choose where to keep its copies.")
        self.empty_label.setWordWrap(True)
        layout.addWidget(self.empty_label)
        self.details = QGroupBox("Selected synchronization")
        detail_layout = QVBoxLayout(self.details)
        self.folder_label = QLabel()
        self.folder_label.setTextFormat(Qt.TextFormat.PlainText)
        self.folder_label.setWordWrap(True)
        self.folder_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        detail_layout.addWidget(self.folder_label)
        self.destination_table = QTableWidget(0, 4)
        self.destination_table.setAccessibleName("Destination priority and results")
        self.destination_table.setHorizontalHeaderLabels(["Destination", "Folder", "Use", "Copy / last result"])
        self.destination_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.destination_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.destination_table.verticalHeader().hide()
        self.destination_table.setMinimumHeight(130)
        self.destination_table.setMaximumHeight(280)
        self.destination_table.setColumnWidth(0, 185)
        self.destination_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.destination_table.setColumnWidth(2, 145)
        self.destination_table.setColumnWidth(3, 150)
        detail_layout.addWidget(self.destination_table)
        self.freshness_label = QLabel()
        self.freshness_label.setTextFormat(Qt.TextFormat.PlainText)
        self.freshness_label.setWordWrap(True)
        self.freshness_label.setProperty("description", "true")
        detail_layout.addWidget(self.freshness_label)
        layout.addWidget(self.details)
        primary = QHBoxLayout()
        self.upload_button = QPushButton("Send to destinations")
        self.upload_button.setProperty("primary", "true")
        self.upload_button.clicked.connect(lambda: self.run_selected("upload"))
        self.download_button = QPushButton("Download to this PC")
        self.download_button.clicked.connect(lambda: self.run_selected("download"))
        self.edit_button = QPushButton("Edit…")
        self.edit_button.clicked.connect(lambda: self.open_editor(self.selected_id()))
        for button in (self.upload_button, self.download_button, self.edit_button):
            primary.addWidget(button)
        primary.addStretch()
        layout.addLayout(primary)
        secondary = QHBoxLayout()
        self.backup_button = QPushButton("Backups and restore…")
        self.backup_button.clicked.connect(self.open_backups)
        self.enabled_button = QPushButton("Disable")
        self.enabled_button.clicked.connect(self.toggle_selected)
        self.remove_button = QPushButton("Remove…")
        self.remove_button.clicked.connect(self.remove_selected)
        self.more_button = QPushButton("More…")
        self.more_button.clicked.connect(self.open_more_actions)
        for button in (self.backup_button, self.enabled_button, self.remove_button, self.more_button):
            secondary.addWidget(button)
        secondary.addStretch()
        self.stop_button = QPushButton("Stop after current destination")
        self.stop_button.clicked.connect(self.stop_requested)
        secondary.addWidget(self.stop_button)
        layout.addLayout(secondary)
        self.status_label = QLabel("Ready")
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setWordWrap(True)
        self.status_label.setAccessibleName("Synchronization status")
        layout.addWidget(self.status_label)
        config_service.changed.connect(self.refresh)
        cloud_service.busy_changed.connect(self.update_actions)
        cloud_service.failed.connect(self.status_label.setText)
        cloud_service.completed.connect(self.cloud_completed)
        if self.sync_service:
            self.sync_service.state_changed.connect(self.update_actions)
            self.sync_service.completed.connect(self.sync_completed)
            self.sync_service.progress.connect(lambda _, message: self.status_label.setText(message))
            self.sync_service.failed.connect(self.status_label.setText)
        self.history_timer = QTimer(self)
        self.history_timer.setInterval(10000)
        self.history_timer.timeout.connect(self.refresh_visible)
        self.history_timer.start()
        self.refresh()

    def selected_id(self):
        item = self.activity_list.currentItem()
        return item.data(0, Qt.ItemDataRole.UserRole) if item else None

    def refresh_visible(self):
        if self.isVisible() and not self.busy():
            self.refresh()

    def refresh(self, *_):
        selected = self.selected_id()
        config = self.config_service.get_app_config()
        self.history = self.sync_service.get_folder_history() if self.sync_service else {}
        self.activities = {}
        self.evidence_error = None
        self.evidence = {}
        if config and config.sync_groups:
            try:
                self.evidence = GroupState(self.config_service.cloud_root).data["groups"]
            except OneDrivePCSyncError as error:
                self.evidence_error = str(error)
        self.activity_list.blockSignals(True)
        self.activity_list.clear()
        if config:
            leaves = {leaf.id: leaf for leaf in [*config.folders, *config.remote_jobs]}
            referenced = {target.job_id for group in config.sync_groups for target in group.destinations}
            for group in config.sync_groups:
                self.activities[group.id] = (group, [(leaves[target.job_id], target) for target in group.destinations])
            for identifier, leaf in leaves.items():
                if identifier not in referenced:
                    self.activities[identifier] = (leaf, [(leaf, None)])
            for identifier, (activity, targets) in self.activities.items():
                last = self.history.get(identifier)
                status = self.history_text(last) if activity.enabled else "Disabled"
                first = targets[0][0]
                destinations = (PROVIDER_SETUP[next(connection.provider for connection in config.connections
                                if connection.id == first.connection_id)].label
                                if isinstance(first, RemoteJobConfig) else "Folder on PC / network")
                if len(targets) > 1:
                    destinations += f" + {len(targets) - 1} more"
                item = QTreeWidgetItem([activity.name, str(activity.local_path), destinations, status])
                item.setData(0, Qt.ItemDataRole.UserRole, identifier)
                for column in range(4):
                    item.setToolTip(column, last["message"] if column == 3 and last else item.text(column))
                self.activity_list.addTopLevelItem(item)
                if identifier == selected:
                    self.activity_list.setCurrentItem(item)
            self.activity_list.setMaximumHeight(max(125, min(280, 65 + len(self.activities) * 42)))
        self.activity_list.blockSignals(False)
        self.filter_activities()
        if self.selected_id() is None and self.activity_list.topLevelItemCount():
            for index in range(self.activity_list.topLevelItemCount()):
                item = self.activity_list.topLevelItem(index)
                if not item.isHidden():
                    self.activity_list.setCurrentItem(item)
                    break
        self.show_selected()

    @staticmethod
    def history_text(history):
        if not history:
            return "Not run yet"
        prefix = "Preview: " if history.get("dry_run") else ""
        return prefix + ("Completed" if history["succeeded"] else "Needs attention")

    def storage_label(self, leaf):
        if not isinstance(leaf, RemoteJobConfig):
            return "Folder on PC / network"
        config = self.config_service.get_app_config()
        connection = next(item for item in config.connections if item.id == leaf.connection_id)
        provider = PROVIDER_SETUP[connection.provider].label
        identity = self.service.account_identities.get(connection.id, {})
        account = identity.get("email") or identity.get("name")
        parts = [provider, account or connection.name]
        return " · ".join(dict.fromkeys(parts))

    def destination_path(self, leaf):
        if not isinstance(leaf, RemoteJobConfig):
            return str(leaf.onedrive_path)
        connection = next(item for item in self.config_service.get_app_config().connections if item.id == leaf.connection_id)
        return f"{connection.root.rstrip('/')}/{leaf.remote_path}"

    def filter_activities(self, *_):
        search = self.search_edit.text().casefold()
        visible = 0
        for index in range(self.activity_list.topLevelItemCount()):
            item = self.activity_list.topLevelItem(index)
            activity, targets = self.activities[item.data(0, Qt.ItemDataRole.UserRole)]
            text = " ".join([activity.name, str(activity.local_path), *(self.storage_label(leaf) + " " + self.destination_path(leaf) for leaf, _ in targets)])
            status_matches = self.filter_combo.currentText() == "All" or activity.enabled == (self.filter_combo.currentText() == "Enabled")
            item.setHidden(search not in text.casefold() or not status_matches)
            visible += not item.isHidden()
        self.empty_label.setVisible(visible == 0)
        self.empty_label.setText("No matching synchronizations. Try a different search or filter." if self.activities else
                                 "No synchronizations yet. Add a folder and choose where to keep its copies.")
        current = self.activity_list.currentItem()
        if current and current.isHidden():
            self.activity_list.setCurrentItem(None)
        self.show_selected()

    def show_selected(self, *_):
        entry = self.activities.get(self.selected_id())
        self.details.setVisible(entry is not None)
        if not entry:
            self.update_actions()
            return
        activity, targets = entry
        self.details.setTitle(activity.name)
        self.folder_label.setText(f"Folder on this PC: {activity.local_path}")
        self.destination_table.setRowCount(len(targets))
        row_height = max(60, self.destination_table.fontMetrics().lineSpacing() * 2 + 20)
        priority = 0
        for row, (leaf, target) in enumerate(targets):
            download = target is None or target.download_enabled
            if download:
                priority += 1
            use = []
            if target is None or target.upload_enabled:
                use.append("Upload")
            if download:
                use.append(f"Download #{priority}")
            history = self.history.get(leaf.id)
            copy_status = self.copy_status(activity, leaf, history)
            values = [self.storage_label(leaf).replace(" · ", "\n", 1), self.destination_path(leaf), "\n".join(use),
                      copy_status if leaf.enabled else "Disabled"]
            for column, value in enumerate(values):
                previous = self.destination_table.cellWidget(row, column)
                if previous is not None:
                    previous.hide()
                    self.destination_table.removeCellWidget(row, column)
                item = QTableWidgetItem("" if column in (0, 2) else value)
                item.setData(Qt.ItemDataRole.AccessibleTextRole, value)
                item.setToolTip((value + "\n" + history["message"]) if column == 3 and history else value)
                self.destination_table.setItem(row, column, item)
                if column in (0, 2):
                    label = QLabel(value)
                    label.setTextFormat(Qt.TextFormat.PlainText)
                    label.setWordWrap(True)
                    label.setMargin(8)
                    label.setToolTip(value)
                    self.destination_table.setCellWidget(row, column, label)
            self.destination_table.setRowHeight(row, row_height)
        self.destination_table.setMinimumHeight(min(280, max(130, 55 + row_height * len(targets))))
        last = self.history.get(activity.id)
        if self.evidence_error:
            self.freshness_label.setText(self.evidence_error)
        elif last:
            try:
                stamp = datetime.fromisoformat(last["timestamp"]).astimezone().strftime("%d %b %Y, %H:%M")
            except (ValueError, KeyError):
                stamp = "Unknown time"
            self.freshness_label.setText(f"Last run: {stamp}\n{last['message']}")
        else:
            self.freshness_label.setText("Freshness unknown. Verified copy history belongs to this configuration on this PC.")
        self.update_actions()

    def copy_status(self, activity, leaf, history):
        config = self.config_service.get_app_config()
        if not any(group.id == activity.id for group in config.sync_groups):
            return self.history_text(history)
        if self.evidence_error:
            return "Evidence unavailable — stopped"
        record = self.evidence.get(activity.id)
        item = record.get("destinations", {}).get(leaf.id) if record else None
        if not record or record["source"] != str(activity.local_path_resolved):
            return "Freshness unknown"
        if not item or item["identity"] != destination_identity(config, leaf):
            return "Freshness unknown"
        if item["status"] == "incomplete":
            return "Incomplete — upload required"
        if item["generation"] != record["generation"]:
            return "Prior copy — upload required"
        return "Verified on this PC"

    def busy(self):
        return self.service.busy or bool(self.sync_service and self.sync_service.is_syncing)

    def update_actions(self, *_):
        entry = self.activities.get(self.selected_id())
        selected = entry is not None
        idle = not self.busy()
        paused = bool(self.sync_service and self.sync_service.is_paused)
        enabled = selected and entry[0].enabled
        targets = entry[1] if entry else []
        bidirectional = any(getattr(leaf, "bidirectional", False) for leaf, _ in targets)
        self.upload_button.setText("Synchronize both folders" if bidirectional else "Send to destinations")
        self.download_button.setVisible(not bidirectional)
        can_run = bool(self.sync_service) and idle and enabled and not paused
        self.upload_button.setEnabled(can_run and any(leaf.enabled and (target is None or target.upload_enabled) for leaf, target in targets))
        self.download_button.setEnabled(can_run and any(leaf.enabled and (target is None or target.download_enabled) for leaf, target in targets))
        for button in (self.edit_button, self.enabled_button, self.remove_button, self.backup_button, self.more_button):
            button.setEnabled(selected and idle)
        self.add_button.setEnabled(idle)
        self.enabled_button.setText("Disable" if enabled else "Enable")
        explicit = selected and hasattr(entry[0], "destinations")
        self.stop_button.setVisible(explicit)
        self.stop_button.setEnabled(bool(explicit and self.sync_service and self.sync_service.is_syncing
                                        and not self.sync_service.cancellation_event.is_set()))
        if paused:
            self.status_label.setText("Synchronization is paused. Resume it to send or download files.")
        elif self.sync_service and self.sync_service.is_syncing:
            self.status_label.setText("Synchronization in progress…")

    def stop_requested(self):
        if self.sync_service:
            self.sync_service.cancel_after_current_destination()
            self.status_label.setText("Stop requested. The current destination can finish safely; remaining destinations will wait.")
            self.stop_button.setEnabled(False)

    def open_more_actions(self):
        entry = self.activities.get(self.selected_id())
        if not entry:
            return
        menu = QMenu(self)
        refresh = menu.addAction("Refresh results")
        refresh.triggered.connect(self.refresh)
        if not hasattr(entry[0], "destinations") and self.sync_service:
            config = self.config_service.get_app_config()
            direction = config.sync.shutdown.direction.value
            force = menu.addAction(f"Force {direction} once (ignore file-count threshold)…")
            force.setEnabled(entry[0].enabled and config.sync.shutdown.enabled and not self.busy() and not self.sync_service.is_paused)
            force.triggered.connect(self.force_selected)
        menu.exec(self.more_button.mapToGlobal(self.more_button.rect().bottomLeft()))

    def force_selected(self):
        identifier = self.selected_id()
        if not identifier or not self.sync_service or self.busy():
            return
        config = self.config_service.get_app_config()
        if any(group.id == identifier for group in config.sync_groups):
            return
        direction = config.sync.shutdown.direction.value
        answer = QMessageBox.question(self, f"Force {direction}?",
            f"Run one {direction} for this activity without the file-count threshold?\n\nOther path, backup and verification checks still apply. Review both folders before continuing.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self.sync_service.request_sync("shutdown", identifier, ignore_threshold=True)

    def open_editor(self, identifier=None):
        if self.busy():
            return
        self.editor = SynchronizationEditor(self.config_service, identifier, self)
        self.editor.ensure_idle = self.service.ensure_idle
        self.editor.saved.connect(self.select_saved)
        self.editor.connections_requested.connect(self.connect_from_editor)
        self.editor.open()

    def connect_from_editor(self):
        self._resume_editor = True
        self.editor.hide()
        self.connections_requested.emit()

    def showEvent(self, event):
        super().showEvent(event)
        if self._resume_editor and self.editor is not None:
            self._resume_editor = False
            self.editor.open()

    def select_saved(self, identifier):
        self.refresh()
        for index in range(self.activity_list.topLevelItemCount()):
            item = self.activity_list.topLevelItem(index)
            if item.data(0, Qt.ItemDataRole.UserRole) == identifier:
                self.activity_list.setCurrentItem(item)
                break
        self.status_label.setText("Synchronization saved. Destinations are used in the displayed download order.")

    def run_selected(self, direction):
        if self.sync_service and self.selected_id():
            self.sync_service.request_direction_sync(direction, self.selected_id())

    def sync_completed(self, outcomes):
        selected = self.selected_id()
        self.refresh()
        result = next((outcome for outcome in outcomes if outcome.folder_id == selected), None)
        if result:
            self.status_label.setText(result.message)

    def toggle_selected(self):
        entry = self.activities.get(self.selected_id())
        if not entry or self.busy():
            return
        activity = entry[0]
        config = self.config_service.get_app_config()
        try:
            self.service.ensure_idle()
            collection = "sync_groups" if any(group.id == activity.id for group in config.sync_groups) else (
                "remote_jobs" if isinstance(activity, RemoteJobConfig) else "folders")
            self.config_service.save(replace(config, **{collection: [replace(item, enabled=not item.enabled)
                if item.id == activity.id else item for item in getattr(config, collection)]}))
        except (OneDrivePCSyncError, ValueError, OSError) as error:
            self.status_label.setText(str(error))

    def remove_selected(self):
        entry = self.activities.get(self.selected_id())
        if not entry or self.busy():
            return
        activity, targets = entry
        config = self.config_service.get_app_config()
        explicit_group = any(group.id == activity.id for group in config.sync_groups)
        explanation = ("Its destinations will remain as disabled activities so you can still access their backups."
                       if explicit_group else "This removes the destination from the configuration. Stored backups are kept on disk.")
        answer = QMessageBox.question(self, "Remove synchronization?",
            f'Remove "{activity.name}"?\n\nFiles, history and backups will be kept. {explanation}',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.service.ensure_idle()
            config = self.config_service.get_app_config()
            ids = {leaf.id for leaf, _ in targets}
            self.config_service.save(replace(config,
                sync_groups=[group for group in config.sync_groups if group.id != activity.id],
                folders=([replace(leaf, enabled=False) if leaf.id in ids else leaf for leaf in config.folders]
                         if explicit_group else [leaf for leaf in config.folders if leaf.id not in ids]),
                remote_jobs=([replace(leaf, enabled=False) if leaf.id in ids else leaf for leaf in config.remote_jobs]
                             if explicit_group else [leaf for leaf in config.remote_jobs if leaf.id not in ids])))
            self.status_label.setText("Synchronization removed. Files and stored backups were kept.")
        except (OneDrivePCSyncError, ValueError, OSError) as error:
            self.status_label.setText(str(error))

    def open_backups(self):
        entry = self.activities.get(self.selected_id())
        if not entry or self.busy():
            return
        menu = QMenu(self)
        for leaf, _ in entry[1]:
            if isinstance(leaf, RemoteJobConfig):
                action = menu.addAction(f"{self.storage_label(leaf)} — snapshots / restore")
                action.triggered.connect(lambda checked=False, job_id=leaf.id: self.show_snapshots(job_id))
            else:
                action = menu.addAction(f"{leaf.name} — local ZIP backups")
                action.triggered.connect(self.backups_requested)
        menu.exec(self.backup_button.mapToGlobal(self.backup_button.rect().bottomLeft()))

    def show_snapshots(self, job_id):
        try:
            self._snapshot_job = job_id
            self.service.list_snapshots(job_id)
        except ValueError as error:
            self.status_label.setText(str(error))

    def cloud_completed(self, action, value):
        if action in {"accounts", "test", "authorize_account"}:
            self.refresh()
        elif action == "snapshots" and self._snapshot_job:
            job_id, self._snapshot_job = self._snapshot_job, None
            dialog = self.snapshot_dialog = QDialog(self)
            dialog.setWindowTitle("Restore a verified cloud snapshot")
            dialog.resize(620, 210)
            layout = QVBoxLayout(dialog)
            note = QLabel("Choose a snapshot and an empty folder on this PC. Your live files are kept.")
            note.setWordWrap(True)
            layout.addWidget(note)
            choices = QComboBox()
            choices.setAccessibleName("Verified cloud snapshot")
            for snapshot in reversed(value):
                choices.addItem(f"{snapshot['created_at']} · {len(snapshot['files'])} files", snapshot["run_id"])
            layout.addWidget(choices)
            restore = QPushButton("Choose empty folder and restore")
            restore.setEnabled(bool(value))
            layout.addWidget(restore)
            if not value:
                note.setText("No verified snapshots are available for this destination yet.")
            def restore_selected():
                target = QFileDialog.getExistingDirectory(dialog, "Choose an empty restore folder")
                if target:
                    try:
                        self.service.restore(job_id, choices.currentData(), target)
                        dialog.accept()
                    except ValueError as error:
                        self.status_label.setText(str(error))
            restore.clicked.connect(restore_selected)
            dialog.open()
        elif action == "restore":
            self.status_label.setText("Snapshot restored and verified in the selected folder.")
