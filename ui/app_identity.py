from __future__ import annotations

import os

from PyQt6.QtCore import QSettings, QStandardPaths

APP_TITLE = "Geodetic Sketch Generator"
SETTINGS_ORG = "acsg"
SETTINGS_APP = "acsg_pro"


def app_settings() -> QSettings:
    return QSettings(SETTINGS_ORG, SETTINGS_APP)


def user_blocks_dir() -> str:
    """Where blocks the user adds to the library are kept - outside the install, so they
    survive an update of the app."""
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)
    return os.path.join(base, SETTINGS_ORG, SETTINGS_APP, "blocks")
