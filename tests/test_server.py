import time
from uuid import uuid4

from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtCore import QIODevice
from ui.app import _write_socket_message, connect_activation_server


def wait_until(app, condition, socket, seconds=3):
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.001)
    assert condition(), socket.errorString()


def test_local_server_activates_existing_window(qapp):
    class Window:
        activations = 0

        def show_and_activate(self):
            self.activations += 1

    server = QLocalServer()
    name = f"OneDrivePCSyncTest-{uuid4().hex}"
    assert server.listen(name), server.errorString()
    window = Window()
    connect_activation_server(server, window)
    socket = QLocalSocket()
    try:
        socket.connectToServer(name, QIODevice.OpenModeFlag.ReadWrite)
        wait_until(qapp, lambda: socket.state() == QLocalSocket.LocalSocketState.ConnectedState, socket)
        assert _write_socket_message(socket, b"sh"), socket.errorString()
        wait_until(qapp, lambda: bool(server.findChildren(QLocalSocket)) and
                   all(s.bytesAvailable() == 0 for s in server.findChildren(QLocalSocket)), socket)
        assert window.activations == 0
        assert _write_socket_message(socket, b"ow"), socket.errorString()
        wait_until(qapp, lambda: window.activations == 1, socket)
    finally:
        socket.abort()
        server.close()
        server.deleteLater()
        socket.deleteLater()


def test_socket_message_accepts_immediate_write():
    class ImmediateSocket:
        def write(self, message):
            return len(message)

        def bytesToWrite(self):
            return 0

        def waitForBytesWritten(self, timeout):
            raise AssertionError("An already completed write must not wait again")

    assert _write_socket_message(ImmediateSocket(), b"show")


def test_socket_message_rejects_unflushed_write():
    class BlockedSocket:
        def write(self, message):
            return len(message)

        def bytesToWrite(self):
            return 4

        def waitForBytesWritten(self, timeout):
            return False

    assert not _write_socket_message(BlockedSocket(), b"show")
