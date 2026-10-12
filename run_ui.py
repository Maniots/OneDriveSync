#!/usr/bin/env python
"""
Source UI launcher for OneDrive PC Sync.

Installed Windows releases use desktop_entry.py as their unified entry point.
"""

from ui.app import main


if __name__ == "__main__":
    raise SystemExit(main())
