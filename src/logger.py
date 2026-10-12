"""
logger.py

Centralized logging configuration for OneDrive PC Sync.

Provides a single entry point (setup_logger) that configures both a
rotating file handler (logs/onedrive_pcsync.log) and a console handler.
All other modules should call get_logger(__name__) to obtain a logger
that inherits this configuration.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOGGER_INITIALIZED = False
_ROOT_LOGGER_NAME = "onedrive_pcsync"

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_MAX_BYTES = 5 * 1024 * 1024  # 5 MB per log file
_BACKUP_COUNT = 5


def set_log_level(log_level: str) -> logging.Logger:
    """Apply settings without creating a log file before the runner starts."""
    root_logger = logging.getLogger(_ROOT_LOGGER_NAME)
    level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger.setLevel(level)
    for handler in root_logger.handlers:
        handler.setLevel(level)
    return root_logger


def setup_logger(log_dir: Path, log_level: str = "INFO") -> logging.Logger:
    """Configure the application-wide root logger.

    Initialize before logging. Subsequent calls update levels on the existing
    logger and handlers without attaching duplicates.

    Args:
        log_dir: Directory in which log files will be created. Created
            automatically if it does not exist.
        log_level: Logging level name (e.g. "INFO", "DEBUG").

    Returns:
        The configured root application logger.
    """
    global _LOGGER_INITIALIZED

    root_logger = logging.getLogger(_ROOT_LOGGER_NAME)
    logging.addLevelName(25, "SUCCESS")
    level = getattr(logging, log_level.upper(), logging.INFO)

    if _LOGGER_INITIALIZED:
        return set_log_level(log_level)

    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "onedrive_pcsync.log"

    level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger.setLevel(level)

    formatter = logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT)

    file_handler = RotatingFileHandler(
        filename=str(log_file),
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    root_logger.addHandler(file_handler)
    # Windowless EXEs and pythonw have no stdout/stderr.
    if sys.stdout is not None:
        console_handler = logging.StreamHandler(stream=sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(level)
        root_logger.addHandler(console_handler)
    root_logger.propagate = False

    _LOGGER_INITIALIZED = True
    return root_logger


def get_logger(module_name: str) -> logging.Logger:
    """Return a child logger namespaced under the application root logger.

    Args:
        module_name: Typically __name__ of the calling module.

    Returns:
        A logging.Logger instance that inherits the root configuration.
    """
    return logging.getLogger(f"{_ROOT_LOGGER_NAME}.{module_name}")
