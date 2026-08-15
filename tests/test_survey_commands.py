"""Tests for core.survey_draw_service.SurveyDrawService and the six
core.commands.survey builders — the direct-to-DXF replacement for the old
core.script_generator.ScriptGenerator (which built .scr script text)."""
from __future__ import annotations

import pytest

from core.config import CableOptions, GenerationConfig, HeightsOptions, PointsOptions
from core.draw_modes import DrawMode
from core.dxf_document import DXFDocument
from core.exceptions import InvalidLayerNameError, NoDataError, NoSelectionError
from core.survey_draw_service import SurveyDrawService
from models.point import Point


@pytest.fixture
def points() -> dict[int, Point]:
    return {
        1: Point(x=0.0, y=0.0, h=10.0),
        2: Point(x=10.0, y=0.0, h=11.0),
        3: Point(x=10.0, y=10.0, h=12.0),
    }


@pytest.fixture
def service() -> SurveyDrawService:
    return SurveyDrawService()


@pytest.fixture
def doc() -> DXFDocument:
    return DXFDocument.new()


def _entities_of_type(doc: DXFDocument, dxftype: str):
    return [e for e in doc.modelspace if e.dxftype() == dxftype]


def test_build_command_raises_when_no_points(service: SurveyDrawService) -> None:
    config = GenerationConfig(layer_name="0", draw_mode=DrawMode.LINES)
    with pytest.raises(NoDataError):
        service.build_command({}, [], config)


def test_build_command_raises_when_no_selection(service: SurveyDrawService, points) -> None:
    config = GenerationConfig(layer_name="0", draw_mode=DrawMode.LINES)
    with pytest.raises(NoSelectionError):
        service.build_command(points, [], config)


def test_build_command_raises_when_layer_name_blank(service: SurveyDrawService, points) -> None:
    config = GenerationConfig(layer_name="   ", draw_mode=DrawMode.LINES)
    with pytest.raises(InvalidLayerNameError):
        service.build_command(points, [1, 2, 3], config)


def test_applying_the_command_creates_the_target_layer(service: SurveyDrawService, points, doc: DXFDocument) -> None:
    config = GenerationConfig(layer_name="MyLayer", draw_mode=DrawMode.LINES)
    command = service.build_command(points, [1, 2, 3], config)
    command.execute(doc)
    assert "MyLayer" in doc.layers
    assert all(e.dxf.layer == "MyLayer" for e in doc.modelspace)


def test_lines_mode_chains_line_entities_through_selected_points(
    service: SurveyDrawService, points, doc: DXFDocument
) -> None:
    config = GenerationConfig(layer_name="0", draw_mode=DrawMode.LINES)
    service.build_command(points, [1, 2, 3], config).execute(doc)
    lines = _entities_of_type(doc, "LINE")
    assert len(lines) == 2  # 3 selected points -> 2 chained segments
    assert tuple(lines[0].dxf.start) == (0.0, 0.0, 10.0)
    assert tuple(lines[0].dxf.end) == (10.0, 0.0, 11.0)
    assert tuple(lines[1].dxf.start) == (10.0, 0.0, 11.0)
    assert tuple(lines[1].dxf.end) == (10.0, 10.0, 12.0)


def test_pline_mode_creates_one_2d_polyline(service: SurveyDrawService, points, doc: DXFDocument) -> None:
    config = GenerationConfig(layer_name="0", draw_mode=DrawMode.PLINES)
    service.build_command(points, [1, 2], config).execute(doc)
    polylines = _entities_of_type(doc, "LWPOLYLINE")
    assert len(polylines) == 1
    assert [pt[:2] for pt in polylines[0].get_points("xy")] == [(0.0, 0.0), (10.0, 0.0)]


def test_poly3d_mode_creates_one_3d_polyline_with_heights(
    service: SurveyDrawService, points, doc: DXFDocument
) -> None:
    config = GenerationConfig(layer_name="0", draw_mode=DrawMode.POLY3D)
    service.build_command(points, [1, 2], config).execute(doc)
    polylines = _entities_of_type(doc, "POLYLINE")
    assert len(polylines) == 1
    assert [tuple(v) for v in polylines[0].points()] == [(0.0, 0.0, 10.0), (10.0, 0.0, 11.0)]


