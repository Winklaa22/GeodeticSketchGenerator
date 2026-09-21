from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, List, Optional, Tuple

from core.exceptions import ProjectFileError
from core.fonts import DEFAULT_FONT_ID
from core.plot import PlotOptions
from core.table_template import CellDef, ColumnDef, FieldDef, RowDef, TableTemplate, default_template

PROJECT_FILE_EXTENSION = ".gsgproj"
PROJECT_FILE_FILTER = "Geodetic Sketch Project (*.gsgproj)"
_FORMAT_VERSION = 1

TABLE_TEMPLATE_FILE_EXTENSION = ".gsgtable"
TABLE_TEMPLATE_FILE_FILTER = "Table Template (*.gsgtable)"
_TEMPLATE_FORMAT_VERSION = 1

DEFAULT_LAYER_RGB: Tuple[int, int, int] = (145, 132, 217)


@dataclass
class DelimiterState:
    mode: str = "auto"
    swap_xy: bool = True
    cabinet_mode: bool = False


@dataclass
class PointsState:
    numbers_enabled: bool = False
    font_size: float = 0.6
    cabinet_font_size_enabled: bool = False
    cabinet_font_size: float = 0.6
    diameter: float = 0.05
    layer_name: str = ""


@dataclass
class HeightsState:
    font_size: float = 0.6
    frequency: int = 5
    layer_name: str = ""


@dataclass
class CableState:
    font_size: float = 0.6
    frequency: int = 5
    marks_text: str = "eN"
    layer_name: str = ""


@dataclass
class PipeState:
    width: float = 0.16
    layer_name: str = ""


@dataclass
class LayerOnlyState:

    layer_name: str = ""


@dataclass
class MeasurementsState:
    font_size: float = 0.6
    offset: float = 0.3
    layer_name: str = ""


_DEFAULT_PLOT = PlotOptions()


@dataclass
class SheetState:
    name: str = "Sheet 1"
    page_key: str = _DEFAULT_PLOT.page_key
    landscape: bool = _DEFAULT_PLOT.landscape
    scale_mode: str = _DEFAULT_PLOT.scale_mode
    scale_denominator: int = _DEFAULT_PLOT.scale_denominator
    margin_mm: float = _DEFAULT_PLOT.margin_mm
    color_mode: str = _DEFAULT_PLOT.color_mode
    min_lineweight_mm: float = _DEFAULT_PLOT.min_lineweight_mm
    center_x: Optional[float] = None
    center_y: Optional[float] = None
    rotation: float = 0.0
    field_values: Dict[str, str] = field(default_factory=dict)


@dataclass
class LayoutState:

    sheets: List[SheetState] = field(default_factory=lambda: [SheetState()])
    active_index: Optional[int] = None
    # How far the Model tab's view is turned, zoomed and panned. Sheets keep their own
    # rotation/centre on the sheet itself; the model view has no sheet to hang these on,
    # so they live here. model_zoom is relative to the fit-to-drawing baseline (1.0 = the
    # fresh fit), which is what stays meaningful across window sizes and DPIs; the raw
    # zoomed-in transform would not be. model_center is None until the user has actually
    # panned/zoomed, so a project that never touched the Model view still opens fitted.
    model_rotation: float = 0.0
    model_zoom: float = 1.0
    model_center: Optional[Tuple[float, float]] = None


@dataclass
class SelectionState:
    mode: str = "all"
    separate_text: str = ""
    range_text: str = ""


@dataclass
class LayerDefState:
    name: str = "0"
    rgb: Tuple[int, int, int] = DEFAULT_LAYER_RGB


@dataclass
class LayerState:

    layers: List[LayerDefState] = field(default_factory=lambda: [LayerDefState()])
    default_name: str = "0"


@dataclass
class ColumnState:
    width_fraction: float = 0.25


@dataclass
class RowState:
    height_mm: float = 8.0


@dataclass
class CellDefState:
    row: int = 0
    col: int = 0
    row_span: int = 1
    col_span: int = 1
    kind: str = "static"
    label: str = ""
    field_name: str = ""
    show_label: bool = False
    align: str = "left"
    valign: str = "top"
    font_id: str = ""
    font_size: float = 2.4
    bold: bool = False
    italic: bool = False
    image_path: str = ""


