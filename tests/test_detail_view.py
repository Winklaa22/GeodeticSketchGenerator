from __future__ import annotations

import pytest

from core.commands.detail_view import AddDetailViewCommand, UpdateDetailViewCommand
from core.commands.edit import DeleteEntityCommand, MoveCommand, RotateCommand, ScaleCommand
from core.commands.history import CommandHistory
from core.detail_view import (
    DetailViewSpec,
    bounds,
    contains_point,
    corner_points,
    from_squares,
    handle_points,
    panned,
    resize_to_handle,
    source_at,
    source_bounds,
    with_scale,
)
from core.dxf_document import DXFDocument
from core.project import ProjectState, load_project, save_project


def _spec(**changes) -> DetailViewSpec:
    values = {
        "center": (20.0, 11.0),
        "width": 10.0,
        "height": 6.0,
        "source": (2.0, 1.5),
        "scale": 4.0,
        "layer": "DETAIL",
    }
    values.update(changes)
    return DetailViewSpec(**values)


def test_from_squares_centres_the_frame_and_the_source() -> None:
    spec = from_squares((2.0, 1.5), 2.5, (20.0, 11.0), 10.0)

    assert spec.center == (20.0, 11.0)
    assert (spec.width, spec.height) == (10.0, 10.0)
    assert spec.source == (2.0, 1.5)
    assert spec.scale == 4.0
    assert corner_points(spec)[0] == (15.0, 6.0)
    assert bounds(spec) == ((15.0, 6.0), (25.0, 16.0))


@pytest.mark.parametrize(
    ("frame_size", "expected_scale"), [(2.5, 1.0), (5.0, 2.0), (10.0, 4.0), (20.0, 8.0)]
)
def test_a_bigger_frame_over_the_same_area_magnifies_more(frame_size: float, expected_scale: float) -> None:
    spec = from_squares((2.0, 1.5), 2.5, (0.0, 0.0), frame_size)

    assert spec.scale == expected_scale


def test_the_marked_area_keeps_the_side_the_user_drew() -> None:
    # Both regions are squares, so the frame shows exactly the marked area: no cropping,
    # no empty margins.
    spec = from_squares((0.0, 0.0), 2.0, (0.0, 0.0), 6.0)

    assert spec.scale == 3.0
    (min_x, min_y), (max_x, max_y) = source_bounds(spec)
    assert (max_x - min_x, max_y - min_y) == pytest.approx((2.0, 2.0))


def test_detail_view_is_stored_as_a_closed_frame_carrying_its_spec() -> None:
    doc = DXFDocument.new()
    command = AddDetailViewCommand(_spec())

    command.execute(doc)

    entity = doc.get_entity(command.handle)
    assert entity.dxftype() == "LWPOLYLINE"
    assert entity.closed is True
    assert entity.dxf.layer == "DETAIL"
    assert doc.detail_view_spec(command.handle) == command.spec
    assert [handle for handle, _entry in doc.iter_detail_views()] == [command.handle]


def test_magnified_source_region_shrinks_as_the_scale_grows() -> None:
    assert source_bounds(_spec(scale=4.0)) == ((0.75, 0.75), (3.25, 2.25))
    assert source_bounds(_spec(scale=8.0)) == ((1.375, 1.125), (2.625, 1.875))


def test_zooming_about_a_point_keeps_the_drawing_under_it_fixed() -> None:
    spec = _spec()
    anchor = (23.0, 12.5)
    before = source_at(spec, anchor)

    zoomed = with_scale(spec, 9.0, anchor)

    assert zoomed.scale == 9.0
    assert source_at(zoomed, anchor) == pytest.approx(before)


def test_panning_moves_the_source_window_against_the_drag_scaled_by_magnification() -> None:
    panned_spec = panned(_spec(scale=4.0), 2.0, -1.0)

    assert panned_spec.source == pytest.approx((1.5, 1.75))


def test_contains_point_covers_the_frame_interior_only() -> None:
    spec = _spec()

    assert contains_point(spec, (20.0, 11.0))
    assert contains_point(spec, (15.0, 8.0))
    assert not contains_point(spec, (14.9, 11.0))


def test_update_command_restores_the_previous_view_on_undo() -> None:
    doc = DXFDocument.new()
    add = AddDetailViewCommand(_spec())
    history = CommandHistory()
    history.execute(add, doc)
    original = doc.detail_view_spec(add.handle)

    history.execute(UpdateDetailViewCommand(add.handle, with_scale(original, 12.0), original), doc)
    assert doc.detail_view_spec(add.handle).scale == 12.0

    assert history.undo(doc)
    assert doc.detail_view_spec(add.handle) == original
    assert history.redo(doc)
    assert doc.detail_view_spec(add.handle).scale == 12.0


def test_adding_a_detail_view_is_undoable_and_deletable() -> None:
    doc = DXFDocument.new()
    history = CommandHistory()
    command = AddDetailViewCommand(_spec())

    history.execute(command, doc)
    assert doc.entity_count() == 1
    assert history.undo(doc)
    assert doc.entity_count() == 0
    assert history.redo(doc)

    history.execute(DeleteEntityCommand([command.handle]), doc)
    assert doc.entity_count() == 0
    assert history.undo(doc)
    assert doc.detail_view_spec(command.handle) == command.spec


def test_moving_a_detail_view_leaves_what_it_shows_alone() -> None:
    doc = DXFDocument.new()
    command = AddDetailViewCommand(_spec())
    command.execute(doc)

    MoveCommand([command.handle], 5.0, -2.0).execute(doc)

    spec = doc.detail_view_spec(command.handle)
    assert spec.center == (25.0, 9.0)
    assert corner_points(spec)[0] == (20.0, 6.0)
    # The frame is a window onto a fixed part of the drawing: sliding the window must
    # not slide the part of the drawing it looks at.
    assert spec.source == (2.0, 1.5)
    assert source_bounds(spec) == source_bounds(command.spec)


