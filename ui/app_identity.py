from __future__ import annotations

from PyQt6.QtCore import QSettings

APP_TITLE = "Geodetic Sketch Generator"
SETTINGS_ORG = "acsg"
SETTINGS_APP = "acsg_pro"


def app_settings() -> QSettings:
    return QSettings(SETTINGS_ORG, SETTINGS_APP)
