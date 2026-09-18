from __future__ import annotations

import pytest

from core.dxf_document import DXFDocument
from core.transform_gizmo import (
    bbox_corners,
    center_of,
    knob_point,
    rotation_delta,
    scale_factor,
)

BOX = ((0.0, 0.0), (10.0, 6.0))


def test_the_gizmo_sits_on_the_outline_it_was_given() -> None:
    assert center_of(*BOX) == (5.0, 3.0)
    assert bbox_corners(*BOX) == ((0.0, 0.0), (10.0, 0.0), (10.0, 6.0), (0.0, 6.0))
    assert knob_point(*BOX, offset=2.0) == (5.0, 8.0)


def test_dragging_a_grip_twice_as_far_doubles_the_size() -> None:
    center, grip = center_of(*BOX), (10.0, 6.0)

    assert scale_factor(center, grip, (15.0, 9.0)) == pytest.approx(2.0)
    assert scale_factor(center, grip, (7.5, 4.5)) == pytest.approx(0.5)
    assert scale_factor(center, grip, grip) == pytest.approx(1.0)


def test_the_factor_ignores_how_big_the_drawing_is() -> None:
    # The same gesture on a drawing 1000x larger must mean the same thing - this is what
    # keeps the tool usable on a fitted sheet, where a pixel spans many drawing units.
    center, grip, cursor = center_of(*BOX), (10.0, 6.0), (15.0, 9.0)
    blow_up = lambda p: (p[0] * 1000.0, p[1] * 1000.0)

    assert scale_factor(blow_up(center), blow_up(grip), blow_up(cursor)) == pytest.approx(
        scale_factor(center, grip, cursor)
    )


def test_a_grip_on_the_centre_has_no_ratio_to_scale_by() -> None:
    assert scale_factor((5.0, 3.0), (5.0, 3.0), (9.0, 3.0)) is None
    assert scale_factor((5.0, 3.0), (10.0, 3.0), (5.0, 3.0)) is None


@pytest.mark.parametrize(
    ("cursor", "expected"),
    [((10.0, 3.0), 0.0), ((5.0, 8.0), 90.0), ((0.0, 3.0), 180.0), ((5.0, -2.0), -90.0)],
)
def test_rotation_follows_the_grip_round_the_centre(cursor, expected) -> None:
    assert rotation_delta((5.0, 3.0), (10.0, 3.0), cursor) == pytest.approx(expected)


def test_rotation_is_measured_from_the_grip_not_from_east() -> None:
    # Grip already at 90 degrees: dragging to 180 is a quarter turn, not a half one.
    assert rotation_delta((0.0, 0.0), (0.0, 5.0), (-5.0, 0.0)) == pytest.approx(90.0)


def test_selection_outline_covers_every_entity_named() -> None:
    doc = DXFDocument.new()
    first = doc.add_line((0.0, 0.0), (4.0, 1.0))
    second = doc.add_line((6.0, -2.0), (10.0, 6.0))

    assert doc.entities_bbox([first, second]) == ((0.0, -2.0), (10.0, 6.0))
    assert doc.entities_bbox([first]) == ((0.0, 0.0), (4.0, 1.0))
    assert doc.entities_bbox([]) is None
    assert doc.entities_bbox(["nope"]) is None


def test_a_quarter_turn_is_never_reported_the_long_way_round() -> None:
    # Both readings come from atan2, so they can sit two turns apart; the delta must stay
    # in (-180, 180] instead of coming back as -268 degrees for a quarter turn.
    for grip, cursor in (((10.0, 3.0), (5.0, 8.0)), ((5.0, 8.0), (0.0, 3.0)), ((0.0, 3.0), (5.0, -2.0))):
        delta = rotation_delta((5.0, 3.0), grip, cursor)
        assert -180.0 < delta <= 180.0
        assert delta == pytest.approx(90.0)
