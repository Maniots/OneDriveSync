"""
Scheduler Service

Provides a clean API for accessing scheduler-related information.
Isolates the UI from the core scheduling logic (which is handled by Windows Scheduled Tasks).
"""

import subprocess
import base64
import json
import re
import time
from typing import Optional, Dict, Any
from .configuration_service import ConfigurationService
from src.config import AppConfig, SyncTriggerSettings, SyncDirection
from PySide6.QtCore import QObject, QThread, QCoreApplication, Qt, Signal, Slot


class _SchedulerQuery(QObject):
    completed = Signal(object)
    finished = Signal()

    def __init__(self, service):
        super().__init__()
        self.service = service

    @Slot()
    def run(self):
        try:
            self.completed.emit(self.service.get_scheduler_summary())
        except Exception:
            self.completed.emit(None)
        finally:
            self.finished.emit()


class SchedulerService(QObject):
    """Service for managing scheduler information."""

    # Task Scheduler folder where OneDrivePCSync tasks are stored
    _TASK_FOLDER = r"\OneDrivePCSync"

    # Mapping from info type to task name (as registered by Setup-ScheduledTasks.ps1)
    _TASK_NAMES = {
        "startup": "OneDrivePCSync - Startup (Download)",
        "periodic": "OneDrivePCSync - Periodic Upload",
        "workstation_lock": "OneDrivePCSync - Shutdown (Upload on Lock)",
    }
    updated = Signal(object)

    def __init__(self, config_service: ConfigurationService):
        """
        Initialize the scheduler service.

        Args:
            config_service: Service to provide application configuration.
        """
        super().__init__()
        self._config_service = config_service
        self._cache = {}
        self.cached_summary = None
        self._last_refresh = 0
        self._thread = None
        self._worker = None
        self._refresh_pending = False
        if QCoreApplication.instance():
            QCoreApplication.instance().aboutToQuit.connect(self.wait_for_finished)

    def request_refresh(self, force=False):
        if self._thread is not None:
            self._refresh_pending |= force
            return False
        if not force and time.monotonic() - self._last_refresh < 30:
            return False
        if force:
            self.invalidate_cache()
        self._thread = QThread(QCoreApplication.instance())
        self._worker = _SchedulerQuery(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.completed.connect(self._query_completed)
        self._worker.finished.connect(self._thread.quit, Qt.ConnectionType.DirectConnection)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._query_finished)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()
        return True

    @Slot(object)
    def _query_completed(self, summary):
        self.cached_summary = summary
        self._last_refresh = time.monotonic()
        self.updated.emit(summary)

    @Slot()
    def _query_finished(self):
        # Qt still processes deferred deletion after emitting finished.
        if self._thread is not None:
            self._thread.wait()
        self._thread = None
        self._worker = None
        if self._refresh_pending:
            self._refresh_pending = False
            self.request_refresh(force=True)

    @Slot()
    def wait_for_finished(self):
        self._refresh_pending = False
        if self._thread is not None:
            self._thread.wait()

    def invalidate_cache(self):
        self._cache.clear()

    @staticmethod
    def _duration(value):
        if not value:
            return "Not configured"
        match = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?", value)
        if not match:
            return value
        units = ("day", "hour", "minute", "second")
        parts = [f"{float(n):g} {unit}{'s' if float(n) != 1 else ''}"
                 for n, unit in zip(match.groups(), units) if n and float(n)]
        return ", ".join(parts) or "No delay"

    def _get_task_info(self, task_name: str) -> Optional[Dict[str, Any]]:
        """Read stable COM properties instead of localized schtasks CSV."""
        cached = self._cache.get(task_name)
        if cached and time.monotonic() - cached[0] < 30:
            return cached[1]
        folder = self._TASK_FOLDER.replace("'", "''")
        name = task_name.replace("'", "''")
        script = """
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$svc = New-Object -ComObject 'Schedule.Service'
$svc.Connect()
try {
    $task = $svc.GetFolder('FOLDER').GetTask('NAME')
} catch {
    if ($_.Exception.HResult -in @(-2147024894,-2147024893) -or $_.Exception.InnerException.HResult -in @(-2147024894,-2147024893)) {
        @{exists=$false;enabled=$false;status='Not Found';last_run_time=$null;next_run_time=$null;triggers=@()} | ConvertTo-Json -Compress
        exit 0
    }
    throw
}
$triggers = @($task.Definition.Triggers | ForEach-Object {
    @{type=[int]$_.Type;delay=[string]$_.Delay;interval=[string]$_.Repetition.Interval;enabled=[bool]$_.Enabled}
})
$last = if ($task.LastRunTime.Year -gt 1900) { $task.LastRunTime.ToString('o') } else { $null }
$next = if ($task.Enabled -and $task.NextRunTime.Year -gt 1900) { $task.NextRunTime.ToString('o') } else { $null }
$states = @('Unknown','Disabled','Queued','Ready','Running')
@{exists=$true;enabled=[bool]$task.Enabled;status=$states[[int]$task.State];last_run_time=$last;next_run_time=$next;triggers=$triggers} | ConvertTo-Json -Compress -Depth 4
""".replace('FOLDER', folder).replace('NAME', name)
        try:
            output = subprocess.check_output(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand",
                 base64.b64encode(script.encode("utf-16-le")).decode("ascii")],
                stderr=subprocess.STDOUT, text=True, encoding="utf-8-sig", timeout=8,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            info = json.loads(output)
            if not isinstance(info, dict) or not isinstance(info.get("enabled"), bool) or not isinstance(info.get("exists"), bool):
                self._cache[task_name] = (time.monotonic(), None)
                return None
        except (OSError, subprocess.SubprocessError, ValueError):
            self._cache[task_name] = (time.monotonic(), None)
            return None
        self._cache[task_name] = (time.monotonic(), info)
        return info

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
            "delay": "Unknown",
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

        if task_info:
            delays = [self._duration(t.get("delay")) for t in task_info.get("triggers", []) if t.get("type") == 9]
            info["delay"] = ", ".join(delays) if delays else "Not configured"
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

        # The task's repetition comes from Windows; its shutdown-mode action
        # obeys the configured shutdown direction.
        info = {
            "interval": "Unknown",
            "direction": app_config.sync.shutdown.direction.value.capitalize(),
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

        if task_info:
            intervals = [self._duration(t.get("interval")) for t in task_info.get("triggers", []) if t.get("interval")]
            info["interval"] = ", ".join(intervals) if intervals else "Not configured"
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
                self.invalidate_cache()
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
