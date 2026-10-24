from __future__ import annotations

import itertools
import math
import random

import pytest
from ezdxf import bbox as ezdxf_bbox

from core.commands.composite import CompositeCommand
from core.config import CableOptions, GenerationConfig, HeightsOptions, PipeOptions, PointsOptions
from core.draw_modes import DrawMode
from core.dxf_document import DXFDocument
from core.exceptions import InvalidLayerNameError, NoDataError, NoSelectionError
from core.generated import mode_from_entity
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


def _bboxes_overlap(a, b) -> bool:
    return not (
        a.extmax.x <= b.extmin.x
        or b.extmax.x <= a.extmin.x
        or a.extmax.y <= b.extmin.y
        or b.extmax.y <= a.extmin.y
    )


def _label_rect(cx: float, cy: float, font_size: float, text: str) -> tuple[float, float, float, float]:
    width = 0.62 * font_size * len(text) + 0.30 * font_size
    height = 1.30 * font_size
    return cx - width / 2.0, cy - height / 2.0, cx + width / 2.0, cy + height / 2.0


def _rects_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


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


def test_layer_rgb_recolors_an_already_existing_layer_too(
    service: SurveyDrawService, points, doc: DXFDocument
) -> None:
    doc.add_layer("MyLayer", rgb=(9, 9, 9))
    config = GenerationConfig(layer_name="MyLayer", draw_mode=DrawMode.LINES, layer_rgb=(200, 30, 40))
    command = service.build_command(points, [1, 2, 3], config)
    command.execute(doc)
    assert doc.get_layer_color("MyLayer") == (200, 30, 40)


def test_layer_rgb_undo_removes_the_layer_it_created_along_with_the_drawing(
    service: SurveyDrawService, points, doc: DXFDocument
) -> None:
    config = GenerationConfig(layer_name="MyLayer", draw_mode=DrawMode.LINES, layer_rgb=(200, 30, 40))
    command = service.build_command(points, [1, 2, 3], config)
    command.execute(doc)
    command.undo(doc)
    assert "MyLayer" not in doc.layers
    assert doc.entity_count() == 0


def test_layer_rgb_undo_restores_an_already_existing_layers_previous_color(
    service: SurveyDrawService, points, doc: DXFDocument
) -> None:
    doc.add_layer("MyLayer", rgb=(9, 9, 9))
    config = GenerationConfig(layer_name="MyLayer", draw_mode=DrawMode.LINES, layer_rgb=(200, 30, 40))
    command = service.build_command(points, [1, 2, 3], config)
    command.execute(doc)
    command.undo(doc)
    assert "MyLayer" in doc.layers
    assert doc.get_layer_color("MyLayer") == (9, 9, 9)
    assert doc.entity_count() == 0


def test_no_layer_rgb_behaves_exactly_as_before(service: SurveyDrawService, points, doc: DXFDocument) -> None:
    config = GenerationConfig(layer_name="MyLayer", draw_mode=DrawMode.LINES)
    command = service.build_command(points, [1, 2, 3], config)
    command.execute(doc)
    assert "MyLayer" in doc.layers
    assert doc.get_layer_color("MyLayer") == (255, 255, 255)


def test_lines_mode_chains_line_entities_through_selected_points(
    service: SurveyDrawService, points, doc: DXFDocument
) -> None:
    config = GenerationConfig(layer_name="0", draw_mode=DrawMode.LINES)
    service.build_command(points, [1, 2, 3], config).execute(doc)
    lines = _entities_of_type(doc, "LINE")
    assert len(lines) == 2
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
    return {
        1: Point(x=0.0, y=0.0, h=0.0),
        2: Point(x=10.0, y=0.0, h=0.0),
        3: Point(x=11.0, y=0.0, h=0.0),
        4: Point(x=11.0, y=1.0, h=0.0),
        5: Point(x=10.0, y=1.0, h=0.0),
        6: Point(x=20.0, y=0.0, h=0.0),
    }


@pytest.fixture
def points_with_enclosure() -> dict[int, Point]:
    return {
        1: Point(x=0.0, y=0.0, h=0.0),
        2: Point(x=10.0, y=0.0, h=0.0),
        3: Point(x=11.0, y=0.0, h=0.0),
        4: Point(x=11.0, y=1.0, h=0.0),
        5: Point(x=10.0, y=1.0, h=0.0),
        6: Point(x=20.0, y=0.0, h=0.0),
        7: Point(x=10.4, y=0.6, h=0.0),
    }


