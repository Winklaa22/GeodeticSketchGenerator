from __future__ import annotations

import itertools
import math
import random

import pytest
from ezdxf import bbox as ezdxf_bbox

from core.config import CableOptions, GenerationConfig, HeightsOptions, PipeOptions, PointsOptions
from core.draw_modes import DrawMode
from core.commands import survey
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


def _bboxes_overlap(a, b) -> bool:
    return not (
        a.extmax.x <= b.extmin.x
        or b.extmax.x <= a.extmin.x
        or a.extmax.y <= b.extmin.y
        or b.extmax.y <= a.extmin.y
    )


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


def test_pline_mode_draws_skrzynka_as_a_separate_closed_polyline(
    service: SurveyDrawService, points_with_box, doc: DXFDocument
) -> None:
    config = GenerationConfig(layer_name="0", draw_mode=DrawMode.PLINES)
    service.build_command(points_with_box, [1, 2, 3, 4, 5, 6], config).execute(doc)
    polylines = _entities_of_type(doc, "LWPOLYLINE")
    assert len(polylines) == 2
    cable, box = polylines
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


def test_pline_mode_draws_wcinka_as_open_stubs_off_its_entry_point(
    service: SurveyDrawService, points_with_wcinka, doc: DXFDocument
) -> None:
    config = GenerationConfig(layer_name="0", draw_mode=DrawMode.PLINES)
    service.build_command(points_with_wcinka, [1, 2, 3, 4], config).execute(doc)
    polylines = _entities_of_type(doc, "LWPOLYLINE")
    assert len(polylines) == 1
    assert [pt[:2] for pt in polylines[0].get_points("xy")] == [(0.0, 0.0), (-20.0, 0.0)]
    lines = _entities_of_type(doc, "LINE")
    assert len(lines) == 2
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
    assert insert["1"][0] == pytest.approx(-0.5)
    assert insert["3"][0] == pytest.approx(1.5)
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
        cabinet_numbers = set()
        for cluster in survey._cabinet_clusters(points, numbers):
            cabinet_numbers.update(cluster)
        doc = DXFDocument.new()
        service.build_command(points, numbers, config).execute(doc)
        cabinet_labels = {}
        for label in _entities_of_type(doc, "TEXT"):
            number = int(label.dxf.text)
            if number not in cabinet_numbers:
                continue
            cabinet_labels[number] = label
            point = points[number]
            extents = ezdxf_bbox.extents([label])
            covered = (
                extents.extmin.x < point.x < extents.extmax.x
                and extents.extmin.y < point.y < extents.extmax.y
            )
            assert not covered, f"trial {_trial}: label {number} covers its own point"
        for a, b in itertools.combinations(cabinet_labels, 2):
            overlap = _bboxes_overlap(
                ezdxf_bbox.extents([cabinet_labels[a]]), ezdxf_bbox.extents([cabinet_labels[b]])
            )
            assert not overlap, f"trial {_trial}: labels {a} and {b} overlap each other"


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
    assert len(labels) == 1
    assert labels[0].dxf.text == "11.0"


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
    assert len(labels) == 2
    assert all(t.dxf.text == "CBL" for t in labels)
    assert _entities_of_type(doc, "LINE") == []
    assert _entities_of_type(doc, "LWPOLYLINE") == []


def test_cable_marks_start_at_the_centre_segment_and_fan_outward(
    service: SurveyDrawService, doc: DXFDocument
) -> None:
    points = {n: Point(x=float(n) * 10.0, y=0.0, h=0.0) for n in range(1, 6)}
    config = GenerationConfig(
        layer_name="0",
        draw_mode=DrawMode.CABLE_MARKS,
        cable=CableOptions(font_size=0.6, frequency=2, marks_text="eN"),
    )
    service.build_command(points, [1, 2, 3, 4, 5], config).execute(doc)
    labels = _entities_of_type(doc, "TEXT")
    xs = sorted(round(t.dxf.insert[0]) for t in labels)
    assert xs == [25, 45]


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
    assert doc.entity_count() == 6
    command.undo(doc)
    assert doc.entity_count() == 0
