from PySide6.QtWidgets import QApplication
from .main_window import MainWindow
from .themes.theme import get_dark_theme
import sys


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(get_dark_theme())
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()