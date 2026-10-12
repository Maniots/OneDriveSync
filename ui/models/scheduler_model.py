from dataclasses import dataclass
from typing import Optional


@dataclass
class SchedulerModel:
    """UI-only model representing scheduler status."""
    # Startup Sync
    startup_trigger: str = "Logon"
    startup_delay: int = 2  # minutes
    startup_direction: str = ""
    startup_enabled: bool = False
    startup_next_run: Optional[str] = None

    # Periodic Sync
    periodic_interval: int = 15  # minutes
    periodic_direction: str = "Upload"  # fixed as per overview
    periodic_enabled: bool = False
    periodic_next_run: Optional[str] = None

    # Workstation Lock (Shutdown on Lock)
    workstation_trigger: str = "Workstation Lock"
    workstation_direction: str = ""
    workstation_enabled: bool = False
    workstation_next_run: Optional[str] = None

    # Shutdown Monitor
    monitor_status: str = "Unknown"  # e.g., "Running", "Stopped"
    last_detected_event: str = "Unknown"
    last_shutdown_sync: Optional[str] = None