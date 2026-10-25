"""Asynchronous account setup and recovery operations for the desktop."""
from dataclasses import replace
from pathlib import Path
import threading

from PySide6.QtCore import QObject, QThread, Signal

from src.cloud_sync import CloudSyncRunner
from src.rclone_transport import RcloneTransport, CloudSyncError, CloudNotFound
from src.single_instance import acquire_single_instance_lock
from src.runtime_paths import sync_lock_path
from src.cloud_providers import OAUTH_PROVIDERS, setup_parameters
from src.cloud_models import validate_relative_path, validate_local_path
from src.cloud_identity import normalize_account_identity


class _Task(QThread):
    def __init__(self, function, parent):
        super().__init__(parent)
        self.function = function
        self.cancel_event = threading.Event()
        self.value = None
        self.error = None

    def run(self):
        lock = None
        try:
            lock = acquire_single_instance_lock(sync_lock_path())
            if lock is None:
                raise ValueError("Another synchronization is running. Wait and retry.")
            self.value = self.function(self.cancel_event)
        except Exception as error:
            self.error = str(error) if isinstance(error, (ValueError, CloudSyncError)) else "Cloud operation failed. Check access and connection settings, then retry."
        finally:
            if lock is not None:
                lock.close()


class CloudService(QObject):
    completed = Signal(str, object)
    failed = Signal(str)
    busy_changed = Signal(bool)
    finished = Signal()

    def __init__(self, config_service, sync_service=None, *, transport_factory=None, parent=None):
        super().__init__(parent)
        self.config_service = config_service
        self.sync_service = sync_service
        self.transport_factory = transport_factory or RcloneTransport
        self._task = None
        self._pending_connection = None
        self._choose_root = False
        self._authorized = False
        self._drive_choices = None
        self.action = ""
        self.account_identities = {}
        self._identity_shutdown = False

    @property
    def busy(self):
        return self._task is not None

    @property
    def pending_connection(self):
        return self._pending_connection

    def ensure_idle(self):
        if self.busy or (self.sync_service is not None and self.sync_service.is_syncing):
            raise ValueError("Wait for the current synchronization or account operation to finish.")

    def _submit(self, action, function):
        self.ensure_idle()
        if self._pending_connection is not None and action not in {"configure", "discard", "folders", "save_root"}:
            raise ValueError("Finish or cancel account setup before starting another cloud operation.")
        self.action = action
        task = self._task = _Task(function, self)
        task.action = action
        task.finished.connect(self._completed)
        self.busy_changed.emit(True)
        task.start()

    def _completed(self, task=None):
        # wait_for_finished may have already handled this queued signal. Never
        # let an earlier worker's signal complete a replacement cleanup worker.
        task = task if task is not None else self.sender()
        if task is None or task is not self._task:
            return
        task.wait()
        self._task = None
        try:
            if ((task.action == "configure" and (task.error or task.cancel_event.is_set()))
                    or (task.action in {"save_root", "folders"} and task.cancel_event.is_set())):
                self._discard_pending(task.error or "Account operation cancelled.")
            elif task.action == "discard":
                if task.error:
                    self.failed.emit("Could not remove unfinished account credentials. Cancel account setup again to retry.")
                else:
                    self._pending_connection = None
                    self._authorized = False
                    self._drive_choices = None
                    self.failed.emit(task.value)
            elif task.action == "accounts" and task.cancel_event.is_set():
                self.failed.emit("Account operation cancelled.")
            elif task.error:
                if task.action == "accounts":
                    current = {c.id for c in self.config_service.get_app_config().connections}
                    self.account_identities.update({identifier: {"status": "unavailable"}
                        for identifier in task.identity_ids if identifier in current})
                self.failed.emit(task.error)
            elif task.cancel_event.is_set():
                self.failed.emit("Account operation cancelled.")
            else:
                value = task.value
                config = self.config_service.get_app_config()
                if task.action == "configure" and value.get("choose_root"):
                    self._authorized = True
                elif task.action in {"configure", "save_root"} and not value.get("question"):
                    connection = value["connection"]
                    if self._provider_connected(connection):
                        self._discard_pending("An account for this service is already connected. Disconnect it before connecting another.")
                        return
                    self.config_service.save(replace(config, connections=[*config.connections, connection]))
                    self._pending_connection = None
                    self._authorized = False
                    self._drive_choices = None
                elif task.action == "remove":
                    self.config_service.save(replace(config, connections=[c for c in config.connections if c.id != value]))
                    self.account_identities.pop(value, None)
                elif task.action == "accounts":
                    current = {c.id for c in config.connections}
                    self.account_identities.update({key: item for key, item in value.items() if key in current})
                elif task.action in {"test", "authorize_account"}:
                    if any(c.id == value["connection_id"] for c in config.connections):
                        self.account_identities[value["connection_id"]] = value["identity"]
                    value = value["connection_id"]
                if task.action == "configure":
                    question = value.get("question") or {}
                    option = question.get("Option") or {}
                    self._drive_choices = ((question["State"], {item["Value"] for item in option.get("Examples", [])})
                        if value["connection"].provider == "onedrive" and option.get("Name") == "config_driveid" else None)
                self.completed.emit(task.action, value)
        except Exception as error:
            message = str(error) if isinstance(error, (ValueError, CloudSyncError)) else "Could not save the connection. Check the configuration and retry."
            if task.action == "configure" and self._pending_connection is not None:
                self._discard_pending(message)
            else:
                self.failed.emit(message)
        finally:
            task.deleteLater()
            if self._task is None:
                self.busy_changed.emit(False)
                self.finished.emit()

    def _discard_pending(self, message):
        connection = self._pending_connection
        if connection is None:
            self.failed.emit(message)
            return
        def discard(cancel_event):
            # Only this service's unfinished new account is eligible. Existing
            # connections are never removed by cancellation or window shutdown.
            if any(item.id == connection.id for item in self.config_service.get_app_config().connections):
                raise ValueError("The connection has already been saved.")
            with self.transport_factory(self.config_service.cloud_root) as client:
                client.call("config/delete", {"name": "es_" + connection.id})
            return message
        self._submit("discard", discard)

    def configure_connection(self, connection, parameters, *, state=None, answer=None, create_root=False, choose_root=False):
        self.ensure_idle()
        if any(item.id == connection.id for item in self.config_service.get_app_config().connections):
            raise ValueError("This connection is already configured.")
        if self._provider_connected(connection):
            raise ValueError("An account for this service is already connected. Disconnect it before connecting another.")
        if state is None and self._pending_connection is not None:
            raise ValueError("Finish or cancel the pending account setup first.")
        if state is not None and self._pending_connection != connection:
            raise ValueError("Start account setup again before continuing authorization.")
        if self._authorized:
            raise ValueError("Choose a cloud folder to finish connecting this account.")
        if state is not None and self._drive_choices is not None:
            expected_state, allowed = self._drive_choices
            if state != expected_state or answer not in allowed:
                raise ValueError("Choose one of the available OneDrive drives.")
        if state is None:
            self._drive_choices = None
            self._choose_root = choose_root and connection.provider in OAUTH_PROVIDERS
            if connection.provider == "drive":
                # Fail before starting a worker or creating an unfinished remote
                # when this release has no Google application identity.
                parameters = setup_parameters("drive", parameters)
        self._pending_connection = connection
        def configure(cancel_event):
            with self.transport_factory(self.config_service.cloud_root, cancel_event=cancel_event) as client:
                if connection.provider == "drive" and state is None:
                    from src.cloud_oauth import google_login
                    token = google_login(parameters, cancel_event)
                    result = client.configure_google(connection, parameters, token)
                else:
                    result = client.configure(connection, parameters, state=state, answer=answer)
                for _ in range(8):
                    option = result.get("Option")
                    if result.get("Error") or not result.get("State"):
                        break
                    if option is None:
                        next_answer = ""
                    elif (connection.provider in OAUTH_PROVIDERS and isinstance(option, dict)
                            and option.get("Name") == "config_is_local"
                            and not option.get("IsPassword") and option.get("Default") is True):
                        next_answer = "true"
                    else:
                        break
                    if cancel_event.is_set():
                        raise CloudSyncError("Account operation cancelled.")
                    result = client.configure(connection, parameters, state=result["State"], answer=next_answer)
                else:
                    raise CloudSyncError("Account setup repeated an unexpected step. Cancel and sign in again.")
                if result.get("Error") and result.get("State") and result.get("Option") is None:
                    return {"connection": connection, "question": self._setup_retry(connection, result)}
                if result.get("State") or result.get("Option"):
                    if not result.get("State") or not isinstance(result.get("Option"), dict) or not result["Option"]:
                        raise CloudSyncError("The provider returned an incomplete account setup step. Cancel and sign in again.")
                    question = {"State": result.get("State", ""), "Option": result.get("Option"),
                                "Error": "The provider rejected that answer. Check it and retry." if result.get("Error") else ""}
                    return {"connection": connection, "question": question}
                if result.get("Error"):
                    raise CloudSyncError("The provider could not finish account authorization. Check the requested values and retry.")
                if self._choose_root:
                    return {"connection": connection, "choose_root": True}
                self._verify_root(client, connection, create_root)
                return {"connection": connection, "question": None}
        self._submit("configure", configure)

    def _provider_connected(self, connection):
        return connection.provider != "local" and any(
            item.provider == connection.provider for item in self.config_service.get_app_config().connections)

    @staticmethod
    def _setup_retry(connection, result):
        state = result["State"]
        message = "Account setup could not continue. Retry to return to the setup choices, or cancel and sign in again."
        if connection.provider == "onedrive":
            error = str(result["Error"]).casefold()
            if "no accessible compatible drives" in error:
                message = "No accessible, compatible OneDrive storage was found. Check access in your browser, then retry or sign in with another account."
            elif "failed to query available drives" in error:
                message = ("Microsoft could not list your OneDrive storage. Retry to load your drives again. "
                           "If this continues, open OneDrive in your browser with the same account and check access.")
                if state == "driveid":
                    state = "onedrive"
            elif "no drives found" in error:
                message = ("Microsoft did not find OneDrive storage for this account. Open OneDrive in your browser "
                           "to check that it is set up, then retry or sign in with another account.")
            elif "failed to query root for drive" in error:
                message = "Microsoft could not open the selected drive. Retry to choose another drive or cancel and sign in again."
        return {"State": state, "Option": None, "Error": message}

    @staticmethod
    def _verify_root(client, connection, create_root):
        if connection.provider == "local" and create_root:
            root = validate_local_path(connection.root)
            # Only the managed child of an existing, user-selected parent.
            if root.name == "EverySync" and root.parent.is_dir():
                root.mkdir(exist_ok=True)
        try:
            client.test(connection)
        except CloudNotFound:
            parent = connection.root.rpartition("/")[0]
            managed = connection.root.endswith("/EverySync") or (connection.provider == "sftp" and connection.root == "EverySync")
            if not create_root or (connection.provider not in {"onedrive", "drive", "dropbox", "webdav"} and not managed):
                raise
            if managed and parent:
                # Test the existing parent first: mkdir must not create a bucket,
                # container or an unavailable/mistyped storage hierarchy.
                client.test(replace(connection, root=parent))
            client.operation("operations/mkdir", {"fs": f"es_{connection.id}:", "remote": connection.root})
            client.test(connection)

    def list_account_folders(self, path=""):
        self.ensure_idle()
        if not self._authorized or self._pending_connection is None:
            raise ValueError("Sign in before choosing a cloud folder.")
        path = validate_relative_path(path, allow_empty=True)
        connection = self._pending_connection
        def folders(cancel_event):
            with self.transport_factory(self.config_service.cloud_root, cancel_event=cancel_event) as client:
                return {"path": path, "folders": client.folders(connection, path)}
        self._submit("folders", folders)

    def choose_connection_root(self, root, *, create_root=False):
        self.ensure_idle()
        if not self._authorized or self._pending_connection is None:
            raise ValueError("Sign in before choosing a cloud folder.")
        connection = replace(self._pending_connection, root=root)
        def save_root(cancel_event):
            with self.transport_factory(self.config_service.cloud_root, cancel_event=cancel_event) as client:
                self._verify_root(client, connection, create_root)
            return {"connection": connection}
        self._submit("save_root", save_root)

    def test_connection(self, connection):
        def test(cancel_event):
            with self.transport_factory(self.config_service.cloud_root, cancel_event=cancel_event) as client:
                client.test(connection)
                identity = self._read_account_identity(client, connection)
            return {"connection_id": connection.id, "identity": identity}
        self._submit("test", test)

    def authorize_account_identity(self, connection):
        if (connection.provider != "onedrive"
                or connection not in self.config_service.get_app_config().connections):
            raise ValueError("Select a saved Microsoft connection first.")
        def authorize(cancel_event):
            with self.transport_factory(self.config_service.cloud_root, cancel_event=cancel_event) as client:
                details = normalize_account_identity(client.authorize_account_identity(connection))
            if not details:
                raise CloudSyncError("Microsoft account details are unavailable. Retry sign-in and allow profile access.")
            return {"connection_id": connection.id, "identity": dict(details, status="available")}
        self._submit("authorize_account", authorize)

    @staticmethod
    def _read_account_identity(client, connection):
        if connection.provider not in OAUTH_PROVIDERS:
            return {"status": "unsupported"}
        try:
            details = normalize_account_identity(client.account_info(connection))
        except CloudSyncError:
            details = {}
        return dict(details, status="available" if details else "unavailable")

    def refresh_account_identities(self, *, force=False):
        if self._identity_shutdown:
            return False
        config = self.config_service.get_app_config()
        current = {c.id for c in config.connections}
        self.account_identities = {key: value for key, value in self.account_identities.items() if key in current}
        connections = [c for c in config.connections if c.provider in OAUTH_PROVIDERS
                       and (force or c.id not in self.account_identities)]
        if not connections:
            return False
        def accounts(cancel_event):
            result = {}
            for connection in connections:
                if cancel_event.is_set():
                    break
                try:
                    with self.transport_factory(self.config_service.cloud_root, cancel_event=cancel_event) as client:
                        result[connection.id] = self._read_account_identity(client, connection)
                except CloudSyncError:
                    result[connection.id] = {"status": "unavailable"}
            return result
        self._submit("accounts", accounts)
        self._task.identity_ids = [c.id for c in connections]
        return True

    def remove_connection(self, connection_id):
        self.ensure_idle()
        config = self.config_service.get_app_config()
        if any(job.connection_id == connection_id for job in config.remote_jobs):
            raise ValueError("Remove the jobs using this connection before disconnecting it.")
        connection = next((item for item in config.connections if item.id == connection_id), None)
        if connection is None:
            raise ValueError("Select a connection first.")
        def remove(cancel_event):
            if connection.provider != "local":
                with self.transport_factory(self.config_service.cloud_root, cancel_event=cancel_event) as client:
                    client.call("config/delete", {"name": "es_" + connection_id})
            return connection_id
        self._submit("remove", remove)

    def list_snapshots(self, job_id):
        self._submit("snapshots", lambda event: CloudSyncRunner(self.config_service.get_app_config(),
                     self.config_service.cloud_root, self.transport_factory).list_snapshots(job_id))

    def restore(self, job_id, run_id, target):
        self._submit("restore", lambda event: CloudSyncRunner(self.config_service.get_app_config(),
                     self.config_service.cloud_root, self.transport_factory).restore(job_id, run_id, target))

    def cancel(self):
        if self._task is not None and self.action in {"configure", "test", "snapshots", "folders", "save_root", "accounts", "authorize_account"}:
            self._task.cancel_event.set()
        elif self._task is None and self._pending_connection is not None:
            self._discard_pending("Account operation cancelled.")

    def wait_for_finished(self):
        self._identity_shutdown = True
        if (self._pending_connection is not None and self.sync_service is not None
                and self.sync_service.is_syncing):
            self.sync_service.wait_for_finished()
        self.cancel()
        while self._task is not None:
            task = self._task
            task.wait()
            self._completed(task)
