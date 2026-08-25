from __future__ import annotations
from os import name

import qtawesome as qta
from PyQt6.QtGui import QIcon

from .theme import Color, ICON_MD

class IconManager:

    _GLYPHS: dict[str, str] = {
        "layer": "fa5s.layer-group",
        "layer_add": "mdi.layers-plus",  # was "fa5s.layer-plus" - not a real fa5s glyph, qta.icon() raised on it
        "layer_remove": "mdi.layers-off",
        "point": "msc.debug-breakpoint-disabled",
        "new_dfx_file_icon": "ei.file-new",
        "change_dxf_file_icon": "ei.file-edit",
        "txt_file_icon": "fa5s.file-alt",
        "arrow_right": "fa5s.arrow-right",

        #dxf edit tools icons (ui/dxf_viewer.py DxfToolbar)
        "select_tool": "mdi.cursor-default-outline",
        "point_tool": "fa5s.dot-circle",
        "text_tool": "mdi.format-text-variant",
        "line_tool": "mdi.vector-line",
        "circle_tool": "mdi.vector-circle",
        "pipe_tool": "mdi.pipe",
        "move_tool": "fa5s.arrows-alt",
        "rotate_tool": "mdi.rotate-right",
        "scale_tool": "mdi.resize-bottom-right",
        "erase_tool": "fa5s.eraser",
        "zoom_extents_tool": "mdi.arrow-expand-all",
        "zoom_in_tool": "fa5s.search-plus",
        "zoom_out_tool": "fa5s.search-minus",

        #left-column accordion section icons (ui/main_window.py _build_left_column specs)
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
        "selection_section": "mdi.selection",

        #checkbox / radio-card bullets (ui/widgets.py CheckField, RadioCardGroup)
        "checkbox_checked": "fa5s.check-square",
        "checkbox_unchecked": "fa5.square",
        "radio_checked": "mdi.radiobox-marked",
        "radio_unchecked": "mdi.radiobox-blank",

        #accordion header chrome (ui/widgets.py AccordionSection)
        "chevron_expanded": "fa5s.chevron-up",
        "chevron_collapsed": "fa5s.chevron-down",
        "modified_dot": "fa5s.circle",

        #top-bar "File ▾" / "Edit ▾" menu buttons (ui/main_window.py)
        "menu_chevron": "fa5s.chevron-down",

        #layer rows (ui/layer_panel.py _LayerRow + ui/tabs/layer_tab.py, same layout twice)
        "layer_active": "fa5s.circle",
        "layer_inactive": "mdi.circle-outline",
        "layer_row_delete": "fa5s.times",
        "prune_layers": "fa5s.broom",

        #dxf source row + empty-state canvas (ui/widgets.py DxfSourceRow, ui/dxf_viewer.py DxfViewer)
        "dxf_icon": "mdi.hexagon-outline",
        "dxf_source_clear": "fa5s.times",

        #error banner (ui/widgets.py ErrorBanner)
        "warning_icon": "fa5s.exclamation-triangle",

        #start screen (ui/start_screen.py)
        "new_project_icon": "fa5s.plus",
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
        