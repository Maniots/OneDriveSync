from uuid import uuid4

from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtCore import QIODevice
from ui.app import connect_activation_server


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
        socket.connectToServer(name, QIODevice.OpenModeFlag.WriteOnly)
        assert socket.waitForConnected(500)
        socket.write(b"sh")
        assert socket.waitForBytesWritten(500)
        qapp.processEvents()
        qapp.processEvents()
        assert window.activations == 0
        socket.write(b"ow")
        assert socket.waitForBytesWritten(500)
        for _ in range(10):
            qapp.processEvents()
        assert window.activations == 1
    finally:
        socket.abort()
        server.close()
