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
from pathlib import Path
import re


class LogsPage(QWidget):
    def __init__(self, config_backend=None, parent=None):
        super().__init__(parent)
        self.config_backend = config_backend
        self.log_file_path = Path(__file__).parent.parent.parent / "logs" / "onedrive_pcsync.log"
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

        if not self.log_file_path.exists():
            self.status_label.setText("Log file not found")
            return

        try:
            with open(self.log_file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                # Keep last 1000 lines
                lines = lines[-1000:] if len(lines) > 1000 else lines
                for line in lines:
                    line = line.rstrip("\n")
                    parsed = self.parse_log_line(line)
                    if parsed:
                        timestamp, level, message = parsed
                        self.log_entries.append((timestamp, level, message, line))
                    else:
                        # If line doesn't parse, still add it as a raw line with level UNKNOWN
                        # Use an invalid QDateTime for timestamp
                        self.log_entries.append((QDateTime(), "UNKNOWN", line, line))
                self.last_read_pos = f.tell()
        except Exception as e:
            self.status_label.setText(f"Error loading log: {e}")
            return

        self.apply_filters()
        self.update_status()

    def check_for_new_logs(self):
        """Check for new lines in the log file and append them."""
        if not self.log_file_path.exists():
            return

        try:
            with open(self.log_file_path, "r", encoding="utf-8") as f:
                f.seek(self.last_read_pos)
                new_lines = f.readlines()
                self.last_read_pos = f.tell()

                for line in new_lines:
                    line = line.rstrip("\n")
                    parsed = self.parse_log_line(line)
                    if parsed:
                        timestamp, level, message = parsed
                        self.log_entries.append((timestamp, level, message, line))
                    else:
                        # If line doesn't parse, still add it as a raw line with level UNKNOWN
                        self.log_entries.append((QDateTime(), "UNKNOWN", line, line))

                if new_lines:
                    self.apply_filters()
                    if self.autoscroll_cb.isChecked():
                        self.scroll_to_bottom()
        except Exception as e:
            self.status_label.setText(f"Error reading log: {e}")

    def parse_log_line(self, line: str):
        """Parse a log line into (timestamp, level, message).
        Expected format: "%Y-%m-%d %H:%M:%S | %(levelname)-8s | %(name)s | %(message)s"
        Returns a tuple (QDateTime, level, message) if successful, else None.
        """
        # Split by " | " but only split into 4 parts
        parts = line.split(" | ", 3)
        if len(parts) < 4:
            return None
        timestamp_str, level, logger_name, message = parts
        try:
            # Remove any trailing whitespace from level
            level = level.strip()
            timestamp = QDateTime.fromString(timestamp_str, "yyyy-MM-dd HH:mm:ss")
            if not timestamp.isValid():
                return None
            # Combine logger name and message for display
            display_message = f"[{logger_name}] {message}"
            return timestamp, level, display_message
        except Exception:
            return None

    def apply_filters(self):
        """Apply search, level, and date filters to the log entries."""
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

        self.filtered_entries = []
        for idx, (timestamp, level, message, raw_line) in enumerate(self.log_entries):
            # Level filter
            level_match = False
            if level == "INFO" and show_info:
                level_match = True
            elif level == "WARNING" and show_warning:
                level_match = True
            elif level == "ERROR" and show_error:
                level_match = True
            elif level == "SUCCESS" and show_success:
                level_match = True
            # If we don't have a match for the level, skip
            if not level_match:
                continue

            # Search filter
            if search_text and search_text not in message.lower() and search_text not in level.lower():
                continue

            # Date filter
            if start_date is not None or end_date is not None:
                # timestamp is already a QDateTime
                qt_timestamp = timestamp
                if start_date is not None and qt_timestamp < start_date:
                    continue
                if end_date is not None and qt_timestamp >= end_date:
                    continue

            self.filtered_entries.append(idx)

        self.update_table()
        self.update_status()

    def update_table(self):
        """Update the table to show only filtered entries."""
        self.log_table.setRowCount(len(self.filtered_entries))
        for row, idx in enumerate(self.filtered_entries):
            timestamp, level, message, raw_line = self.log_entries[idx]
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
        self.last_read_pos = 0
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