@dataclass
class FieldDefState:
    name: str = ""
    label: str = ""
    scope: str = "sheet"
    blank_behavior: str = "hide"


def _cell_def_state(cell: CellDef) -> CellDefState:
    return CellDefState(
        row=cell.row, col=cell.col, row_span=cell.row_span, col_span=cell.col_span, kind=cell.kind,
        label=cell.label, field_name=cell.field_name, show_label=cell.show_label, align=cell.align,
        valign=cell.valign, font_id=cell.font_id, font_size=cell.font_size, bold=cell.bold,
        italic=cell.italic, image_path=cell.image_path,
    )


def _field_def_state(field_def: FieldDef) -> FieldDefState:
    return FieldDefState(
        name=field_def.name, label=field_def.label, scope=field_def.scope,
        blank_behavior=field_def.blank_behavior,
    )


_DEFAULT_TABLE_TEMPLATE = default_template()


@dataclass
class TableTemplateState:
    columns: List[ColumnState] = field(
        default_factory=lambda: [ColumnState(c.width_fraction) for c in _DEFAULT_TABLE_TEMPLATE.columns]
    )
    rows: List[RowState] = field(
        default_factory=lambda: [RowState(r.height_mm) for r in _DEFAULT_TABLE_TEMPLATE.rows]
    )
    cells: List[CellDefState] = field(
        default_factory=lambda: [_cell_def_state(c) for c in _DEFAULT_TABLE_TEMPLATE.cells]
    )
    fields: List[FieldDefState] = field(
        default_factory=lambda: [_field_def_state(f) for f in _DEFAULT_TABLE_TEMPLATE.fields]
    )
    project_field_values: Dict[str, str] = field(default_factory=dict)
    default_font_id: str = DEFAULT_FONT_ID


def state_from_template(template: TableTemplate) -> TableTemplateState:
    return TableTemplateState(
        columns=[ColumnState(c.width_fraction) for c in template.columns],
        rows=[RowState(r.height_mm) for r in template.rows],
        cells=[_cell_def_state(c) for c in template.cells],
        fields=[_field_def_state(f) for f in template.fields],
        project_field_values=dict(template.project_field_values),
        default_font_id=template.default_font_id,
    )


def template_from_state(state: TableTemplateState) -> TableTemplate:
    return TableTemplate(
        columns=[ColumnDef(c.width_fraction) for c in state.columns],
        rows=[RowDef(r.height_mm) for r in state.rows],
        cells=[
            CellDef(
                row=c.row, col=c.col, row_span=c.row_span, col_span=c.col_span, kind=c.kind,
                label=c.label, field_name=c.field_name, show_label=c.show_label, align=c.align,
                valign=c.valign, font_id=c.font_id, font_size=c.font_size, bold=c.bold,
                italic=c.italic, image_path=c.image_path,
            )
            for c in state.cells
        ],
        fields=[
            FieldDef(name=f.name, label=f.label, scope=f.scope, blank_behavior=f.blank_behavior)
            for f in state.fields
        ],
        project_field_values=dict(state.project_field_values),
        default_font_id=state.default_font_id,
    )


def table_template_state_from_payload(payload: Dict[str, Any]) -> TableTemplateState:
    default = TableTemplateState()
    columns_payload = payload.get("columns")
    rows_payload = payload.get("rows")
    cells_payload = payload.get("cells")
    fields_payload = payload.get("fields")
    columns = [ColumnState(**item) for item in columns_payload] if columns_payload is not None else default.columns
    rows = [RowState(**item) for item in rows_payload] if rows_payload is not None else default.rows
    cells = [CellDefState(**item) for item in cells_payload] if cells_payload is not None else default.cells
    fields = [FieldDefState(**item) for item in fields_payload] if fields_payload is not None else default.fields
    project_field_values = {str(k): str(v) for k, v in (payload.get("project_field_values") or {}).items()}
    return TableTemplateState(
        columns=columns, rows=rows, cells=cells, fields=fields,
        project_field_values=project_field_values,
        default_font_id=str(payload.get("default_font_id", default.default_font_id)),
    )