def test_scaling_a_detail_view_grows_the_frame_and_its_magnification_together() -> None:
    doc = DXFDocument.new()
    command = AddDetailViewCommand(_spec())
    command.execute(doc)

    ScaleCommand([command.handle], 2.0, (0.0, 0.0)).execute(doc)

    spec = doc.detail_view_spec(command.handle)
    assert (spec.width, spec.height) == (20.0, 12.0)
    assert spec.center == (40.0, 22.0)
    assert bounds(spec) == ((30.0, 16.0), (50.0, 28.0))
    # Twice the frame at twice the magnification shows exactly the same drawing.
    assert spec.scale == 8.0
    assert spec.source == (2.0, 1.5)
    assert source_bounds(spec) == source_bounds(command.spec)


def test_rotating_a_detail_view_turns_the_frame_and_its_contents_as_one() -> None:
    doc = DXFDocument.new()
    command = AddDetailViewCommand(_spec())
    command.execute(doc)

    RotateCommand([command.handle], 90.0, (0.0, 0.0)).execute(doc)

    spec = doc.detail_view_spec(command.handle)
    assert spec.center == pytest.approx((-11.0, 20.0))
    assert (spec.width, spec.height) == (10.0, 6.0)
    assert spec.rotation == 90.0
    assert corner_points(spec)[0] == pytest.approx((-8.0, 15.0))
    assert spec.source == (2.0, 1.5)
    assert source_bounds(spec) == source_bounds(command.spec)


def test_a_rotated_frame_only_contains_what_its_turned_corners_enclose() -> None:
    upright = _spec(width=10.0, height=6.0)
    turned = _spec(width=10.0, height=6.0, rotation=90.0)

    corner = (24.0, 13.0)
    assert contains_point(upright, corner)
    assert not contains_point(turned, corner)
    assert contains_point(turned, (18.0, 15.0))
    assert contains_point(turned, turned.center)


def test_dragging_a_corner_scales_the_frame_and_keeps_the_far_corner_still() -> None:
    spec = _spec(width=10.0, height=6.0).normalized()
    far_corner = handle_points(spec)[4]

    resized = resize_to_handle(spec, 0, (10.0, 2.0))

    assert handle_points(resized)[4] == pytest.approx(far_corner)
    assert resized.scale == pytest.approx(spec.scale * 2.0)
    assert (resized.width, resized.height) == pytest.approx((20.0, 12.0))
    before, after = source_bounds(spec), source_bounds(resized)
    assert after[0] == pytest.approx(before[0])
    assert after[1] == pytest.approx(before[1])


def test_dragging_an_edge_reveals_more_drawing_at_the_same_magnification() -> None:
    spec = _spec(width=10.0, height=6.0).normalized()
    left_edge = handle_points(spec)[7]
    (source_min_x, source_min_y), (source_max_x, _) = source_bounds(spec)

    resized = resize_to_handle(spec, 3, (30.0, 11.0))

    assert handle_points(resized)[7] == pytest.approx(left_edge)
    assert resized.scale == spec.scale
    assert (resized.width, resized.height) == pytest.approx((15.0, 6.0))
    # The extra 5 units of frame expose 5 / scale more of the drawing on that side only.
    (new_min_x, new_min_y), (new_max_x, _) = source_bounds(resized)
    assert (new_min_x, new_min_y) == pytest.approx((source_min_x, source_min_y))
    assert new_max_x == pytest.approx(source_max_x + 5.0 / spec.scale)


def test_detail_view_survives_dxf_and_project_round_trips(tmp_path) -> None:
    doc = DXFDocument.new()
    doc.add_line((0.0, 0.0), (4.0, 3.0))
    command = AddDetailViewCommand(_spec(scale=7.5, rotation=30.0))
    command.execute(doc)
    content = doc.to_text()

    reopened = DXFDocument.from_text(content)
    restored = reopened.iter_detail_views()
    assert len(restored) == 1
    assert restored[0][1].scale == 7.5
    assert restored[0][1].source == (2.0, 1.5)
    assert restored[0][1].rotation == 30.0

    path = tmp_path / "detail.gsgproj"
    save_project(path, ProjectState(name="Detail", dxf_content=content))
    project_doc = DXFDocument.from_text(load_project(path).dxf_content)
    assert len(project_doc.iter_detail_views()) == 1


def test_a_detail_view_saved_before_rotation_existed_loads_upright() -> None:
    payload = _spec().to_payload()
    del payload["rotation"]

    assert DetailViewSpec.from_payload(payload).rotation == 0.0


def test_the_eight_grips_are_the_corners_and_the_edge_midpoints() -> None:
    spec = _spec(center=(0.0, 0.0), width=10.0, height=6.0).normalized()

    assert handle_points(spec) == (
        (-5.0, -3.0),
        (0.0, -3.0),
        (5.0, -3.0),
        (5.0, 0.0),
        (5.0, 3.0),
        (0.0, 3.0),
        (-5.0, 3.0),
        (-5.0, 0.0),
    )


def test_the_grips_turn_with_the_frame() -> None:
    upright = _spec(center=(0.0, 0.0), width=10.0, height=6.0).normalized()
    turned = _spec(center=(0.0, 0.0), width=10.0, height=6.0, rotation=90.0).normalized()

    # A quarter turn maps (x, y) onto (-y, x), so every grip moves to where the next
    # one but two used to be - the arrow anchors ride along with the frame.
    for grip, expected in zip(handle_points(turned), handle_points(upright)):
        assert grip == pytest.approx((-expected[1], expected[0]))