def test_pline_mode_draws_the_enclosure_as_a_separate_closed_polyline(
    service: SurveyDrawService, points_with_enclosure, doc: DXFDocument
) -> None:
    config = GenerationConfig(layer_name="0", draw_mode=DrawMode.PLINES, quantum=0.01)
    service.build_command(points_with_enclosure, [1, 2, 3, 4, 5, 6, 7], config).execute(doc)
    polylines = _entities_of_type(doc, "LWPOLYLINE")
    assert len(polylines) == 2
    cable, outline = polylines
    assert [pt[:2] for pt in cable.get_points("xy")] == [(20.0, 0.0), (10.4, 0.6), (0.0, 0.0)]
    assert [pt[:2] for pt in outline.get_points("xy")] == [(10.0, 0.0), (11.0, 0.0), (11.0, 1.0), (10.0, 1.0)]
    assert outline.closed


def test_poly3d_mode_draws_the_enclosure_as_a_separate_closed_polyline(
    service: SurveyDrawService, points_with_enclosure, doc: DXFDocument
) -> None:
    config = GenerationConfig(layer_name="0", draw_mode=DrawMode.POLY3D, quantum=0.01)
    service.build_command(points_with_enclosure, [1, 2, 3, 4, 5, 6, 7], config).execute(doc)
    polylines = _entities_of_type(doc, "POLYLINE")
    assert len(polylines) == 2
    cable, outline = polylines
    assert [tuple(v) for v in cable.points()] == [(20.0, 0.0, 0.0), (10.4, 0.6, 0.0), (0.0, 0.0, 0.0)]
    assert [tuple(v) for v in outline.points()] == [
        (10.0, 0.0, 0.0), (11.0, 0.0, 0.0), (11.0, 1.0, 0.0), (10.0, 1.0, 0.0),
    ]
    assert outline.is_closed


def test_lines_mode_draws_enclosure_sides_alongside_the_cable_edges(
    service: SurveyDrawService, points_with_enclosure, doc: DXFDocument
) -> None:
    config = GenerationConfig(layer_name="0", draw_mode=DrawMode.LINES, quantum=0.01)
    service.build_command(points_with_enclosure, [1, 2, 3, 4, 5, 6, 7], config).execute(doc)
    lines = _entities_of_type(doc, "LINE")
    assert len(lines) == 6
    cable_lines = [
        line for line in lines if 0.0 in (line.dxf.start[0], line.dxf.end[0]) or 20.0 in (line.dxf.start[0], line.dxf.end[0])
    ]
    assert len(cable_lines) == 2
    endpoints = {tuple(line.dxf.start)[:2] for line in cable_lines} | {tuple(line.dxf.end)[:2] for line in cable_lines}
    assert endpoints == {(0.0, 0.0), (10.4, 0.6), (20.0, 0.0)}


@pytest.fixture
def points_with_tap() -> dict[int, Point]:
    return {
        1: Point(x=-20.5, y=-0.5, h=0.0),
        2: Point(x=-19.5, y=-0.5, h=0.0),
        3: Point(x=-19.5, y=0.5, h=0.0),
        4: Point(x=-20.5, y=0.5, h=0.0),
        5: Point(x=-20.0, y=0.0, h=0.0),
        6: Point(x=19.5, y=-0.5, h=0.0),
        7: Point(x=20.5, y=-0.5, h=0.0),
        8: Point(x=20.5, y=0.5, h=0.0),
        9: Point(x=19.5, y=0.5, h=0.0),
        10: Point(x=20.0, y=0.0, h=0.0),
        11: Point(x=0.0, y=0.0, h=0.0),
        12: Point(x=0.0, y=10.0, h=0.0),
    }


def test_lines_mode_draws_one_line_per_edge_at_a_tap_junction(
    service: SurveyDrawService, points_with_tap, doc: DXFDocument
) -> None:
    config = GenerationConfig(layer_name="0", draw_mode=DrawMode.LINES, quantum=0.01)
    service.build_command(points_with_tap, list(points_with_tap), config).execute(doc)
    lines = _entities_of_type(doc, "LINE")
    # 3 tree edges (5-11, 10-11, 11-12) plus 2 x 4 enclosure sides.
    assert len(lines) == 11


def test_pline_mode_merges_the_through_run_at_a_tap_into_one_continuous_polyline(
    service: SurveyDrawService, points_with_tap, doc: DXFDocument
) -> None:
    config = GenerationConfig(layer_name="0", draw_mode=DrawMode.PLINES, quantum=0.01)
    service.build_command(points_with_tap, list(points_with_tap), config).execute(doc)
    polylines = _entities_of_type(doc, "LWPOLYLINE")
    open_polylines = [p for p in polylines if not p.closed]
    assert len(open_polylines) == 2
    through_run = next(p for p in open_polylines if len(p) == 3)
    branch = next(p for p in open_polylines if len(p) == 2)
    assert [pt[:2] for pt in through_run.get_points("xy")] == [(-20.0, 0.0), (0.0, 0.0), (20.0, 0.0)]
    assert [pt[:2] for pt in branch.get_points("xy")] == [(0.0, 0.0), (0.0, 10.0)]
    assert sum(1 for p in polylines if p.closed) == 2


