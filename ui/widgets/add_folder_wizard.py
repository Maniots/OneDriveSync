from PySide6.QtWidgets import (
    QWizard,
    QWizardPage,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QCheckBox,
    QSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QFrame,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from ..themes import spacing
from ..resources.icons import get_icon


class AddFolderWizard(QWizard):
    """A polished multi-step wizard for adding/editing folder configurations."""

    # Signal emitted when wizard is completed with collected data
    folderDataCollected = Signal(dict)

    def __init__(self, parent=None, folder_data=None):
        super().__init__(parent)
        self.setWindowTitle("Add Folder" if folder_data is None else "Edit Folder")
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        # Disable help button (default is False, but being explicit)
        self.setOption(QWizard.WizardOption.HaveHelpButton, False)
        # Enable cancel button (default is True, but being explicit)
        # No need to set options for back/finish buttons as they are default

        # Store folder data for editing mode
        self.folder_data = folder_data or {}

        # Create pages
        self.page_basic_info = BasicInfoPage(self)
        self.page_local_folder = LocalFolderPage(self)
        self.page_onedrive_folder = OneDriveFolderPage(self)
        self.page_safety = SafetyPage(self)
        self.page_backup = BackupPage(self)
        self.page_review = ReviewPage(self)

        # Add pages
        self.addPage(self.page_basic_info)
        self.addPage(self.page_local_folder)
        self.addPage(self.page_onedrive_folder)
        self.addPage(self.page_safety)
        self.addPage(self.page_backup)
        self.addPage(self.page_review)

        # Connect finish signal
        self.finished.connect(self._on_finished)

        # Set initial sizes
        self.resize(500, 400)

    def _on_finished(self, result):
        """Handle wizard finish."""
        if result == QWizard.DialogCode.Accepted:
            # Collect data from all pages
            data = {}
            data.update(self.page_basic_info.get_data())
            data.update(self.page_local_folder.get_data())
            data.update(self.page_onedrive_folder.get_data())
            data.update(self.page_safety.get_data())
            data.update(self.page_backup.get_data())

            # Emit the collected data
            self.folderDataCollected.emit(data)


class BasicInfoPage(QWizardPage):
    """Page for basic folder information: ID, name, enabled."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Basic Information")
        self.setSubTitle("Enter the folder's basic details")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(spacing.LARGE, spacing.LARGE, spacing.LARGE, spacing.LARGE)
        layout.setSpacing(spacing.MEDIUM)

        # Form layout for fields
        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(spacing.SMALL)

        # ID field
        self.id_edit = QLineEdit()
        self.id_edit.setPlaceholderText("e.g., my_folder")
        self.id_edit.setToolTip("Unique identifier for the folder (letters, numbers, underscores)")
        self.id_edit.setProperty("value", "true")
        id_label = QLabel("ID:")
        id_label.setProperty("title", "true")
        form_layout.addRow(id_label, self.id_edit)

        # Name field
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g., My Folder")
        self.name_edit.setToolTip("Display name for the folder")
        self.name_edit.setProperty("value", "true")
        name_label = QLabel("Name:")
        name_label.setProperty("title", "true")
        form_layout.addRow(name_label, self.name_edit)

        # Enabled checkbox
        self.enabled_check = QCheckBox("Enabled")
        self.enabled_check.setChecked(True)
        self.enabled_check.setProperty("value", "true")
        enabled_label = QLabel("Enabled:")
        enabled_label.setProperty("title", "true")
        form_layout.addRow(enabled_label, self.enabled_check)

        layout.addLayout(form_layout)
        layout.addStretch()

        # Register fields for validation
        self.registerField("id*", self.id_edit)
        self.registerField("name*", self.name_edit)

    def validatePage(self):
        """Validate the page before moving forward."""
        id_text = self.id_edit.text().strip()
        name_text = self.name_edit.text().strip()

        if not id_text:
            self.id_edit.setToolTip("Please enter an ID")
            self.setField("id*", False)
            return False

        if not name_text:
            self.name_edit.setToolTip("Please enter a name")
            self.setField("name*", False)
            return False

        # Basic ID validation: alphanumeric and underscores only
        if not all(c.isalnum() or c == '_' for c in id_text):
            self.id_edit.setToolTip("ID can only contain letters, numbers, and underscores")
            self.setField("id*", False)
            return False

        self.id_edit.setToolTip("Unique identifier for the folder (letters, numbers, underscores)")
        self.setField("id*", True)
        self.setField("name*", True)
        return True

    def get_data(self):
        """Get data from this page."""
        return {
            "id": self.id_edit.text().strip(),
            "name": self.name_edit.text().strip(),
            "enabled": self.enabled_check.isChecked(),
        }

    def initializePage(self):
        """Initialize page with existing data if editing."""
        if hasattr(self, 'folder_data') and self.folder_data:
            self.id_edit.setText(self.folder_data.get("id", ""))
            self.name_edit.setText(self.folder_data.get("name", ""))
            self.enabled_check.setChecked(self.folder_data.get("enabled", True))


class LocalFolderPage(QWizardPage):
    """Page for selecting the local folder path."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Local Folder")
        self.setSubTitle("Select the local folder to synchronize")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(spacing.LARGE, spacing.LARGE, spacing.LARGE, spacing.LARGE)
        layout.setSpacing(spacing.MEDIUM)

        # Form layout
        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(spacing.SMALL)

        # Path field with browse button
        path_layout = QHBoxLayout()
        path_layout.setSpacing(spacing.SMALL)
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("e.g., C:\\Users\\Name\\Documents\\MyFolder")
        self.path_edit.setToolTip("Full path to the local folder")
        self.path_edit.setProperty("value", "true")
        self.browse_button = QPushButton("Browse...")
        self.browse_button.setIcon(get_icon("folder-open"))
        self.browse_button.clicked.connect(self._browse_local_folder)
        path_layout.addWidget(self.path_edit, 1)
        path_layout.addWidget(self.browse_button)

        local_path_label = QLabel("Local Path:")
        local_path_label.setProperty("title", "true")
        form_layout.addRow(local_path_label, path_layout)
        layout.addLayout(form_layout)

        # Validation hint
        self.hint_label = QLabel("Please select an existing local folder")
        self.hint_label.setProperty("description", "true")
        layout.addWidget(self.hint_label)
        layout.addStretch()

        # Register field
        self.registerField("local_path*", self.path_edit)

    def _browse_local_folder(self):
        """Open folder selection dialog."""
        current_path = self.path_edit.text() or ""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Local Folder",
            current_path,
            QFileDialog.Option.ShowDirsOnly
        )
        if folder:
            self.path_edit.setText(folder)

    def validatePage(self):
        """Validate the page before moving forward."""
        path_text = self.path_edit.text().strip()

        if not path_text:
            self.path_edit.setToolTip("Please enter a local folder path")
            self.setField("local_path*", False)
            self.hint_label.setText("Please select an existing local folder")
            return False

        # Check if path exists (basic validation)
        import os
        if not os.path.exists(path_text):
            self.path_edit.setToolTip("The specified path does not exist")
            self.setField("local_path*", False)
            self.hint_label.setText("Please select an existing local folder")
            return False

        if not os.path.isdir(path_text):
            self.path_edit.setToolTip("The specified path is not a folder")
            self.setField("local_path*", False)
            self.hint_label.setText("Please select an existing local folder")
            return False

        self.path_edit.setToolTip("Full path to the local folder")
        self.setField("local_path*", True)
        self.hint_label.setText("Local folder path is valid")
        return True

    def get_data(self):
        """Get data from this page."""
        return {
            "local_path": self.path_edit.text().strip(),
        }

    def initializePage(self):
        """Initialize page with existing data if editing."""
        if hasattr(self, 'folder_data') and self.folder_data:
            self.path_edit.setText(self.folder_data.get("local_path", ""))


