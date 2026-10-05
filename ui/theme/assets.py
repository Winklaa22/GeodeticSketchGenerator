from __future__ import annotations

import os

_THEME_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(_THEME_DIR))
ICON_PATH = os.path.join(PROJECT_ROOT, "assets", "icon.png")
# The blocks the app ships with - one DXF file per block, see core/blocks.py.
BLOCKS_DIR = os.path.join(PROJECT_ROOT, "assets", "blocks")
