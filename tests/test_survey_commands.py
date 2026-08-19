"""Tests for core.survey_draw_service.SurveyDrawService and the six
core.commands.survey builders — the direct-to-DXF replacement for the old
core.script_generator.ScriptGenerator (which built .scr script text)."""
from __future__ import annotations

import pytest

from core.config import CableOptions, GenerationConfig, HeightsOptions, PipeOptions, PointsOptions
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


def test_layer_rgb_colors_a_newly_created_layer(service: SurveyDrawService, points, doc: DXFDocument) -> None:
    config = GenerationConfig(layer_name="MyLayer", draw_mode=DrawMode.LINES, layer_rgb=(200, 30, 40))
    command = service.build_command(points, [1, 2, 3], config)
    command.execute(doc)
    assert doc.get_layer_color("MyLayer") == (200, 30, 40)


def test_layer_rgb_never_recolors_an_already_existing_layer(
    service: SurveyDrawService, points, doc: DXFDocument
) -> None:
    doc.add_layer("MyLayer", rgb=(9, 9, 9))  # e.g. imported from a DXF
    config = GenerationConfig(layer_name="MyLayer", draw_mode=DrawMode.LINES, layer_rgb=(200, 30, 40))
    command = service.build_command(points, [1, 2, 3], config)
    command.execute(doc)
    assert doc.get_layer_color("MyLayer") == (9, 9, 9)


def test_layer_rgb_undo_removes_the_layer_it_created_along_with_the_drawing(
    service: SurveyDrawService, points, doc: DXFDocument
) -> None:
    config = GenerationConfig(layer_name="MyLayer", draw_mode=DrawMode.LINES, layer_rgb=(200, 30, 40))
    command = service.build_command(points, [1, 2, 3], config)
    command.execute(doc)
    command.undo(doc)
    assert "MyLayer" not in doc.layers
    assert doc.entity_count() == 0


def test_no_layer_rgb_behaves_exactly_as_before(service: SurveyDrawService, points, doc: DXFDocument) -> None:
    config = GenerationConfig(layer_name="MyLayer", draw_mode=DrawMode.LINES)  # layer_rgb defaults to None
    command = service.build_command(points, [1, 2, 3], config)
    command.execute(doc)
    assert "MyLayer" in doc.layers
    assert doc.get_layer_color("MyLayer") == (255, 255, 255)  # ezdxf's own plain default


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


@pytest.fixture
def points_with_box() -> dict[int, Point]:
    # Point 1 is a plain main-line point; 2,3,4,5 trace a rectangle; point
    # 6 continues the main line afterwards.
    return {
        1: Point(x=0.0, y=0.0, h=0.0),
        2: Point(x=10.0, y=0.0, h=0.0),
        3: Point(x=11.0, y=0.0, h=0.0),
        4: Point(x=11.0, y=1.0, h=0.0),
        5: Point(x=10.0, y=1.0, h=0.0),
        6: Point(x=20.0, y=0.0, h=0.0),
    }


def test_pline_mode_draws_skrzynka_as_a_separate_closed_polyline(
    service: SurveyDrawService, points_with_box, doc: DXFDocument
) -> None:
    config = GenerationConfig(layer_name="0", draw_mode=DrawMode.PLINES)
    service.build_command(points_with_box, [1, 2, 3, 4, 5, 6], config).execute(doc)
    polylines = _entities_of_type(doc, "LWPOLYLINE")
    assert len(polylines) == 2  # the cable run and the box, as separate entities
    cable, box = polylines
    # The cable skips straight from point 1 to point 6, touching none of
    # the box's corners.
    assert [pt[:2] for pt in cable.get_points("xy")] == [(0.0, 0.0), (20.0, 0.0)]
    assert [pt[:2] for pt in box.get_points("xy")] == [(10.0, 0.0), (11.0, 0.0), (11.0, 1.0), (10.0, 1.0)]
    assert box.closed


