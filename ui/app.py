"""Desktop UI entry point and single-instance activation."""

import argparse
import os
import sys
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QIODevice
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from backend.services.configuration_service import ConfigurationService
from .main_window import MainWindow
from .themes.theme import get_dark_theme

SERVER_NAME = "OneDrivePCSyncUIInstance"

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    ERROR_ALREADY_EXISTS = 183

    def create_ui_mutex(name: str) -> tuple[int, int]:
        handle = kernel32.CreateMutexW(None, False, name)
        return handle or 0, ctypes.get_last_error()

    def release_ui_mutex(handle: int) -> None:
        # Created without ownership: CloseHandle releases our reference.
        if handle:
            kernel32.CloseHandle(handle)


def _write_socket_message(socket: QLocalSocket, message: bytes, timeout_ms: int = 500) -> bool:
    """Handle immediate writes as well as buffered writes on Windows pipes."""
    if socket.write(message) != len(message):
        return False
    timer = QElapsedTimer()
    timer.start()
    while socket.bytesToWrite() > 0:
        remaining = timeout_ms - timer.elapsed()
        if remaining <= 0:
            return False
        if not socket.waitForBytesWritten(remaining):
            return socket.bytesToWrite() == 0
    return True


def send_show_message(server_name: str = SERVER_NAME) -> bool:
    socket = QLocalSocket()
    socket.connectToServer(server_name, QIODevice.OpenModeFlag.ReadWrite)
    if socket.state() != QLocalSocket.LocalSocketState.ConnectedState and not socket.waitForConnected(500):
        return False
    sent = _write_socket_message(socket, b"show")
    socket.disconnectFromServer()
    return sent


def connect_activation_server(server: QLocalServer, window: MainWindow) -> None:
    """Retain sockets until their message is read, then activate the window."""
    def on_connection():
        while server.hasPendingConnections():
            socket = server.nextPendingConnection()

            def on_ready(s=socket, message=bytearray()):
                message.extend(bytes(s.readAll()))
                if len(message) >= 4:
                    if message == b"show":
                        window.show_and_activate()
                    s.disconnectFromServer()

            socket.readyRead.connect(on_ready)
            socket.disconnected.connect(socket.deleteLater)
            if socket.bytesAvailable():
                on_ready()

    server.newConnection.connect(on_connection)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="OneDrive PC Sync UI")
    parser.add_argument("--config", type=Path, help="Configuration file (defaults to application config.json)")
    args, qt_args = parser.parse_known_args(argv)
    app = QApplication.instance() or QApplication([sys.argv[0], *qt_args])
    app.setStyleSheet(get_dark_theme())
    offscreen = os.environ.get("QT_QPA_PLATFORM") == "offscreen"
    mutex_handle = 0
    server = None
    try:
        if not offscreen:
            if sys.platform == "win32":
                mutex_handle, last_error = create_ui_mutex("Global\\OneDrivePCSyncUIMutex")
                if not mutex_handle:
                    raise OSError(last_error, "Cannot acquire UI mutex")
                if last_error == ERROR_ALREADY_EXISTS:
                    # The first process may still be initializing its server.
                    send_show_message()
                    return 0
            elif send_show_message():
                return 0
            server = QLocalServer(app)
            if not server.listen(SERVER_NAME):
                # Remove a stale endpoint only after verifying no process answers.
                if send_show_message():
                    return 0
                QLocalServer.removeServer(SERVER_NAME)
                if not server.listen(SERVER_NAME):
                    raise RuntimeError(server.errorString())

        window = MainWindow(configuration_service=ConfigurationService(args.config))
        if server is not None:
            connect_activation_server(server, window)
        window.show()
        return app.exec()
    finally:
        if server is not None:
            server.close()
            server.deleteLater()
        if mutex_handle and sys.platform == "win32":
            release_ui_mutex(mutex_handle)


if __name__ == "__main__":
    raise SystemExit(main())
