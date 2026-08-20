"""Paths to bundled static assets (icons, etc.) — one place so main.py,
MainWindow, and StartScreen all point at the same file."""
from __future__ import annotations

import os

_UI_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(_UI_DIR)
ICON_PATH = os.path.join(PROJECT_ROOT, "assets", "icon.png")
