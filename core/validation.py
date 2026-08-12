from __future__ import annotations

from typing import Dict, List

from core.exceptions import InvalidLayerNameError, NoDataError, NoSelectionError
from models.point import Point

NO_DATA_MESSAGE = "No valid input file selected."
NO_LAYER_MESSAGE = "Please enter layer name."
NO_SELECTION_MESSAGE = "No points selected."


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