def test_poly3d_mode_draws_skrzynka_as_a_separate_closed_polyline(
    service: SurveyDrawService, points_with_box, doc: DXFDocument
) -> None:
    config = GenerationConfig(layer_name="0", draw_mode=DrawMode.POLY3D)
    service.build_command(points_with_box, [1, 2, 3, 4, 5, 6], config).execute(doc)
    polylines = _entities_of_type(doc, "POLYLINE")
    assert len(polylines) == 2
    cable, box = polylines
    assert [tuple(v) for v in cable.points()] == [(0.0, 0.0, 0.0), (20.0, 0.0, 0.0)]
    assert [tuple(v) for v in box.points()] == [
        (10.0, 0.0, 0.0), (11.0, 0.0, 0.0), (11.0, 1.0, 0.0), (10.0, 1.0, 0.0),
    ]
    assert box.is_closed


def test_lines_mode_draws_skrzynka_sides_alongside_the_cable_segments(
    service: SurveyDrawService, points_with_box, doc: DXFDocument
) -> None:
    config = GenerationConfig(layer_name="0", draw_mode=DrawMode.LINES)
    service.build_command(points_with_box, [1, 2, 3, 4, 5, 6], config).execute(doc)
    lines = _entities_of_type(doc, "LINE")
    # 1 cable segment (1->6, skipping the box) + 4 box sides
    assert len(lines) == 5
    cable_line = lines[0]
    assert tuple(cable_line.dxf.start) == (0.0, 0.0, 0.0)
    assert tuple(cable_line.dxf.end) == (20.0, 0.0, 0.0)


def test_pipe_mode_draws_two_parallel_lines_straddling_each_segment(
    service: SurveyDrawService, doc: DXFDocument
) -> None:
    points = {1: Point(x=0.0, y=0.0, h=0.0), 2: Point(x=10.0, y=0.0, h=0.0)}
    config = GenerationConfig(layer_name="0", draw_mode=DrawMode.PIPE, pipe=PipeOptions(width=0.2))
    service.build_command(points, [1, 2], config).execute(doc)
    lines = sorted(_entities_of_type(doc, "LINE"), key=lambda line: line.dxf.start[1])
    assert len(lines) == 2  # one segment -> two parallel lines
    below, above = lines
    assert tuple(below.dxf.start)[:2] == (0.0, -0.1)
    assert tuple(below.dxf.end)[:2] == (10.0, -0.1)
    assert tuple(above.dxf.start)[:2] == (0.0, 0.1)
    assert tuple(above.dxf.end)[:2] == (10.0, 0.1)


def test_pipe_mode_skips_straight_past_a_skrzynka_like_lines_mode(
    service: SurveyDrawService, points_with_box, doc: DXFDocument
) -> None:
    config = GenerationConfig(layer_name="0", draw_mode=DrawMode.PIPE, pipe=PipeOptions(width=0.2))
    service.build_command(points_with_box, [1, 2, 3, 4, 5, 6], config).execute(doc)
    lines = _entities_of_type(doc, "LINE")
    # 1 cable segment (1->6, skipping the box) -> 2 parallel pipe lines,
    # and the box itself is never touched by the pipe.
    assert len(lines) == 2
    for line in lines:
        assert tuple(line.dxf.start)[0] == 0.0
        assert tuple(line.dxf.end)[0] == 20.0


@pytest.fixture
def points_with_wcinka() -> dict[int, Point]:
    # 1, 2, 3 are a tight triangle at the very start of the selection; 4 is
    # a normal, far-away main-line point. Point 3 - nearest to 4 - should be
    # the entry point that stays on the cable's path.
    return {
        1: Point(x=2.0, y=-3.0, h=0.0),
        2: Point(x=2.0, y=3.0, h=0.0),
        3: Point(x=0.0, y=0.0, h=0.0),
        4: Point(x=-20.0, y=0.0, h=0.0),
    }


