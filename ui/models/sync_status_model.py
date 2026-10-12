from dataclasses import dataclass
from typing import Optional


@dataclass
class SyncStatusModel:
    """UI-only model representing the overall sync status."""
    is_syncing: bool
    last_sync_time: Optional[str] = None
    last_sync_result: str = "Unknown"  # e.g., Success, Failed, In Progress
    folders_synced: int = 0
    total_folders: int = 0
    # Optional UI-specific fields
    next_scheduled_upload: Optional[str] = None
    service_status: str = "Stopped"  # e.g., Running, Stopped