def test_poly3d_mode_merges_the_through_run_at_a_tap_into_one_continuous_polyline(
    service: SurveyDrawService, points_with_tap, doc: DXFDocument
) -> None:
    config = GenerationConfig(layer_name="0", draw_mode=DrawMode.POLY3D, quantum=0.01)
    service.build_command(points_with_tap, list(points_with_tap), config).execute(doc)
    polylines = _entities_of_type(doc, "POLYLINE")
    open_polylines = [p for p in polylines if not p.is_closed]
    assert len(open_polylines) == 2
    through_run = next(p for p in open_polylines if len(list(p.points())) == 3)
    branch = next(p for p in open_polylines if len(list(p.points())) == 2)
    assert [tuple(v) for v in through_run.points()] == [(-20.0, 0.0, 0.0), (0.0, 0.0, 0.0), (20.0, 0.0, 0.0)]
    assert [tuple(v) for v in branch.points()] == [(0.0, 0.0, 0.0), (0.0, 10.0, 0.0)]
    assert sum(1 for p in polylines if p.is_closed) == 2


def test_pipe_mode_draws_two_parallel_lines_straddling_each_segment(
    service: SurveyDrawService, doc: DXFDocument
) -> None:
    points = {1: Point(x=0.0, y=0.0, h=0.0), 2: Point(x=10.0, y=0.0, h=0.0)}
    config = GenerationConfig(layer_name="0", draw_mode=DrawMode.PIPE, pipe=PipeOptions(width=0.2))
    service.build_command(points, [1, 2], config).execute(doc)
    lines = sorted(_entities_of_type(doc, "LINE"), key=lambda line: line.dxf.start[1])
    assert len(lines) == 2
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
    assert len(lines) == 2
    for line in lines:
        assert tuple(line.dxf.start)[0] == 0.0
        assert tuple(line.dxf.end)[0] == 20.0


@pytest.fixture
def points_with_wcinka() -> dict[int, Point]:
    return {
        1: Point(x=2.0, y=-3.0, h=0.0),
        2: Point(x=2.0, y=3.0, h=0.0),
        3: Point(x=0.0, y=0.0, h=0.0),
        4: Point(x=-20.0, y=0.0, h=0.0),
    }


