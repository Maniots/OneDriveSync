"""Shared writable paths for source runs and installed Windows bundles."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent.parent


def data_root() -> Path:
    if not getattr(sys, "frozen", False):
        return SOURCE_ROOT
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise RuntimeError("LOCALAPPDATA is required for the installed application")
    return Path(local_app_data) / "OneDrivePCSync"


def default_config_path() -> Path:
    return data_root() / "config.json"


def log_dir() -> Path:
    return data_root() / "logs"


def sync_lock_path() -> Path:
    return data_root() / "onedrive_pcsync.lock"


def ensure_default_config() -> Path:
    """Seed a fresh installation; never overwrite an existing configuration."""
    target = default_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    template = SOURCE_ROOT / "packaging" / "default-config.json"
    contents = template.read_text(encoding="utf-8")
    json.loads(contents)
    try:
        with target.open("x", encoding="utf-8") as handle:
            handle.write(contents)
    except FileExistsError:
        pass
    return target
