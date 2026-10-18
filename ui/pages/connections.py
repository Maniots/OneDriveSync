"""Guided account setup with asynchronous browser authentication."""
from uuid import uuid4

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QLineEdit, QComboBox, QPushButton, QListWidget, QListWidgetItem, QCheckBox,
    QGroupBox, QScrollArea, QFileDialog, QMessageBox)

from src.cloud_models import ConnectionConfig
from src.cloud_providers import PROVIDER_SETUP, OAUTH_PROVIDERS, SIGN_IN_LABELS
from src.cloud_oauth import load_oauth_apps
from ..themes import spacing


PROVIDER_GUIDES = {
    "local": "https://rclone.org/local/",
    "onedrive": "https://rclone.org/onedrive/",
    "drive": "https://rclone.org/drive/#making-your-own-client-id",
    "s3": "https://rclone.org/s3/", "sftp": "https://rclone.org/sftp/",
    "webdav": "https://rclone.org/webdav/", "dropbox": "https://rclone.org/dropbox/",
    "azureblob": "https://rclone.org/azureblob/", "b2": "https://rclone.org/b2/",
}


class ConnectionsPage(QWidget):
    def __init__(self, config_service, cloud_service, parent=None):
        super().__init__(parent)
        self.config_service = config_service
        self.service = cloud_service
        self.pending = None
        self.pending_parameters = {}
        self.question = None
        self.option_inputs = {}
        self.folder_path = ""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(spacing.LARGE, spacing.MEDIUM, spacing.LARGE, spacing.MEDIUM)
        self.status_label = QLabel("Connect an account, then add an activity in Cloud Sync.")
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        outer.addWidget(self.status_label)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        self.connection_list = QListWidget()
        self.connection_list.setAccessibleName("Connected accounts")
        self.connection_list.setMaximumHeight(150)
        layout.addWidget(self.connection_list)
        actions = QHBoxLayout()
        self.test_button = QPushButton("Test connection")
        self.remove_button = QPushButton("Disconnect")
        self.test_button.clicked.connect(self.test_selected)
        self.remove_button.clicked.connect(self.remove_selected)
        actions.addWidget(self.test_button)
        actions.addWidget(self.remove_button)
        actions.addStretch()
        layout.addLayout(actions)
        self.setup_group = QGroupBox("Connect storage")
        setup = QFormLayout(self.setup_group)
        self.provider_combo = QComboBox()
        for key, spec in PROVIDER_SETUP.items():
            self.provider_combo.addItem(spec.label, key)
        self.provider_combo.setAccessibleName("Storage provider")
        self.name_edit = QLineEdit()
        self.name_edit.setAccessibleName("Connection name")
        self.root_edit = QLineEdit()
        self.root_edit.setAccessibleName("Connection root folder or bucket")
        self.provider_hint = QLabel()
        self.provider_hint.setWordWrap(True)
        self.provider_hint.setTextFormat(Qt.TextFormat.PlainText)
        setup.addRow("Provider", self.provider_combo)
        setup.addRow(self.provider_hint)
        self.guide_button = QPushButton("Open provider setup guide")
        self.guide_button.setToolTip("Open the official setup instructions in your browser")
        self.guide_button.clicked.connect(self.open_provider_guide)
        setup.addRow(self.guide_button)
        setup.addRow("Name", self.name_edit)
        self.root_controls = QWidget()
        root_row = QHBoxLayout(self.root_controls)
        root_row.setContentsMargins(0, 0, 0, 0)
        root_row.addWidget(self.root_edit)
        browse = QPushButton("Browse local folder")
        browse.clicked.connect(self.browse_root)
        root_row.addWidget(browse)
        setup.addRow("Root folder / bucket", self.root_controls)
        self.root_label = setup.labelForField(self.root_controls)
        self.advanced_button = QPushButton("Advanced settings")
        self.advanced_button.setCheckable(True)
        self.advanced_button.toggled.connect(lambda checked: self.options_widget.setVisible(checked))
        setup.addRow(self.advanced_button)
        self.options_widget = QWidget()
        self.options_form = QFormLayout(self.options_widget)
        setup.addRow(self.options_widget)
        self.create_root = QCheckBox("Create the root folder if missing (OneDrive, Drive, Dropbox, WebDAV)")
        self.create_root.setChecked(True)
        setup.addRow(self.create_root)
        self.connect_button = QPushButton("Connect account")
        self.connect_button.setProperty("primary", "true")
        self.connect_button.clicked.connect(self.connect_account)
        setup.addRow(self.connect_button)
        layout.addWidget(self.setup_group)
        self.question_group = QGroupBox("Finish account setup")
        question_layout = QVBoxLayout(self.question_group)
        self.question_label = QLabel()
        self.question_label.setWordWrap(True)
        self.question_label.setTextFormat(Qt.TextFormat.PlainText)
        self.answer_combo = QComboBox()
        self.answer_combo.setAccessibleName("Account setup choice")
        self.answer_edit = QLineEdit()
        self.answer_edit.setAccessibleName("Account setup answer")
        self.continue_button = QPushButton("Continue setup")
        self.continue_button.clicked.connect(self.continue_setup)
        for widget in (self.question_label, self.answer_combo, self.answer_edit, self.continue_button):
            question_layout.addWidget(widget)
        layout.addWidget(self.question_group)
        self.question_group.hide()
        self.folder_group = QGroupBox("Choose your cloud folder")
        folder_layout = QVBoxLayout(self.folder_group)
        folder_hint = QLabel("Select a folder, double-click to browse inside it, or enter a new folder path.")
        folder_hint.setWordWrap(True)
        folder_layout.addWidget(folder_hint)
        self.folder_location = QLabel("Your cloud storage")
        self.folder_location.setTextFormat(Qt.TextFormat.PlainText)
        self.folder_location.setWordWrap(True)
        folder_layout.addWidget(self.folder_location)
        self.folder_list = QListWidget()
        self.folder_list.setAccessibleName("Cloud folders; double-click to open")
        self.folder_list.setMaximumHeight(180)
        self.folder_list.itemActivated.connect(self.open_cloud_folder)
        self.folder_list.currentItemChanged.connect(self.select_cloud_folder)
        folder_layout.addWidget(self.folder_list)
        folder_nav = QHBoxLayout()
        self.parent_folder_button = QPushButton("Parent folder")
        self.parent_folder_button.clicked.connect(self.parent_cloud_folder)
        self.reload_folders_button = QPushButton("Reload folders")
        self.reload_folders_button.clicked.connect(lambda: self.load_cloud_folders(self.folder_path))
        folder_nav.addWidget(self.parent_folder_button)
        folder_nav.addWidget(self.reload_folders_button)
        folder_nav.addStretch()
        folder_layout.addLayout(folder_nav)
        self.cloud_root_edit = QLineEdit()
        self.cloud_root_edit.setAccessibleName("Selected cloud folder path")
        self.cloud_root_edit.setPlaceholderText("EverySync or Games/Saves")
        folder_layout.addWidget(QLabel("Folder to synchronize"))
        folder_layout.addWidget(self.cloud_root_edit)
        self.folder_create = QCheckBox("Create this folder if it does not exist")
        self.folder_create.setChecked(True)
        folder_layout.addWidget(self.folder_create)
        self.save_root_button = QPushButton("Use this folder")
        self.save_root_button.setProperty("primary", "true")
        self.save_root_button.clicked.connect(self.save_cloud_root)
        folder_layout.addWidget(self.save_root_button)
        layout.addWidget(self.folder_group)
        self.folder_group.hide()
        self.cancel_button = QPushButton("Cancel account setup")
        self.cancel_button.clicked.connect(self.cancel_setup)
        self.cancel_button.setEnabled(False)
        layout.addWidget(self.cancel_button)
        layout.addStretch()
        scroll.setWidget(body)
        outer.addWidget(scroll)
        self.provider_combo.currentIndexChanged.connect(self.provider_changed)
        self.service.completed.connect(self.completed)
        self.service.failed.connect(self.show_error)
        self.service.busy_changed.connect(self.update_actions)
        if self.service.sync_service is not None:
            self.service.sync_service.state_changed.connect(self.update_actions)
        config_service.changed.connect(self.refresh)
        self.provider_changed()
        self.refresh()

    def provider_changed(self):
        while self.options_form.rowCount():
            self.options_form.removeRow(0)
        self.option_inputs = {}
        provider = self.provider_combo.currentData()
        spec = PROVIDER_SETUP[provider]
        self.provider_hint.setText(spec.hint)
        for field in spec.fields:
            edit = QLineEdit()
            edit.setAccessibleName(field.label)
            if field.secret:
                edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.options_form.addRow(field.label, edit)
            self.option_inputs[field.key] = edit
            edit.textChanged.connect(self.update_actions)
        oauth = provider in OAUTH_PROVIDERS
        self.advanced_button.setChecked(False)
        self.advanced_button.setVisible(oauth)
        self.options_widget.setVisible(not oauth)
        self.guide_button.setVisible(not oauth)
        self.root_controls.setVisible(not oauth)
        self.root_label.setVisible(not oauth)
        self.create_root.setVisible(not oauth)
        self.connect_button.setText(SIGN_IN_LABELS.get(provider, "Connect account"))
        self.root_edit.setPlaceholderText("Choose an existing folder" if provider == "local" else
                                         "bucket-name/prefix" if provider in {"s3", "b2"} else
                                         "container-name/prefix" if provider == "azureblob" else "EverySync")
        self.create_root.setEnabled(provider in {"onedrive", "drive", "dropbox", "webdav"})
        self.update_actions()

    def browse_root(self):
        selected = QFileDialog.getExistingDirectory(self, "Choose connection root")
        if selected:
            self.root_edit.setText(selected)

    def open_provider_guide(self):
        url = PROVIDER_GUIDES.get(self.provider_combo.currentData())
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def refresh(self, *args):
        self.connection_list.clear()
        config = self.config_service.get_app_config()
        for connection in config.connections if config else []:
            item = QListWidgetItem(f"{connection.name}  ·  {PROVIDER_SETUP[connection.provider].label}  ·  {connection.root}")
            item.setData(Qt.ItemDataRole.UserRole, connection.id)
            self.connection_list.addItem(item)
        self.update_actions()

    def selected(self):
        item = self.connection_list.currentItem()
        identifier = item.data(Qt.ItemDataRole.UserRole) if item else None
        return next((c for c in self.config_service.get_app_config().connections if c.id == identifier), None)

    def connect_account(self):
        try:
            provider = self.provider_combo.currentData()
            oauth = provider in OAUTH_PROVIDERS
            self.pending = ConnectionConfig("c_" + uuid4().hex,
                self.name_edit.text().strip() or (PROVIDER_SETUP[provider].label if oauth else ""),
                provider, "EverySync" if oauth else self.root_edit.text().strip())
            self.pending_parameters = {key: edit.text() for key, edit in self.option_inputs.items() if edit.text()}
            self.question = None
            self.service.configure_connection(self.pending, self.pending_parameters,
                create_root=self.create_root.isChecked(), choose_root=oauth)
            self.status_label.setText("Setting up the connection. Complete sign-in in your browser when it opens.")
        except (ValueError, RuntimeError) as error:
            self.show_error(str(error))

    def continue_setup(self):
        if not self.pending or not self.question:
            return
        option = self.question.get("Option") or {}
        answer = self.answer_combo.currentData() if option.get("Exclusive") else self.answer_edit.text()
        try:
            self.service.configure_connection(self.pending, self.pending_parameters,
                state=self.question["State"], answer=str(answer or ""), create_root=self.create_root.isChecked())
            self.status_label.setText("Continuing account setup. Complete sign-in in your browser when requested.")
        except (ValueError, RuntimeError) as error:
            self.show_error(str(error))

    def completed(self, action, value):
        if action == "configure":
            self.question = value.get("question")
            if value.get("choose_root"):
                self.pending_parameters.clear()
                for edit in self.option_inputs.values():
                    edit.clear()
                self.question_group.hide()
                self.setup_group.hide()
                self.folder_group.show()
                self.cloud_root_edit.setText(self.pending.root)
                self.folder_path = ""
                self.folder_list.clear()
                self.status_label.setText("Signed in. Choose the cloud folder you want to synchronize.")
                self.load_cloud_folders("")
            elif self.question:
                option = self.question.get("Option") or {}
                self.question_label.setText((self.question.get("Error") or "") + "\n" + str(option.get("Help", "Choose an account setup option.")))
                self.answer_combo.clear()
                for item in option.get("Examples") or []:
                    self.answer_combo.addItem(str(item.get("Help") or item.get("Value")), item.get("Value"))
                self.answer_combo.setVisible(bool(option.get("Exclusive")))
                self.answer_edit.setVisible(not option.get("Exclusive"))
                self.answer_edit.setEchoMode(QLineEdit.EchoMode.Password if option.get("IsPassword") else QLineEdit.EchoMode.Normal)
                default = option.get("Default", "")
                self.answer_edit.setText("" if option.get("IsPassword") else str(default).lower() if isinstance(default, bool) else str(default or ""))
                self.question_group.show()
                self.status_label.setText("One more step is required to authorize this account.")
            else:
                self.clear_setup()
                self.status_label.setText("Connected. Add a folder activity in Cloud Sync.")
        elif action == "folders":
            self.folder_path = value["path"]
            self.folder_location.setText(self.folder_path or "Your cloud storage")
            self.folder_list.clear()
            self.folder_list.addItems(value["folders"])
            self.status_label.setText("Choose a cloud folder, then select Use this folder." if value["folders"] else
                                     "This folder has no subfolders. Enter a folder path or use the current folder.")
        elif action == "save_root":
            self.clear_setup()
            self.status_label.setText("Connected. Add a folder activity in Cloud Sync.")
        elif action == "test":
            self.status_label.setText("Connection verified: the configured root is readable.")
        elif action == "remove":
            self.status_label.setText("Disconnected. Remote files were kept.")
        self.refresh()

    def show_error(self, message):
        if self.pending is not None and self.service.pending_connection is None:
            self.clear_setup()
        self.status_label.setText(message)
        self.update_actions()

    def update_actions(self, *args):
        busy = self.service.busy or (self.service.sync_service is not None and self.service.sync_service.is_syncing)
        self.setup_group.setEnabled(not busy and self.pending is None)
        self.question_group.setEnabled(not busy)
        self.folder_group.setEnabled(not busy)
        self.parent_folder_button.setEnabled(not busy and bool(self.folder_path))
        self.test_button.setEnabled(not busy and self.pending is None)
        self.remove_button.setEnabled(not busy and self.pending is None)
        self.cancel_button.setEnabled(self.pending is not None)
        google_ready = True
        if self.provider_combo.currentData() == "drive":
            try:
                apps = load_oauth_apps()
                custom = any(edit.text().strip() for edit in self.option_inputs.values())
                google_ready = (all(self.option_inputs[key].text().strip() for key in ("client_id", "client_secret"))
                                if custom else bool(apps.get("drive")))
                self.provider_hint.setText(PROVIDER_SETUP["drive"].hint if google_ready else
                    "Google sign-in is not available in this build yet. Install a release with Google sign-in enabled. Custom desktop apps can use Advanced settings.")
            except ValueError as error:
                google_ready = False
                self.provider_hint.setText(str(error))
        self.connect_button.setEnabled(not busy and self.pending is None and google_ready)

    def load_cloud_folders(self, path):
        try:
            self.service.list_account_folders(path)
            self.status_label.setText("Loading cloud folders…")
        except (ValueError, RuntimeError) as error:
            self.show_error(str(error))

    def open_cloud_folder(self, item):
        path = "/".join(part for part in (self.folder_path, item.text()) if part)
        self.cloud_root_edit.setText(path)
        self.load_cloud_folders(path)

    def select_cloud_folder(self, item, previous=None):
        if item is not None:
            self.cloud_root_edit.setText("/".join(part for part in (self.folder_path, item.text()) if part))

    def parent_cloud_folder(self):
        path = self.folder_path.rpartition("/")[0]
        # Synchronization is always scoped to a named folder, never the whole account.
        self.cloud_root_edit.setText(path or "EverySync")
        self.load_cloud_folders(path)

    def save_cloud_root(self):
        try:
            self.service.choose_connection_root(self.cloud_root_edit.text().strip(), create_root=self.folder_create.isChecked())
            self.status_label.setText("Verifying your cloud folder…")
        except (ValueError, RuntimeError) as error:
            self.show_error(str(error))

    def cancel_setup(self):
        try:
            self.service.cancel()
        except ValueError as error:
            self.show_error(str(error))
            return
        # Keep the pending ID until protected credentials have been removed;
        # cleanup failures remain retryable with the same Cancel button.
        self.pending_parameters.clear()
        self.answer_edit.clear()
        for edit in self.option_inputs.values():
            edit.clear()
        self.question_group.hide()
        self.folder_group.hide()
        self.status_label.setText("Cancelling account setup and removing unfinished credentials…")
        self.update_actions()

    def clear_setup(self):
        self.pending = None
        self.pending_parameters.clear()
        self.question = None
        self.answer_edit.clear()
        for edit in self.option_inputs.values():
            edit.clear()
        self.question_group.hide()
        self.folder_group.hide()
        self.folder_list.clear()
        self.cloud_root_edit.clear()
        self.setup_group.show()

    def test_selected(self):
        connection = self.selected()
        if connection:
            try:
                self.service.test_connection(connection)
            except ValueError as error:
                self.show_error(str(error))

    def remove_selected(self):
        connection = self.selected()
        if connection and QMessageBox.question(self, "Disconnect account", "Disconnect this account? Remote files will be kept.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            try:
                self.service.remove_connection(connection.id)
            except ValueError as error:
                self.show_error(str(error))
