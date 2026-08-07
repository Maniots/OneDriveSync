from dataclasses import dataclass
from typing import Optional


@dataclass
class SchedulerModel:
    """UI-only model representing scheduler status."""
    startup_task_enabled: bool
    shutdown_task_enabled: bool
    periodic_task_enabled: bool
    # Optional UI-specific fields
    startup_task_next_run: Optional[str] = None
    shutdown_task_next_run: Optional[str] = None
    periodic_task_next_run: Optional[str] = None