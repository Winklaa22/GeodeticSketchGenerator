"""Project save/load — a .gsgproj file bundles the point file, the DXF file,
and every option tab's settings into one JSON document, so reopening a
project (see ui/start_screen.py) puts the app back exactly where it was
left off, not just with the same files loaded.

Pure serialization only: no Qt here (the app's other core/ modules stay
framework-agnostic the same way) — ui/main_window.py converts between this
and the actual tab widgets, and ui/start_screen.py owns the QSettings-backed
"recent projects" list, since that's UI-shell state, not project data.
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
    # The last text typed into the "Separately.../In range..." prompt for
    # each mode - restored as that dialog's pre-filled default, not applied
    # silently, since re-confirming a selection each Apply is deliberate.
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
    # A full snapshot of the DXF's actual content (see DXFDocument.to_text),
    # embedded directly in the project file — not just a reference to
    # dxf_file_path. Without this, any DXF edit never separately saved to
    # its own .dxf file (drawn interactively, or via Apply) would be lost
    # on reopening the project even though the project itself was saved.
    # None if no DXF was loaded when the project was saved.
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
    load into the editor — shared by ui/start_screen.py's Import… and
    ui/main_window.py's File > Open, so both understand exactly the same
    set of openable files.

    A .gsgproj is loaded as-is (see `load_project`). A bare .dxf or .txt
    isn't wrapped in a project yet, so this starts a fresh, unsaved one
    pointed at it rather than requiring the user to create a .gsgproj first
    just to open one file.

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
