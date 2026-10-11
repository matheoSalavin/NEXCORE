import sys

from PySide6.QtWidgets import QApplication
from ui.main_window import Nexcore


def main():
    app = QApplication(sys.argv)

    window = Nexcore()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()