class OneDriveFolderPage(QWizardPage):
    """Page for selecting the OneDrive folder path."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("OneDrive Folder")
        self.setSubTitle("Select the OneDrive folder to synchronize with")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(spacing.LARGE, spacing.LARGE, spacing.LARGE, spacing.LARGE)
        layout.setSpacing(spacing.MEDIUM)

        # Form layout
        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(spacing.SMALL)

        # Path field with browse button
        path_layout = QHBoxLayout()
        path_layout.setSpacing(spacing.SMALL)
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("e.g., OneDrive\\MyFolder")
        self.path_edit.setToolTip("Path relative to OneDrive root")
        self.path_edit.setProperty("value", "true")
        self.browse_button = QPushButton("Browse...")
        self.browse_button.setIcon(get_icon("folder-open"))
        self.browse_button.clicked.connect(self._browse_onedrive_folder)
        path_layout.addWidget(self.path_edit, 1)
        path_layout.addWidget(self.browse_button)

        onedrive_path_label = QLabel("OneDrive Path:")
        onedrive_path_label.setProperty("title", "true")
        form_layout.addRow(onedrive_path_label, path_layout)
        layout.addLayout(form_layout)

        # Validation hint
        self.hint_label = QLabel("Please enter a valid OneDrive relative path")
        self.hint_label.setProperty("description", "true")
        layout.addWidget(self.hint_label)
        layout.addStretch()

        # Register field
        self.registerField("onedrive_path*", self.path_edit)

    def _browse_onedrive_folder(self):
        """Open folder selection dialog for OneDrive."""
        # Note: In a real app, we would integrate with OneDrive API
        # For now, we'll use a standard folder dialog as placeholder
        current_path = self.path_edit.text() or ""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select OneDrive Folder (placeholder)",
            current_path,
            QFileDialog.Option.ShowDirsOnly
        )
        if folder:
            # Convert to relative path (placeholder implementation)
            # In reality, we'd need to check if it's under OneDrive root
            self.path_edit.setText(folder)

    def validatePage(self):
        """Validate the page before moving forward."""
        path_text = self.path_edit.text().strip()

        if not path_text:
            self.path_edit.setToolTip("Please enter a OneDrive folder path")
            self.setField("onedrive_path*", False)
            self.hint_label.setText("Please enter a valid OneDrive relative path")
            return False

        # Basic validation: non-empty and reasonable format
        if len(path_text) < 1:
            self.path_edit.setToolTip("OneDrive path cannot be empty")
            self.setField("onedrive_path*", False)
            self.hint_label.setText("Please enter a valid OneDrive relative path")
            return False

        # Check for invalid characters (basic)
        invalid_chars = ['<', '>', ':', '"', '|', '?', '*']
        if any(c in path_text for c in invalid_chars):
            self.path_edit.setToolTip("OneDrive path contains invalid characters")
            self.setField("onedrive_path*", False)
            self.hint_label.setText("Please enter a valid OneDrive relative path")
            return False

        self.path_edit.setToolTip("Path relative to OneDrive root")
        self.setField("onedrive_path*", True)
        self.hint_label.setText("OneDrive path is valid")
        return True

    def get_data(self):
        """Get data from this page."""
        return {
            "onedrive_path": self.path_edit.text().strip(),
        }

    def initializePage(self):
        """Initialize page with existing data if editing."""
        if hasattr(self, 'folder_data') and self.folder_data:
            self.path_edit.setText(self.folder_data.get("onedrive_path", ""))


class SafetyPage(QWizardPage):
    """Page for safety settings: minimum sync percentage, verification, destination creation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Safety Settings")
        self.setSubTitle("Configure safety options for synchronization")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(spacing.LARGE, spacing.LARGE, spacing.LARGE, spacing.LARGE)
        layout.setSpacing(spacing.MEDIUM)

        # Form layout
        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(spacing.SMALL)

        # Minimum sync percentage
        self.percentage_spin = QSpinBox()
        self.percentage_spin.setRange(0, 100)
        self.percentage_spin.setValue(80)
        self.percentage_spin.setSuffix("%")
        self.percentage_spin.setToolTip("Minimum percentage of files that must sync successfully")
        self.percentage_spin.setProperty("value", "true")
        percentage_label = QLabel("Minimum Sync Percentage:")
        percentage_label.setProperty("title", "true")
        form_layout.addRow(percentage_label, self.percentage_spin)

        # Verification enabled
        self.verify_check = QCheckBox("Verify files after synchronization")
        self.verify_check.setChecked(True)
        self.verify_check.setToolTip("Check that files were copied correctly after sync")
        self.verify_check.setProperty("value", "true")
        verify_label = QLabel("Verify files after synchronization:")
        verify_label.setProperty("title", "true")
        form_layout.addRow(verify_label, self.verify_check)

        # Destination creation enabled
        self.create_dest_check = QCheckBox("Create destination folder if it doesn't exist")
        self.create_dest_check.setChecked(True)
        self.create_dest_check.setToolTip("Automatically create the OneDrive folder if missing")
        self.create_dest_check.setProperty("value", "true")
        create_dest_label = QLabel("Create destination folder if it doesn't exist:")
        create_dest_label.setProperty("title", "true")
        form_layout.addRow(create_dest_label, self.create_dest_check)

        layout.addLayout(form_layout)
        layout.addStretch()

        # Register fields
        self.registerField("minimum_sync_percentage", self.percentage_spin)
        self.registerField("verify_after_sync", self.verify_check)
        self.registerField("create_destination", self.create_dest_check)

    def validatePage(self):
        """Validate the page before moving forward."""
        # Safety page always validates (no required fields with complex validation)
        return True

    def get_data(self):
        """Get data from this page."""
        return {
            "minimum_sync_percentage": self.percentage_spin.value(),
            "verify_after_sync": self.verify_check.isChecked(),
            "create_destination": self.create_dest_check.isChecked(),
        }

    def initializePage(self):
        """Initialize page with existing data if editing."""
        if hasattr(self, 'folder_data') and self.folder_data:
            self.percentage_spin.setValue(self.folder_data.get("minimum_sync_percentage", 80))
            self.verify_check.setChecked(self.folder_data.get("verify_after_sync", True))
            self.create_dest_check.setChecked(self.folder_data.get("create_destination", True))