def test_points_mode_draws_circles_with_diameter_derived_radius(
    service: SurveyDrawService, points, doc: DXFDocument
) -> None:
    config = GenerationConfig(
        layer_name="0",
        draw_mode=DrawMode.POINTS,
        points=PointsOptions(numbers_enabled=False, diameter=0.1),
    )
    service.build_command(points, [1, 2, 3], config).execute(doc)
    circles = _entities_of_type(doc, "CIRCLE")
    assert len(circles) == 3
    assert all(c.dxf.radius == 0.05 for c in circles)
    assert _entities_of_type(doc, "TEXT") == []


def test_points_mode_adds_number_labels_when_enabled(
    service: SurveyDrawService, points, doc: DXFDocument
) -> None:
    config = GenerationConfig(
        layer_name="0",
        draw_mode=DrawMode.POINTS,
        points=PointsOptions(numbers_enabled=True, font_size=0.6, diameter=0.1),
    )
    service.build_command(points, [1, 2, 3], config).execute(doc)
    labels = _entities_of_type(doc, "TEXT")
    assert sorted(t.dxf.text for t in labels) == ["1", "2", "3"]


def test_points_mode_cabinet_shrinks_last_six_labels(service: SurveyDrawService, doc: DXFDocument) -> None:
    points = {n: Point(x=float(n), y=0.0, h=1.0) for n in range(1, 8)}
    config = GenerationConfig(
        layer_name="0",
        draw_mode=DrawMode.POINTS,
        cabinet_mode=True,
        points=PointsOptions(numbers_enabled=True, font_size=0.6, diameter=0.1),
    )
    service.build_command(points, list(range(1, 8)), config).execute(doc)
    labels = {t.dxf.text: t for t in _entities_of_type(doc, "TEXT")}
    # Point 1 is not among the last 6 selected -> normal size 0.6.
    assert labels["1"].dxf.height == 0.6
    # Point 2 is among the last 6 selected -> shrunk to 0.3, no offset.
    assert labels["2"].dxf.height == 0.3
    assert tuple(labels["2"].dxf.insert) == (2.0, 0.0, 1.0)


def test_heights_mode_respects_frequency_and_rounds_height_up(
    service: SurveyDrawService, points, doc: DXFDocument
) -> None:
    config = GenerationConfig(
        layer_name="0",
        draw_mode=DrawMode.HEIGHTS,
        heights=HeightsOptions(font_size=0.6, frequency=2),
    )
    service.build_command(points, [1, 2, 3], config).execute(doc)
    labels = _entities_of_type(doc, "TEXT")
    assert len(labels) == 1  # only point #2 is a multiple of frequency=2
    assert labels[0].dxf.text == "11.0"  # ceil(11.0 * 10) / 10 == 11.0


def test_cable_marks_use_segment_midpoint_and_custom_text(
    service: SurveyDrawService, points, doc: DXFDocument
) -> None:
    config = GenerationConfig(
        layer_name="0",
        draw_mode=DrawMode.CABLE_MARKS,
        cable=CableOptions(font_size=0.6, frequency=1, marks_text="CBL"),
    )
    service.build_command(points, [1, 2, 3], config).execute(doc)
    labels = _entities_of_type(doc, "TEXT")
    # Point 3 has no successor in the selection, so only points 1 and 2 emit marks.
    assert len(labels) == 2
    assert all(t.dxf.text == "CBL" for t in labels)


def test_whole_batch_undoes_as_one_step(service: SurveyDrawService, points, doc: DXFDocument) -> None:
    config = GenerationConfig(
        layer_name="0",
        draw_mode=DrawMode.POINTS,
        points=PointsOptions(numbers_enabled=True, diameter=0.1),
    )
    command = service.build_command(points, [1, 2, 3], config)
    command.execute(doc)
    assert doc.entity_count() == 6  # 3 circles + 3 labels
    command.undo(doc)
    assert doc.entity_count() == 0