def table_template_payload(template: TableTemplate) -> Dict[str, Any]:
    state = state_from_template(template)
    return {
        "version": _TEMPLATE_FORMAT_VERSION,
        "columns": [asdict(c) for c in state.columns],
        "rows": [asdict(r) for r in state.rows],
        "cells": [asdict(c) for c in state.cells],
        "fields": [asdict(f) for f in state.fields],
        "default_font_id": state.default_font_id,
    }


def template_from_payload(payload: Dict[str, Any]) -> TableTemplate:
    if not isinstance(payload, dict):
        raise ProjectFileError("Not a valid table template: expected a JSON object.")
    try:
        state = table_template_state_from_payload(payload)
    except (TypeError, ValueError) as exc:
        raise ProjectFileError(f"Not a valid table template: {exc}") from exc
    return template_from_state(state)


def save_table_template_file(path: str, template: TableTemplate) -> None:
    payload = table_template_payload(template)
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
    except OSError as exc:
        raise ProjectFileError(f"Could not save table template: {exc}") from exc


def load_table_template_file(path: str) -> TableTemplate:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except OSError as exc:
        raise ProjectFileError(f"Could not read table template file: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ProjectFileError(f"Not a valid table template file: {exc}") from exc
    return template_from_payload(payload)


@dataclass
class ProjectState:

    name: str = "Untitled"
    txt_file_path: str = ""
    dxf_file_path: str = ""
    dxf_content: Optional[str] = None
    draw_modes: List[str] = field(default_factory=lambda: ["plines"])
    delimiter: DelimiterState = field(default_factory=DelimiterState)
    points: PointsState = field(default_factory=PointsState)
    lines: LayerOnlyState = field(default_factory=LayerOnlyState)
    plines: LayerOnlyState = field(default_factory=LayerOnlyState)
    poly3d: LayerOnlyState = field(default_factory=LayerOnlyState)
    heights: HeightsState = field(default_factory=HeightsState)
    cable: CableState = field(default_factory=CableState)
    pipe: PipeState = field(default_factory=PipeState)
    measurements: MeasurementsState = field(default_factory=MeasurementsState)
    selection: SelectionState = field(default_factory=SelectionState)
    layer: LayerState = field(default_factory=LayerState)
    layout: LayoutState = field(default_factory=LayoutState)
    table_template: TableTemplateState = field(default_factory=TableTemplateState)
    default_font_id: str = DEFAULT_FONT_ID
    default_font_italic: bool = False
    default_font_lineweight_mm: Optional[float] = None


def save_project(path: str, state: ProjectState) -> None:
    payload: Dict[str, Any] = {"version": _FORMAT_VERSION, **asdict(state)}
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
    except OSError as exc:
        raise ProjectFileError(f"Could not save project: {exc}") from exc


def load_project(path: str) -> ProjectState:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except OSError as exc:
        raise ProjectFileError(f"Could not read project file: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ProjectFileError(f"Not a valid project file: {exc}") from exc

    if not isinstance(payload, dict):
        raise ProjectFileError("Not a valid project file: expected a JSON object.")

    try:
        dxf_content = payload.get("dxf_content")
        draw_modes = payload.get("draw_modes")
        if draw_modes is None:
            draw_modes = [payload["draw_mode"]] if "draw_mode" in payload else ["plines"]
        return ProjectState(
            name=str(payload.get("name", "Untitled")),
            txt_file_path=str(payload.get("txt_file_path", "")),
            dxf_file_path=str(payload.get("dxf_file_path", "")),
            dxf_content=str(dxf_content) if dxf_content is not None else None,
            draw_modes=[str(mode) for mode in draw_modes] or ["plines"],
            delimiter=DelimiterState(**(payload.get("delimiter") or {})),
            points=PointsState(**(payload.get("points") or {})),
            lines=LayerOnlyState(**(payload.get("lines") or {})),
            plines=LayerOnlyState(**(payload.get("plines") or {})),
            poly3d=LayerOnlyState(**(payload.get("poly3d") or {})),
            heights=HeightsState(**(payload.get("heights") or {})),
            cable=CableState(**(payload.get("cable") or {})),
            pipe=PipeState(**(payload.get("pipe") or {})),
            measurements=MeasurementsState(**(payload.get("measurements") or {})),
            selection=SelectionState(**(payload.get("selection") or {})),
            layer=_load_layer_state(payload.get("layer") or {}),
            layout=_load_layout_state(payload.get("layout") or {}),
            table_template=table_template_state_from_payload(payload.get("table_template") or {}),
            default_font_id=str(payload.get("default_font_id", DEFAULT_FONT_ID)),
            default_font_italic=bool(payload.get("default_font_italic", False)),
            default_font_lineweight_mm=(
                float(payload["default_font_lineweight_mm"])
                if payload.get("default_font_lineweight_mm") is not None
                else None
            ),
        )
    except (TypeError, ValueError) as exc:
        raise ProjectFileError(f"Not a valid project file: {exc}") from exc


def _load_layer_state(layer_payload: Dict[str, Any]) -> LayerState:
    layers_payload = layer_payload.get("layers")
    if layers_payload is None:
        name = str(layer_payload.get("name", "0"))
        rgb = tuple(layer_payload.get("rgb", DEFAULT_LAYER_RGB))
        return LayerState(layers=[LayerDefState(name=name, rgb=rgb)], default_name=name)
    layers = [LayerDefState(name=str(item["name"]), rgb=tuple(item["rgb"])) for item in layers_payload]
    if not layers:
        layers = [LayerDefState()]
    default_name = str(layer_payload.get("default_name", layers[0].name))
    if default_name not in {layer.name for layer in layers}:
        default_name = layers[0].name
    return LayerState(layers=layers, default_name=default_name)


_SHEET_STATE_FIELD_NAMES = {f.name for f in fields(SheetState)}


def _model_rotation_from(layout_payload: Dict[str, Any]) -> float:
    try:
        return float(layout_payload.get("model_rotation", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _model_zoom_from(layout_payload: Dict[str, Any]) -> float:
    try:
        zoom = float(layout_payload.get("model_zoom", 1.0))
    except (TypeError, ValueError):
        return 1.0
    return zoom if zoom > 0 else 1.0


def _model_center_from(layout_payload: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    center = layout_payload.get("model_center")
    if center is None:
        return None
    try:
        x, y = center
        return float(x), float(y)
    except (TypeError, ValueError):
        return None


def _load_layout_state(layout_payload: Dict[str, Any]) -> LayoutState:
    model_rotation = _model_rotation_from(layout_payload)
    model_zoom = _model_zoom_from(layout_payload)
    model_center = _model_center_from(layout_payload)
    sheets_payload = layout_payload.get("sheets")
    if sheets_payload is None:
        return LayoutState(model_rotation=model_rotation, model_zoom=model_zoom, model_center=model_center)
    sheets = [
        SheetState(**{key: value for key, value in item.items() if key in _SHEET_STATE_FIELD_NAMES})
        for item in sheets_payload
    ]
    active_index = layout_payload.get("active_index")
    if active_index is not None:
        active_index = int(active_index)
        if not 0 <= active_index < len(sheets):
            active_index = None
    return LayoutState(
        sheets=sheets,
        active_index=active_index,
        model_rotation=model_rotation,
        model_zoom=model_zoom,
        model_center=model_center,
    )


def open_any(path: str) -> ProjectState:
    lower = path.lower()
    if lower.endswith(PROJECT_FILE_EXTENSION):
        return load_project(path)
    state = ProjectState(name=os.path.splitext(os.path.basename(path))[0])
    if lower.endswith(".dxf"):
        state.dxf_file_path = path
    elif lower.endswith(".txt"):
        state.txt_file_path = path
    else:
        raise ProjectFileError("Choose a .gsgproj, .dxf, or .txt file.")
    return state


def project_path_if_saved(path: str) -> Optional[str]:
    return path if path.lower().endswith(PROJECT_FILE_EXTENSION) else None


def default_project_name(txt_file_path: str, dxf_file_path: str) -> str:
    for path in (dxf_file_path, txt_file_path):
        if path:
            return os.path.splitext(os.path.basename(path))[0]
    return "Untitled"
