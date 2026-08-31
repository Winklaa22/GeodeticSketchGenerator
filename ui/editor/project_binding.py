from __future__ import annotations

from typing import Optional

from core.project import (
    DelimiterState,
    LayerDefState,
    LayerState,
    ProjectState,
    SelectionState,
)
from ui.editor.mode_registry import MODE_SPECS, options_from_state, state_from_tab
from ui.editor.sections_panel import SectionsPanel


def collect_project_state(
    panel: SectionsPanel,
    *,
    name: str,
    txt_file_path: str,
    dxf_file_path: str,
    dxf_content: Optional[str],
) -> ProjectState:
    separate_text, range_text = panel.selection_tab.get_expression_state()
    layers, default_name = panel.layer_tab.get_state()
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
        selection=SelectionState(
            mode=panel.selection_tab.mode_key, separate_text=separate_text, range_text=range_text
        ),
        layer=LayerState(
            layers=[LayerDefState(name=layer_name, rgb=rgb) for layer_name, rgb in layers],
            default_name=default_name,
        ),
        **mode_states,
    )


def apply_project_state(panel: SectionsPanel, state: ProjectState) -> None:
    panel.delimiter_tab.set_state(state.delimiter.mode, state.delimiter.swap_xy)
    panel.draw_tab.set_mode_keys(state.draw_modes)
    panel.layer_tab.set_state(
        [(layer.name, tuple(layer.rgb)) for layer in state.layer.layers], state.layer.default_name
    )
    panel.sync_layer_dropdowns()
    for spec in MODE_SPECS:
        mode_state = getattr(state, spec.state_field)
        tab = panel.mode_tabs[spec.key]
        tab.set_options(options_from_state(spec, mode_state))
        tab.set_layer_name(mode_state.layer_name)
    panel.selection_tab.set_state(
        state.selection.mode, state.selection.separate_text, state.selection.range_text
    )
