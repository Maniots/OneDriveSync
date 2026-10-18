"""Keep the app-owned rclone encryption password protected by the current user."""
import os
import secrets
import sys
import tempfile
from pathlib import Path


def _protect(value):
    if sys.platform != "win32":
        raise RuntimeError("Cloud credentials require Windows user protection.")
    import win32crypt
    return win32crypt.CryptProtectData(value, "EverySync cloud credentials", None, None, None, 1)


def _unprotect(value):
    if sys.platform != "win32":
        raise RuntimeError("Cloud credentials require Windows user protection.")
    import win32crypt
    return win32crypt.CryptUnprotectData(value, None, None, None, 1)[1]


class CredentialStore:
    def __init__(self, root: Path, *, protect=None, unprotect=None):
        self.root = Path(root)
        self.key_path = self.root / "rclone-key.dpapi"
        self._protect = protect or _protect
        self._unprotect = unprotect or _unprotect

    def password(self):
        from .single_instance import acquire_single_instance_lock
        self.root.mkdir(parents=True, exist_ok=True)
        lock = acquire_single_instance_lock(self.root / "credentials.lock")
        if lock is None:
            raise RuntimeError("Cloud credentials are being configured. Please retry.")
        temporary = None
        try:
            if self.key_path.exists():
                try:
                    return self._unprotect(self.key_path.read_bytes()).decode("utf-8")
                except Exception:
                    raise RuntimeError("Cannot unlock cloud credentials for this Windows user.") from None
            if (self.root / "rclone.conf").exists():
                raise RuntimeError("Cannot unlock cloud credentials: the protected key is missing.")
            password = secrets.token_urlsafe(48)
            try:
                protected = self._protect(password.encode("utf-8"))
            except Exception:
                raise RuntimeError("Cannot protect cloud credentials for this Windows user.") from None
            with tempfile.NamedTemporaryFile(dir=self.root, prefix=".cloud-key-", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(protected)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.key_path)
            return password
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            lock.close()