def test_pline_mode_does_not_merge_an_unclassified_junction_with_no_enclosures(
    service: SurveyDrawService, points_with_wcinka, doc: DXFDocument
) -> None:
    config = GenerationConfig(layer_name="0", draw_mode=DrawMode.PLINES, quantum=0.01)
    service.build_command(points_with_wcinka, [1, 2, 3, 4], config).execute(doc)
    polylines = _entities_of_type(doc, "LWPOLYLINE")
    # No enclosure means no TAP classification, so only-through-run merging
    # never applies here: the junction at (0, 0) stays a hard break between
    # all three of its arms, same as a plain degree-2-chain split.
    assert len(polylines) == 3
    endpoint_pairs = {tuple(pt[:2] for pt in p.get_points("xy")) for p in polylines}
    assert endpoint_pairs == {
        ((2.0, -3.0), (0.0, 0.0)),
        ((2.0, 3.0), (0.0, 0.0)),
        ((0.0, 0.0), (-20.0, 0.0)),
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


def test_points_mode_normally_spaced_points_are_never_treated_as_a_cabinet(
    service: SurveyDrawService, doc: DXFDocument
) -> None:
    points = {n: Point(x=float(n) * 5.0, y=0.0, h=1.0) for n in range(1, 8)}
    config = GenerationConfig(
        layer_name="0",
        draw_mode=DrawMode.POINTS,
        points=PointsOptions(numbers_enabled=True, font_size=0.6, diameter=0.1),
    )
    service.build_command(points, list(range(1, 8)), config).execute(doc)
    labels = {t.dxf.text: t for t in _entities_of_type(doc, "TEXT")}
    assert {label.dxf.height for label in labels.values()} == {0.6}


def test_points_mode_auto_detects_a_tight_cluster_as_a_cabinet(
    service: SurveyDrawService, doc: DXFDocument
) -> None:
    points = {
        1: Point(x=0.0, y=50.0, h=1.0),
        2: Point(x=0.0, y=0.0, h=1.0),
        3: Point(x=0.2, y=0.0, h=1.0),
        4: Point(x=0.2, y=0.2, h=1.0),
        5: Point(x=0.0, y=0.2, h=1.0),
    }
    config = GenerationConfig(
        layer_name="0",
        draw_mode=DrawMode.POINTS,
        points=PointsOptions(numbers_enabled=True, font_size=0.6, diameter=0.1),
    )
    service.build_command(points, [1, 2, 3, 4, 5], config).execute(doc)
    labels = {t.dxf.text: t for t in _entities_of_type(doc, "TEXT")}
    for n in ("1", "2", "3", "4", "5"):
        assert labels[n].dxf.height == 0.6
    assert tuple(labels["2"].dxf.insert) != (0.0, 0.0, 1.0)


def test_points_mode_cabinet_label_offset_points_away_from_the_cluster_center(
    service: SurveyDrawService, doc: DXFDocument
) -> None:
    points = {
        1: Point(x=0.0, y=100.0, h=1.0),
        2: Point(x=0.0, y=1.0, h=1.0),
        3: Point(x=1.0, y=1.0, h=1.0),
        4: Point(x=1.0, y=0.0, h=1.0),
        5: Point(x=0.0, y=0.0, h=1.0),
        6: Point(x=0.5, y=0.5, h=1.0),
        7: Point(x=0.5, y=0.6, h=1.0),
    }
    config = GenerationConfig(
        layer_name="0",
        draw_mode=DrawMode.POINTS,
        points=PointsOptions(numbers_enabled=True, font_size=1.0, diameter=0.05),
    )
    service.build_command(points, [1, 2, 3, 4, 5, 6, 7], config).execute(doc)
    insert = {t.dxf.text: tuple(t.dxf.insert) for t in _entities_of_type(doc, "TEXT")}

    assert insert["2"][0] < points[2].x and insert["2"][1] > points[2].y
    assert insert["3"][0] > points[3].x and insert["3"][1] > points[3].y
    assert insert["4"][0] > points[4].x and insert["4"][1] < points[4].y
    assert insert["5"][0] < points[5].x and insert["5"][1] < points[5].y


def test_points_mode_cabinet_label_offset_magnitude_matches_font_size(
    service: SurveyDrawService, doc: DXFDocument
) -> None:
    points = {
        1: Point(x=0.0, y=0.0, h=1.0),
        2: Point(x=1.0, y=0.0, h=1.0),
        3: Point(x=1.0, y=1.0, h=1.0),
        4: Point(x=0.0, y=1.0, h=1.0),
    }
    config = GenerationConfig(
        layer_name="0",
        draw_mode=DrawMode.POINTS,
        points=PointsOptions(numbers_enabled=True, font_size=1.0, diameter=0.1),
    )
    service.build_command(points, [1, 2, 3, 4], config).execute(doc)
    insert = {t.dxf.text: tuple(t.dxf.insert) for t in _entities_of_type(doc, "TEXT")}
    labels = {t.dxf.text: t for t in _entities_of_type(doc, "TEXT")}

    width = 0.62 * 1.0 * 1 + 0.30 * 1.0
    height = 1.30 * 1.0
    expected_radius = 0.1 / 2.0 + math.hypot(width, height) / 2.0
    for number, point in points.items():
        dx = insert[str(number)][0] - point.x
        dy = insert[str(number)][1] - point.y
        assert math.hypot(dx, dy) == pytest.approx(expected_radius, rel=1e-6)
    for n in ("1", "2", "3", "4"):
        assert labels[n].dxf.height == 1.0


def test_points_mode_cabinet_separates_a_center_point_from_the_four_corners(
    service: SurveyDrawService, doc: DXFDocument
) -> None:
    points = {
        6: Point(x=5686173.46, y=6447787.73, h=217.07),
        7: Point(x=5686173.81, y=6447787.89, h=217.06),
        8: Point(x=5686173.11, y=6447787.89, h=217.02),
        9: Point(x=5686173.11, y=6447787.57, h=0.0),
        10: Point(x=5686173.81, y=6447787.57, h=0.0),
    }
    config = GenerationConfig(
        layer_name="0",
        draw_mode=DrawMode.POINTS,
        points=PointsOptions(numbers_enabled=True, font_size=0.6, diameter=0.1),
    )
    service.build_command(points, [6, 7, 8, 9, 10], config).execute(doc)
    insert = {t.dxf.text: tuple(t.dxf.insert)[:2] for t in _entities_of_type(doc, "TEXT")}

    min_separation = min(
        math.hypot(insert[a][0] - insert[b][0], insert[a][1] - insert[b][1])
        for a, b in itertools.combinations(insert, 2)
    )
    assert min_separation > 0.3

    assert insert["8"][0] < points[8].x and insert["8"][1] > points[8].y
    assert insert["7"][0] > points[7].x and insert["7"][1] > points[7].y
    assert insert["9"][0] < points[9].x and insert["9"][1] < points[9].y
    assert insert["10"][0] > points[10].x and insert["10"][1] < points[10].y


def test_points_mode_uses_a_separate_font_size_for_cabinet_numbers(
    service: SurveyDrawService, doc: DXFDocument
) -> None:
    points = {
        1: Point(x=0.0, y=100.0, h=1.0),
        2: Point(x=0.0, y=1.0, h=1.0),
        3: Point(x=1.0, y=1.0, h=1.0),
        4: Point(x=1.0, y=0.0, h=1.0),
        5: Point(x=0.0, y=0.0, h=1.0),
    }
    config = GenerationConfig(
        layer_name="0",
        draw_mode=DrawMode.POINTS,
        points=PointsOptions(
            numbers_enabled=True, font_size=0.6, cabinet_font_size_enabled=True, cabinet_font_size=1.2,
            diameter=0.05,
        ),
    )
    service.build_command(points, [1, 2, 3, 4, 5], config).execute(doc)
    heights = {t.dxf.text: t.dxf.height for t in _entities_of_type(doc, "TEXT")}

    assert heights["1"] == pytest.approx(0.6)
    for n in ("2", "3", "4", "5"):
        assert heights[n] == pytest.approx(1.2)


def test_points_mode_cabinet_font_size_is_ignored_unless_enabled(
    service: SurveyDrawService, doc: DXFDocument
) -> None:
    points = {
        1: Point(x=0.0, y=100.0, h=1.0),
        2: Point(x=0.0, y=1.0, h=1.0),
        3: Point(x=1.0, y=1.0, h=1.0),
        4: Point(x=1.0, y=0.0, h=1.0),
        5: Point(x=0.0, y=0.0, h=1.0),
    }
    config = GenerationConfig(
        layer_name="0",
        draw_mode=DrawMode.POINTS,
        points=PointsOptions(
            numbers_enabled=True, font_size=0.6, cabinet_font_size_enabled=False, cabinet_font_size=1.2,
            diameter=0.05,
        ),
    )
    service.build_command(points, [1, 2, 3, 4, 5], config).execute(doc)
    heights = {t.dxf.text: t.dxf.height for t in _entities_of_type(doc, "TEXT")}
    assert all(height == pytest.approx(0.6) for height in heights.values())


def test_points_options_cabinet_font_size_defaults_to_the_same_value_as_font_size() -> None:
    options = PointsOptions()
    assert options.cabinet_font_size == options.font_size
    assert options.cabinet_font_size_enabled is False


def test_points_mode_wcinka_wedge_numbers_keep_the_regular_font_size(
    service: SurveyDrawService, points_with_wcinka, doc: DXFDocument
) -> None:
    config = GenerationConfig(
        layer_name="0",
        draw_mode=DrawMode.POINTS,
        points=PointsOptions(
            numbers_enabled=True, font_size=0.6, cabinet_font_size_enabled=True, cabinet_font_size=1.5,
            diameter=0.05,
        ),
    )
    service.build_command(points_with_wcinka, [1, 2, 3, 4], config).execute(doc)
    heights = {t.dxf.text: t.dxf.height for t in _entities_of_type(doc, "TEXT")}

    assert all(height == pytest.approx(0.6) for height in heights.values())


@pytest.mark.parametrize(
    "points",
    [
        {
            6: Point(x=5686173.46, y=6447787.73, h=217.07),
            7: Point(x=5686173.81, y=6447787.89, h=217.06),
            8: Point(x=5686173.11, y=6447787.89, h=217.02),
            9: Point(x=5686173.11, y=6447787.57, h=0.0),
            10: Point(x=5686173.81, y=6447787.57, h=0.0),
        },
        {
            1: Point(x=0.0, y=0.0, h=0.0),
            2: Point(x=1.0, y=0.0, h=0.0),
            3: Point(x=1.0, y=1.0, h=0.0),
            4: Point(x=0.0, y=1.0, h=0.0),
            5: Point(x=0.5, y=0.5, h=0.0),
        },
    ],
)
def test_points_mode_cabinet_label_never_covers_its_own_point(
    service: SurveyDrawService, doc: DXFDocument, points
) -> None:
    config = GenerationConfig(
        layer_name="0",
        draw_mode=DrawMode.POINTS,
        points=PointsOptions(numbers_enabled=True, font_size=0.6, diameter=0.1),
    )
    service.build_command(points, list(points), config).execute(doc)
    labels = {int(t.dxf.text): t for t in _entities_of_type(doc, "TEXT")}
    for number, label in labels.items():
        point = points[number]
        extents = ezdxf_bbox.extents([label])
        covered = (
            extents.extmin.x < point.x < extents.extmax.x
            and extents.extmin.y < point.y < extents.extmax.y
        )
        assert not covered, f"label {number} covers its own point"

    for a, b in itertools.combinations(labels, 2):
        overlap = _bboxes_overlap(ezdxf_bbox.extents([labels[a]]), ezdxf_bbox.extents([labels[b]]))
        assert not overlap, f"labels {a} and {b} overlap each other"


def test_points_mode_cabinet_label_never_covers_its_own_point_across_random_routes(
    service: SurveyDrawService,
) -> None:
    rng = random.Random(0)
    for _trial in range(200):
        numbers = list(range(1, rng.randint(4, 10)))
        points: dict[int, Point] = {}
        x, y = 0.0, 0.0
        for number in numbers:
            if rng.random() < 0.3 and number > 1:
                cx, cy = points[number - 1].x, points[number - 1].y
                x = cx + rng.uniform(-0.2, 0.2)
                y = cy + rng.uniform(-0.2, 0.2)
            else:
                x += rng.uniform(-5.0, 5.0)
                y += rng.uniform(-5.0, 5.0)
            points[number] = Point(x=x, y=y, h=0.0)
        font_size = rng.choice([0.3, 0.6, 1.0, 2.0])
        config = GenerationConfig(
            layer_name="0",
            draw_mode=DrawMode.POINTS,
            points=PointsOptions(numbers_enabled=True, font_size=font_size, diameter=0.1),
        )
        doc = DXFDocument.new()
        service.build_command(points, numbers, config).execute(doc)
        labels = {int(label.dxf.text): label for label in _entities_of_type(doc, "TEXT")}
        rects = {
            number: _label_rect(label.dxf.insert[0], label.dxf.insert[1], font_size, label.dxf.text)
            for number, label in labels.items()
        }
        for number, rect in rects.items():
            point = points[number]
            covered = rect[0] < point.x < rect[2] and rect[1] < point.y < rect[3]
            assert not covered, f"trial {_trial}: label {number} covers its own point"
        for a, b in itertools.combinations(rects, 2):
            assert not _rects_overlap(rects[a], rects[b]), f"trial {_trial}: labels {a} and {b} overlap each other"


@pytest.fixture
def straight_cable() -> dict[int, Point]:
    return {n: Point(x=float(n - 1) * 10.0, y=0.0, h=100.0 + float(n - 1)) for n in range(1, 6)}


def _texts_by_x(doc: DXFDocument) -> list[tuple[float, str]]:
    return sorted((t.dxf.insert[0], t.dxf.text) for t in _entities_of_type(doc, "TEXT"))


def test_cable_marks_sit_on_the_cable_between_points(
    service: SurveyDrawService, straight_cable, doc: DXFDocument
) -> None:
    config = GenerationConfig(
        layer_name="0",
        draw_mode=DrawMode.CABLE_MARKS,
        cable=CableOptions(font_size=1.0, spacing=10.0, marks_text="CBL"),
    )
    service.build_command(straight_cable, [1, 2, 3, 4, 5], config).execute(doc)
    labels = _entities_of_type(doc, "TEXT")
    assert [t.dxf.text for t in labels] == ["CBL", "CBL"]
    for label in labels:
        x, y = label.dxf.insert[0], label.dxf.insert[1]
        assert y == pytest.approx(0.0)
        assert all(abs(x - p.x) > 1.0 for p in straight_cable.values())
    assert _entities_of_type(doc, "LINE") == []


def test_cable_marks_and_heights_alternate_along_the_cable(
    service: SurveyDrawService, straight_cable, doc: DXFDocument
) -> None:
    configs = [
        GenerationConfig(
            layer_name="0",
            draw_mode=mode,
            selected_numbers=(1, 2, 3, 4, 5),
            cable=CableOptions(font_size=1.0, spacing=10.0, marks_text="eN"),
            heights=HeightsOptions(font_size=1.0),
        )
        for mode in (DrawMode.CABLE_MARKS, DrawMode.HEIGHTS)
    ]
    for command in service.build_commands(straight_cable, configs):
        command.execute(doc)
    texts = [text for _x, text in _texts_by_x(doc)]
    assert texts[0] == "eN"
    assert texts[1::2] and all(t != "eN" for t in texts[1::2])
    assert all(t == "eN" for t in texts[0::2])


def test_heights_stand_next_to_a_point_with_its_height_rounded_up(
    service: SurveyDrawService, straight_cable, doc: DXFDocument
) -> None:
    config = GenerationConfig(
        layer_name="0",
        draw_mode=DrawMode.HEIGHTS,
        cable=CableOptions(font_size=1.0, spacing=10.0),
        heights=HeightsOptions(font_size=1.0),
    )
    service.build_command(straight_cable, [1, 2, 3, 4, 5], config).execute(doc)
    labels = _texts_by_x(doc)
    assert labels
    for x, text in labels:
        nearest = min(straight_cable.values(), key=lambda p: abs(p.x - x))
        assert abs(x - nearest.x) < 5.0
        assert float(text) == pytest.approx(math.ceil(nearest.h * 10) / 10)


def test_cable_marks_rotate_with_the_segment(service: SurveyDrawService, doc: DXFDocument) -> None:
    points = {1: Point(x=0.0, y=0.0, h=0.0), 2: Point(x=0.0, y=30.0, h=0.0)}
    config = GenerationConfig(
        layer_name="0",
        draw_mode=DrawMode.CABLE_MARKS,
        cable=CableOptions(font_size=1.0, spacing=10.0),
    )
    service.build_command(points, [1, 2], config).execute(doc)
    labels = _entities_of_type(doc, "TEXT")
    assert labels
    assert all(t.dxf.rotation == pytest.approx(90.0) for t in labels)
    assert all(t.dxf.insert[0] == pytest.approx(0.0) for t in labels)


def test_cable_marks_skip_a_cable_too_short_to_hold_one(service: SurveyDrawService, doc: DXFDocument) -> None:
    points = {1: Point(x=0.0, y=0.0, h=0.0), 2: Point(x=1.0, y=0.0, h=0.0)}
    config = GenerationConfig(
        layer_name="0",
        draw_mode=DrawMode.CABLE_MARKS,
        cable=CableOptions(font_size=1.0, spacing=10.0),
    )
    service.build_command(points, [1, 2], config).execute(doc)
    assert _entities_of_type(doc, "TEXT") == []


def test_cable_marks_never_land_inside_a_skipped_skrzynka(
    service: SurveyDrawService, points_with_box, doc: DXFDocument
) -> None:
    config = GenerationConfig(
        layer_name="0",
        draw_mode=DrawMode.CABLE_MARKS,
        cable=CableOptions(font_size=0.6, spacing=5.0, marks_text="eN"),
    )
    service.build_command(points_with_box, [1, 2, 3, 4, 5, 6], config).execute(doc)
    labels = _entities_of_type(doc, "TEXT")
    assert labels
    assert all(not (10.0 <= t.dxf.insert[0] <= 11.0 and 0.0 < t.dxf.insert[1] <= 1.0) for t in labels)


def test_measurements_mode_labels_every_segment_with_dashed_length(
    service: SurveyDrawService, points, doc: DXFDocument
) -> None:
    config = GenerationConfig(layer_name="0", draw_mode=DrawMode.MEASUREMENTS)
    service.build_command(points, [1, 2, 3], config).execute(doc)
    labels = _entities_of_type(doc, "TEXT")
    assert len(labels) == 2  # 3 points -> 2 segments, both length 10.0
    assert all(t.dxf.text == "-10.00-" for t in labels)
    assert _entities_of_type(doc, "LINE") == []
    assert _entities_of_type(doc, "LWPOLYLINE") == []


def test_measurements_mode_skips_skrzynka_sides(
    service: SurveyDrawService, points_with_box, doc: DXFDocument
) -> None:
    config = GenerationConfig(layer_name="0", draw_mode=DrawMode.MEASUREMENTS)
    service.build_command(points_with_box, [1, 2, 3, 4, 5, 6], config).execute(doc)
    labels = _entities_of_type(doc, "TEXT")
    # Only the one real segment (1 -> 6, the box is skipped entirely).
    assert len(labels) == 1
    assert labels[0].dxf.text == "-20.00-"


def test_measurements_mode_labels_wcinka_wing_stubs_too(
    service: SurveyDrawService, points_with_wcinka, doc: DXFDocument
) -> None:
    config = GenerationConfig(layer_name="0", draw_mode=DrawMode.MEASUREMENTS)
    service.build_command(points_with_wcinka, [1, 2, 3, 4], config).execute(doc)
    labels = _entities_of_type(doc, "TEXT")
    # The main segment (3 -> 4) plus both wedge wings (3 -> 1, 3 -> 2).
    assert sorted(t.dxf.text for t in labels) == ["-20.00-", "-3.61-", "-3.61-"]


def test_build_commands_keeps_point_numbers_off_the_labels_on_the_cable(
    service: SurveyDrawService, doc: DXFDocument
) -> None:
    points = {
        1: Point(x=0.0, y=0.0, h=10.0),
        2: Point(x=3.0, y=0.0, h=11.0),
        3: Point(x=3.0, y=3.0, h=12.0),
        4: Point(x=8.0, y=3.0, h=12.5),
    }
    configs = [
        GenerationConfig(
            layer_name=mode.name,
            draw_mode=mode,
            selected_numbers=(1, 2, 3, 4),
            points=PointsOptions(numbers_enabled=True, font_size=0.6, diameter=0.1),
            cable=CableOptions(font_size=0.6, spacing=3.0),
            heights=HeightsOptions(font_size=0.6),
        )
        for mode in (DrawMode.POINTS, DrawMode.CABLE_MARKS, DrawMode.HEIGHTS)
    ]
    for command in service.build_commands(points, configs):
        command.execute(doc)
    labels = _entities_of_type(doc, "TEXT")
    assert {t.dxf.layer for t in labels} == {"POINTS", "CABLE_MARKS", "HEIGHTS"}
    overlaps = sum(
        1
        for a, b in itertools.combinations(labels, 2)
        if _bboxes_overlap(ezdxf_bbox.extents([a]), ezdxf_bbox.extents([b]))
    )
    assert overlaps == 0


def test_whole_batch_undoes_as_one_step(service: SurveyDrawService, points, doc: DXFDocument) -> None:
    config = GenerationConfig(
        layer_name="0",
        draw_mode=DrawMode.POINTS,
        points=PointsOptions(numbers_enabled=True, diameter=0.1),
    )
    command = service.build_command(points, [1, 2, 3], config)
    command.execute(doc)
    assert doc.entity_count() == 6
    command.undo(doc)
    assert doc.entity_count() == 0


def _points_config(diameter: float = 0.1) -> GenerationConfig:
    return GenerationConfig(
        layer_name="0",
        draw_mode=DrawMode.POINTS,
        points=PointsOptions(numbers_enabled=True, diameter=diameter),
    )


def test_generated_entities_are_stamped_with_their_mode(
    service: SurveyDrawService, points, doc: DXFDocument
) -> None:
    service.build_command(points, [1, 2, 3], _points_config()).execute(doc)
    assert {mode_from_entity(entity) for entity in doc.modelspace} == {DrawMode.POINTS.name}
    assert len(doc.generated_handles([DrawMode.POINTS.name])) == doc.entity_count()


def test_generating_again_replaces_its_own_output(
    service: SurveyDrawService, points, doc: DXFDocument
) -> None:
    service.build_command(points, [1, 2, 3], _points_config()).execute(doc)
    first = {entity.dxf.handle for entity in doc.modelspace}

    service.build_command(points, [1, 2, 3], _points_config(diameter=0.5)).execute(doc)

    assert doc.entity_count() == len(first), "the second run stacked on top of the first"
    assert not (first & {entity.dxf.handle for entity in doc.modelspace})
    assert {e.dxf.radius for e in doc.modelspace if e.dxftype() == "CIRCLE"} == {0.25}


def test_generating_leaves_hand_drawn_entities_alone(
    service: SurveyDrawService, points, doc: DXFDocument
) -> None:
    service.build_command(points, [1, 2, 3], _points_config()).execute(doc)
    hand_drawn = doc.add_line((-5.0, -5.0), (-1.0, -1.0), layer="0")

    service.build_command(points, [1, 2, 3], _points_config(diameter=0.5)).execute(doc)

    assert doc.get_entity(hand_drawn) is not None
    assert hand_drawn in {entity.dxf.handle for entity in doc.modelspace}


def test_generating_one_mode_leaves_another_modes_output(
    service: SurveyDrawService, points, doc: DXFDocument
) -> None:
    lines_config = GenerationConfig(layer_name="0", draw_mode=DrawMode.LINES)
    service.build_command(points, [1, 2, 3], lines_config).execute(doc)
    service.build_command(points, [1, 2, 3], _points_config()).execute(doc)
    lines = set(doc.generated_handles([DrawMode.LINES.name]))
    assert lines

    service.build_command(points, [1, 2, 3], _points_config(diameter=0.5)).execute(doc)

    assert set(doc.generated_handles([DrawMode.LINES.name])) == lines


def test_undoing_a_regeneration_brings_the_previous_one_back(
    service: SurveyDrawService, points, doc: DXFDocument
) -> None:
    service.build_command(points, [1, 2, 3], _points_config()).execute(doc)
    first = {entity.dxf.handle for entity in doc.modelspace}

    again = service.build_command(points, [1, 2, 3], _points_config(diameter=0.5))
    again.execute(doc)
    again.undo(doc)

    assert {entity.dxf.handle for entity in doc.modelspace} == first


def test_stamps_survive_a_save_and_reopen(service: SurveyDrawService, points, doc: DXFDocument) -> None:
    service.build_command(points, [1, 2, 3], _points_config()).execute(doc)
    reopened = DXFDocument.from_text(doc.to_text())
    assert len(reopened.generated_handles([DrawMode.POINTS.name])) == doc.entity_count()

    service.build_command(points, [1, 2, 3], _points_config(diameter=0.5)).execute(reopened)

    assert reopened.entity_count() == doc.entity_count(), "reopening lost track of earlier output"


def test_switching_the_cable_type_replaces_the_cable_drawn_with_the_previous_type(
    service: SurveyDrawService, points, doc: DXFDocument
) -> None:
    plines = GenerationConfig(layer_name="0", draw_mode=DrawMode.PLINES)
    lines = GenerationConfig(layer_name="0", draw_mode=DrawMode.LINES)
    service.build_command(points, [1, 2, 3], plines).execute(doc)
    assert _entities_of_type(doc, "LWPOLYLINE")
    service.build_command(points, [1, 2, 3], lines).execute(doc)
    assert _entities_of_type(doc, "LWPOLYLINE") == []
    assert len(_entities_of_type(doc, "LINE")) == 2
