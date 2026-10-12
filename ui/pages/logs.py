from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QCheckBox,
    QComboBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFrame,
    QSizePolicy,
    QApplication,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QBrush
from backend.services.log_service import LogService
from ..themes import spacing, colors


class LogsPage(QWidget):
    def __init__(self, log_service: LogService, parent=None):
        super().__init__(parent)
        self.log_service = log_service
        self.last_read_pos = 0
        self.log_entries = []  # filtered rows (timestamp, level, message, raw_line)
        self._all_entries = []
        self.filtered_entries = []  # indices of log_entries that match filters
        self.setup_ui()
        self.setup_timer()
        self.load_initial_logs()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(spacing.MEDIUM, spacing.MEDIUM, spacing.MEDIUM, spacing.MEDIUM)
        layout.setSpacing(spacing.SMALL)

        # Toolbar
        toolbar = QFrame()
        toolbar.setProperty("card", "true")
        toolbar_body = QVBoxLayout(toolbar)
        toolbar_body.setContentsMargins(spacing.SMALL, spacing.SMALL, spacing.SMALL, spacing.SMALL)
        toolbar_body.setSpacing(12)
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(12)
        toolbar_body.addLayout(toolbar_layout)
        filters_layout = QHBoxLayout()
        filters_layout.setSpacing(12)
        toolbar_body.addLayout(filters_layout)

        # Search
        search_label = QLabel("Search:")
        search_label.setProperty("title", "true")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search logs...")
        self.search_input.setAccessibleName("Search logs")
        self.search_input.setMinimumWidth(160)
        search_label.setBuddy(self.search_input)
        self.search_input.textChanged.connect(self.apply_filters)
        toolbar_layout.addWidget(search_label)
        toolbar_layout.addWidget(self.search_input, 1)

        # Level filters
        levels_label = QLabel("Levels:")
        levels_label.setProperty("title", "true")
        filters_layout.addWidget(levels_label)
        self.info_cb = QCheckBox("INFO")
        self.info_cb.setChecked(True)
        self.info_cb.stateChanged.connect(self.apply_filters)
        self.info_cb.setProperty("value", "true")
        self.warning_cb = QCheckBox("WARNING")
        self.warning_cb.setChecked(True)
        self.warning_cb.stateChanged.connect(self.apply_filters)
        self.warning_cb.setProperty("value", "true")
        self.error_cb = QCheckBox("ERROR")
        self.error_cb.setChecked(True)
        self.error_cb.stateChanged.connect(self.apply_filters)
        self.error_cb.setProperty("value", "true")
        self.success_cb = QCheckBox("SUCCESS")
        self.success_cb.setChecked(False)  # We don't have SUCCESS logs by default
        self.success_cb.stateChanged.connect(self.apply_filters)
        self.success_cb.setProperty("value", "true")
        filters_layout.addWidget(self.info_cb)
        filters_layout.addWidget(self.warning_cb)
        filters_layout.addWidget(self.error_cb)
        filters_layout.addWidget(self.success_cb)
        filters_layout.addStretch()

        # Date filter
        date_label = QLabel("Date:")
        date_label.setProperty("title", "true")
        toolbar_layout.addWidget(date_label)
        self.date_combo = QComboBox()
        self.date_combo.addItems(["All", "Today", "Yesterday", "Last 7 Days", "Last 30 Days"])
        self.date_combo.setAccessibleName("Filter logs by date")
        date_label.setBuddy(self.date_combo)
        self.date_combo.currentIndexChanged.connect(self.apply_filters)
        toolbar_layout.addWidget(self.date_combo)

        # Buttons
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setToolTip("Refresh logs")
        self.refresh_btn.clicked.connect(self.refresh_logs)
        toolbar_layout.addWidget(self.refresh_btn)

        self.copy_btn = QPushButton("Copy Selected")
        self.copy_btn.setToolTip("Copy selected log entries to clipboard")
        self.copy_btn.clicked.connect(self.copy_selected_rows)
        toolbar_layout.addWidget(self.copy_btn)

        self.autoscroll_cb = QCheckBox("Auto-scroll")
        self.autoscroll_cb.setChecked(True)
        self.autoscroll_cb.setProperty("value", "true")
        filters_layout.addWidget(self.autoscroll_cb)

        layout.addWidget(toolbar)

        # Log table
        self.log_table = QTableWidget()
        self.log_table.setColumnCount(3)
        self.log_table.setHorizontalHeaderLabels(["Timestamp", "Level", "Message"])
        header = self.log_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        self.log_table.setColumnWidth(0, 180)  # Timestamp
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        self.log_table.setColumnWidth(1, 80)   # Level
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self.log_table.setShowGrid(False)
        self.log_table.setAlternatingRowColors(True)
        self.log_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.log_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.log_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.log_table.verticalHeader().setVisible(False)
        self.log_table.verticalHeader().setDefaultSectionSize(40)
        layout.addWidget(self.log_table)

        # Status bar
        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setProperty("description", "true")
        layout.addWidget(self.status_label)

    def setup_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_for_new_logs)
        self.timer.start(500)  # check every 500ms

    def load_initial_logs(self):
        """Load the last N lines of the log file to avoid too many rows."""
        self.log_table.setRowCount(0)
        self.log_entries.clear()
        self.filtered_entries.clear()
        self._all_entries.clear()

        if not self.log_service:
            self.status_label.setText("Log service not available")
            return

        try:
            # Get log entries from the log service (last 1000 lines)
            entries = self.log_service.get_log_entries(max_lines=1000)
            self._all_entries = entries
            self.last_read_pos = 0  # Not used anymore, but keep for compatibility
        except Exception as e:
            self.status_label.setText(f"Error loading log: {e}")
            return

        self.apply_filters()
        self.update_status()

    def check_for_new_logs(self):
        """Check for new lines in the log file and append them."""
        if not self.log_service:
            return

        try:
            # Preserve row selections until the bounded log input changes.
            entries = self.log_service.get_log_entries(max_lines=1000)
            if entries != self._all_entries:
                self._all_entries = entries
                self.apply_filters()
                if self.autoscroll_cb.isChecked():
                    self.scroll_to_bottom()
        except Exception as e:
            self.status_label.setText(f"Error reading log: {e}")

    def parse_log_line(self, line: str):
        """This method is no longer used, but we keep it for compatibility."""
        # We don't use this anymore because we use the log service.
        return None

    def apply_filters(self):
        """Apply search, level, and date filters to the log entries."""
        if not self.log_service:
            return

        search_text = self.search_input.text().lower()
        show_info = self.info_cb.isChecked()
        show_warning = self.warning_cb.isChecked()
        show_error = self.error_cb.isChecked()
        show_success = self.success_cb.isChecked()

        date_index = self.date_combo.currentIndex()
        # Date filtering belongs to LogService; use the bounded cached input.
        filtered_internal = self.log_service.filter_entries(
            self._all_entries,
            search_text=search_text,
            show_info=show_info,
            show_warning=show_warning,
            show_error=show_error,
            show_success=show_success,
            date_index=date_index
        )
        # Convert back to our internal format with raw line (empty string)
        self.log_entries = [(timestamp, level, message, "") for (timestamp, level, message) in filtered_internal]
        self.filtered_entries = list(range(len(self.log_entries)))  # All entries are shown after filtering

        self.update_table()
        self.update_status()

    def update_table(self):
        """Update the table to show only filtered entries."""
        self.log_table.setRowCount(len(self.log_entries))
        for row, (timestamp, level, message, _) in enumerate(self.log_entries):
            # Timestamp
            if timestamp.isValid():
                timestamp_str = timestamp.toString("yyyy-MM-dd HH:mm:ss")
            else:
                timestamp_str = "Invalid timestamp"
            timestamp_item = QTableWidgetItem(timestamp_str)
            timestamp_item.setFlags(timestamp_item.flags() & ~Qt.ItemIsEditable)
            self.log_table.setItem(row, 0, timestamp_item)
            # Level
            level_item = QTableWidgetItem(level)
            level_item.setFlags(level_item.flags() & ~Qt.ItemIsEditable)
            # Use readable semantic text colors on the shared table surface.
            color = self.get_level_color(level)
            level_item.setForeground(QBrush(color))
            self.log_table.setItem(row, 1, level_item)
            # Message
            message_item = QTableWidgetItem(message)
            message_item.setFlags(message_item.flags() & ~Qt.ItemIsEditable)
            self.log_table.setItem(row, 2, message_item)

    def get_level_color(self, level: str) -> QColor:
        """Return the color for a given log level."""
        if level == "INFO":
            return QColor(colors.SECONDARY)
        elif level == "WARNING":
            return QColor(colors.WARNING)
        elif level == "ERROR":
            return QColor(colors.ERROR)
        elif level == "SUCCESS":
            return QColor(colors.SUCCESS)
        else:
            return QColor(colors.TEXT_SECONDARY)

    def update_status(self):
        """Update the status label."""
        total = len(self._all_entries)
        shown = len(self.filtered_entries)
        self.status_label.setText(f"Showing {shown} of {total} log entries")

    def scroll_to_bottom(self):
        """Scroll the table to the bottom."""
        self.log_table.scrollToBottom()

    def refresh_logs(self):
        """Refresh the log display by reloading the file."""
        self.load_initial_logs()

    def copy_selected_rows(self):
        """Copy the selected rows to the clipboard."""
        selected_rows = set()
        for item in self.log_table.selectedItems():
            selected_rows.add(item.row())
        if not selected_rows:
            return

        # Sort rows
        sorted_rows = sorted(selected_rows)
        lines = []
        for row in sorted_rows:
            timestamp_item = self.log_table.item(row, 0)
            level_item = self.log_table.item(row, 1)
            message_item = self.log_table.item(row, 2)
            if timestamp_item and level_item and message_item:
                line = f"{timestamp_item.text()} | {level_item.text()} | {message_item.text()}"
                lines.append(line)

        text = "\n".join(lines)
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        self.status_label.setText(f"Copied {len(lines)} line(s) to clipboard")

    # For compatibility with the existing MainWindow, we keep the config_backend argument
    # even though we don't use it.
