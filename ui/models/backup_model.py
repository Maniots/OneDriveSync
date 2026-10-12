from dataclasses import dataclass
from typing import Optional


@dataclass
class BackupModel:
    """UI-only model representing a backup."""
    folder_id: str
    folder_name: str
    backup_path: str
    timestamp: str
    size: str  # Could be bytes, but for UI we keep as string for display
    # Optional UI-specific fields
    status: str = "Success"  # e.g., Success, Failed, In Progress