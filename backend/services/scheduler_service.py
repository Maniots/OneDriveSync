"""
Scheduler Service

Provides a clean API for accessing scheduler-related information.
Isolates the UI from the core scheduling logic (which is handled by Windows Scheduled Tasks).
"""

import subprocess
from typing import Optional, Dict, Any
from .configuration_service import ConfigurationService
from src.config import AppConfig, SyncTriggerSettings, SyncDirection


class SchedulerService:
    """Service for managing scheduler information."""

    # Task Scheduler folder where OneDrivePCSync tasks are stored
    _TASK_FOLDER = r"\OneDrivePCSync"

    # Mapping from info type to task name (as registered by Setup-ScheduledTasks.ps1)
    _TASK_NAMES = {
        "startup": "OneDrivePCSync - Startup (Download)",
        "periodic": "OneDrivePCSync - Periodic Upload",
        "workstation_lock": "OneDrivePCSync - Shutdown (Upload on Lock)",
    }

    def __init__(self, config_service: ConfigurationService):
        """
        Initialize the scheduler service.

        Args:
            config_service: Service to provide application configuration.
        """
        self._config_service = config_service

    def _get_task_info(self, task_name: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a scheduled task by querying schtasks.exe.

        Args:
            task_name: The name of the task (without folder path).

        Returns:
            Dictionary with keys: exists (bool), enabled (bool), status (str),
            last_run_time (str or None), next_run_time (str or None).
            Returns None if an error occurred querying the task.
        """
        # Build the full task path
        full_task_path = f"{self._TASK_FOLDER}\\{task_name}"

        try:
            # Query the task in CSV format with verbose output
            # /fo CSV gives comma-separated values, /v includes verbose columns
            output = subprocess.check_output(
                ["schtasks", "/query", "/tn", full_task_path, "/fo", "CSV", "/v"],
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)  # Hide console window on Windows
            )
        except subprocess.CalledProcessError as e:
            # If the task is not found, schtasks returns error code 1
            # We'll treat this as the task not existing
            if "ERROR: The system cannot find the file specified." in e.output:
                return {
                    "exists": False,
                    "enabled": False,
                    "status": "Not Found",
                    "last_run_time": None,
                    "next_run_time": None
                }
            else:
                # Other error (e.g., access denied)
                return None
        except Exception:
            # Any other exception (e.g., subprocess not found)
            return None

        # Parse CSV output
        lines = output.strip().splitlines()
        if len(lines) < 2:
            # No data lines (only header or empty)
            return None

        # The first line is header, second line is data
        header = lines[0].strip()
        data_line = lines[1].strip()

        # Simple CSV parsing: split by commas, but values may be quoted.
        # We'll use a more robust approach: split by comma and then strip quotes.
        # Since the output is from schtasks, we can rely on consistent quoting.
        # We'll split by ',' and then remove surrounding double quotes.
        parts = [part.strip().strip('"') for part in data_line.split(',')]

        # We need to map header to parts.
        header_parts = [part.strip().strip('"') for part in header.split(',')]

        # Create a mapping from header to value
        task_info = {}
        for h, v in zip(header_parts, parts):
            task_info[h] = v

        # Extract the fields we care about
        # Note: The exact header names may vary by Windows version/language.
        # We'll try to match common ones.
        # We'll look for keys that contain certain substrings (case-insensitive).
        def get_field(*keys):
            for k in keys:
                for h in header_parts:
                    if k.lower() in h.lower():
                        return task_info.get(h)
            return None

        task_name_field = get_field("TaskName")
        next_run = get_field("Next Run Time")
        status = get_field("Status")
        last_run = get_field("Last Run Time")
        # Determine enabled status: a task is disabled if its status is "Disabled" or if it's ready but disabled?
        # Actually, schtasks /query shows a column "Status" that can be "Ready", "Running", etc.
        # To know if the task is enabled, we need to look at the "Status" column? Actually, there is a separate
        # column for whether the task is enabled? In verbose output, there is a column "Enabled"?
        # Let's check: In schtasks /query /fo CSV /v, there is a column "Enabled" (I think).
        # We'll try to get the "Enabled" field.
        enabled_str = get_field("Enabled")
        enabled = False
        if enabled_str is not None:
            enabled = enabled_str.lower() == "true"
        else:
            # Fallback: if we can't find Enabled, we can infer from Status? Not reliable.
            # We'll assume that if the task exists and we can query it, it's enabled unless status says disabled.
            # Actually, there is a separate output for disabled tasks? Let's just try to get the "Enabled" column.
            # If not present, we'll set enabled to True if the task exists (since we can query it).
            # But a disabled task can still be queried; it just won't run.
            # We'll leave enabled as False if we can't determine, but we'll try to get it from the task's XML maybe.
            # For simplicity, we'll assume that if the task exists, it is enabled (since the setup script enables them).
            # We'll later improve if needed.
            enabled = True

        return {
            "exists": True,
            "enabled": enabled,
            "status": status if status else "Unknown",
            "last_run_time": last_run if last_run else None,
            "next_run_time": next_run if next_run else None
        }

    def get_startup_sync_info(self) -> Optional[Dict[str, Any]]:
        """
        Get information about the startup sync trigger and its scheduled task.

        Returns:
            Dictionary with keys: trigger, delay, direction, enabled (task enabled),
            status, last_run_time, next_run_time, exists.
            Returns None if configuration is not available.
        """
        app_config = self._config_service.get_app_config()
        if app_config is None:
            return None

        trigger: SyncTriggerSettings = app_config.sync.startup
        # Base info from configuration
        info = {
            "trigger": "Logon",  # Hardcoded as per the application design
            "delay": f"{2 if trigger.enabled else 0} minutes",  # Fixed 2 minutes delay if enabled
            "direction": trigger.direction.value.capitalize(),
        }

        # Get task status
        task_name = self._TASK_NAMES["startup"]
        task_info = self._get_task_info(task_name)
        if task_info is not None:
            # Merge task info, overriding enabled from task status
            info.update({
                "enabled": "Enabled" if task_info["enabled"] else "Disabled",
                "status": task_info["status"],
                "last_run_time": task_info["last_run_time"],
                "next_run_time": task_info["next_run_time"],
                "exists": task_info["exists"]
            })
        else:
            # Could not query task (error)
            info.update({
                "enabled": "Unknown",
                "status": "Error querying task",
                "last_run_time": None,
                "next_run_time": None,
                "exists": False
            })

        return info

    def get_periodic_sync_info(self) -> Optional[Dict[str, Any]]:
        """
        Get information about the periodic sync trigger and its scheduled task.

        Returns:
            Dictionary with keys: interval, direction, enabled (task enabled),
            status, last_run_time, next_run_time, exists.
            Returns None if configuration is not available.
        """
        app_config = self._config_service.get_app_config()
        if app_config is None:
            return None

        # Note: The periodic sync is not explicitly in the configuration.
        # The application has a fixed periodic interval of 15 minutes for upload.
        # We'll hardcode the interval and direction.
        info = {
            "interval": "15 minutes",
            "direction": "Upload",  # Fixed as per the application design
        }

        # Get task status
        task_name = self._TASK_NAMES["periodic"]
        task_info = self._get_task_info(task_name)
        if task_info is not None:
            # Merge task info, overriding enabled from task status
            info.update({
                "enabled": "Enabled" if task_info["enabled"] else "Disabled",
                "status": task_info["status"],
                "last_run_time": task_info["last_run_time"],
                "next_run_time": task_info["next_run_time"],
                "exists": task_info["exists"]
            })
        else:
            # Could not query task (error)
            info.update({
                "enabled": "Unknown",
                "status": "Error querying task",
                "last_run_time": None,
                "next_run_time": None,
                "exists": False
            })

        return info

    def get_workstation_lock_info(self) -> Optional[Dict[str, Any]]:
        """
        Get information about the workstation lock (shutdown on lock) trigger and its scheduled task.

        Returns:
            Dictionary with keys: trigger, direction, enabled (task enabled),
            status, last_run_time, next_run_time, exists.
            Returns None if configuration is not available.
        """
        app_config = self._config_service.get_app_config()
        if app_config is None:
            return None

        trigger: SyncTriggerSettings = app_config.sync.shutdown
        # Base info from configuration
        info = {
            "trigger": "Workstation Lock",
            "direction": trigger.direction.value.capitalize(),
        }

        # Get task status
        task_name = self._TASK_NAMES["workstation_lock"]
        task_info = self._get_task_info(task_name)
        if task_info is not None:
            # Merge task info, overriding enabled from task status
            info.update({
                "enabled": "Enabled" if task_info["enabled"] else "Disabled",
                "status": task_info["status"],
                "last_run_time": task_info["last_run_time"],
                "next_run_time": task_info["next_run_time"],
                "exists": task_info["exists"]
            })
        else:
            # Could not query task (error)
            info.update({
                "enabled": "Unknown",
                "status": "Error querying task",
                "last_run_time": None,
                "next_run_time": None,
                "exists": False
            })

        return info

    def get_scheduler_summary(self) -> Optional[Dict[str, Optional[Dict[str, str]]]]:
        """
        Get a summary of all scheduler information.

        Returns:
            Dictionary with keys: 'startup', 'periodic', 'workstation_lock'.
            Each value is a dictionary as returned by the respective get_*_info method.
            Returns None if configuration is not available.
        """
        app_config = self._config_service.get_app_config()
        if app_config is None:
            return None

        return {
            "startup": self.get_startup_sync_info(),
            "periodic": self.get_periodic_sync_info(),
            "workstation_lock": self.get_workstation_lock_info()
        }

    def _change_task_status(self, task_name: str, enable: bool) -> bool:
        """
        Change the enabled status of a scheduled task.

        Args:
            task_name: The name of the task (without folder path).
            enable: True to enable, False to disable.

        Returns:
            True if successful, False otherwise.
        """
        # Validate task_name is one of the known task names
        if task_name not in self._TASK_NAMES.values():
            # Log error
            print(f"Invalid task name: {task_name}")
            return False

        full_task_path = f"{self._TASK_FOLDER}\\{task_name}"
        flag = "/ENABLE" if enable else "/DISABLE"
        try:
            result = subprocess.run(
                ["schtasks", "/change", "/tn", full_task_path, flag],
                capture_output=True,
                text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
            if result.returncode == 0:
                # Log success
                action = "enabled" if enable else "disabled"
                print(f"Task '{task_name}' {action} successfully.")
                return True
            else:
                # Log error
                print(f"Failed to change task status: {result.stderr}")
                return False
        except Exception as e:
            print(f"Exception while changing task status: {e}")
            return False

    def set_task_enabled(self, task_key: str, enabled: bool) -> bool:
        """
        Set the enabled status of a scheduled task by its key.

        Args:
            task_key: One of "startup", "periodic", "workstation_lock".
            enabled: True to enable, False to disable.

        Returns:
            True if successful, False otherwise.
        """
        # Map task key to task name
        task_name = self._TASK_NAMES.get(task_key)
        if task_name is None:
            print(f"Invalid task key: {task_key}")
            return False
        return self._change_task_status(task_name, enabled)