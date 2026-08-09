import os
import sys
from PySide6.QtNetwork import QLocalServer
from PySide6.QtCore import QCoreApplication

app = QCoreApplication.instance()
if app is None:
    app = QCoreApplication(sys.argv)

server = QLocalServer()
if server.listen("OneDrivePCSyncUIInstance"):
    print("Successfully listened on OneDrivePCSyncUIInstance")
    # Close the server
    server.close()
    print("Server closed")
else:
    print("Failed to listen on OneDrivePCSyncUIInstance")
    print(f"Error: {server.error()}")
    print(f"Error string: {server.errorString()}")