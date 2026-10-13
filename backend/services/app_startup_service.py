"""Per-user Windows desktop startup registration, independent of sync tasks."""
import sys
from pathlib import Path

try:
    import winreg
except ImportError:
    winreg = None


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "OneDrivePCSync"


class AppStartupService:
    def __init__(self, executable=None, value_name=VALUE_NAME):
        self.executable = (Path(executable).resolve() if executable is not None else
                           Path(sys.executable).resolve() if getattr(sys, "frozen", False) else None)
        self.value_name = value_name

    @property
    def supported(self):
        return winreg is not None and self.executable is not None

    @property
    def command(self):
        return f'"{self.executable}"'

    def _read(self, key):
        try:
            value, kind = winreg.QueryValueEx(key, self.value_name)
            return value if kind == winreg.REG_SZ else (value, kind)
        except FileNotFoundError:
            return None

    def is_enabled(self):
        if not self.supported:
            return False
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                return self._read(key) == self.command
        except FileNotFoundError:
            return False

    def set_enabled(self, enabled):
        if not self.supported:
            raise RuntimeError("Run at startup is available in the installed Windows app.")
        if enabled and len(self.command) > 260:
            raise RuntimeError("The application path is too long for Windows startup.")
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as key:
            current = self._read(key)
            if current not in (None, self.command):
                raise RuntimeError("A different installation already uses this startup entry.")
            if enabled:
                winreg.SetValueEx(key, self.value_name, 0, winreg.REG_SZ, self.command)
            elif current is not None:
                winreg.DeleteValue(key, self.value_name)
        if self.is_enabled() != bool(enabled):
            raise RuntimeError("Windows did not retain the startup setting. Please retry.")
