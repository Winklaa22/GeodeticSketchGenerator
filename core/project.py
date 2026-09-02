from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.exceptions import ProjectFileError
from core.plot import PlotOptions

PROJECT_FILE_EXTENSION = ".gsgproj"
PROJECT_FILE_FILTER = "Geodetic Sketch Project (*.gsgproj)"
_FORMAT_VERSION = 1

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
    powiat: str = ""
    gmina: str = ""
    obreb: str = ""
    dz_nr: str = ""
    sketch_number: str = ""


@dataclass
class LayoutState:

    sheets: List[SheetState] = field(default_factory=lambda: [SheetState()])
    active_index: Optional[int] = None


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


def _load_layout_state(layout_payload: Dict[str, Any]) -> LayoutState:
    sheets_payload = layout_payload.get("sheets")
    if sheets_payload is None:
        return LayoutState()
    sheets = [SheetState(**item) for item in sheets_payload]
    active_index = layout_payload.get("active_index")
    if active_index is not None:
        active_index = int(active_index)
        if not 0 <= active_index < len(sheets):
            active_index = None
    return LayoutState(sheets=sheets, active_index=active_index)


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
