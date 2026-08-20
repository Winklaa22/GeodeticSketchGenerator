"""Project save/load — a .gsgproj file bundles the point file, the DXF file,
and every option tab's settings into one JSON document, so reopening a
project puts the app back exactly where it was left off.

Pure serialization, no Qt: ui/main_window.py converts this to/from the
actual tab widgets, and ui/start_screen.py owns the "recent projects" list.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional, Tuple

from core.exceptions import ProjectFileError

PROJECT_FILE_EXTENSION = ".gsgproj"
PROJECT_FILE_FILTER = "Geodetic Sketch Project (*.gsgproj)"
_FORMAT_VERSION = 1

DEFAULT_LAYER_RGB: Tuple[int, int, int] = (145, 132, 217)


@dataclass
class DelimiterState:
    mode: str = "auto"  # "auto" | "space" | "tab" - see ui.tabs.delimiter_tab
    swap_xy: bool = True
    cabinet_mode: bool = False


@dataclass
class PointsState:
    numbers_enabled: bool = False
    font_size: float = 0.6
    diameter: float = 0.05


@dataclass
class HeightsState:
    font_size: float = 0.6
    frequency: int = 5


@dataclass
class CableState:
    font_size: float = 0.6
    frequency: int = 5
    marks_text: str = "eN"


@dataclass
class PipeState:
    width: float = 0.16


@dataclass
class SelectionState:
    mode: str = "all"  # "all" | "separately" | "range" - see ui.tabs.selection_tab
    # Last text typed into the "Separately.../In range..." prompt - restored
    # as that dialog's pre-filled default, not applied silently.
    separate_text: str = ""
    range_text: str = ""


@dataclass
class LayerState:
    name: str = "0"
    rgb: Tuple[int, int, int] = DEFAULT_LAYER_RGB


@dataclass
class ProjectState:
    """Everything needed to restore a working session: the point file and
    DXF file it used, plus every option tab's settings at the time."""

    name: str = "Untitled"
    txt_file_path: str = ""
    dxf_file_path: str = ""
    # Full snapshot of the DXF's content (see DXFDocument.to_text), not just
    # a reference to dxf_file_path - otherwise edits never separately saved
    # to their own .dxf would be lost on reopening the project.
    dxf_content: Optional[str] = None
    draw_mode: str = "plines"  # see ui.tabs.draw_tab's mode keys
    delimiter: DelimiterState = field(default_factory=DelimiterState)
    points: PointsState = field(default_factory=PointsState)
    heights: HeightsState = field(default_factory=HeightsState)
    cable: CableState = field(default_factory=CableState)
    pipe: PipeState = field(default_factory=PipeState)
    selection: SelectionState = field(default_factory=SelectionState)
    layer: LayerState = field(default_factory=LayerState)


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
        layer_payload = payload.get("layer") or {}
        rgb = layer_payload.get("rgb", DEFAULT_LAYER_RGB)
        dxf_content = payload.get("dxf_content")
        return ProjectState(
            name=str(payload.get("name", "Untitled")),
            txt_file_path=str(payload.get("txt_file_path", "")),
            dxf_file_path=str(payload.get("dxf_file_path", "")),
            dxf_content=str(dxf_content) if dxf_content is not None else None,
            draw_mode=str(payload.get("draw_mode", "plines")),
            delimiter=DelimiterState(**(payload.get("delimiter") or {})),
            points=PointsState(**(payload.get("points") or {})),
            heights=HeightsState(**(payload.get("heights") or {})),
            cable=CableState(**(payload.get("cable") or {})),
            pipe=PipeState(**(payload.get("pipe") or {})),
            selection=SelectionState(**(payload.get("selection") or {})),
            layer=LayerState(name=str(layer_payload.get("name", "0")), rgb=tuple(rgb)),
        )
    except (TypeError, ValueError) as exc:
        raise ProjectFileError(f"Not a valid project file: {exc}") from exc


def open_any(path: str) -> ProjectState:
    """Resolves a .gsgproj, .dxf, or .txt path into a ProjectState ready to
    load — shared by start_screen's Import… and main_window's File > Open.
    A bare .dxf/.txt starts a fresh, unsaved project pointed at it.

    Raises `ProjectFileError` for an unsupported extension or a malformed
    .gsgproj.
    """
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
    """The `project_path` a caller of `open_any(path)` should track once it
    succeeds: `path` itself for an actual .gsgproj, None for a bare
    .dxf/.txt (which isn't a saved project yet)."""
    return path if path.lower().endswith(PROJECT_FILE_EXTENSION) else None


def default_project_name(txt_file_path: str, dxf_file_path: str) -> str:
    """A reasonable project name derived from whichever file is set — used
    to pre-fill "Save Project As" and as the fallback display name."""
    for path in (dxf_file_path, txt_file_path):
        if path:
            return os.path.splitext(os.path.basename(path))[0]
    return "Untitled"
