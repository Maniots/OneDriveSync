"""
Log Service

Provides a clean API for accessing and filtering log data.
Isolates the UI from direct log file reading.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional
from PySide6.QtCore import QDateTime, QDate


class LogService:
    """Service for managing log data."""

    def __init__(self, log_path: Optional[Path] = None):
        """
        Initialize the log service.

        Args:
            log_path: Path to the log file.
                      If None, uses the default location (logs/onedrive_pcsync.log
                      relative to the project root).
        """
        if log_path is None:
            # Default to logs/onedrive_pcsync.log in the project root
            # We assume the project root is two levels up from this file:
            #   backend/services/log_service.py -> backend -> project root
            log_path = Path(__file__).resolve().parent.parent.parent / "logs" / "onedrive_pcsync.log"
        self._log_path = log_path
        # Pre-compile the regex for parsing log lines
        # Expected format: "%Y-%m-%d %H:%M:%S | %(levelname)-8s | %(name)s | %(message)s"
        self._log_regex = re.compile(
            r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| (\w+)\s*\| (.+?) \| (.+)$"
        )

    def _parse_log_line(self, line: str) -> Optional[Tuple[QDateTime, str, str]]:
        """
        Parse a log line into (timestamp, level, message).

        Args:
            line: A single line from the log file.

        Returns:
            A tuple (timestamp, level, message) if the line matches the expected format,
            None otherwise.
        """
        match = self._log_regex.match(line)
        if not match:
            return None

        timestamp_str, level, logger_name, message = match.groups()
        try:
            timestamp = QDateTime.fromString(timestamp_str, "yyyy-MM-dd HH:mm:ss")
            if not timestamp.isValid():
                return None
            # Combine logger name and message for display
            display_message = f"[{logger_name}] {message}"
            return timestamp, level.strip(), display_message
        except Exception:
            return None

    def get_log_entries(self, max_lines: Optional[int] = None) -> List[Tuple[QDateTime, str, str]]:
        """
        Get log entries from the log file.

        Args:
            max_lines: Maximum number of lines to read from the end of the file.
                       If None, reads all lines.

        Returns:
            A list of tuples (timestamp, level, message) for each log entry.
            Returns an empty list if the log file does not exist or cannot be read.
        """
        if not self._log_path.exists():
            return []

        try:
            with self._log_path.open("r", encoding="utf-8") as f:
                lines = f.readlines()
                if max_lines is not None:
                    lines = lines[-max_lines:]
                entries: List[Tuple[QDateTime, str, str]] = []
                for line in lines:
                    line = line.rstrip("\n")
                    parsed = self._parse_log_line(line)
                    if parsed:
                        entries.append(parsed)
                return entries
        except Exception:
            return []

    def filter_entries(
        self,
        entries: List[Tuple[QDateTime, str, str]],
        search_text: str = "",
        show_info: bool = True,
        show_warning: bool = True,
        show_error: bool = True,
        show_success: bool = False,
        date_index: int = 0  # 0: All, 1: Today, 2: Yesterday, 3: Last 7 Days, 4: Last 30 Days
    ) -> List[Tuple[QDateTime, str, str]]:
        """
        Filter log entries based on search text, level, and date range.

        Args:
            entries: List of log entries to filter.
            search_text: Case-insensitive search text to match in level or message.
            show_info: Whether to include INFO level entries.
            show_warning: Whether to include WARNING level entries.
            show_error: Whether to include ERROR level entries.
            show_success: Whether to include SUCCESS level entries.
            date_index: Index for date range (0: All, 1: Today, 2: Yesterday, 3: Last 7 Days, 4: Last 30 Days).

        Returns:
            A list of filtered log entries.
        """
        if not entries:
            return []

        # Date range
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

        filtered: List[Tuple[QDateTime, str, str]] = []
        for timestamp, level, message in entries:
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

            if not level_match:
                continue

            # Search filter
            if search_text:
                search_lower = search_text.lower()
                if search_lower not in level.lower() and search_lower not in message.lower():
                    continue

            # Date filter
            if start_date is not None or end_date is not None:
                if start_date is not None and timestamp < start_date:
                    continue
                if end_date is not None and timestamp >= end_date:
                    continue

            filtered.append((timestamp, level, message))

        return filtered