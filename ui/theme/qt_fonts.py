from __future__ import annotations

from PyQt6.QtGui import QFont

from core.fonts import font_spec


def apply_font_family(font: QFont, font_id: str) -> QFont:
    # fallback_families is an ordered list of real family names, so Qt walks it and picks
    # the first one installed - the same substitution idea core/fonts.py applies to ezdxf.
    families = list(font_spec(font_id).fallback_families)
    if families:
        font.setFamilies(families)
    return font


def font_for(font_id: str, *, bold: bool = False, italic: bool = False) -> QFont:
    font = QFont()
    apply_font_family(font, font_id)
    font.setBold(bold)
    font.setItalic(italic)
    return font
