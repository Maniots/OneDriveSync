#!/usr/bin/env python
"""
Development-only UI launcher for OneDrive PC Sync.

This script launches the PySide6 user interface for development and testing.
It is not used in production; the production entry point is via the
PowerShell wrapper and src/main.py for synchronization.
"""

from ui.app import main


if __name__ == "__main__":
    main()