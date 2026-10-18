"""Manage cloud activities through the same synchronization coordinator."""
from dataclasses import replace
from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QLineEdit, QComboBox, QPushButton, QListWidget, QListWidgetItem, QCheckBox,
    QSpinBox, QGroupBox, QScrollArea, QFileDialog, QMessageBox, QDialog)

from src.cloud_models import RemoteJobConfig
from ..themes import spacing


class CloudSyncPage(QWidget):
    def __init__(self, config_service, cloud_service, parent=None):
        super().__init__(parent)
        self.config_service = config_service
        self.service = cloud_service
        self.editing_id = None
        self.snapshot_job = None
        self.snapshot_dialog = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(spacing.LARGE, spacing.MEDIUM, spacing.LARGE, spacing.MEDIUM)
        self.status_label = QLabel("Choose a connected account and a specific local folder. Upload and download never propagate deletions.")
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        outer.addWidget(self.status_label)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        self.job_list = QListWidget()
        self.job_list.setAccessibleName("Cloud synchronization activities")
        self.job_list.setMaximumHeight(160)
        self.job_list.currentItemChanged.connect(self.select_job)
        layout.addWidget(self.job_list)
        actions = QHBoxLayout()
        self.new_button = QPushButton("New activity")
        self.upload_button = QPushButton("Upload")
        self.download_button = QPushButton("Download")
        self.backups_button = QPushButton("Snapshots / restore")
        self.delete_button = QPushButton("Delete activity")
        self.new_button.clicked.connect(self.new_job)
        self.upload_button.clicked.connect(lambda: self.run_job("shutdown"))
        self.download_button.clicked.connect(lambda: self.run_job("startup"))
        self.backups_button.clicked.connect(self.show_snapshots)
        self.delete_button.clicked.connect(self.delete_job)
        for button in (self.new_button, self.upload_button, self.download_button, self.backups_button, self.delete_button):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.form_group = QGroupBox("Activity settings")
        form = QFormLayout(self.form_group)
        self.name_edit = QLineEdit()
        self.name_edit.setAccessibleName("Cloud activity name")
        self.connection_combo = QComboBox()
        self.connection_combo.setAccessibleName("Cloud activity connection")
        self.local_edit = QLineEdit()
        self.local_edit.setAccessibleName("Cloud activity local folder")
        local_row = QHBoxLayout()
        local_row.addWidget(self.local_edit)
        browse = QPushButton("Browse")
        browse.clicked.connect(self.browse_local)
        local_row.addWidget(browse)
        self.remote_edit = QLineEdit()
        self.remote_edit.setAccessibleName("Folder below connection root")
        self.remote_edit.setPlaceholderText("Game/Saves")
        self.enabled_check = QCheckBox("Enabled for manual and scheduled synchronization")
        self.enabled_check.setChecked(True)
        self.threshold_spin = QSpinBox()
        self.threshold_spin.setRange(0, 100)
        self.threshold_spin.setValue(80)
        self.threshold_spin.setSuffix("%")
        self.threshold_spin.setAccessibleName("Minimum file-count safety ratio")
        self.backup_check = QCheckBox("Keep a full remote snapshot before overwriting files")
        self.backup_check.setChecked(True)
        self.bidirectional_check = QCheckBox("Bidirectional: reconcile both sides; stop on conflicting changes")
        self.save_button = QPushButton("Save activity")
        self.save_button.setProperty("primary", "true")
        self.save_button.clicked.connect(self.save_job)
        form.addRow("Name", self.name_edit)
        form.addRow("Connection", self.connection_combo)
        form.addRow("Local folder", local_row)
        form.addRow("Folder below root", self.remote_edit)
        form.addRow("Safety threshold", self.threshold_spin)
        form.addRow(self.enabled_check)
        form.addRow(self.backup_check)
        form.addRow(self.bidirectional_check)
        note = QLabel("Uses the existing startup/shutdown directions and dry-run setting. Snapshots are full remote copies, stored separately from legacy ZIP backups. They are kept until you remove them on the provider.")
        note.setWordWrap(True)
        form.addRow(note)
        form.addRow(self.save_button)
        layout.addWidget(self.form_group)
        layout.addStretch()
        scroll.setWidget(body)
        outer.addWidget(scroll)
        config_service.changed.connect(self.refresh)
        self.service.busy_changed.connect(self.update_actions)
        self.service.failed.connect(self.status_label.setText)
        self.service.completed.connect(self.completed)
        if self.service.sync_service is not None:
            self.service.sync_service.state_changed.connect(self.update_actions)
            self.service.sync_service.completed.connect(self.sync_completed)
            self.service.sync_service.failed.connect(self.status_label.setText)
        self.refresh()

    def refresh(self, *args):
        config = self.config_service.get_app_config()
        selected_connection = self.connection_combo.currentData()
        self.connection_combo.clear()
        self.job_list.blockSignals(True)
        self.job_list.clear()
        if config:
            for connection in config.connections:
                self.connection_combo.addItem(connection.name, connection.id)
            for job in config.remote_jobs:
                item = QListWidgetItem(f"{job.name}  ·  {'Enabled' if job.enabled else 'Disabled'}  ·  {job.remote_path}")
                item.setData(Qt.ItemDataRole.UserRole, job.id)
                self.job_list.addItem(item)
                if job.id == self.editing_id:
                    self.job_list.setCurrentItem(item)
        self.job_list.blockSignals(False)
        if selected_connection:
            self.connection_combo.setCurrentIndex(self.connection_combo.findData(selected_connection))
        self.update_actions()

    def select_job(self, current, previous=None):
        identifier = current.data(Qt.ItemDataRole.UserRole) if current else None
        config = self.config_service.get_app_config()
        job = next((j for j in config.remote_jobs if j.id == identifier), None)
        if not job:
            return
        self.editing_id = job.id
        self.name_edit.setText(job.name)
        self.local_edit.setText(job.local_path)
        self.remote_edit.setText(job.remote_path)
        self.connection_combo.setCurrentIndex(self.connection_combo.findData(job.connection_id))
        self.enabled_check.setChecked(job.enabled)
        self.threshold_spin.setValue(int(job.minimum_sync_percentage))
        self.backup_check.setChecked(job.backup_enabled)
        self.bidirectional_check.setChecked(job.bidirectional)

    def new_job(self):
        self.editing_id = None
        self.job_list.clearSelection()
        self.job_list.setCurrentItem(None)
        for edit in (self.name_edit, self.local_edit, self.remote_edit):
            edit.clear()
        self.enabled_check.setChecked(True)
        self.backup_check.setChecked(True)
        self.bidirectional_check.setChecked(False)
        self.threshold_spin.setValue(80)

    def browse_local(self):
        selected = QFileDialog.getExistingDirectory(self, "Choose an application data folder")
        if selected:
            self.local_edit.setText(selected)

    def save_job(self):
        try:
            self.service.ensure_idle()
            config = self.config_service.get_app_config()
            job = RemoteJobConfig(self.editing_id or "j_" + uuid4().hex, self.name_edit.text().strip(),
                self.local_edit.text().strip(), self.connection_combo.currentData() or "", self.remote_edit.text().strip(),
                enabled=self.enabled_check.isChecked(), minimum_sync_percentage=self.threshold_spin.value(),
                backup_enabled=self.backup_check.isChecked(), bidirectional=self.bidirectional_check.isChecked())
            self.config_service.save(replace(config, remote_jobs=[j for j in config.remote_jobs if j.id != job.id] + [job]))
            self.editing_id = job.id
            self.refresh()
            self.status_label.setText("Activity saved. Preview with Settings → Dry Run before the first real transfer.")
        except Exception as error:
            self.status_label.setText(str(error))

    def run_job(self, operation):
        try:
            self.service.ensure_idle()
            if not self.editing_id:
                raise ValueError("Select a saved activity first.")
            if self.service.sync_service is None:
                raise ValueError("Synchronization service is unavailable.")
            self.service.sync_service.request_sync(operation, self.editing_id)
        except ValueError as error:
            self.status_label.setText(str(error))

    def sync_completed(self, outcomes):
        result = next((item for item in outcomes if item.folder_id == self.editing_id), None)
        if result:
            self.status_label.setText(result.message)

    def delete_job(self):
        if not self.editing_id:
            return
        if QMessageBox.question(self, "Delete activity", "Remove this activity? Local files, remote files and snapshots will be kept.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.service.ensure_idle()
            config = self.config_service.get_app_config()
            self.config_service.save(replace(config, remote_jobs=[j for j in config.remote_jobs if j.id != self.editing_id]))
            self.new_job()
            self.status_label.setText("Activity removed. Files and snapshots were kept.")
        except ValueError as error:
            self.status_label.setText(str(error))

    def show_snapshots(self):
        if self.editing_id:
            try:
                self.snapshot_job = self.editing_id
                self.service.list_snapshots(self.snapshot_job)
            except ValueError as error:
                self.status_label.setText(str(error))

    def completed(self, action, value):
        if action == "snapshots":
            job_id = self.snapshot_job
            dialog = self.snapshot_dialog = QDialog(self)
            dialog.setWindowTitle("Restore a remote snapshot")
            layout = QVBoxLayout(dialog)
            label = QLabel("Choose a verified snapshot. Restore uses an empty local folder and keeps the live files unchanged.")
            label.setWordWrap(True)
            layout.addWidget(label)
            combo = QComboBox()
            for snapshot in reversed(value):
                combo.addItem(f"{snapshot['created_at']} · {len(snapshot['files'])} files", snapshot["run_id"])
            layout.addWidget(combo)
            restore = QPushButton("Choose empty folder and restore")
            restore.setEnabled(bool(value))
            layout.addWidget(restore)
            def restore_selected():
                target = QFileDialog.getExistingDirectory(dialog, "Choose an empty restore folder")
                if target:
                    try:
                        self.service.restore(job_id, combo.currentData(), target)
                        dialog.accept()
                    except ValueError as error:
                        self.status_label.setText(str(error))
            restore.clicked.connect(restore_selected)
            dialog.resize(600, 180)
            dialog.show()
        elif action == "restore":
            self.status_label.setText("Snapshot restored and verified in the selected folder.")

    def update_actions(self, *args):
        busy = self.service.busy or (self.service.sync_service is not None and self.service.sync_service.is_syncing)
        config = self.config_service.get_app_config()
        if config:
            self.upload_button.setText(config.sync.shutdown.direction.value.title() + " (shutdown)")
            self.download_button.setText(config.sync.startup.direction.value.title() + " (startup)")
        for widget in (self.form_group, self.new_button, self.upload_button, self.download_button, self.backups_button, self.delete_button):
            widget.setEnabled(not busy)
