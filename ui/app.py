from PySide6.QtWidgets import QApplication
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtCore import QIODevice, Qt
from .main_window import MainWindow
from .themes.theme import get_dark_theme
import sys
import os

# Windows mutex for single instance enforcement
if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    ERROR_ALREADY_EXISTS = 180

    def create_ui_mutex(name: str) -> tuple[int, int]:
        """Create a named mutex for UI single instance.
        Returns (handle, last_error)."""
        handle = kernel32.CreateMutexW(
            None,  # default security attributes
            False,  # initially not owned
            name
        )
        if not handle:
            return 0, ctypes.get_last_error()
        return handle, ctypes.get_last_error()

    def release_ui_mutex(handle: int) -> None:
        if handle:
            kernel32.ReleaseMutex(handle)
            kernel32.CloseHandle(handle)


def send_show_message() -> None:
    """Send a 'show' message to the running UI instance via local socket."""
    socket = QLocalSocket()
    socket.connectToServer("OneDrivePCSyncUIInstance")
    if socket.waitForConnected(500):
        if socket.state() == QLocalSocket.ConnectedState:
            socket.write(b"show")
            socket.waitForBytesWritten()
        socket.disconnectFromServer()


def main() -> None:
    # Skip single instance check in headless/offscreen mode (e.g., for testing)
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        print("[UI Single Instance] Skipping single instance check (offscreen mode).")
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        app.setStyleSheet(get_dark_theme())
        window = MainWindow()
        window.show()
        sys.exit(app.exec())
        return

    # --- UI Single Instance Enforcement ---
    mutex_name = "Global\\OneDrivePCSyncUIMutex"
    if sys.platform == "win32":
        mutex_handle, last_error = create_ui_mutex(mutex_name)
        if last_error == ERROR_ALREADY_EXISTS:
            # Another instance is running, show it and exit
            print(f"[UI Single Instance] Another instance is running (error {last_error}). Sending show message.")
            send_show_message()
            sys.exit(0)
        print(f"[UI Single Instance] We are the first instance (mutex handle {mutex_handle}).")
        # We own the mutex; keep the handle alive for the lifetime of the application
        # (we'll store it in a global variable to prevent garbage collection)
        global _ui_mutex_handle
        _ui_mutex_handle = mutex_handle
    else:
        # On non-Windows, we fall back to the Qt local socket method (not expected in this project)
        socket = QLocalSocket()
        socket.connectToServer("OneDrivePCSyncUIInstance")
        if socket.waitForConnected(500):
            print("[UI Single Instance] Another instance is running (socket connected). Sending show message.")
            send_show_message()
            sys.exit(0)
        socket.disconnectFromServer()
        print("[UI Single Instance] We are the first instance (socket not connected).")
        # We are the first instance; set up a server to listen for show messages
        server = QLocalServer()
        if not server.listen("OneDrivePCSyncUIInstance"):
            # Should not happen, but if it does, we continue anyway
            print("[UI Single Instance] Failed to listen for show messages.")
        # Keep the server reference to prevent garbage collection
        global _ui_server
        _ui_server = server

    # --- Normal Application Startup ---
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    # Apply the dark theme stylesheet
    app.setStyleSheet(get_dark_theme())

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()