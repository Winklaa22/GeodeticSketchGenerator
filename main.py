from __future__ import annotations

import sys

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from ui.assets import ICON_PATH
from ui.start_screen import StartScreen


def _set_windows_taskbar_identity() -> None:
    if sys.platform != "win32":
        return
    import ctypes

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("acsg.geodetic_sketch_generator")
    except (AttributeError, OSError):
        pass


def main() -> int:
    _set_windows_taskbar_identity()
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(ICON_PATH))
    window = StartScreen()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