def test_pline_mode_draws_wcinka_as_open_stubs_off_its_entry_point(
    service: SurveyDrawService, points_with_wcinka, doc: DXFDocument
) -> None:
    config = GenerationConfig(layer_name="0", draw_mode=DrawMode.PLINES)
    service.build_command(points_with_wcinka, [1, 2, 3, 4], config).execute(doc)
    polylines = _entities_of_type(doc, "LWPOLYLINE")
    assert len(polylines) == 1  # the cable's own polyline - point 3 is part of it, not separate
    assert [pt[:2] for pt in polylines[0].get_points("xy")] == [(0.0, 0.0), (-20.0, 0.0)]
    lines = _entities_of_type(doc, "LINE")
    assert len(lines) == 2  # the two open stubs: 3->1 and 3->2 (no 1-2 edge)
    stub_endpoints = {(tuple(l.dxf.start), tuple(l.dxf.end)) for l in lines}
    assert stub_endpoints == {
        ((0.0, 0.0, 0.0), (2.0, -3.0, 0.0)),
        ((0.0, 0.0, 0.0), (2.0, 3.0, 0.0)),
    }


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
    # 3 points -> 2 segments, and frequency=1 marks every segment.
    assert len(labels) == 2
    assert all(t.dxf.text == "CBL" for t in labels)


def test_cable_marks_start_at_the_centre_segment_and_fan_outward(
    service: SurveyDrawService, doc: DXFDocument
) -> None:
    # 5 points -> 4 segments (indices 0-3), centre index (4-1)//2 = 1.
    points = {n: Point(x=float(n) * 10.0, y=0.0, h=0.0) for n in range(1, 6)}
    config = GenerationConfig(
        layer_name="0",
        draw_mode=DrawMode.CABLE_MARKS,
        cable=CableOptions(font_size=0.6, frequency=2, marks_text="eN"),
    )
    service.build_command(points, [1, 2, 3, 4, 5], config).execute(doc)
    labels = _entities_of_type(doc, "TEXT")
    # Centre segment (index 1: points 2-3) plus index 1-2=-1 (out of bounds)
    # and index 1+2=3 (points 4-5) -> 2 marks, not starting from either end.
    xs = sorted(round(t.dxf.insert[0]) for t in labels)
    assert xs == [25, 45]  # midpoints of (20,30) and (40,50)
    # The cable itself is still fully drawn: the 2 unmarked segments as one
    # LINE each, the 2 marked segments split into 2 LINEs each (the notch).
    lines = _entities_of_type(doc, "LINE")
    assert len(lines) == 2 + 2 * 2


def test_cable_marks_cut_a_gap_into_the_line_sized_to_the_mark_text(
    service: SurveyDrawService, doc: DXFDocument
) -> None:
    points = {1: Point(x=0.0, y=0.0, h=0.0), 2: Point(x=10.0, y=0.0, h=0.0)}
    config = GenerationConfig(
        layer_name="0",
        draw_mode=DrawMode.CABLE_MARKS,
        cable=CableOptions(font_size=0.6, frequency=5, marks_text="eN"),
    )
    service.build_command(points, [1, 2], config).execute(doc)
    labels = _entities_of_type(doc, "TEXT")
    assert len(labels) == 1
    assert round(labels[0].dxf.insert[0]) == 5

    # gap_length = len("eN") * 0.6 * 0.7 + 0.6 * 0.5 = 0.84 + 0.3 = 1.14
    lines = sorted(_entities_of_type(doc, "LINE"), key=lambda line: line.dxf.start[0])
    assert len(lines) == 2  # the segment is cut into two stubs around the mark
    assert tuple(lines[0].dxf.start)[:2] == (0.0, 0.0)
    assert round(lines[0].dxf.end[0], 2) == 4.43
    assert round(lines[1].dxf.start[0], 2) == 5.57
    assert tuple(lines[1].dxf.end)[:2] == (10.0, 0.0)


def test_cable_marks_never_land_inside_a_skipped_skrzynka(
    service: SurveyDrawService, points_with_box, doc: DXFDocument
) -> None:
    config = GenerationConfig(
        layer_name="0",
        draw_mode=DrawMode.CABLE_MARKS,
        cable=CableOptions(font_size=0.6, frequency=1, marks_text="eN"),
    )
    service.build_command(points_with_box, [1, 2, 3, 4, 5, 6], config).execute(doc)
    labels = _entities_of_type(doc, "TEXT")
    # Only 1 real cable segment once the box is skipped (1 -> 6): its own
    # midpoint, nowhere near the box at x=10-11.
    assert len(labels) == 1
    assert round(labels[0].dxf.insert[0]) == 10


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