class BackupPage(QWizardPage):
    """Page for backup settings: enable backup, backup path, retention days."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Backup Settings")
        self.setSubTitle("Configure backup options for the folder")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(spacing.LARGE, spacing.LARGE, spacing.LARGE, spacing.LARGE)
        layout.setSpacing(spacing.MEDIUM)

        # Form layout
        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(spacing.SMALL)

        # Backup enabled
        self.enabled_check = QCheckBox("Enable backup for this folder")
        self.enabled_check.setChecked(False)
        self.enabled_check.toggled.connect(self._on_backup_toggled)
        self.enabled_check.setProperty("value", "true")
        enabled_label = QLabel("Enable backup for this folder:")
        enabled_label.setProperty("title", "true")
        form_layout.addRow(enabled_label, self.enabled_check)

        # Backup path (conditionally visible)
        self.backup_path_label = QLabel("Backup Path:")
        self.backup_path_label.setProperty("title", "true")
        self.backup_path_edit = QLineEdit()
        self.backup_path_edit.setPlaceholderText("e.g., OneDrive\\Backups\\MyFolder")
        self.backup_path_edit.setToolTip("Path where backups will be stored")
        self.backup_path_edit.setProperty("value", "true")
        self.backup_browse_button = QPushButton("Browse...")
        self.backup_browse_button.setIcon(get_icon("folder-open"))
        self.backup_browse_button.clicked.connect(self._browse_backup_folder)

        backup_path_layout = QHBoxLayout()
        backup_path_layout.setSpacing(spacing.SMALL)
        backup_path_layout.addWidget(self.backup_path_edit, 1)
        backup_path_layout.addWidget(self.backup_browse_button)

        # Retention days (conditionally visible)
        self.retention_label = QLabel("Retention Days:")
        self.retention_label.setProperty("title", "true")
        self.retention_spin = QSpinBox()
        self.retention_spin.setRange(0, 365)
        self.retention_spin.setValue(7)
        self.retention_spin.setSuffix(" days")
        self.retention_spin.setToolTip("Number of days to retain backups")
        self.retention_spin.setProperty("value", "true")

        # Add conditionally visible widgets to form
        form_layout.addRow("", self.enabled_check)
        form_layout.addRow(self.backup_path_label, backup_path_layout)
        form_layout.addRow(self.retention_label, self.retention_spin)

        layout.addLayout(form_layout)
        layout.addStretch()

        # Register fields
        self.registerField("backup_enabled", self.enabled_check)
        self.registerField("backup_path", self.backup_path_edit)
        self.registerField("backup_retention_days", self.retention_spin)

        # Initialize visibility
        self._on_backup_toggled(False)

    def _on_backup_toggled(self, checked):
        """Handle backup enable/disable toggle."""
        self.backup_path_label.setVisible(checked)
        self.backup_path_edit.setVisible(checked)
        self.backup_browse_button.setVisible(checked)
        self.retention_label.setVisible(checked)
        self.retention_spin.setVisible(checked)

        # If disabling, clear the backup path
        if not checked:
            self.backup_path_edit.clear()

    def _browse_backup_folder(self):
        """Open folder selection dialog for backup path."""
        current_path = self.backup_path_edit.text() or ""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Backup Folder (placeholder)",
            current_path,
            QFileDialog.Option.ShowDirsOnly
        )
        if folder:
            self.backup_path_edit.setText(folder)

    def validatePage(self):
        """Validate the page before moving forward."""
        # If backup is enabled, validate backup path
        if self.enabled_check.isChecked():
            backup_path = self.backup_path_edit.text().strip()
            if not backup_path:
                self.backup_path_edit.setToolTip("Please enter a backup path")
                return False

            # Basic validation for backup path
            invalid_chars = ['<', '>', ':', '"', '|', '?', '*']
            if any(c in backup_path for c in invalid_chars):
                self.backup_path_edit.setToolTip("Backup path contains invalid characters")
                return False

        return True

    def get_data(self):
        """Get data from this page."""
        return {
            "backup_enabled": self.enabled_check.isChecked(),
            "backup_path": self.backup_path_edit.text().strip(),
            "backup_retention_days": self.retention_spin.value(),
        }

    def initializePage(self):
        """Initialize page with existing data if editing."""
        if hasattr(self, 'folder_data') and self.folder_data:
            backup_enabled = self.folder_data.get("backup_enabled", False)
            self.enabled_check.setChecked(backup_enabled)
            self._on_backup_toggled(backup_enabled)
            self.backup_path_edit.setText(self.folder_data.get("backup_path", ""))
            self.retention_spin.setValue(self.folder_data.get("backup_retention_days", 7))


class ReviewPage(QWizardPage):
    """Page for reviewing the entered folder configuration."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Review")
        self.setSubTitle("Review your folder configuration before finishing")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(spacing.LARGE, spacing.LARGE, spacing.LARGE, spacing.LARGE)
        layout.setSpacing(spacing.MEDIUM)

        # Review text area
        self.review_text = QLabel()
        self.review_text.setTextFormat(Qt.RichText)
        self.review_text.setWordWrap(True)
        self.review_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.review_text)
        layout.addStretch()

    def initializePage(self):
        """Initialize the review page with collected data."""
        # Collect data from all previous pages
        wizard = self.wizard()
        if not isinstance(wizard, AddFolderWizard):
            return

        data = {}
        data.update(wizard.page_basic_info.get_data())
        data.update(wizard.page_local_folder.get_data())
        data.update(wizard.page_onedrive_folder.get_data())
        data.update(wizard.page_safety.get_data())
        data.update(wizard.page_backup.get_data())

        # Format the review text
        review_html = self._format_review(data)
        self.review_text.setText(review_html)

    def _format_review(self, data):
        """Format the review data as HTML."""
        html = """
        <style>
            .field-label { font-weight: bold; margin-right: 10px; }
            .field-value { margin-left: 20px; }
            .section-title { font-size: 14pt; font-weight: bold; margin-top: 15px; margin-bottom: 5px; color: #0078d4; }
        </style>
        """

        # Basic Information
        html += '<div class="section-title">Basic Information</div>'
        html += f'<span class="field-label">ID:</span> <span class="field-value">{data.get("id", "N/A")}</span><br/>'
        html += f'<span class="field-label">Name:</span> <span class="field-value">{data.get("name", "N/A")}</span><br/>'
        html += f'<span class="field-label">Enabled:</span> <span class="field-value">{"Yes" if data.get("enabled", False) else "No"}</span><br/>'

        # Paths
        html += '<div class="section-title">Paths</div>'
        html += f'<span class="field-label">Local Path:</span> <span class="field-value">{data.get("local_path", "N/A")}</span><br/>'
        html += f'<span class="field-label">OneDrive Path:</span> <span class="field-value">{data.get("onedrive_path", "N/A")}</span><br/>'

        # Safety Settings
        html += '<div class="section-title">Safety Settings</div>'
        html += f'<span class="field-label">Minimum Sync Percentage:</span> <span class="field-value">{data.get("minimum_sync_percentage", 0)}%</span><br/>'
        html += f'<span class="field-label">Verify After Sync:</span> <span class="field-value">{"Yes" if data.get("verify_after_sync", False) else "No"}</span><br/>'
        html += f'<span class="field-label">Create Destination:</span> <span class="field-value">{"Yes" if data.get("create_destination", False) else "No"}</span><br/>'

        # Backup Settings
        html += '<div class="section-title">Backup Settings</div>'
        html += f'<span class="field-label">Backup Enabled:</span> <span class="field-value">{"Yes" if data.get("backup_enabled", False) else "No"}</span><br/>'
        if data.get("backup_enabled", False):
            html += f'<span class="field-label">Backup Path:</span> <span class="field-value">{data.get("backup_path", "N/A")}</span><br/>'
            html += f'<span class="field-label">Retention Days:</span> <span class="field-value">{data.get("backup_retention_days", 0)} days</span><br/>'

        return html

    def validatePage(self):
        """The review page always validates."""
        return True

    def get_data(self):
        """Review page doesn't collect additional data."""
        return {}