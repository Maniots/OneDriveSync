import pytest

from src.cloud_credentials import CredentialStore


def test_password_is_protected_and_reused(tmp_path):
    # Inject an explicit test protector; production must use the OS protector.
    protect = lambda value: b"test-protected:" + bytes(value)[::-1]
    unprotect = lambda value: bytes(value).removeprefix(b"test-protected:")[::-1]
    store = CredentialStore(tmp_path, protect=protect, unprotect=unprotect)
    password = store.password()
    assert len(password) >= 32
    assert password.encode() not in (tmp_path / "rclone-key.dpapi").read_bytes()
    assert CredentialStore(tmp_path, protect=protect, unprotect=unprotect).password() == password


def test_unreadable_key_is_not_replaced(tmp_path):
    path = tmp_path / "rclone-key.dpapi"
    path.write_bytes(b"original-protected-key")
    def fail(value):
        raise ValueError("private details")
    store = CredentialStore(tmp_path, protect=fail, unprotect=fail)
    with pytest.raises(RuntimeError, match="unlock") as error:
        store.password()
    assert "private details" not in str(error.value)
    assert path.read_bytes() == b"original-protected-key"
