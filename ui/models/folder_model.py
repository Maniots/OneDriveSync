from dataclasses import dataclass
from typing import Optional


@dataclass
class FolderModel:
    """UI-only model representing a folder to be synced."""
    id: str
    name: str
    enabled: bool
    local_path: str
    onedrive_path: str
    minimum_sync_percentage: int
    verify_after_sync: bool
    create_destination: bool
    # Optional UI-specific fields
    last_sync_status: Optional[str] = None
    last_sync_time: Optional[str] = None
    backup_enabled: bool = False
    backup_retention_days: int = 0