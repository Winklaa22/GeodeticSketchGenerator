from __future__ import annotations

import os

_THEME_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(_THEME_DIR))
ICON_PATH = os.path.join(PROJECT_ROOT, "assets", "icon.png")
