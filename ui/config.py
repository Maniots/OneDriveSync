"""
UI configuration handling.
Converts backend AppConfig to UI models and handles configuration errors.
"""

from typing import List, Optional
from src.config import AppConfig, FolderSyncConfig, GeneralSettings, SyncSettings
from .models.folder_model import FolderModel
from .models.sync_status_model import SyncStatusModel
from .models.backup_model import BackupModel
from .models.scheduler_model import SchedulerModel
from .resources.icons import get_icon
import os
from pathlib import Path


def convert_folder_to_ui_model(folder_config: FolderSyncConfig) -> FolderModel:
    """
    Convert a backend FolderSyncConfig to a UI FolderModel.

    Args:
        folder_config: Backend folder configuration

    Returns:
        UI FolderModel
    """
    # Convert Path objects to strings with environment variables unexpanded for display
    # In a real app, we might want to keep them expanded or have a preference
    local_path_str = str(folder_config.local_path)
    onedrive_path_str = str(folder_config.onedrive_path)

    # Try to convert back to environment variable format for display if possible
    # This is a simplified approach - in practice, we might want to store the original
    # or have a setting for how to display paths
    try:
        # Try to convert common environment variables back
        appdata = os.getenv("APPDATA", "")
        userprofile = os.getenv("USERPROFILE", "")
        onedrive = os.getenv("OneDrive", "")

        if appdata and local_path_str.startswith(appdata):
            local_path_str = local_path_str.replace(appdata, "%APPDATA%", 1)
        if userprofile and local_path_str.startswith(userprofile):
            local_path_str = local_path_str.replace(userprofile, "%USERPROFILE%", 1)
        if onedrive and onedrive_path_str.startswith(onedrive):
            onedrive_path_str = onedrive_path_str.replace(onedrive, "%OneDrive%", 1)
    except:
        # If anything goes wrong, just use the expanded paths
        pass

    return FolderModel(
        id=folder_config.id,
        name=folder_config.name,
        enabled=folder_config.enabled,
        local_path=local_path_str,
        onedrive_path=onedrive_path_str,
        minimum_sync_percentage=int(folder_config.minimum_sync_percentage),
        verify_after_sync=folder_config.verify_after_sync,
        create_destination=folder_config.create_destination,
        # UI-specific fields - these would normally come from a sync status service
        last_sync_status=None,
        last_sync_time=None,
        backup_enabled=folder_config.backup is not None and folder_config.backup.enabled,
        backup_retention_days=folder_config.backup.retention_days if folder_config.backup else 0
    )


def convert_to_ui_models(config: AppConfig) -> tuple[
    List[FolderModel],
    SyncStatusModel,
    List[BackupModel],
    SchedulerModel
]:
    """
    Convert backend AppConfig to UI models.

    Args:
        config: Backend AppConfig

    Returns:
        Tuple of (folder_models, sync_status_model, backup_models, scheduler_model)
    """
    # Convert folders
    folder_models = [
        convert_folder_to_ui_model(folder)
        for folder in config.folders
    ]

    # Create sync status model (in a real app, this would come from a sync service)
    sync_status_model = SyncStatusModel(
        is_syncing=False,
        last_sync_time=None,
        last_sync_result="Unknown",
        folders_synced=0,
        total_folders=len(config.folders),
        next_scheduled_upload=None,
        service_status="Stopped"
    )

    # Create backup models (in a real app, these would come from a backup service)
    backup_models = []
    for folder in config.folders:
        if folder.backup and folder.backup.enabled:
            # In a real app, we would get actual backup data from the backup service
            backup_models.append(BackupModel(
                folder_id=folder.id,
                folder_name=folder.name,
                backup_path=str(folder.backup.backup_path),
                timestamp="Unknown",  # Would come from backup service
                size="Unknown",       # Would come from backup service
                status="Unknown"      # Would come from backup service
            ))

    # Create scheduler model with the new structure
    scheduler_model = SchedulerModel(
        # Startup Sync
        startup_direction=config.sync.startup.direction.value if hasattr(config.sync.startup.direction, 'value') else str(config.sync.startup.direction),
        startup_enabled=config.sync.startup.enabled,
        startup_next_run=None,  # Would come from task scheduler in a full implementation

        # Periodic Sync
        periodic_direction="Upload",  # Fixed as per overview
        periodic_enabled=False,       # We don't have a way to get the periodic task status from config
        periodic_next_run=None,       # Would come from task scheduler

        # Workstation Lock (Shutdown on Lock)
        workstation_direction=config.sync.shutdown.direction.value if hasattr(config.sync.shutdown.direction, 'value') else str(config.sync.shutdown.direction),
        workstation_enabled=config.sync.shutdown.enabled,
        workstation_next_run=None,   # Would come from task scheduler

        # Shutdown Monitor
        monitor_status="Unknown",    # We don't have this info from config
        last_detected_event="Unknown", # We don't have this info
        last_shutdown_sync=None      # We don't have this info
    )

    return folder_models, sync_status_model, backup_models, scheduler_model


def get_config_path() -> Path:
    """
    Get the path to the configuration file.

    Returns:
        Path to config.json
    """
    # Assume config.json is in the same directory as this file's parent parent (project root)
    # ui/config.py -> ui/ -> project root
    return Path(__file__).parent.parent / "config.json"