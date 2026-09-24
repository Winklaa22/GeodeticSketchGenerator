from __future__ import annotations

from typing import Optional

import qtawesome as qta
from PyQt6.QtGui import QIcon

from ui.theme.tokens import Color, ICON_MD

class IconManager:

    _GLYPHS: dict[str, str] = {
        "layer": "fa5s.layer-group",
        "layer_add": "mdi.layers-plus",
        "layer_remove": "mdi.layers-off",
        "point": "msc.debug-breakpoint-disabled",
        "new_dfx_file_icon": "ei.file-new",
        "change_dxf_file_icon": "ei.file-edit",
        "txt_file_icon": "fa5s.file-alt",
        "arrow_right": "fa5s.arrow-right",

        "select_tool": "mdi.cursor-default-outline",
        "point_tool": "fa5s.dot-circle",
        "text_tool": "mdi.format-text-variant",
        "text_on_line_tool": "mdi.format-text-rotation-angle-up",
        "line_tool": "mdi.vector-line",
        "circle_tool": "mdi.vector-circle",
        "pipe_tool": "mdi.pipe",
        "multileader_tool": "mdi.call-split",
        "detail_tool": "mdi.magnify-scan",
        "detail_edit": "mdi.pencil-outline",
        "move_tool": "fa5s.arrows-alt",
        "rotate_tool": "mdi.rotate-right",
        "scale_tool": "mdi.resize-bottom-right",
        "rotate_each_tool": "mdi.rotate-orbit",
        "scale_each_tool": "mdi.resize",
        "select_similar_tool": "mdi.auto-fix",
        "erase_tool": "fa5s.eraser",
        "zoom_extents_tool": "mdi.arrow-expand-all",
        "zoom_in_tool": "fa5s.search-plus",
        "zoom_out_tool": "fa5s.search-minus",

        "point_file_section": "mdi.file-document-outline",
        "drawing_mode_section": "fa5s.pencil-alt",
        "layer_section": "fa5s.layer-group",
        "points_section": "mdi.vector-point",
        "lines_section": "mdi.vector-line",
        "plines_section": "mdi.vector-polyline",
        "poly3d_section": "mdi.axis-arrow",
        "heights_section": "mdi.altimeter",
        "cable_marks_section": "mdi.cable-data",
        "pipe_section": "mdi.pipe",
        "measurements_section": "mdi.ruler",
        "selection_section": "mdi.selection",
        "sheets_section": "mdi.file-multiple-outline",
        "page_setup_section": "mdi.page-layout-body",
        "table_section": "mdi.table",
        "font_section": "mdi.format-font",
        "language_section": "mdi.translate",
        "sheet_add": "fa5s.plus",

        "checkbox_checked": "fa5s.check-square",
        "checkbox_unchecked": "fa5.square",
        "radio_checked": "mdi.radiobox-marked",
        "radio_unchecked": "mdi.radiobox-blank",

        "chevron_expanded": "fa5s.chevron-up",
        "chevron_collapsed": "fa5s.chevron-down",
        "modified_dot": "fa5s.circle",

        "menu_chevron": "fa5s.chevron-down",

        "layer_active": "fa5s.circle",
        "layer_inactive": "mdi.circle-outline",
        "layer_row_delete": "fa5s.times",
        "prune_layers": "fa5s.broom",

        "dxf_icon": "mdi.hexagon-outline",
        "dxf_source_clear": "fa5s.times",

        "warning_icon": "fa5s.exclamation-triangle",

        "new_project_icon": "fa5s.plus",

        "loading": "mdi.loading",
    }

    def __init__ (self) -> None:
        self._cache: dict[tuple[str, int, str], QIcon] = {}

    def get(
        self,
        name: str,
        size: int = ICON_MD,
        color: str = Color.TEXT_MUTED,
        animation: Optional[object] = None,
    ) -> QIcon:
        glyph = self._GLYPHS.get(name)

        # An animation is bound to one specific widget, so an animated icon must never be
        # shared through the cache.
        if animation is not None:
            return qta.icon(glyph, color=color, animation=animation) if glyph else QIcon()

        key = (name, size, color)
        cashed = self._cache.get(key)
        if cashed is not None:
            return cashed

        if glyph is None:
            icon = QIcon()
        else:
            icon = qta.icon(glyph, color=color)

        self._cache[key] = icon
        return icon

icon_manager = IconManager()
