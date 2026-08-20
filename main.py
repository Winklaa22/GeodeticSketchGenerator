from __future__ import annotations

import sys

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from ui.assets import ICON_PATH
from ui.start_screen import StartScreen


def _set_windows_taskbar_identity() -> None:
    """Without this, Windows groups the app under the generic Python icon
    in the taskbar instead of its own — a well-known PyQt-on-Windows quirk,
    harmless (and skipped) on any other platform."""
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
