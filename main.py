from __future__ import annotations

import os
import sys
import traceback
from types import TracebackType
from typing import Type

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from ui.start_screen import StartScreen
from ui.theme.assets import ICON_PATH
from ui.theme.icons import IconManager

icon_manager = IconManager()


def _set_windows_taskbar_identity() -> None:
    if sys.platform != "win32":
        return
    import ctypes

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("acsg.geodetic_sketch_generator")
    except (AttributeError, OSError):
        pass


def _disable_linux_native_theme_integration() -> None:
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORMTHEME", "generic")


def _install_crash_handler(app: QApplication) -> None:
    def handle_exception(
        exc_type: Type[BaseException], exc_value: BaseException, exc_tb: TracebackType
    ) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            app.quit()
            return
        details = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        try:
            sys.stderr.write(details)
        except (AttributeError, OSError):
            pass
        summary = f"{exc_type.__name__}: {exc_value}" if str(exc_value) else exc_type.__name__

        from ui.crash_dialog import CrashDialog

        dialog = CrashDialog(summary, details, app.activeWindow())
        dialog.exec()
        os._exit(1)

    sys.excepthook = handle_exception


def main() -> int:
    _set_windows_taskbar_identity()
    _disable_linux_native_theme_integration()
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(ICON_PATH))
    _install_crash_handler(app)
    window = StartScreen()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
