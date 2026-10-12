import sys
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    # We don't want to run the event loop, just test creation
    window.destroy()
    app.quit()
    print("UI test passed")
