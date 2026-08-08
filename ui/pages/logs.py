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
from PySide6.QtCore import Qt, QTimer, QDateTime, QDate
from PySide6.QtGui import QColor, QBrush
from backend.services.log_service import LogService


class LogsPage(QWidget):
    def __init__(self, log_service: LogService, parent=None):
        super().__init__(parent)
        self.log_service = log_service
        self.last_read_pos = 0
        self.log_entries = []  # list of (timestamp, level, message, raw_line)
        self.filtered_entries = []  # indices of log_entries that match filters
        self.setup_ui()
        self.setup_timer()
        self.load_initial_logs()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Toolbar
        toolbar = QFrame()
        toolbar.setFrameShape(QFrame.StyledPanel)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(4, 4, 4, 4)
        toolbar_layout.setSpacing(8)

        # Search
        search_label = QLabel("Search:")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search logs...")
        self.search_input.textChanged.connect(self.apply_filters)
        toolbar_layout.addWidget(search_label)
        toolbar_layout.addWidget(self.search_input)

        # Level filters
        levels_label = QLabel("Levels:")
        toolbar_layout.addWidget(levels_label)
        self.info_cb = QCheckBox("INFO")
        self.info_cb.setChecked(True)
        self.info_cb.stateChanged.connect(self.apply_filters)
        self.warning_cb = QCheckBox("WARNING")
        self.warning_cb.setChecked(True)
        self.warning_cb.stateChanged.connect(self.apply_filters)
        self.error_cb = QCheckBox("ERROR")
        self.error_cb.setChecked(True)
        self.error_cb.stateChanged.connect(self.apply_filters)
        self.success_cb = QCheckBox("SUCCESS")
        self.success_cb.setChecked(False)  # We don't have SUCCESS logs by default
        self.success_cb.stateChanged.connect(self.apply_filters)
        toolbar_layout.addWidget(self.info_cb)
        toolbar_layout.addWidget(self.warning_cb)
        toolbar_layout.addWidget(self.error_cb)
        toolbar_layout.addWidget(self.success_cb)

        # Date filter
        date_label = QLabel("Date:")
        toolbar_layout.addWidget(date_label)
        self.date_combo = QComboBox()
        self.date_combo.addItems(["All", "Today", "Yesterday", "Last 7 Days", "Last 30 Days"])
        self.date_combo.currentIndexChanged.connect(self.apply_filters)
        toolbar_layout.addWidget(self.date_combo)

        # Spacer
        toolbar_layout.addStretch()

        # Buttons
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_logs)
        toolbar_layout.addWidget(self.refresh_btn)

        self.copy_btn = QPushButton("Copy Selected")
        self.copy_btn.clicked.connect(self.copy_selected_rows)
        toolbar_layout.addWidget(self.copy_btn)

        self.autoscroll_cb = QCheckBox("Auto-scroll")
        self.autoscroll_cb.setChecked(True)
        toolbar_layout.addWidget(self.autoscroll_cb)

        layout.addWidget(toolbar)

        # Log table
        self.log_table = QTableWidget()
        self.log_table.setColumnCount(3)
        self.log_table.setHorizontalHeaderLabels(["Timestamp", "Level", "Message"])
        self.log_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.log_table.setColumnWidth(0, 150)  # Timestamp
        self.log_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.log_table.setColumnWidth(1, 100)  # Level
        self.log_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.log_table.setShowGrid(True)
        self.log_table.setAlternatingRowColors(True)
        self.log_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.log_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.log_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.log_table.verticalHeader().setVisible(False)
        layout.addWidget(self.log_table)

        # Status bar
        self.status_label = QLabel("Ready")
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

        if not self.log_service:
            self.status_label.setText("Log service not available")
            return

        try:
            # Get log entries from the log service (last 1000 lines)
            entries = self.log_service.get_log_entries(max_lines=1000)
            # Convert to our internal format: (timestamp, level, message, raw_line)
            # We don't have the raw line from the log service, so we'll set it to an empty string.
            # We'll change the log_entries to store (timestamp, level, message) only.
            # We'll adjust the update_table method accordingly.
            self.log_entries = [(timestamp, level, message, "") for (timestamp, level, message) in entries]
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
            # Get all log entries (we could optimize to get only new ones, but for simplicity we get all and then filter)
            # We'll get the last 1000 lines again and then compare with what we have?
            # Instead, we'll just reload the entire log entries and then reapply filters.
            # This is simpler and acceptable for a log viewer that updates every 500ms.
            entries = self.log_service.get_log_entries(max_lines=1000)
            new_log_entries = [(timestamp, level, message, "") for (timestamp, level, message) in entries]
            # Check if we have new entries by comparing the length or the last entry?
            # We'll just replace the log_entries and then reapply filters.
            self.log_entries = new_log_entries
            if self.log_entries:
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

        # Date range
        date_index = self.date_combo.currentIndex()
        now = QDateTime.currentDateTime()
        if date_index == 0:  # All
            start_date = None
            end_date = None
        elif date_index == 1:  # Today
            start_date = QDateTime(QDate.currentDate())
            end_date = now
        elif date_index == 2:  # Yesterday
            yesterday = QDate.currentDate().addDays(-1)
            start_date = QDateTime(yesterday)
            end_date = QDateTime(yesterday).addDays(1)
        elif date_index == 3:  # Last 7 Days
            start_date = now.addDays(-7)
            end_date = now
        elif date_index == 4:  # Last 30 Days
            start_date = now.addDays(-30)
            end_date = now
        else:
            start_date = None
            end_date = None

        # Get all log entries from the log service (we could cache, but for simplicity we get all)
        entries = self.log_service.get_log_entries()
        # Convert to our internal format for filtering
        internal_entries = [(timestamp, level, message, "") for (timestamp, level, message) in entries]
        # Apply filters using the log service's filter_entries method
        filtered_internal = self.log_service.filter_entries(
            [(timestamp, level, message) for (timestamp, level, message, _) in internal_entries],
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
            # Set background color based on level
            color = self.get_level_color(level)
            level_item.setBackground(QBrush(color))
            level_item.setForeground(QBrush(Qt.white))
            self.log_table.setItem(row, 1, level_item)
            # Message
            message_item = QTableWidgetItem(message)
            message_item.setFlags(message_item.flags() & ~Qt.ItemIsEditable)
            self.log_table.setItem(row, 2, message_item)

    def get_level_color(self, level: str) -> QColor:
        """Return the color for a given log level."""
        if level == "INFO":
            return QColor("#0078d4")  # PRIMARY from theme
        elif level == "WARNING":
            return QColor("#ffb900")  # WARNING from theme
        elif level == "ERROR":
            return QColor("#d13434")  # ERROR from theme
        elif level == "SUCCESS":
            return QColor("#107c10")  # SUCCESS from theme
        else:
            return QColor("#6e6e6e")  # TEXT_DISABLED for unknown

    def update_status(self):
        """Update the status label."""
        total = len(self.log_entries)
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