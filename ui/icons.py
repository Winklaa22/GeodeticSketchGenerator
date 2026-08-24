from __future__ import annotations
from os import name

import qtawesome as qta
from PyQt6.QtGui import QIcon

from .theme import Color, ICON_MD

class IconManager:

    _GLYPHS: dict[str, str] = {
        "layer": "fa5s.layer-group",
    }

    def __init__ (self) -> None:
        self._cache: dict[tuple[str, int, str], QIcon] = {}

    def get(self, name: str, size: int = ICON_MD, color: str = Color.TEXT_MUTED) -> QIcon:
        key = (name, size, color)
        cashed = self._cache.get(key)
        if cashed is not None:
            return cashed

        glyph = self._GLYPHS.get(name)

        if glyph is None:
            icon = QIcon()
        else:
            icon = qta.icon(glyph, color=color)

        self._cache[key] = icon
        return icon

icon_manager = IconManager()
        