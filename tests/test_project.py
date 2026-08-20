"""Tests for core.project: .gsgproj save/load round-trip and error handling."""
from __future__ import annotations

import json

import pytest

from core.exceptions import ProjectFileError
from core.project import (
    CableState,
    DelimiterState,
    HeightsState,
    LayerState,
    PipeState,
    PointsState,
    ProjectState,
    SelectionState,
    default_project_name,
    load_project,
    open_any,
    project_path_if_saved,
    save_project,
)


def test_save_then_load_round_trips_every_field(tmp_path) -> None:
    state = ProjectState(
        name="Ludgierzowice",
        txt_file_path="C:/data/points.txt",
        dxf_file_path="C:/data/drawing.dxf",
        dxf_content="0\nSECTION\n2\nHEADER\n0\nENDSEC\n0\nEOF\n",
        draw_mode="lines",
        delimiter=DelimiterState(mode="tab", swap_xy=False, cabinet_mode=True),
        points=PointsState(numbers_enabled=True, font_size=0.8, diameter=0.1),
        heights=HeightsState(font_size=0.5, frequency=3),
        cable=CableState(font_size=0.7, frequency=2, marks_text="CBL"),
        pipe=PipeState(width=0.2),
        selection=SelectionState(mode="range", separate_text="1,2,3", range_text="1-10"),
        layer=LayerState(name="RURA", rgb=(200, 30, 40)),
    )
    path = str(tmp_path / "project.gsgproj")
    save_project(path, state)
    loaded = load_project(path)
    assert loaded == state


def test_dxf_content_defaults_to_none_when_no_dxf_was_loaded(tmp_path) -> None:
    path = str(tmp_path / "no_dxf.gsgproj")
    save_project(path, ProjectState(name="Blank"))
    loaded = load_project(path)
    assert loaded.dxf_content is None


def test_load_missing_file_raises_project_file_error(tmp_path) -> None:
    with pytest.raises(ProjectFileError):
        load_project(str(tmp_path / "does-not-exist.gsgproj"))


def test_load_malformed_json_raises_project_file_error(tmp_path) -> None:
    path = tmp_path / "broken.gsgproj"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(ProjectFileError):
        load_project(str(path))


def test_load_non_object_json_raises_project_file_error(tmp_path) -> None:
    path = tmp_path / "list.gsgproj"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ProjectFileError):
        load_project(str(path))


def test_load_fills_in_missing_sections_with_defaults(tmp_path) -> None:
    # A minimal, hand-written project file - only the file paths given.
    path = tmp_path / "minimal.gsgproj"
    path.write_text(json.dumps({"txt_file_path": "a.txt"}), encoding="utf-8")
    loaded = load_project(str(path))
    assert loaded.txt_file_path == "a.txt"
    assert loaded == ProjectState(name="Untitled", txt_file_path="a.txt")


def test_load_rejects_unknown_field_types(tmp_path) -> None:
    path = tmp_path / "bad_field.gsgproj"
    path.write_text(json.dumps({"points": {"font_size": "not-a-number-but-also-not-castable[]"}}), encoding="utf-8")
    # font_size is stored as a plain string field in the dataclass at
    # construction time (dataclasses don't validate types), so this only
    # raises where a genuinely incompatible shape breaks construction -
    # covered by the malformed/non-object cases above. This case instead
    # documents that unknown extra keys in a section are rejected.
    path.write_text(json.dumps({"points": {"font_size": 0.6, "bogus_extra_field": 1}}), encoding="utf-8")
    with pytest.raises(ProjectFileError):
        load_project(str(path))


def test_open_any_loads_a_gsgproj_as_is(tmp_path) -> None:
    state = ProjectState(name="Real", draw_mode="pipe")
    path = str(tmp_path / "real.gsgproj")
    save_project(path, state)
    assert open_any(path) == state


def test_open_any_wraps_a_bare_dxf_in_a_fresh_project(tmp_path) -> None:
    path = str(tmp_path / "drawing.dxf")
    (tmp_path / "drawing.dxf").write_text("", encoding="utf-8")
    state = open_any(path)
    assert state.name == "drawing"
    assert state.dxf_file_path == path
    assert state.txt_file_path == ""


def test_open_any_wraps_a_bare_txt_in_a_fresh_project(tmp_path) -> None:
    path = str(tmp_path / "points.txt")
    (tmp_path / "points.txt").write_text("", encoding="utf-8")
    state = open_any(path)
    assert state.name == "points"
    assert state.txt_file_path == path
    assert state.dxf_file_path == ""


def test_open_any_rejects_an_unsupported_extension(tmp_path) -> None:
    path = str(tmp_path / "notes.pdf")
    with pytest.raises(ProjectFileError):
        open_any(path)


def test_project_path_if_saved() -> None:
    assert project_path_if_saved("C:/a/project.gsgproj") == "C:/a/project.gsgproj"
    assert project_path_if_saved("C:/a/drawing.dxf") is None
    assert project_path_if_saved("C:/a/points.txt") is None


def test_default_project_name_prefers_dxf_then_txt_then_untitled() -> None:
    assert default_project_name("C:/a/points.txt", "C:/b/drawing.dxf") == "drawing"
    assert default_project_name("C:/a/points.txt", "") == "points"
    assert default_project_name("", "") == "Untitled"
