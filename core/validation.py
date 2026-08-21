from __future__ import annotations

from typing import Dict, List

from core.draw_modes import DrawMode
from core.exceptions import InvalidLayerNameError, NoDataError, NoDrawModeError, NoSelectionError
from models.point import Point

NO_DATA_MESSAGE = "No valid input file selected."
NO_LAYER_MESSAGE = "Please enter layer name."
NO_SELECTION_MESSAGE = "No points selected."
NO_DRAW_MODE_MESSAGE = "Select at least one drawing mode."


def ensure_has_data(data: Dict[int, Point], file_path: str = "") -> None:

    if not data and not file_path:
        raise NoDataError(NO_DATA_MESSAGE)


def resolve_layer_name(raw_layer_name: str) -> str:
    layer_name = (raw_layer_name or "0").strip()
    if not layer_name:
        raise InvalidLayerNameError(NO_LAYER_MESSAGE)
    return layer_name


def ensure_selection(selected_numbers: List[int]) -> None:
    if not selected_numbers:
        raise NoSelectionError(NO_SELECTION_MESSAGE)


def ensure_draw_modes(draw_modes: List[DrawMode]) -> None:
    if not draw_modes:
        raise NoDrawModeError(NO_DRAW_MODE_MESSAGE)
