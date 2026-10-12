import os
import sys
from PySide6.QtNetwork import QLocalSocket
from PySide6.QtCore import QCoreApplication

app = QCoreApplication.instance()
if app is None:
    app = QCoreApplication(sys.argv)

socket = QLocalSocket()
socket.connectToServer("OneDrivePCSyncUIInstance")
if socket.waitForConnected(1000):
    print("Connected to server")
    # Try to send a message
    socket.write(b"show")
    socket.waitForBytesWritten()
    # Wait for a response? We don't have a response protocol, so just read if there is anything
    if socket.waitForReadyRead(1000):
        data = socket.readAll()
        print(f"Received: {data}")
    else:
        print("No response received")
    socket.disconnectFromServer()
else:
    print("Failed to connect to server")
    error = socket.error()
    print(f"Error: {error}")
    print(f"Error string: {socket.errorString()}")