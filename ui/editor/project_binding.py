from __future__ import annotations

from typing import Optional

from core.project import (
    DelimiterState,
    LayerDefState,
    LayerState,
    LayoutState,
    ProjectState,
    TableTemplateState,
)
from ui.editor.fonts_panel import FontsPanel
from ui.editor.mode_registry import MODE_SPECS, options_from_state, state_from_tab
from ui.editor.sections_panel import SectionsPanel


def collect_project_state(
    panel: SectionsPanel,
    fonts_panel: FontsPanel,
    *,
    name: str,
    txt_file_path: str,
    dxf_file_path: str,
    dxf_content: Optional[str],
    layout: LayoutState,
    table_template: TableTemplateState,
) -> ProjectState:
    layers, default_name = panel.layer_tab.get_state()
    font_id, font_italic, font_lineweight_mm = fonts_panel.get_state()
    mode_states = {
        spec.state_field: state_from_tab(spec, panel.mode_tabs[spec.key]) for spec in MODE_SPECS
    }
    return ProjectState(
        name=name,
        txt_file_path=txt_file_path,
        dxf_file_path=dxf_file_path,
        dxf_content=dxf_content,
        draw_modes=panel.draw_tab.mode_keys,
        delimiter=DelimiterState(
            mode=panel.delimiter_tab.gap_key,
            swap_xy=panel.delimiter_tab.swap_xy_enabled,
        ),
        layer=LayerState(
            layers=[LayerDefState(name=layer_name, rgb=rgb) for layer_name, rgb in layers],
            default_name=default_name,
        ),
        layout=layout,
        table_template=table_template,
        default_font_id=font_id,
        default_font_italic=font_italic,
        default_font_lineweight_mm=font_lineweight_mm,
        **mode_states,
    )


def apply_project_state(panel: SectionsPanel, fonts_panel: FontsPanel, state: ProjectState) -> None:
    panel.delimiter_tab.set_state(state.delimiter.mode, state.delimiter.swap_xy)
    panel.draw_tab.set_mode_keys(state.draw_modes)
    panel.layer_tab.set_state(
        [(layer.name, tuple(layer.rgb)) for layer in state.layer.layers], state.layer.default_name
    )
    panel.sync_layer_dropdowns()
    fonts_panel.set_state(state.default_font_id, state.default_font_italic, state.default_font_lineweight_mm)
    for spec in MODE_SPECS:
        mode_state = getattr(state, spec.state_field)
        tab = panel.mode_tabs[spec.key]
        tab.set_options(options_from_state(spec, mode_state))
        tab.set_layer_name(mode_state.layer_name)
        tab.set_selection_state(mode_state.selection)
